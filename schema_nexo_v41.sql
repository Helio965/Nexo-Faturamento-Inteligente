-- =============================================================================
-- NEXO — Faturamento Inteligente
-- Schema SQL — DER V4.1 — MVP com Suporte Mínimo
-- 10 tabelas oficiais
-- =============================================================================

PRAGMA foreign_keys = ON;

-- 1. plano
CREATE TABLE IF NOT EXISTS plano (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    nome_plano         TEXT    NOT NULL UNIQUE,
    descricao          TEXT,
    nivel_atendimento  TEXT    NOT NULL,
    ativo              INTEGER NOT NULL DEFAULT 1,
    CONSTRAINT ck_plano_nome    CHECK (nome_plano        IN ('BRONZE','PRATA','OURO')),
    CONSTRAINT ck_plano_nivel   CHECK (nivel_atendimento IN ('BAIXO','MEDIO','ALTO'))
);

-- 2. segmento
CREATE TABLE IF NOT EXISTS segmento (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    nome_segmento  TEXT NOT NULL UNIQUE,
    descricao      TEXT
);

-- 3. empresa
CREATE TABLE IF NOT EXISTS empresa (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    id_segmento     INTEGER REFERENCES segmento(id),
    id_plano_atual  INTEGER NOT NULL REFERENCES plano(id),
    nome_fantasia   TEXT    NOT NULL,
    razao_social    TEXT,
    cnpj            TEXT    UNIQUE,
    email_contato   TEXT,
    status_conta    TEXT    NOT NULL DEFAULT 'ATIVA',
    data_criacao    TEXT    NOT NULL DEFAULT (datetime('now')),
    CONSTRAINT ck_empresa_status CHECK (status_conta IN ('ATIVA','SUSPENSA','CANCELADA'))
);

CREATE INDEX IF NOT EXISTS ix_empresa_id_segmento    ON empresa(id_segmento);
CREATE INDEX IF NOT EXISTS ix_empresa_id_plano_atual ON empresa(id_plano_atual);

-- 4. usuario
CREATE TABLE IF NOT EXISTS usuario (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    id_empresa  INTEGER REFERENCES empresa(id),
    nome        TEXT    NOT NULL,
    email       TEXT    NOT NULL UNIQUE,
    senha_hash  TEXT    NOT NULL,
    role        TEXT    NOT NULL,
    ativo       INTEGER NOT NULL DEFAULT 1,
    data_criacao TEXT   NOT NULL DEFAULT (datetime('now')),
    CONSTRAINT ck_usuario_role          CHECK (role IN ('ADMIN','CLIENTE')),
    CONSTRAINT ck_usuario_role_empresa  CHECK (
        (role = 'ADMIN'   AND id_empresa IS NULL) OR
        (role = 'CLIENTE' AND id_empresa IS NOT NULL)
    )
);

CREATE INDEX IF NOT EXISTS ix_usuario_id_empresa ON usuario(id_empresa);

-- 5. analise
CREATE TABLE IF NOT EXISTS analise (
    id                            INTEGER PRIMARY KEY AUTOINCREMENT,
    id_empresa                    INTEGER NOT NULL REFERENCES empresa(id),
    id_plano_referencia           INTEGER NOT NULL REFERENCES plano(id),
    id_usuario_admin_responsavel  INTEGER NOT NULL REFERENCES usuario(id),
    tipo_analise                  TEXT    NOT NULL,
    mes_referencia                INTEGER NOT NULL,
    ano_referencia                INTEGER NOT NULL,
    quinzena_referencia           INTEGER,
    status_analise                TEXT    NOT NULL DEFAULT 'AGUARDANDO_RELATORIO',
    data_criacao                  TEXT    NOT NULL DEFAULT (datetime('now')),
    data_conclusao                TEXT,
    CONSTRAINT ck_analise_status  CHECK (status_analise IN (
        'AGUARDANDO_RELATORIO','RELATORIO_RECEBIDO','EM_ANALISE','CONCLUIDO'
    )),
    CONSTRAINT ck_analise_tipo    CHECK (tipo_analise IN ('MENSAL','QUINZENAL')),
    CONSTRAINT ck_analise_quinzena CHECK (
        (tipo_analise = 'MENSAL'    AND quinzena_referencia IS NULL) OR
        (tipo_analise = 'QUINZENAL' AND quinzena_referencia IN (1, 2))
    )
);

CREATE INDEX IF NOT EXISTS ix_analise_id_empresa ON analise(id_empresa);
CREATE INDEX IF NOT EXISTS ix_analise_id_plano   ON analise(id_plano_referencia);
CREATE INDEX IF NOT EXISTS ix_analise_id_admin   ON analise(id_usuario_admin_responsavel);

