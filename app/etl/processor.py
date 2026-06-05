"""
ETL do NEXO — processa relatórios de VENDAS e COMPRAS de PDV agregados por produto.

KPIs calculados e persistidos em indicador_analise:
  - faturamento_total
  - total_comprado
  - saldo_estimado_compras_vendas  (NULL se não houver custo confiável por produto)
  - produto_mais_vendido_nome / quantidade
  - produto_maior_faturamento_nome / valor
  - produto_maior_saldo_parado_nome
  - saldo_estimado_parado  (QUANTIDADE, não valor monetário)
  - versao_processamento
  - data_geracao

Indicador de Pressão de Estoque:
  Para cada produto normalizado:
    saldo_qty = quantidade_comprada - quantidade_vendida
    saldo_qty_positivo = max(saldo_qty, 0)
  Se houver custo confiável:
    custo_medio = valor_comprado / quantidade_comprada
    valor_parado = saldo_qty_positivo * custo_medio
    saldo_estimado_compras_vendas = soma(valor_parado)
  Caso contrário: saldo_estimado_compras_vendas = NULL

PROIBIDO: saldo = total_comprado - faturamento_total
"""
import re
import unicodedata
import hashlib
import pandas as pd
from datetime import datetime
from pathlib import Path


# --- Normalização de produtos -----------------------------------------------

def normalizar_produto(nome) -> str:
    if not isinstance(nome, str):
        nome = str(nome) if nome is not None else ''
    nome = unicodedata.normalize('NFD', nome)
    nome = ''.join(c for c in nome if unicodedata.category(c) != 'Mn')
    nome = nome.upper()
    nome = re.sub(r'[^A-Z0-9\s]', '', nome)
    nome = re.sub(r'\s+', ' ', nome).strip()
    return nome


# --- Detecção de colunas -------------------------------------------------------

_ALIASES_PRODUTO = [
    'produto', 'descricao', 'descrição', 'item', 'mercadoria',
    'nome_produto', 'nome produto', 'product', 'produto_servico',
    'produto/servico', 'produto/serviço', 'descr',
]
_ALIASES_QTD = [
    'quantidade', 'qtde', 'qtd', 'qty', 'quant',
    'quantidade_vendida', 'qtde_vendida', 'qtd_vendida',
    'qtde vendida', 'unidades', 'un', 'qnt', 'qtd vendida',
]
_ALIASES_VALOR = [
    'valor_total', 'vl_total', 'total', 'valor total', 'vl total',
    'faturamento', 'receita', 'valor', 'preco_total', 'preco total',
    'valor vendas', 'vl vendas', 'valor_venda', 'custo_total',
    'vl_custo', 'custo total', 'valor custo', 'valor_custo',
]


def _detectar_coluna(df_cols, aliases):
    norm_map = {}
    for c in df_cols:
        key = re.sub(r'\s+', '_', c.lower().strip())
        key = unicodedata.normalize('NFD', key)
        key = ''.join(ch for ch in key if unicodedata.category(ch) != 'Mn')
        norm_map[key] = c

    for alias in aliases:
        alias_key = re.sub(r'\s+', '_', alias.lower().strip())
        if alias_key in norm_map:
            return norm_map[alias_key]

    # Partial match fallback
    for alias in aliases:
        alias_key = re.sub(r'\s+', '_', alias.lower().strip())
        for nk, orig in norm_map.items():
            if alias_key in nk or nk in alias_key:
                return orig
    return None


def _mapear_colunas(df):
    cols = df.columns.tolist()
    col_produto = _detectar_coluna(cols, _ALIASES_PRODUTO)
    col_qtd = _detectar_coluna(cols, _ALIASES_QTD)
    col_valor = _detectar_coluna(cols, _ALIASES_VALOR)
    return col_produto, col_qtd, col_valor


# --- Leitura de arquivos -------------------------------------------------------

