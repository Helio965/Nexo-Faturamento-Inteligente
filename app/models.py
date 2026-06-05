from datetime import datetime
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import CheckConstraint, Index, UniqueConstraint
from app import db


class Plano(db.Model):
    __tablename__ = 'plano'

    id_plano = db.Column(db.Integer, primary_key=True)
    nome_plano = db.Column(db.String(50), nullable=False, unique=True)
    descricao = db.Column(db.Text)
    valor_mensal = db.Column(db.Numeric(10, 2), nullable=False)
    qtd_analises_mes = db.Column(db.Integer, nullable=False)
    tipo_analise_permitida = db.Column(db.String(20), nullable=False)   # MENSAL, QUINZENAL
    nivel_entrega_analise = db.Column(db.String(20), nullable=False)    # BASICA, COMPLETA, PREMIUM
    nivel_dashboard = db.Column(db.String(20), nullable=False)           # RESUMIDO, GERENCIAL, COMPLETO
    nivel_atendimento = db.Column(db.String(10), nullable=False)  # BAIXO, MEDIO, ALTO
    ativo = db.Column(db.Boolean, default=True, nullable=False)
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    data_atualizacao = db.Column(db.DateTime, default=datetime.utcnow,
                                 onupdate=datetime.utcnow, nullable=False)

    empresas = db.relationship('Empresa', back_populates='plano_atual', lazy='dynamic')
    analises = db.relationship('Analise', foreign_keys='Analise.id_plano_referencia',
                               back_populates='plano_referencia', lazy='dynamic')

    __table_args__ = (
        CheckConstraint("nome_plano IN ('BRONZE','PRATA','OURO')", name='ck_plano_nome'),
        CheckConstraint("nivel_atendimento IN ('BAIXO','MEDIO','ALTO')", name='ck_plano_nivel'),
        CheckConstraint(
            "tipo_analise_permitida IN ('MENSAL','QUINZENAL')",
            name='ck_plano_tipo_analise'),
        CheckConstraint(
            "nivel_entrega_analise IN ('BASICA','COMPLETA','PREMIUM')",
            name='ck_plano_nivel_entrega'),
        CheckConstraint(
            "nivel_dashboard IN ('RESUMIDO','GERENCIAL','COMPLETO')",
            name='ck_plano_nivel_dashboard'),
    )

    @property
    def prioridade_ticket(self):
        mapa = {'BAIXO': 'BAIXA', 'MEDIO': 'MEDIA', 'ALTO': 'ALTA'}
        return mapa.get(self.nivel_atendimento, 'BAIXA')


class Segmento(db.Model):
    __tablename__ = 'segmento'

    id_segmento = db.Column(db.Integer, primary_key=True)
    nome_segmento = db.Column(db.String(100), nullable=False, unique=True)
    descricao = db.Column(db.Text)
    ativo = db.Column(db.Boolean, default=True, nullable=False)
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    data_atualizacao = db.Column(db.DateTime, default=datetime.utcnow,
                                 onupdate=datetime.utcnow, nullable=False)

    empresas = db.relationship('Empresa', back_populates='segmento', lazy='dynamic')


class Empresa(db.Model):
    __tablename__ = 'empresa'

    id_empresa = db.Column(db.Integer, primary_key=True)
    id_segmento = db.Column(db.Integer, db.ForeignKey('segmento.id_segmento'), nullable=False)
    id_plano_atual = db.Column(db.Integer, db.ForeignKey('plano.id_plano'), nullable=False)
    cnpj = db.Column(db.String(18), unique=True, nullable=False)
    razao_social = db.Column(db.String(200), nullable=False)
    nome_fantasia = db.Column(db.String(200))
    email_contato = db.Column(db.String(200), nullable=False)
    telefone_contato = db.Column(db.String(20))
    data_contratacao = db.Column(db.Date, nullable=False)
    faturamento_base_mensal = db.Column(db.Numeric(15, 2))
    status_conta = db.Column(db.String(20), nullable=False, default='ATIVA')
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    data_atualizacao = db.Column(db.DateTime, default=datetime.utcnow,
                                 onupdate=datetime.utcnow, nullable=False)

    segmento = db.relationship('Segmento', back_populates='empresas')
    plano_atual = db.relationship('Plano', back_populates='empresas')
    usuarios = db.relationship('Usuario', back_populates='empresa', lazy='dynamic')
    analises = db.relationship('Analise', back_populates='empresa', lazy='dynamic')
    chamados = db.relationship('ChamadoSuporte', back_populates='empresa', lazy='dynamic')

    __table_args__ = (
        CheckConstraint("status_conta IN ('ATIVA','SUSPENSA','CANCELADA')",
                        name='ck_empresa_status'),
        Index('ix_empresa_id_segmento', 'id_segmento'),
        Index('ix_empresa_id_plano_atual', 'id_plano_atual'),
    )

    @property
    def nome_exibicao(self):
        """Nome fantasia é opcional; usa razão social como fallback."""
        return self.nome_fantasia or self.razao_social


