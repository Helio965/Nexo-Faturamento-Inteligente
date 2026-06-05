-- =============================================================================
-- NEXO — Faturamento Inteligente
-- Schema SQL — DER V4.1 — MVP com Suporte Mínimo
-- 10 tabelas oficiais — PKs documentais
-- =============================================================================

PRAGMA foreign_keys = ON;

-- 1. plano
CREATE TABLE IF NOT EXISTS plano (
    id_plano                 INTEGER PRIMARY KEY AUTOINCREMENT,
    nome_plano               TEXT    NOT NULL UNIQUE,
    descricao                TEXT,
    valor_mensal             REAL    NOT NULL,
    qtd_analises_mes         INTEGER NOT NULL,
    tipo_analise_permitida   TEXT    NOT NULL,
    nivel_entrega_analise    TEXT    NOT NULL,
    nivel_dashboard          TEXT    NOT NULL,
    nivel_atendimento        TEXT    NOT NULL,
    ativo                    INTEGER NOT NULL DEFAULT 1,
    data_criacao             TEXT    NOT NULL DEFAULT (datetime('now')),
    data_atualizacao         TEXT    NOT NULL DEFAULT (datetime('now')),
    CONSTRAINT ck_plano_nome          CHECK (nome_plano             IN ('BRONZE','PRATA','OURO')),
    CONSTRAINT ck_plano_nivel         CHECK (nivel_atendimento      IN ('BAIXO','MEDIO','ALTO')),
    CONSTRAINT ck_plano_tipo_analise  CHECK (tipo_analise_permitida IN ('MENSAL','QUINZENAL')),
    CONSTRAINT ck_plano_nivel_entrega CHECK (nivel_entrega_analise  IN ('BASICA','COMPLETA','PREMIUM')),
    CONSTRAINT ck_plano_nivel_dash    CHECK (nivel_dashboard        IN ('RESUMIDO','GERENCIAL','COMPLETO'))
);

-- 2. segmento
CREATE TABLE IF NOT EXISTS segmento (
    id_segmento     INTEGER PRIMARY KEY AUTOINCREMENT,
    nome_segmento   TEXT    NOT NULL UNIQUE,
    descricao       TEXT,
    ativo           INTEGER NOT NULL DEFAULT 1,
    data_criacao    TEXT    NOT NULL DEFAULT (datetime('now')),
    data_atualizacao TEXT   NOT NULL DEFAULT (datetime('now'))
);

-- 3. empresa
CREATE TABLE IF NOT EXISTS empresa (
    id_empresa               INTEGER PRIMARY KEY AUTOINCREMENT,
    id_segmento              INTEGER NOT NULL REFERENCES segmento(id_segmento),
    id_plano_atual           INTEGER NOT NULL REFERENCES plano(id_plano),
    nome_fantasia            TEXT,
    razao_social             TEXT    NOT NULL,
    cnpj                     TEXT    NOT NULL UNIQUE,
    email_contato            TEXT    NOT NULL,
    telefone_contato         TEXT,
    data_contratacao         TEXT    NOT NULL,
    faturamento_base_mensal  REAL,
    status_conta             TEXT    NOT NULL DEFAULT 'ATIVA',
    data_criacao             TEXT    NOT NULL DEFAULT (datetime('now')),
    data_atualizacao         TEXT    NOT NULL DEFAULT (datetime('now')),
    CONSTRAINT ck_empresa_status CHECK (status_conta IN ('ATIVA','SUSPENSA','CANCELADA'))
);

CREATE INDEX IF NOT EXISTS ix_empresa_id_segmento    ON empresa(id_segmento);
CREATE INDEX IF NOT EXISTS ix_empresa_id_plano_atual ON empresa(id_plano_atual);

