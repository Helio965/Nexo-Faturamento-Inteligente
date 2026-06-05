# NEXO — Faturamento Inteligente

Sistema web acadêmico desenvolvido para o **Projeto Integrador II**, com entrega final em 18/06/2026.

Consultoria de BI/dados para pequenos comércios (especialmente lojas de tintas e material de pintura) que transforma relatórios de PDV em KPIs, dashboards e devolutivas estratégicas.

---

## Stack oficial (MVP/PI2)

| Camada         | Tecnologia                        |
|----------------|-----------------------------------|
| Backend        | Python + Flask + Blueprints       |
| Banco de dados | SQLite (PRAGMA foreign_keys = ON) |
| ORM            | SQLAlchemy                        |
| ETL            | Pandas                            |
| Charts         | Plotly.js (nativo no template)    |
| Frontend       | Bootstrap 5 + Jinja2 templates    |
| Autenticação   | Flask-Login + Werkzeug Security   |

> **Power BI Embedded foi descartado.** Não faz parte do MVP.

---

## DER V4.1 — 10 tabelas oficiais do MVP

| # | Tabela                |
|---|-----------------------|
| 1 | `plano`               |
| 2 | `segmento`            |
| 3 | `empresa`             |
| 4 | `usuario`             |
| 5 | `analise`             |
| 6 | `upload_relatorio`    |
| 7 | `indicador_analise`   |
| 8 | `relatorio_analise`   |
| 9 | `chamado_suporte`     |
|10 | `mensagem_suporte`    |

A Central de Tickets mínima (`chamado_suporte` + `mensagem_suporte`) **faz parte do MVP**.

### Tabelas FORA do MVP (não implementadas)

- `avaliacao_analise`
- `fatura_cobranca`
- `historico_plano_empresa`
- `log_auditoria`

---

## Planos disponíveis

| Plano  | Frequência de análise | Nível de atendimento |
|--------|-----------------------|----------------------|
| BRONZE | Mensal                | BAIXO → prioridade BAIXA |
| PRATA  | Mensal                | MEDIO → prioridade MEDIA |
| OURO   | Mensal ou Quinzenal   | ALTO → prioridade ALTA   |

---

## Perfis de usuário

- **ADMIN** — criado via `seed.py`. Sem empresa associada (`id_empresa = NULL`). Não há cadastro de administrador pela interface.
- **CLIENTE** — criado pelo ADMIN. Sempre vinculado a uma empresa.

---

## Indicador de Pressão de Estoque

O indicador **não** representa resultado financeiro real, margem, apuração contábil, rentabilidade real nem estoque físico real.

**Cálculo por produto normalizado:**

```
Para cada produto:
  saldo_qty = quantidade_comprada - quantidade_vendida
  saldo_qty_positivo = max(saldo_qty, 0)

Se houver custo confiável por produto:
  custo_medio = valor_comprado / quantidade_comprada
  saldo_estimado_compras_vendas = soma(saldo_qty_positivo × custo_medio)

Se não houver custo confiável:
  saldo_estimado_compras_vendas = NULL  (indisponível)
```

> **PROIBIDO:** `total_comprado - faturamento_total` — essa fórmula mistura bases econômicas diferentes e nunca deve ser usada.

O campo `saldo_estimado_parado` armazena a **quantidade** estimada parada do produto com maior saldo, não o valor monetário.

---

## Como rodar localmente

### 1. Pré-requisitos

```bash
python -m venv .venv
source .venv/bin/activate   # Linux/Mac
.venv\Scripts\activate      # Windows

pip install -r requirements.txt
```

### 2. Variáveis de ambiente

```bash
cp .env.example .env
# Edite .env com seus valores reais
```

### 3. Seed (cria tabelas + admin + planos)

```bash
python seed.py
```

### 4. Executar

```bash
python run.py
```

Acesse: `http://localhost:5000`

### 5. Login

- Usar e-mail e senha definidos no `.env` (ADMIN_EMAIL / ADMIN_SENHA)

---

## Ciclo de análise

1. ADMIN cria análise → `AGUARDANDO_RELATORIO`
2. ADMIN faz upload de VENDAS e COMPRAS → `RELATORIO_RECEBIDO`
3. ADMIN clica "Processar Agora" (POST) → `EM_ANALISE` → KPIs gerados
4. ADMIN redige relatório estratégico
5. ADMIN publica → `CONCLUIDO`, relatório visível para o CLIENTE
6. ADMIN pode despublicar → volta para `EM_ANALISE`

---

## Fora do escopo do MVP

- Avaliação de análise pelo cliente
- Cobrança real / fatura
- Histórico de plano
- Log de auditoria
- WebSocket / chat em tempo real
- Anexos em tickets
- Notificações externas
- IA respondendo tickets
- PDF obrigatório
- Cadastro de novos administradores pela interface
- Múltiplos usuários CLIENTE por empresa

---

## Documentação obsoleta

Documentos anteriores ao DER V4.1 estão em `Docs/obsoleto/`.
Qualquer documento que cite 8 tabelas, 12 tabelas, Power BI Embedded,
"Nexo Start/Performance/Fatura Plus" ou a fórmula `total_comprado - faturamento_total`
é **obsoleto** e não deve ser usado como referência.