def ler_arquivo(caminho: str, extensao: str) -> pd.DataFrame:
    ext = extensao.upper()
    if ext == 'CSV':
        for encoding in ('utf-8', 'latin-1', 'cp1252'):
            for sep in (';', ',', '\t'):
                try:
                    df = pd.read_csv(caminho, encoding=encoding, sep=sep)
                    if len(df.columns) > 1:
                        return df
                except Exception:
                    continue
        return pd.read_csv(caminho, encoding='latin-1')
    elif ext == 'XLSX':
        return pd.read_excel(caminho, engine='openpyxl')
    elif ext == 'XLS':
        return pd.read_excel(caminho, engine='xlrd')
    else:
        raise ValueError(f'Extensão não suportada: {extensao}')


# --- Cálculo do Indicador de Pressão de Estoque --------------------------------

def _calcular_pressao_estoque(df_vendas_norm, df_compras_norm, col_vqtd, col_vval,
                               col_cqtd, col_cval):
    """
    df_vendas_norm e df_compras_norm já têm coluna 'produto_norm'.
    col_vqtd: coluna de quantidade em vendas
    col_vval: coluna de valor em vendas (pode ser None)
    col_cqtd: coluna de quantidade em compras
    col_cval: coluna de valor em compras (pode ser None)
    """
    vendas_agg = df_vendas_norm.groupby('produto_norm').agg(
        quantidade_vendida=(col_vqtd, 'sum')
    ).reset_index()

    compras_agg = df_compras_norm.groupby('produto_norm').agg(
        quantidade_comprada=(col_cqtd, 'sum')
    ).reset_index()

    if col_cval:
        compras_val = df_compras_norm.groupby('produto_norm').agg(
            valor_comprado=(col_cval, 'sum')
        ).reset_index()
        compras_agg = compras_agg.merge(compras_val, on='produto_norm', how='left')

    merged = compras_agg.merge(vendas_agg, on='produto_norm', how='left')
    merged['quantidade_vendida'] = merged['quantidade_vendida'].fillna(0)

    merged['saldo_qty'] = merged['quantidade_comprada'] - merged['quantidade_vendida']
    merged['saldo_qty_positivo'] = merged['saldo_qty'].clip(lower=0)

    if merged['saldo_qty_positivo'].sum() == 0:
        return {
            'produto_maior_saldo_parado_nome': None,
            'saldo_estimado_parado': None,
            'saldo_estimado_compras_vendas': None,
        }

    idx_maior = merged['saldo_qty_positivo'].idxmax()
    produto_maior = merged.loc[idx_maior, 'produto_norm']
    saldo_maior_qtd = float(merged.loc[idx_maior, 'saldo_qty_positivo'])

    # Calcula valor estimado parado (somente se houver custo confiável)
    saldo_valor = None
    if col_cval and 'valor_comprado' in merged.columns:
        merged['custo_medio'] = merged.apply(
            lambda r: float(r['valor_comprado']) / float(r['quantidade_comprada'])
            if float(r['quantidade_comprada']) > 0 else 0.0,
            axis=1
        )
        merged['valor_parado'] = merged['saldo_qty_positivo'] * merged['custo_medio']
        total_valor_parado = float(merged['valor_parado'].sum())
        # Só usa se o total de custo for > 0 (dados confiáveis)
        total_custo = float(merged.get('valor_comprado', pd.Series([0])).sum())
        if total_custo > 0:
            saldo_valor = total_valor_parado

    return {
        'produto_maior_saldo_parado_nome': produto_maior,
        'saldo_estimado_parado': saldo_maior_qtd,
        'saldo_estimado_compras_vendas': saldo_valor,
    }


# --- Processamento principal --------------------------------------------------