-- 4. usuario
CREATE TABLE IF NOT EXISTS usuario (
    id_usuario      INTEGER PRIMARY KEY AUTOINCREMENT,
    id_empresa      INTEGER REFERENCES empresa(id_empresa),
    nome            TEXT    NOT NULL,
    email           TEXT    NOT NULL UNIQUE,
    senha_hash      TEXT    NOT NULL,
    role            TEXT    NOT NULL,
    ativo           INTEGER NOT NULL DEFAULT 1,
    ultimo_acesso   TEXT,
    data_criacao    TEXT    NOT NULL DEFAULT (datetime('now')),
    data_atualizacao TEXT   NOT NULL DEFAULT (datetime('now')),
    CONSTRAINT ck_usuario_role         CHECK (role IN ('ADMIN','CLIENTE')),
    CONSTRAINT ck_usuario_role_empresa CHECK (
        (role = 'ADMIN'   AND id_empresa IS NULL) OR
        (role = 'CLIENTE' AND id_empresa IS NOT NULL)
    )
);

CREATE INDEX IF NOT EXISTS ix_usuario_id_empresa ON usuario(id_empresa);

-- 5. analise
CREATE TABLE IF NOT EXISTS analise (
    id_analise                    INTEGER PRIMARY KEY AUTOINCREMENT,
    id_empresa                    INTEGER NOT NULL REFERENCES empresa(id_empresa),
    id_plano_referencia           INTEGER NOT NULL REFERENCES plano(id_plano),
    id_usuario_admin_responsavel  INTEGER NOT NULL REFERENCES usuario(id_usuario),
    periodo_inicio                TEXT    NOT NULL,
    periodo_fim                   TEXT    NOT NULL,
    tipo_analise                  TEXT    NOT NULL,
    mes_referencia                INTEGER NOT NULL,
    ano_referencia                INTEGER NOT NULL,
    quinzena_referencia           INTEGER,
    status_analise                TEXT    NOT NULL DEFAULT 'AGUARDANDO_RELATORIO',
    data_criacao                  TEXT    NOT NULL DEFAULT (datetime('now')),
    data_atualizacao              TEXT    NOT NULL DEFAULT (datetime('now')),
    data_conclusao                TEXT,
    CONSTRAINT ck_analise_status   CHECK (status_analise IN (
        'AGUARDANDO_RELATORIO','RELATORIO_RECEBIDO','EM_ANALISE','CONCLUIDO'
    )),
    CONSTRAINT ck_analise_tipo     CHECK (tipo_analise IN ('MENSAL','QUINZENAL')),
    CONSTRAINT ck_analise_mes      CHECK (mes_referencia BETWEEN 1 AND 12),
    CONSTRAINT ck_analise_periodo  CHECK (periodo_fim >= periodo_inicio),
    CONSTRAINT ck_analise_quinzena CHECK (
        (tipo_analise = 'MENSAL'    AND quinzena_referencia IS NULL) OR
        (tipo_analise = 'QUINZENAL' AND quinzena_referencia IS NOT NULL
                                    AND quinzena_referencia IN (1, 2))
    )
);

CREATE INDEX IF NOT EXISTS ix_analise_id_empresa ON analise(id_empresa);
CREATE INDEX IF NOT EXISTS ix_analise_id_plano   ON analise(id_plano_referencia);
CREATE INDEX IF NOT EXISTS ix_analise_id_admin   ON analise(id_usuario_admin_responsavel);

-- 6. upload_relatorio
CREATE TABLE IF NOT EXISTS upload_relatorio (
    id_upload             INTEGER PRIMARY KEY AUTOINCREMENT,
    id_analise            INTEGER NOT NULL REFERENCES analise(id_analise),
    id_usuario_admin      INTEGER NOT NULL REFERENCES usuario(id_usuario),
    tipo_relatorio        TEXT    NOT NULL,
    nome_arquivo_original TEXT    NOT NULL,
    caminho_arquivo       TEXT    NOT NULL,
    extensao_arquivo      TEXT    NOT NULL,
    tamanho_arquivo       INTEGER,
    hash_arquivo          TEXT,
    data_upload           TEXT    NOT NULL DEFAULT (datetime('now')),
    status_processamento  TEXT    NOT NULL DEFAULT 'PENDENTE',
    data_processamento    TEXT,
    mensagem_erro         TEXT,
    CONSTRAINT uq_upload_analise_tipo UNIQUE (id_analise, tipo_relatorio),
    CONSTRAINT ck_upload_tipo        CHECK (tipo_relatorio       IN ('VENDAS','COMPRAS')),
    CONSTRAINT ck_upload_extensao    CHECK (extensao_arquivo     IN ('CSV','XLSX','XLS')),
    CONSTRAINT ck_upload_status      CHECK (status_processamento IN ('PENDENTE','PROCESSADO','ERRO'))
);

