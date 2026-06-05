"""
ETL do NEXO — processa relatórios de VENDAS e COMPRAS de PDV.

Leitura robusta:
  - detecta a linha real de cabeçalho (não assume linha 1);
  - combina cabeçalhos compostos em duas linhas;
  - remove colunas vazias / "Unnamed";
  - converte números em formato brasileiro (1.234,56) e americano (1,234.56).

KPIs persistidos em indicador_analise:
  - faturamento_total
  - total_comprado
  - saldo_estimado_compras_vendas  (NULL se não houver custo confiável por produto)
  - produto_mais_vendido_nome / quantidade
  - produto_maior_faturamento_nome / valor
  - produto_maior_saldo_parado_nome
  - saldo_estimado_parado  (QUANTIDADE estimada parada, não valor monetário)
  - versao_processamento
  - data_geracao

Indicador de Pressão de Estoque (por produto normalizado):
    saldo_qty = quantidade_comprada - quantidade_vendida
    saldo_qty_positivo = max(saldo_qty, 0)
  Com custo confiável por produto:
    custo_medio = valor_comprado / quantidade_comprada
    saldo_estimado_compras_vendas = soma(saldo_qty_positivo * custo_medio)
  Sem produto+quantidade+custo confiável em COMPRAS:
    saldo_estimado_compras_vendas / produto_maior_saldo_parado_nome /
    saldo_estimado_parado ficam indisponíveis (None).

PROIBIDO: saldo = total_comprado - faturamento_total
"""
import re
import unicodedata
import hashlib
import pandas as pd
from datetime import datetime


# --- Normalização -------------------------------------------------------------

def normalizar_produto(nome) -> str:
    if not isinstance(nome, str):
        nome = str(nome) if nome is not None else ''
    nome = unicodedata.normalize('NFD', nome)
    nome = ''.join(c for c in nome if unicodedata.category(c) != 'Mn')
    nome = nome.upper()
    nome = re.sub(r'[^A-Z0-9\s]', '', nome)
    nome = re.sub(r'\s+', ' ', nome).strip()
    return nome