class Usuario(UserMixin, db.Model):
    __tablename__ = 'usuario'

    id_usuario = db.Column(db.Integer, primary_key=True)
    id_empresa = db.Column(db.Integer, db.ForeignKey('empresa.id_empresa'), nullable=True)
    nome = db.Column(db.String(200), nullable=False)
    email = db.Column(db.String(200), nullable=False, unique=True)
    senha_hash = db.Column(db.String(512), nullable=False)
    role = db.Column(db.String(10), nullable=False)  # ADMIN, CLIENTE
    ativo = db.Column(db.Boolean, default=True, nullable=False)
    ultimo_acesso = db.Column(db.DateTime, nullable=True)
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    data_atualizacao = db.Column(db.DateTime, default=datetime.utcnow,
                                 onupdate=datetime.utcnow, nullable=False)

    empresa = db.relationship('Empresa', back_populates='usuarios')
    analises_responsavel = db.relationship(
        'Analise', foreign_keys='Analise.id_usuario_admin_responsavel',
        back_populates='admin_responsavel', lazy='dynamic')
    relatorios_autor = db.relationship(
        'RelatorioAnalise', foreign_keys='RelatorioAnalise.id_usuario_admin_autor',
        back_populates='admin_autor', lazy='dynamic')
    uploads = db.relationship(
        'UploadRelatorio', foreign_keys='UploadRelatorio.id_usuario_admin',
        back_populates='admin_upload', lazy='dynamic')
    chamados_cliente = db.relationship(
        'ChamadoSuporte', foreign_keys='ChamadoSuporte.id_usuario_cliente_autor',
        back_populates='cliente_autor', lazy='dynamic')
    mensagens = db.relationship(
        'MensagemSuporte', foreign_keys='MensagemSuporte.id_usuario_autor',
        back_populates='autor', lazy='dynamic')

    __table_args__ = (
        CheckConstraint("role IN ('ADMIN','CLIENTE')", name='ck_usuario_role'),
        CheckConstraint(
            "(role = 'ADMIN' AND id_empresa IS NULL) OR (role = 'CLIENTE' AND id_empresa IS NOT NULL)",
            name='ck_usuario_role_empresa'),
        Index('ix_usuario_id_empresa', 'id_empresa'),
    )

    # Flask-Login exige get_id(); retorna id_usuario como str
    def get_id(self):
        return str(self.id_usuario)

    def set_password(self, password):
        self.senha_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.senha_hash, password)

    @property
    def is_admin(self):
        return self.role == 'ADMIN'

    @property
    def is_cliente(self):
        return self.role == 'CLIENTE'


class Analise(db.Model):
    __tablename__ = 'analise'

    id_analise = db.Column(db.Integer, primary_key=True)
    id_empresa = db.Column(db.Integer, db.ForeignKey('empresa.id_empresa'), nullable=False)
    id_plano_referencia = db.Column(db.Integer, db.ForeignKey('plano.id_plano'), nullable=False)
    id_usuario_admin_responsavel = db.Column(db.Integer, db.ForeignKey('usuario.id_usuario'),
                                             nullable=False)
    periodo_inicio = db.Column(db.Date, nullable=False)
    periodo_fim = db.Column(db.Date, nullable=False)
    mes_referencia = db.Column(db.Integer, nullable=False)
    ano_referencia = db.Column(db.Integer, nullable=False)
    tipo_analise = db.Column(db.String(20), nullable=False)   # MENSAL, QUINZENAL
    quinzena_referencia = db.Column(db.Integer, nullable=True)  # NULL, 1 ou 2
    status_analise = db.Column(db.String(30), nullable=False, default='AGUARDANDO_RELATORIO')
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    data_atualizacao = db.Column(db.DateTime, default=datetime.utcnow,
                                 onupdate=datetime.utcnow, nullable=False)
    data_conclusao = db.Column(db.DateTime, nullable=True)

    empresa = db.relationship('Empresa', back_populates='analises')
    plano_referencia = db.relationship('Plano', foreign_keys=[id_plano_referencia],
                                       back_populates='analises')
    admin_responsavel = db.relationship(
        'Usuario', foreign_keys=[id_usuario_admin_responsavel],
        back_populates='analises_responsavel')
    uploads = db.relationship('UploadRelatorio', back_populates='analise', lazy='dynamic')
    indicadores = db.relationship('IndicadorAnalise', back_populates='analise', uselist=False)
    relatorio = db.relationship('RelatorioAnalise', back_populates='analise', uselist=False)

    __table_args__ = (
        CheckConstraint(
            "status_analise IN ('AGUARDANDO_RELATORIO','RELATORIO_RECEBIDO','EM_ANALISE','CONCLUIDO')",
            name='ck_analise_status'),
        CheckConstraint("tipo_analise IN ('MENSAL','QUINZENAL')", name='ck_analise_tipo'),
        CheckConstraint("mes_referencia BETWEEN 1 AND 12", name='ck_analise_mes'),
        CheckConstraint("periodo_fim >= periodo_inicio", name='ck_analise_periodo'),
        CheckConstraint(
            "(tipo_analise = 'MENSAL' AND quinzena_referencia IS NULL) OR "
            "(tipo_analise = 'QUINZENAL' AND quinzena_referencia IS NOT NULL "
            "AND quinzena_referencia IN (1, 2))",
            name='ck_analise_quinzena'),
        Index('ix_analise_id_empresa', 'id_empresa'),
        Index('ix_analise_id_plano', 'id_plano_referencia'),
        Index('ix_analise_id_admin', 'id_usuario_admin_responsavel'),
    )

    @property
    def periodo_label(self):
        MESES = ['Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun',
                 'Jul', 'Ago', 'Set', 'Out', 'Nov', 'Dez']
        mes = MESES[self.mes_referencia - 1] if 1 <= self.mes_referencia <= 12 else str(self.mes_referencia)
        if self.tipo_analise == 'QUINZENAL':
            return f"{mes}/{self.ano_referencia} – {self.quinzena_referencia}ª Quinzena"
        return f"{mes}/{self.ano_referencia}"