CREATE INDEX IF NOT EXISTS ix_upload_id_analise ON upload_relatorio(id_analise);
CREATE INDEX IF NOT EXISTS ix_upload_id_usuario ON upload_relatorio(id_usuario_admin);

-- 7. indicador_analise
CREATE TABLE IF NOT EXISTS indicador_analise (
    id_indicador                    INTEGER PRIMARY KEY AUTOINCREMENT,
    id_analise                      INTEGER NOT NULL UNIQUE REFERENCES analise(id_analise),
    faturamento_total               REAL,
    total_comprado                  REAL,
    saldo_estimado_compras_vendas   REAL,   -- NULL quando não há custo confiável por produto
    produto_mais_vendido_nome       TEXT,
    produto_mais_vendido_quantidade REAL,
    produto_maior_faturamento_nome  TEXT,
    produto_maior_faturamento_valor REAL,
    produto_maior_saldo_parado_nome TEXT,
    saldo_estimado_parado           REAL,   -- quantidade estimada parada (não valor monetário)
    versao_processamento            INTEGER NOT NULL DEFAULT 1,
    data_geracao                    TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS ix_indicador_id_analise ON indicador_analise(id_analise);

-- 8. relatorio_analise
CREATE TABLE IF NOT EXISTS relatorio_analise (
    id_relatorio            INTEGER PRIMARY KEY AUTOINCREMENT,
    id_analise              INTEGER NOT NULL UNIQUE REFERENCES analise(id_analise),
    id_usuario_admin_autor  INTEGER NOT NULL REFERENCES usuario(id_usuario),
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
    id_chamado               INTEGER PRIMARY KEY AUTOINCREMENT,
    id_empresa               INTEGER NOT NULL REFERENCES empresa(id_empresa),
    id_usuario_cliente_autor INTEGER NOT NULL REFERENCES usuario(id_usuario),
    assunto                  TEXT    NOT NULL,
    descricao                TEXT    NOT NULL,
    prioridade_atendimento   TEXT    NOT NULL,
    status_chamado           TEXT    NOT NULL DEFAULT 'ABERTO',
    data_abertura            TEXT    NOT NULL DEFAULT (datetime('now')),
    data_atualizacao         TEXT    NOT NULL DEFAULT (datetime('now')),
    data_fechamento          TEXT,
    CONSTRAINT ck_chamado_status     CHECK (status_chamado         IN ('ABERTO','EM_ANDAMENTO','RESPONDIDO','RESOLVIDO')),
    CONSTRAINT ck_chamado_prioridade CHECK (prioridade_atendimento IN ('BAIXA','MEDIA','ALTA')),
    CONSTRAINT ck_chamado_assunto    CHECK (length(trim(assunto))   > 0),
    CONSTRAINT ck_chamado_descricao  CHECK (length(trim(descricao)) > 0)
);

CREATE INDEX IF NOT EXISTS ix_chamado_id_empresa ON chamado_suporte(id_empresa);
CREATE INDEX IF NOT EXISTS ix_chamado_id_usuario ON chamado_suporte(id_usuario_cliente_autor);

-- 10. mensagem_suporte
CREATE TABLE IF NOT EXISTS mensagem_suporte (
    id_mensagem      INTEGER PRIMARY KEY AUTOINCREMENT,
    id_chamado       INTEGER NOT NULL REFERENCES chamado_suporte(id_chamado),
    id_usuario_autor INTEGER NOT NULL REFERENCES usuario(id_usuario),
    conteudo         TEXT    NOT NULL,
    data_envio       TEXT    NOT NULL DEFAULT (datetime('now')),
    CONSTRAINT ck_mensagem_conteudo CHECK (length(trim(conteudo)) > 0)
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