def processar(analise, upload_vendas, upload_compras) -> dict:
    """
    Processa os arquivos de VENDAS e COMPRAS e retorna dict com KPIs.
    Levanta ValueError em caso de dados insuficientes.
    """
    df_v = ler_arquivo(upload_vendas.caminho_arquivo, upload_vendas.extensao_arquivo)
    df_c = ler_arquivo(upload_compras.caminho_arquivo, upload_compras.extensao_arquivo)

    # Remove linhas completamente vazias
    df_v = df_v.dropna(how='all').reset_index(drop=True)
    df_c = df_c.dropna(how='all').reset_index(drop=True)

    if df_v.empty:
        raise ValueError('Relatório de VENDAS está vazio.')
    if df_c.empty:
        raise ValueError('Relatório de COMPRAS está vazio.')

    col_vprod, col_vqtd, col_vval = _mapear_colunas(df_v)
    col_cprod, col_cqtd, col_cval = _mapear_colunas(df_c)

    if col_vprod is None:
        raise ValueError('Não foi possível identificar a coluna de produto no relatório de VENDAS.')
    if col_vqtd is None:
        raise ValueError('Não foi possível identificar a coluna de quantidade no relatório de VENDAS.')
    if col_vval is None:
        raise ValueError('Não foi possível identificar a coluna de valor no relatório de VENDAS.')
    if col_cprod is None:
        raise ValueError('Não foi possível identificar a coluna de produto no relatório de COMPRAS.')
    if col_cqtd is None:
        raise ValueError('Não foi possível identificar a coluna de quantidade no relatório de COMPRAS.')

    # Converte para numérico
    df_v[col_vqtd] = pd.to_numeric(df_v[col_vqtd], errors='coerce').fillna(0)
    df_v[col_vval] = pd.to_numeric(df_v[col_vval], errors='coerce').fillna(0)
    df_c[col_cqtd] = pd.to_numeric(df_c[col_cqtd], errors='coerce').fillna(0)
    if col_cval:
        df_c[col_cval] = pd.to_numeric(df_c[col_cval], errors='coerce').fillna(0)

    # Normaliza nomes de produto
    df_v['produto_norm'] = df_v[col_vprod].apply(normalizar_produto)
    df_c['produto_norm'] = df_c[col_cprod].apply(normalizar_produto)

    # Remove produtos com nome vazio após normalização
    df_v = df_v[df_v['produto_norm'] != '']
    df_c = df_c[df_c['produto_norm'] != '']

    # --- KPIs de vendas ---
    faturamento_total = float(df_v[col_vval].sum())

    vendas_por_produto_qtd = df_v.groupby('produto_norm')[col_vqtd].sum()
    vendas_por_produto_val = df_v.groupby('produto_norm')[col_vval].sum()

    produto_mais_vendido_nome = str(vendas_por_produto_qtd.idxmax())
    produto_mais_vendido_quantidade = float(vendas_por_produto_qtd.max())

    produto_maior_faturamento_nome = str(vendas_por_produto_val.idxmax())
    produto_maior_faturamento_valor = float(vendas_por_produto_val.max())

    # --- KPIs de compras ---
    total_comprado = None
    if col_cval:
        total_comprado = float(df_c[col_cval].sum())
        if total_comprado == 0:
            total_comprado = None

    # --- Indicador de Pressão de Estoque ---
    pressao = _calcular_pressao_estoque(
        df_v, df_c, col_vqtd, col_vval, col_cqtd, col_cval
    )

    return {
        'faturamento_total': faturamento_total,
        'total_comprado': total_comprado,
        'saldo_estimado_compras_vendas': pressao['saldo_estimado_compras_vendas'],
        'produto_mais_vendido_nome': produto_mais_vendido_nome,
        'produto_mais_vendido_quantidade': produto_mais_vendido_quantidade,
        'produto_maior_faturamento_nome': produto_maior_faturamento_nome,
        'produto_maior_faturamento_valor': produto_maior_faturamento_valor,
        'produto_maior_saldo_parado_nome': pressao['produto_maior_saldo_parado_nome'],
        'saldo_estimado_parado': pressao['saldo_estimado_parado'],
        'versao_processamento': 1,
        'data_geracao': datetime.utcnow(),
    }


def sha256_arquivo(caminho: str) -> str:
    h = hashlib.sha256()
    with open(caminho, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            h.update(chunk)
    return h.hexdigest()