class UploadRelatorio(db.Model):
    __tablename__ = 'upload_relatorio'

    id_upload = db.Column(db.Integer, primary_key=True)
    id_analise = db.Column(db.Integer, db.ForeignKey('analise.id_analise'), nullable=False)
    id_usuario_admin = db.Column(db.Integer, db.ForeignKey('usuario.id_usuario'), nullable=False)
    tipo_relatorio = db.Column(db.String(10), nullable=False)   # VENDAS, COMPRAS
    nome_arquivo_original = db.Column(db.String(500), nullable=False)
    caminho_arquivo = db.Column(db.String(500), nullable=False)
    extensao_arquivo = db.Column(db.String(5), nullable=False)  # CSV, XLSX, XLS
    tamanho_arquivo = db.Column(db.Integer)
    hash_arquivo = db.Column(db.String(64))
    data_upload = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    status_processamento = db.Column(db.String(15), nullable=False, default='PENDENTE')
    data_processamento = db.Column(db.DateTime, nullable=True)
    mensagem_erro = db.Column(db.Text, nullable=True)

    analise = db.relationship('Analise', back_populates='uploads')
    admin_upload = db.relationship('Usuario', foreign_keys=[id_usuario_admin],
                                   back_populates='uploads')

    __table_args__ = (
        UniqueConstraint('id_analise', 'tipo_relatorio', name='uq_upload_analise_tipo'),
        CheckConstraint("tipo_relatorio IN ('VENDAS','COMPRAS')", name='ck_upload_tipo'),
        CheckConstraint("extensao_arquivo IN ('CSV','XLSX','XLS')", name='ck_upload_extensao'),
        CheckConstraint("status_processamento IN ('PENDENTE','PROCESSADO','ERRO')",
                        name='ck_upload_status'),
        Index('ix_upload_id_analise', 'id_analise'),
        Index('ix_upload_id_usuario', 'id_usuario_admin'),
    )


class IndicadorAnalise(db.Model):
    __tablename__ = 'indicador_analise'

    id_indicador = db.Column(db.Integer, primary_key=True)
    id_analise = db.Column(db.Integer, db.ForeignKey('analise.id_analise'),
                           nullable=False, unique=True)
    faturamento_total = db.Column(db.Numeric(15, 2))
    total_comprado = db.Column(db.Numeric(15, 2))
    # NULL quando não há custo confiável por produto
    saldo_estimado_compras_vendas = db.Column(db.Numeric(15, 2), nullable=True)
    produto_mais_vendido_nome = db.Column(db.String(500))
    produto_mais_vendido_quantidade = db.Column(db.Numeric(15, 3))
    produto_maior_faturamento_nome = db.Column(db.String(500))
    produto_maior_faturamento_valor = db.Column(db.Numeric(15, 2))
    produto_maior_saldo_parado_nome = db.Column(db.String(500))
    # Quantidade estimada parada (não valor monetário)
    saldo_estimado_parado = db.Column(db.Numeric(15, 3))
    versao_processamento = db.Column(db.Integer, default=1, nullable=False)
    data_geracao = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    analise = db.relationship('Analise', back_populates='indicadores')

    __table_args__ = (
        Index('ix_indicador_id_analise', 'id_analise'),
    )