-- 6. upload_relatorio
CREATE TABLE IF NOT EXISTS upload_relatorio (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    id_analise            INTEGER NOT NULL REFERENCES analise(id),
    id_usuario_admin      INTEGER NOT NULL REFERENCES usuario(id),
    tipo_relatorio        TEXT    NOT NULL,
    nome_arquivo_original TEXT    NOT NULL,
    extensao_arquivo      TEXT    NOT NULL,
    caminho_arquivo       TEXT    NOT NULL,
    tamanho_bytes         INTEGER,
    hash_sha256           TEXT,
    status_processamento  TEXT    NOT NULL DEFAULT 'PENDENTE',
    data_upload           TEXT    NOT NULL DEFAULT (datetime('now')),
    CONSTRAINT uq_upload_analise_tipo UNIQUE (id_analise, tipo_relatorio),
    CONSTRAINT ck_upload_tipo       CHECK (tipo_relatorio       IN ('VENDAS','COMPRAS')),
    CONSTRAINT ck_upload_extensao   CHECK (extensao_arquivo     IN ('CSV','XLSX','XLS')),
    CONSTRAINT ck_upload_status     CHECK (status_processamento IN ('PENDENTE','PROCESSADO','ERRO'))
);

CREATE INDEX IF NOT EXISTS ix_upload_id_analise ON upload_relatorio(id_analise);
CREATE INDEX IF NOT EXISTS ix_upload_id_usuario ON upload_relatorio(id_usuario_admin);

-- 7. indicador_analise
CREATE TABLE IF NOT EXISTS indicador_analise (
    id                              INTEGER PRIMARY KEY AUTOINCREMENT,
    id_analise                      INTEGER NOT NULL UNIQUE REFERENCES analise(id),
    faturamento_total               REAL,
    total_comprado                  REAL,
    -- NULL quando não há custo confiável por produto
    saldo_estimado_compras_vendas   REAL,
    produto_mais_vendido_nome       TEXT,
    produto_mais_vendido_quantidade REAL,
    produto_maior_faturamento_nome  TEXT,
    produto_maior_faturamento_valor REAL,
    produto_maior_saldo_parado_nome TEXT,
    -- Quantidade estimada parada (não valor monetário)
    saldo_estimado_parado           REAL,
    versao_processamento            INTEGER NOT NULL DEFAULT 1,
    data_geracao                    TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS ix_indicador_id_analise ON indicador_analise(id_analise);

-- 8. relatorio_analise
CREATE TABLE IF NOT EXISTS relatorio_analise (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    id_analise              INTEGER NOT NULL UNIQUE REFERENCES analise(id),
    id_usuario_admin_autor  INTEGER NOT NULL REFERENCES usuario(id),
    titulo                  TEXT    NOT NULL,
    resumo_executivo        TEXT,
    pontos_positivos        TEXT,
    pontos_de_alerta        TEXT,
    recomendacoes           TEXT,
    conclusao_estrategica   TEXT    NOT NULL,
    publicado               INTEGER NOT NULL DEFAULT 0,
    data_publicacao         TEXT,
    data_criacao            TEXT    NOT NULL DEFAULT (datetime('now')),
    data_atualizacao        TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS ix_relatorio_id_analise ON relatorio_analise(id_analise);
CREATE INDEX IF NOT EXISTS ix_relatorio_id_autor   ON relatorio_analise(id_usuario_admin_autor);

-- 9. chamado_suporte
CREATE TABLE IF NOT EXISTS chamado_suporte (
    id                         INTEGER PRIMARY KEY AUTOINCREMENT,
    id_empresa                 INTEGER NOT NULL REFERENCES empresa(id),
    id_usuario_cliente_autor   INTEGER NOT NULL REFERENCES usuario(id),
    assunto                    TEXT    NOT NULL,
    prioridade_atendimento     TEXT    NOT NULL,
    status_chamado             TEXT    NOT NULL DEFAULT 'ABERTO',
    data_criacao               TEXT    NOT NULL DEFAULT (datetime('now')),
    data_atualizacao           TEXT    NOT NULL DEFAULT (datetime('now')),
    CONSTRAINT ck_chamado_status     CHECK (status_chamado         IN ('ABERTO','EM_ANDAMENTO','RESPONDIDO','RESOLVIDO')),
    CONSTRAINT ck_chamado_prioridade CHECK (prioridade_atendimento IN ('BAIXA','MEDIA','ALTA'))
);

CREATE INDEX IF NOT EXISTS ix_chamado_id_empresa ON chamado_suporte(id_empresa);
CREATE INDEX IF NOT EXISTS ix_chamado_id_usuario ON chamado_suporte(id_usuario_cliente_autor);

-- 10. mensagem_suporte
CREATE TABLE IF NOT EXISTS mensagem_suporte (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    id_chamado       INTEGER NOT NULL REFERENCES chamado_suporte(id),
    id_usuario_autor INTEGER NOT NULL REFERENCES usuario(id),
    conteudo         TEXT    NOT NULL,
    data_criacao     TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS ix_mensagem_id_chamado ON mensagem_suporte(id_chamado);
CREATE INDEX IF NOT EXISTS ix_mensagem_id_autor   ON mensagem_suporte(id_usuario_autor);

-- =============================================================================
-- Tabelas FORA do MVP/PI2 — NÃO criar no schema ativo:
--   avaliacao_analise
--   fatura_cobranca
--   historico_plano_empresa
--   log_auditoria
-- =============================================================================