def _norm_header(texto) -> str:
    """Normaliza um nome de coluna para comparação: maiúsculas, sem acentos,
    sem caracteres especiais e espaços colapsados."""
    if texto is None:
        return ''
    try:
        if pd.isna(texto):
            return ''
    except (TypeError, ValueError):
        pass
    s = str(texto)
    if s.strip().lower() == 'nan':
        return ''
    s = unicodedata.normalize('NFD', s)
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')
    s = s.upper()
    s = re.sub(r'[^A-Z0-9\s]', ' ', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s


def _to_number(val):
    """Converte valores em formato brasileiro/americano para float.
    Aceita '1.234,56', '1234,56', '1,234.56', '1234.56', 'R$ 1.234,56'.
    Retorna None quando não há número."""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        if isinstance(val, float) and pd.isna(val):
            return None
        return float(val)
    s = str(val).strip()
    if not s:
        return None
    # Mantém apenas dígitos, sinais e separadores
    s = re.sub(r'[^\d,.\-]', '', s)
    if s in ('', '-', '.', ',', '--'):
        return None
    tem_virgula = ',' in s
    tem_ponto = '.' in s
    if tem_virgula and tem_ponto:
        if s.rfind(',') > s.rfind('.'):
            # vírgula é o separador decimal (BR): 1.234,56
            s = s.replace('.', '').replace(',', '.')
        else:
            # ponto é o separador decimal (US): 1,234.56
            s = s.replace(',', '')
    elif tem_virgula:
        # somente vírgula → decimal brasileiro
        s = s.replace(',', '.')
    # somente ponto ou apenas dígitos → já está em formato float
    try:
        return float(s)
    except ValueError:
        return None


# --- Leitura bruta ------------------------------------------------------------

def _ler_raw(caminho: str, extensao: str) -> pd.DataFrame:
    """Lê o arquivo inteiro sem assumir cabeçalho (header=None)."""
    ext = extensao.upper()
    if ext == 'CSV':
        for encoding in ('utf-8', 'latin-1', 'cp1252'):
            for sep in (';', ',', '\t'):
                try:
                    df = pd.read_csv(caminho, encoding=encoding, sep=sep,
                                     header=None, dtype=str)
                    if df.shape[1] > 1:
                        return df
                except Exception:
                    continue
        return pd.read_csv(caminho, encoding='latin-1', header=None, dtype=str)
    elif ext == 'XLSX':
        return pd.read_excel(caminho, engine='openpyxl', header=None)
    elif ext == 'XLS':
        return pd.read_excel(caminho, engine='xlrd', header=None)
    else:
        raise ValueError(f'Extensão não suportada: {extensao}')


_ANCHORS = [
    'PRODUTO', 'DESCRICAO', 'NOME', 'QTD', 'QTDE', 'QUANTIDADE', 'TOTAL',
    'VALOR', 'VR TOTAL', 'FORNECEDOR', 'NUMERO', 'NF', 'DATA', 'CODIGO',
    'SERIE', 'ITEM', 'MERCADORIA', 'UNIT', 'CUSTO', 'DESPESA',
]


def _linha_eh_header(valores) -> int:
    """Conta quantas células de uma linha batem com tokens esperados de cabeçalho."""
    matches = 0
    for cel in valores:
        nc = _norm_header(cel)
        if not nc:
            continue
        if any(tok in nc or nc in tok for tok in _ANCHORS):
            matches += 1
    return matches


def _linha_eh_complemento(valores, n_header) -> bool:
    """Uma linha é complemento de cabeçalho (segunda linha) se todas as suas
    células preenchidas forem textuais (não numéricas) e em menor quantidade
    que o cabeçalho principal."""
    preenchidas = [v for v in valores if _norm_header(v)]
    if not preenchidas or len(preenchidas) >= n_header:
        return False
    # Nenhuma célula preenchida pode ser número (senão é linha de dados)
    for v in preenchidas:
        if _to_number(v) is not None:
            return False
    return True


def _carregar_dataframe(caminho: str, extensao: str) -> pd.DataFrame:
    """Lê o arquivo, detecta a linha de cabeçalho (e eventual segunda linha
    de cabeçalho composto) e devolve um DataFrame limpo."""
    raw = _ler_raw(caminho, extensao)
    raw = raw.dropna(how='all').reset_index(drop=True)
    if raw.empty:
        return pd.DataFrame()

    # Encontra a linha de cabeçalho nas primeiras linhas
    limite = min(20, len(raw))
    melhor_idx, melhor_score = 0, -1
    for i in range(limite):
        score = _linha_eh_header(list(raw.iloc[i].values))
        if score > melhor_score:
            melhor_score, melhor_idx = score, i
    if melhor_score < 2:
        melhor_idx = 0  # fallback: primeira linha

    header_vals = list(raw.iloc[melhor_idx].values)
    n_header = len([v for v in header_vals if _norm_header(v)])

    # Verifica cabeçalho composto em duas linhas
    comp_vals = None
    data_start = melhor_idx + 1
    if melhor_idx + 1 < len(raw):
        prox = list(raw.iloc[melhor_idx + 1].values)
        if _linha_eh_complemento(prox, n_header):
            comp_vals = prox
            data_start = melhor_idx + 2

    # Monta nomes de coluna (combina as duas linhas quando há complemento)
    nomes = []
    for j in range(raw.shape[1]):
        topo = header_vals[j] if j < len(header_vals) else None
        partes = []
        if topo is not None and not (isinstance(topo, float) and pd.isna(topo)):
            t = str(topo).strip()
            if t and t.lower() != 'nan':
                partes.append(t)
        if comp_vals is not None and j < len(comp_vals):
            base = comp_vals[j]
            if base is not None and not (isinstance(base, float) and pd.isna(base)):
                b = str(base).strip()
                if b and b.lower() != 'nan':
                    partes.append(b)
        nome = ' '.join(partes).strip()
        nomes.append(nome if nome else f'col_{j}')

    dados = raw.iloc[data_start:].copy()
    dados.columns = nomes
    dados = dados.reset_index(drop=True)

    # Remove colunas totalmente vazias e colunas sem nome real
    manter = []
    for c in dados.columns:
        col = dados[c]
        vazia = col.apply(lambda v: not str(v).strip() or str(v).lower() == 'nan').all()
        sem_nome = str(c).startswith('col_') or _norm_header(c) == ''
        if vazia and sem_nome:
            continue
        if vazia:
            continue
        manter.append(c)
    dados = dados[manter]

    # Remove linhas completamente vazias
    dados = dados.dropna(how='all').reset_index(drop=True)
    return dados


# --- Detecção de colunas ------------------------------------------------------

def _candidatos(cols, aliases):
    """Lista de colunas candidatas em ordem de preferência (exatas, depois
    por substring), sem duplicar."""
    norm_map = {}
    for c in cols:
        norm_map.setdefault(_norm_header(c), c)
    ordenadas = []

    def _add(orig):
        if orig not in ordenadas:
            ordenadas.append(orig)

    for a in aliases:
        na = _norm_header(a)
        if na in norm_map:
            _add(norm_map[na])
    for a in aliases:
        na = _norm_header(a)
        if not na:
            continue
        for nk, orig in norm_map.items():
            if na in nk or nk in na:
                _add(orig)
    return ordenadas


def _densidade_numerica(serie) -> float:
    valores = [v for v in serie if str(v).strip() and str(v).lower() != 'nan']
    if not valores:
        return 0.0
    numericos = sum(1 for v in valores if _to_number(v) is not None)
    return numericos / len(valores)


def _detectar_texto(cols, aliases):
    cands = _candidatos(cols, aliases)
    return cands[0] if cands else None


def _detectar_numerica(df, aliases, minimo=0.3):
    cands = _candidatos(df.columns, aliases)
    for c in cands:
        if _densidade_numerica(df[c]) >= minimo:
            return c
    return cands[0] if cands else None


_VENDAS_PRODUTO = [
    'PRODUTO', 'DESCRICAO PRODUTO', 'NOME DO PRODUTO', 'NOME PRODUTO',
    'DESCRICAO', 'ITEM', 'MERCADORIA',
]
_VENDAS_QTD = [
    'QTDE VENDIDA', 'QTD VENDIDA', 'QUANTIDADE VENDIDA', 'QTDE VEND',
    'QTDE', 'QTD', 'QUANTIDADE', 'QTY', 'QUANT', 'UNIDADES',
]
_VENDAS_VALOR = [
    'TOTAL VENDA', 'VALOR TOTAL VENDA', 'TOTAL VENDIDO', 'VALOR VENDA',
    'VALOR TOTAL', 'TOTAL VEND', 'VR TOTAL', 'FATURAMENTO', 'TOTAL', 'VALOR',
]

_COMPRAS_TOTAL = [
    'VR TOTAL PRODUTOS', 'VALOR TOTAL PRODUTOS', 'TOTAL PRODUTOS', 'VALOR NF',
    'TOTAL NOTA', 'VR TOTAL', 'VALOR TOTAL', 'TOTAL',
]
_COMPRAS_PRODUTO = [
    'PRODUTO', 'DESCRICAO PRODUTO', 'NOME DO PRODUTO', 'NOME PRODUTO',
    'DESCRICAO', 'ITEM', 'MERCADORIA',
]
_COMPRAS_QTD = [
    'QTDE COMPRADA', 'QTD COMPRADA', 'QUANTIDADE COMPRADA', 'QTDE', 'QTD',
    'QUANTIDADE',
]
# Valor TOTAL por linha/produto (não unitário): custo_medio = valor/quantidade.
_COMPRAS_VALOR_PRODUTO = [
    'VALOR TOTAL ITEM', 'VALOR TOTAL PRODUTO', 'TOTAL ITEM', 'VALOR ITEM',
    'VALOR PRODUTO', 'CUSTO TOTAL', 'CUSTO PRODUTO',
]


# --- Pressão de estoque -------------------------------------------------------

def _calcular_pressao_estoque(df_v, df_c, col_vqtd, col_cprod, col_cqtd, col_cval):
    """Calcula a Pressão de Estoque apenas quando COMPRAS tem
    produto + quantidade + custo confiável por produto."""
    indisponivel = {
        'produto_maior_saldo_parado_nome': None,
        'saldo_estimado_parado': None,
        'saldo_estimado_compras_vendas': None,
    }
    if not (col_cprod and col_cqtd and col_cval):
        return indisponivel
    if _densidade_numerica(df_c[col_cqtd]) < 0.3 or _densidade_numerica(df_c[col_cval]) < 0.3:
        return indisponivel

    compras = df_c.copy()
    compras['produto_norm'] = compras[col_cprod].apply(normalizar_produto)
    compras['_qtd'] = compras[col_cqtd].apply(_to_number)
    compras['_val'] = compras[col_cval].apply(_to_number)
    compras = compras[(compras['produto_norm'] != '') & compras['_qtd'].notna()]
    if compras.empty:
        return indisponivel

    compras_agg = compras.groupby('produto_norm').agg(
        quantidade_comprada=('_qtd', 'sum'),
        valor_comprado=('_val', 'sum'),
    ).reset_index()

    vendas = df_v.groupby('produto_norm').agg(
        quantidade_vendida=(col_vqtd, 'sum')).reset_index()

    merged = compras_agg.merge(vendas, on='produto_norm', how='left')
    merged['quantidade_vendida'] = merged['quantidade_vendida'].fillna(0)
    merged['saldo_qty'] = merged['quantidade_comprada'] - merged['quantidade_vendida']
    merged['saldo_qty_positivo'] = merged['saldo_qty'].clip(lower=0)

    if merged['saldo_qty_positivo'].sum() == 0:
        return indisponivel

    idx_maior = merged['saldo_qty_positivo'].idxmax()
    produto_maior = merged.loc[idx_maior, 'produto_norm']
    saldo_maior_qtd = float(merged.loc[idx_maior, 'saldo_qty_positivo'])

    saldo_valor = None
    total_custo = float(merged['valor_comprado'].fillna(0).sum())
    if total_custo > 0:
        merged['custo_medio'] = merged.apply(
            lambda r: float(r['valor_comprado']) / float(r['quantidade_comprada'])
            if r['quantidade_comprada'] and float(r['quantidade_comprada']) > 0 else 0.0,
            axis=1)
        merged['valor_parado'] = merged['saldo_qty_positivo'] * merged['custo_medio']
        saldo_valor = float(merged['valor_parado'].sum())

    return {
        'produto_maior_saldo_parado_nome': produto_maior,
        'saldo_estimado_parado': saldo_maior_qtd,
        'saldo_estimado_compras_vendas': saldo_valor,
    }


# --- Processamento principal --------------------------------------------------

def processar(analise, upload_vendas, upload_compras) -> dict:
    """Processa VENDAS e COMPRAS e devolve dict de KPIs.
    Levanta ValueError quando faltam colunas mínimas de VENDAS."""
    df_v = _carregar_dataframe(upload_vendas.caminho_arquivo, upload_vendas.extensao_arquivo)
    df_c = _carregar_dataframe(upload_compras.caminho_arquivo, upload_compras.extensao_arquivo)

    if df_v.empty:
        raise ValueError('Relatório de VENDAS está vazio ou ilegível.')
    if df_c.empty:
        raise ValueError('Relatório de COMPRAS está vazio ou ilegível.')

    # --- VENDAS (colunas mínimas obrigatórias) ---
    col_vprod = _detectar_texto(df_v.columns, _VENDAS_PRODUTO)
    col_vqtd = _detectar_numerica(df_v, _VENDAS_QTD)
    col_vval = _detectar_numerica(df_v, _VENDAS_VALOR)

    if col_vprod is None:
        raise ValueError('Não foi possível identificar a coluna de produto no relatório de VENDAS.')
    if col_vqtd is None:
        raise ValueError('Não foi possível identificar a coluna de quantidade no relatório de VENDAS.')
    if col_vval is None:
        raise ValueError('Não foi possível identificar a coluna de valor no relatório de VENDAS.')

    df_v[col_vqtd] = df_v[col_vqtd].apply(_to_number)
    df_v[col_vval] = df_v[col_vval].apply(_to_number)
    df_v['produto_norm'] = df_v[col_vprod].apply(normalizar_produto)
    # Considera apenas linhas com produto e algum valor numérico (ignora rodapés/assinaturas)
    df_v = df_v[(df_v['produto_norm'] != '') &
                (df_v[col_vqtd].notna() | df_v[col_vval].notna())]
    df_v[col_vqtd] = df_v[col_vqtd].fillna(0)
    df_v[col_vval] = df_v[col_vval].fillna(0)

    if df_v.empty:
        raise ValueError('Nenhuma linha de venda válida encontrada no relatório de VENDAS.')

    faturamento_total = float(df_v[col_vval].sum())
    vendas_qtd = df_v.groupby('produto_norm')[col_vqtd].sum()
    vendas_val = df_v.groupby('produto_norm')[col_vval].sum()
    produto_mais_vendido_nome = str(vendas_qtd.idxmax())
    produto_mais_vendido_quantidade = float(vendas_qtd.max())
    produto_maior_faturamento_nome = str(vendas_val.idxmax())
    produto_maior_faturamento_valor = float(vendas_val.max())

    # --- COMPRAS (total comprado por nota/fornecedor) ---
    col_ctotal = _detectar_numerica(df_c, _COMPRAS_TOTAL)
    total_comprado = None
    if col_ctotal is not None:
        compras_tot = df_c.copy()
        compras_tot['_total'] = compras_tot[col_ctotal].apply(_to_number)
        compras_tot = compras_tot[compras_tot['_total'].notna()]
        # Em relatórios por nota fiscal, soma apenas linhas com identificador de
        # nota/data preenchido (descarta rodapés e linhas de "TOTAL GERAL").
        col_cdata = _detectar_texto(df_c.columns, ['DATA DA COMPRA', 'DATA COMPRA', 'DATA'])
        col_cnf = _detectar_texto(df_c.columns, ['NUMERO NF', 'NUMERO DA NF', 'NUMERO', 'NF'])
        ident_cols = [c for c in (col_cdata, col_cnf) if c]
        if ident_cols:
            mask = False
            for c in ident_cols:
                mask = mask | compras_tot[c].apply(lambda v: _norm_header(v) != '')
            compras_tot = compras_tot[mask]
        if len(compras_tot) > 0:
            soma = float(compras_tot['_total'].sum())
            total_comprado = soma if soma != 0 else None

    # --- Pressão de Estoque (só com produto+qtd+custo confiável) ---
    col_cprod = _detectar_texto(df_c.columns, _COMPRAS_PRODUTO)
    col_cqtd = _detectar_numerica(df_c, _COMPRAS_QTD)
    col_cval = _detectar_numerica(df_c, _COMPRAS_VALOR_PRODUTO)
    pressao = _calcular_pressao_estoque(df_v, df_c, col_vqtd, col_cprod, col_cqtd, col_cval)

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