class RelatorioAnalise(db.Model):
    __tablename__ = 'relatorio_analise'

    id_relatorio = db.Column(db.Integer, primary_key=True)
    id_analise = db.Column(db.Integer, db.ForeignKey('analise.id_analise'),
                           nullable=False, unique=True)
    id_usuario_admin_autor = db.Column(db.Integer, db.ForeignKey('usuario.id_usuario'),
                                       nullable=False)
    titulo = db.Column(db.String(300), nullable=False)
    resumo_executivo = db.Column(db.Text)
    pontos_positivos = db.Column(db.Text)
    pontos_de_alerta = db.Column(db.Text)
    recomendacoes = db.Column(db.Text)
    conclusao_estrategica = db.Column(db.Text, nullable=False)
    publicado = db.Column(db.Boolean, default=False, nullable=False)
    data_publicacao = db.Column(db.DateTime, nullable=True)
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    data_atualizacao = db.Column(db.DateTime, default=datetime.utcnow,
                                 onupdate=datetime.utcnow, nullable=False)

    analise = db.relationship('Analise', back_populates='relatorio')
    admin_autor = db.relationship('Usuario', foreign_keys=[id_usuario_admin_autor],
                                  back_populates='relatorios_autor')

    __table_args__ = (
        Index('ix_relatorio_id_analise', 'id_analise'),
        Index('ix_relatorio_id_autor', 'id_usuario_admin_autor'),
    )


class ChamadoSuporte(db.Model):
    __tablename__ = 'chamado_suporte'

    id_chamado = db.Column(db.Integer, primary_key=True)
    id_empresa = db.Column(db.Integer, db.ForeignKey('empresa.id_empresa'), nullable=False)
    id_usuario_cliente_autor = db.Column(db.Integer, db.ForeignKey('usuario.id_usuario'),
                                         nullable=False)
    assunto = db.Column(db.String(300), nullable=False)
    descricao = db.Column(db.Text, nullable=False)
    status_chamado = db.Column(db.String(15), nullable=False, default='ABERTO')
    prioridade_atendimento = db.Column(db.String(10), nullable=False)  # BAIXA, MEDIA, ALTA
    data_abertura = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    data_atualizacao = db.Column(db.DateTime, default=datetime.utcnow,
                                 onupdate=datetime.utcnow, nullable=False)
    data_fechamento = db.Column(db.DateTime, nullable=True)

    empresa = db.relationship('Empresa', back_populates='chamados')
    cliente_autor = db.relationship('Usuario', foreign_keys=[id_usuario_cliente_autor],
                                    back_populates='chamados_cliente')
    mensagens = db.relationship('MensagemSuporte', back_populates='chamado',
                                order_by='MensagemSuporte.data_envio', lazy='dynamic')

    __table_args__ = (
        CheckConstraint(
            "status_chamado IN ('ABERTO','EM_ANDAMENTO','RESPONDIDO','RESOLVIDO')",
            name='ck_chamado_status'),
        CheckConstraint("prioridade_atendimento IN ('BAIXA','MEDIA','ALTA')",
                        name='ck_chamado_prioridade'),
        CheckConstraint("length(trim(assunto)) > 0", name='ck_chamado_assunto'),
        CheckConstraint("length(trim(descricao)) > 0", name='ck_chamado_descricao'),
        Index('ix_chamado_id_empresa', 'id_empresa'),
        Index('ix_chamado_id_usuario', 'id_usuario_cliente_autor'),
        Index('idx_chamado_suporte_prioridade_atualizacao',
              'status_chamado', 'prioridade_atendimento', 'data_atualizacao'),
    )


class MensagemSuporte(db.Model):
    __tablename__ = 'mensagem_suporte'

    id_mensagem = db.Column(db.Integer, primary_key=True)
    id_chamado = db.Column(db.Integer, db.ForeignKey('chamado_suporte.id_chamado'),
                           nullable=False)
    id_usuario_autor = db.Column(db.Integer, db.ForeignKey('usuario.id_usuario'), nullable=False)
    conteudo = db.Column(db.Text, nullable=False)
    data_envio = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    chamado = db.relationship('ChamadoSuporte', back_populates='mensagens')
    autor = db.relationship('Usuario', foreign_keys=[id_usuario_autor], back_populates='mensagens')

    __table_args__ = (
        CheckConstraint("length(trim(conteudo)) > 0", name='ck_mensagem_conteudo'),
        Index('ix_mensagem_id_chamado', 'id_chamado'),
        Index('ix_mensagem_id_autor', 'id_usuario_autor'),
    )
