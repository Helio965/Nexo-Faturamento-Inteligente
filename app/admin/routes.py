import os
from datetime import datetime
from flask import (Blueprint, render_template, redirect, url_for, flash,
                   request, abort, current_app)
from flask_login import login_required, current_user
from sqlalchemy import case
from werkzeug.utils import secure_filename

from app import db
from app.models import (Plano, Segmento, Empresa, Usuario, Analise,
                         UploadRelatorio, IndicadorAnalise, RelatorioAnalise,
                         ChamadoSuporte, MensagemSuporte)
from app.etl.processor import processar, sha256_arquivo

admin_bp = Blueprint('admin', __name__)

EXTENSOES_PERMITIDAS = {'csv', 'xlsx', 'xls'}


def _requer_admin():
    if not current_user.is_authenticated or not current_user.is_admin:
        abort(403)


# ---------- Dashboard --------------------------------------------------------

@admin_bp.route('/')
@login_required
def dashboard():
    _requer_admin()
    total_empresas = Empresa.query.count()
    total_ativas = Empresa.query.filter_by(status_conta='ATIVA').count()
    analises_pendentes = Analise.query.filter(
        Analise.status_analise.in_(['AGUARDANDO_RELATORIO', 'RELATORIO_RECEBIDO', 'EM_ANALISE'])
    ).count()
    tickets_abertos = ChamadoSuporte.query.filter(
        ChamadoSuporte.status_chamado.in_(['ABERTO', 'EM_ANDAMENTO'])
    ).count()

    analises_recentes = (Analise.query
                         .order_by(Analise.data_criacao.desc())
                         .limit(5).all())
    tickets_recentes = (ChamadoSuporte.query
                        .order_by(ChamadoSuporte.data_criacao.desc())
                        .limit(5).all())

    return render_template('admin/dashboard.html',
                           total_empresas=total_empresas,
                           total_ativas=total_ativas,
                           analises_pendentes=analises_pendentes,
                           tickets_abertos=tickets_abertos,
                           analises_recentes=analises_recentes,
                           tickets_recentes=tickets_recentes)


# ---------- Empresas ---------------------------------------------------------

@admin_bp.route('/empresas')
@login_required
def empresas():
    _requer_admin()
    lista = Empresa.query.order_by(Empresa.nome_fantasia).all()
    return render_template('admin/empresas.html', empresas=lista)


@admin_bp.route('/empresa/nova', methods=['GET', 'POST'])
@login_required
def empresa_nova():
    _requer_admin()
    planos = Plano.query.filter_by(ativo=True).all()
    segmentos = Segmento.query.order_by(Segmento.nome_segmento).all()

    if request.method == 'POST':
        nome_fantasia = request.form.get('nome_fantasia', '').strip()
        razao_social = request.form.get('razao_social', '').strip()
        cnpj = request.form.get('cnpj', '').strip() or None
        email_contato = request.form.get('email_contato', '').strip() or None
        id_plano = request.form.get('id_plano_atual')
        id_segmento = request.form.get('id_segmento') or None

        if not nome_fantasia or not id_plano:
            flash('Nome fantasia e plano são obrigatórios.', 'danger')
            return render_template('admin/empresa_form.html', planos=planos,
                                   segmentos=segmentos, empresa=None)

        empresa = Empresa(
            nome_fantasia=nome_fantasia,
            razao_social=razao_social or None,
            cnpj=cnpj,
            email_contato=email_contato,
            id_plano_atual=int(id_plano),
            id_segmento=int(id_segmento) if id_segmento else None,
            status_conta='ATIVA',
        )
        db.session.add(empresa)
        db.session.commit()
        flash(f'Empresa "{empresa.nome_fantasia}" criada com sucesso.', 'success')
        return redirect(url_for('admin.empresa_detalhe', id=empresa.id))

    return render_template('admin/empresa_form.html', planos=planos,
                           segmentos=segmentos, empresa=None)


@admin_bp.route('/empresa/<int:id>')
@login_required
def empresa_detalhe(id):
    _requer_admin()
    empresa = Empresa.query.get_or_404(id)
    usuarios = empresa.usuarios.all()
    analises = (empresa.analises
                .order_by(Analise.ano_referencia.desc(), Analise.mes_referencia.desc())
                .all())
    return render_template('admin/empresa_detalhe.html',
                           empresa=empresa, usuarios=usuarios, analises=analises)


@admin_bp.route('/empresa/<int:id>/editar', methods=['GET', 'POST'])
@login_required
def empresa_editar(id):
    _requer_admin()
    empresa = Empresa.query.get_or_404(id)
    planos = Plano.query.filter_by(ativo=True).all()
    segmentos = Segmento.query.order_by(Segmento.nome_segmento).all()

    if request.method == 'POST':
        empresa.nome_fantasia = request.form.get('nome_fantasia', '').strip()
        empresa.razao_social = request.form.get('razao_social', '').strip() or None
        empresa.cnpj = request.form.get('cnpj', '').strip() or None
        empresa.email_contato = request.form.get('email_contato', '').strip() or None
        empresa.id_plano_atual = int(request.form.get('id_plano_atual'))
        id_seg = request.form.get('id_segmento')
        empresa.id_segmento = int(id_seg) if id_seg else None
        empresa.status_conta = request.form.get('status_conta', 'ATIVA')

        db.session.commit()
        flash('Empresa atualizada.', 'success')
        return redirect(url_for('admin.empresa_detalhe', id=empresa.id))

    return render_template('admin/empresa_form.html', planos=planos,
                           segmentos=segmentos, empresa=empresa)


# ---------- Usuários CLIENTE -------------------------------------------------

@admin_bp.route('/empresa/<int:id_empresa>/usuario/novo', methods=['GET', 'POST'])
@login_required
def usuario_novo(id_empresa):
    _requer_admin()
    empresa = Empresa.query.get_or_404(id_empresa)

    if request.method == 'POST':
        nome = request.form.get('nome', '').strip()
        email = request.form.get('email', '').strip().lower()
        senha = request.form.get('senha', '')

        if not nome or not email or not senha:
            flash('Todos os campos são obrigatórios.', 'danger')
            return render_template('admin/usuario_form.html', empresa=empresa)

        if Usuario.query.filter_by(email=email).first():
            flash('E-mail já cadastrado.', 'danger')
            return render_template('admin/usuario_form.html', empresa=empresa)

        u = Usuario(nome=nome, email=email, role='CLIENTE', id_empresa=empresa.id)
        u.set_password(senha)
        db.session.add(u)
        db.session.commit()
        flash(f'Usuário "{u.nome}" criado.', 'success')
        return redirect(url_for('admin.empresa_detalhe', id=empresa.id))

    return render_template('admin/usuario_form.html', empresa=empresa)


@admin_bp.route('/usuario/<int:id>/toggle', methods=['POST'])
@login_required
def usuario_toggle(id):
    _requer_admin()
    u = Usuario.query.get_or_404(id)
    if u.is_admin:
        flash('Não é possível desativar um administrador por aqui.', 'warning')
        return redirect(url_for('admin.dashboard'))
    u.ativo = not u.ativo
    db.session.commit()
    estado = 'ativado' if u.ativo else 'desativado'
    flash(f'Usuário {estado}.', 'success')
    return redirect(url_for('admin.empresa_detalhe', id=u.id_empresa))


# ---------- Análises ---------------------------------------------------------

@admin_bp.route('/analises')
@login_required
def analises():
    _requer_admin()
    lista = (Analise.query
             .order_by(Analise.data_criacao.desc())
             .all())
    return render_template('admin/analises.html', analises=lista)


@admin_bp.route('/analise/nova', methods=['GET', 'POST'])
@login_required
def analise_nova():
    _requer_admin()
    empresas_ativas = Empresa.query.filter_by(status_conta='ATIVA').order_by(Empresa.nome_fantasia).all()

    if request.method == 'POST':
        id_empresa = request.form.get('id_empresa')
        tipo_analise = request.form.get('tipo_analise', 'MENSAL')
        mes = request.form.get('mes_referencia')
        ano = request.form.get('ano_referencia')
        quinzena = request.form.get('quinzena_referencia') or None

        if not id_empresa or not mes or not ano:
            flash('Empresa, mês e ano são obrigatórios.', 'danger')
            return render_template('admin/analise_form.html', empresas=empresas_ativas,
                                   now=datetime.utcnow())

        empresa = Empresa.query.get_or_404(int(id_empresa))

        if empresa.status_conta != 'ATIVA':
            flash('Empresa precisa estar ATIVA para receber análise.', 'danger')
            return render_template('admin/analise_form.html', empresas=empresas_ativas,
                                   now=datetime.utcnow())

        if tipo_analise == 'QUINZENAL' and empresa.plano_atual.nome_plano != 'OURO':
            flash('Análise quinzenal é exclusiva para empresas com plano OURO.', 'danger')
            return render_template('admin/analise_form.html', empresas=empresas_ativas,
                                   now=datetime.utcnow())

        quinzena_int = int(quinzena) if quinzena and tipo_analise == 'QUINZENAL' else None

        analise = Analise(
            id_empresa=empresa.id,
            id_plano_referencia=empresa.id_plano_atual,
            id_usuario_admin_responsavel=current_user.id,
            tipo_analise=tipo_analise,
            mes_referencia=int(mes),
            ano_referencia=int(ano),
            quinzena_referencia=quinzena_int,
            status_analise='AGUARDANDO_RELATORIO',
        )
        db.session.add(analise)
        db.session.commit()
        flash('Análise criada. Faça o upload dos relatórios.', 'success')
        return redirect(url_for('admin.analise_detalhe', id=analise.id))

    return render_template('admin/analise_form.html', empresas=empresas_ativas,
                           now=datetime.utcnow())


@admin_bp.route('/analise/<int:id>')
@login_required
def analise_detalhe(id):
    _requer_admin()
    analise = Analise.query.get_or_404(id)
    upload_vendas = UploadRelatorio.query.filter_by(
        id_analise=id, tipo_relatorio='VENDAS').first()
    upload_compras = UploadRelatorio.query.filter_by(
        id_analise=id, tipo_relatorio='COMPRAS').first()
    return render_template('admin/analise_detalhe.html',
                           analise=analise,
                           upload_vendas=upload_vendas,
                           upload_compras=upload_compras)


@admin_bp.route('/analise/<int:id>/upload', methods=['POST'])
@login_required
def analise_upload(id):
    _requer_admin()
    analise = Analise.query.get_or_404(id)

    if analise.status_analise in ('EM_ANALISE', 'CONCLUIDO'):
        flash('Não é possível fazer upload em análise em processamento ou concluída.', 'warning')
        return redirect(url_for('admin.analise_detalhe', id=id))

    tipo = request.form.get('tipo_relatorio', '').upper()
    if tipo not in ('VENDAS', 'COMPRAS'):
        flash('Tipo de relatório inválido.', 'danger')
        return redirect(url_for('admin.analise_detalhe', id=id))

    arquivo = request.files.get('arquivo')
    if not arquivo or arquivo.filename == '':
        flash('Nenhum arquivo selecionado.', 'danger')
        return redirect(url_for('admin.analise_detalhe', id=id))

    nome_original = arquivo.filename
    ext = nome_original.rsplit('.', 1)[-1].lower() if '.' in nome_original else ''
    if ext not in EXTENSOES_PERMITIDAS:
        flash('Extensão inválida. Use CSV, XLSX ou XLS.', 'danger')
        return redirect(url_for('admin.analise_detalhe', id=id))

    ext_upper = ext.upper()

    # Substituir upload anterior do mesmo tipo
    upload_existente = UploadRelatorio.query.filter_by(
        id_analise=id, tipo_relatorio=tipo).first()
    if upload_existente:
        try:
            os.remove(upload_existente.caminho_arquivo)
        except FileNotFoundError:
            pass
        db.session.delete(upload_existente)
        db.session.flush()

    nome_seguro = secure_filename(nome_original)
    nome_salvo = f"analise{id}_{tipo}_{nome_seguro}"
    caminho = os.path.join(current_app.config['UPLOAD_FOLDER'], nome_salvo)
    arquivo.save(caminho)

    tamanho = os.path.getsize(caminho)
    hash_sha = sha256_arquivo(caminho)

    upload = UploadRelatorio(
        id_analise=id,
        id_usuario_admin=current_user.id,
        tipo_relatorio=tipo,
        nome_arquivo_original=nome_original,
        extensao_arquivo=ext_upper,
        caminho_arquivo=caminho,
        tamanho_bytes=tamanho,
        hash_sha256=hash_sha,
        status_processamento='PENDENTE',
    )
    db.session.add(upload)

    # Verifica se ambos os uploads existem → muda para RELATORIO_RECEBIDO
    outro_tipo = 'COMPRAS' if tipo == 'VENDAS' else 'VENDAS'
    outro_upload = UploadRelatorio.query.filter_by(
        id_analise=id, tipo_relatorio=outro_tipo).first()
    if outro_upload:
        analise.status_analise = 'RELATORIO_RECEBIDO'

    db.session.commit()
    flash(f'Relatório de {tipo} enviado com sucesso.', 'success')
    return redirect(url_for('admin.analise_detalhe', id=id))


@admin_bp.route('/analise/<int:id>/processar', methods=['POST'])
@login_required
def analise_processar(id):
    """Processamento exclusivamente via POST. Nunca via GET."""
    _requer_admin()
    analise = Analise.query.get_or_404(id)

    if analise.status_analise == 'CONCLUIDO':
        flash('Análise publicada. Despublique antes de reprocessar.', 'warning')
        return redirect(url_for('admin.analise_detalhe', id=id))

    if analise.status_analise != 'RELATORIO_RECEBIDO':
        flash('Análise precisa estar em RELATORIO_RECEBIDO para processar.', 'warning')
        return redirect(url_for('admin.analise_detalhe', id=id))

    upload_vendas = UploadRelatorio.query.filter_by(
        id_analise=id, tipo_relatorio='VENDAS').first()
    upload_compras = UploadRelatorio.query.filter_by(
        id_analise=id, tipo_relatorio='COMPRAS').first()

    if not upload_vendas or not upload_compras:
        flash('Ambos os relatórios (VENDAS e COMPRAS) são necessários.', 'danger')
        return redirect(url_for('admin.analise_detalhe', id=id))

    analise.status_analise = 'EM_ANALISE'
    db.session.commit()

    try:
        resultado = processar(analise, upload_vendas, upload_compras)

        indicador = IndicadorAnalise.query.filter_by(id_analise=id).first()
        if indicador:
            for k, v in resultado.items():
                setattr(indicador, k, v)
        else:
            indicador = IndicadorAnalise(id_analise=id, **resultado)
            db.session.add(indicador)

        upload_vendas.status_processamento = 'PROCESSADO'
        upload_compras.status_processamento = 'PROCESSADO'
        db.session.commit()
        flash('Processamento concluído. KPIs gerados.', 'success')
    except Exception as exc:
        db.session.rollback()
        analise.status_analise = 'RELATORIO_RECEBIDO'
        upload_vendas.status_processamento = 'ERRO'
        upload_compras.status_processamento = 'ERRO'
        db.session.commit()
        flash(f'Erro no processamento: {exc}', 'danger')

    return redirect(url_for('admin.analise_detalhe', id=id))


# ---------- Relatório estratégico --------------------------------------------

@admin_bp.route('/analise/<int:id>/relatorio', methods=['GET', 'POST'])
@login_required
def relatorio_editar(id):
    _requer_admin()
    analise = Analise.query.get_or_404(id)

    if analise.status_analise not in ('EM_ANALISE', 'CONCLUIDO'):
        flash('A análise precisa ser processada antes de redigir o relatório.', 'warning')
        return redirect(url_for('admin.analise_detalhe', id=id))

    relatorio = analise.relatorio

    if request.method == 'POST':
        titulo = request.form.get('titulo', '').strip()
        conclusao = request.form.get('conclusao_estrategica', '').strip()

        if not titulo or not conclusao:
            flash('Título e conclusão estratégica são obrigatórios.', 'danger')
            return render_template('admin/relatorio_form.html',
                                   analise=analise, relatorio=relatorio)

        if relatorio:
            relatorio.titulo = titulo
            relatorio.resumo_executivo = request.form.get('resumo_executivo', '').strip() or None
            relatorio.pontos_positivos = request.form.get('pontos_positivos', '').strip() or None
            relatorio.pontos_de_alerta = request.form.get('pontos_de_alerta', '').strip() or None
            relatorio.recomendacoes = request.form.get('recomendacoes', '').strip() or None
            relatorio.conclusao_estrategica = conclusao
            relatorio.data_atualizacao = datetime.utcnow()
        else:
            relatorio = RelatorioAnalise(
                id_analise=id,
                id_usuario_admin_autor=current_user.id,
                titulo=titulo,
                resumo_executivo=request.form.get('resumo_executivo', '').strip() or None,
                pontos_positivos=request.form.get('pontos_positivos', '').strip() or None,
                pontos_de_alerta=request.form.get('pontos_de_alerta', '').strip() or None,
                recomendacoes=request.form.get('recomendacoes', '').strip() or None,
                conclusao_estrategica=conclusao,
                publicado=False,
            )
            db.session.add(relatorio)

        db.session.commit()
        flash('Relatório salvo como rascunho.', 'success')
        return redirect(url_for('admin.analise_detalhe', id=id))

    return render_template('admin/relatorio_form.html',
                           analise=analise, relatorio=relatorio)


@admin_bp.route('/analise/<int:id>/publicar', methods=['POST'])
@login_required
def analise_publicar(id):
    _requer_admin()
    analise = Analise.query.get_or_404(id)
    relatorio = analise.relatorio

    if not relatorio:
        flash('Crie o relatório estratégico antes de publicar.', 'warning')
        return redirect(url_for('admin.analise_detalhe', id=id))

    relatorio.publicado = True
    relatorio.data_publicacao = datetime.utcnow()
    analise.status_analise = 'CONCLUIDO'
    analise.data_conclusao = datetime.utcnow()
    db.session.commit()
    flash('Análise publicada para o cliente.', 'success')
    return redirect(url_for('admin.analise_detalhe', id=id))


@admin_bp.route('/analise/<int:id>/despublicar', methods=['POST'])
@login_required
def analise_despublicar(id):
    _requer_admin()
    analise = Analise.query.get_or_404(id)
    relatorio = analise.relatorio

    if relatorio:
        relatorio.publicado = False
        relatorio.data_publicacao = None

    analise.status_analise = 'EM_ANALISE'
    analise.data_conclusao = None
    db.session.commit()
    flash('Análise despublicada. Status voltou para EM_ANALISE.', 'info')
    return redirect(url_for('admin.analise_detalhe', id=id))


# ---------- Tickets (painel admin) -------------------------------------------

@admin_bp.route('/tickets')
@login_required
def tickets():
    _requer_admin()
    aba = request.args.get('aba', 'ativos')
    busca = request.args.get('q', '').strip()

    # Ordenação explícita por prioridade: ALTA > MEDIA > BAIXA
    ordem_prioridade = case(
        (ChamadoSuporte.prioridade_atendimento == 'ALTA', 1),
        (ChamadoSuporte.prioridade_atendimento == 'MEDIA', 2),
        (ChamadoSuporte.prioridade_atendimento == 'BAIXA', 3),
        else_=4
    )

    query = ChamadoSuporte.query

    if busca:
        query = query.join(Empresa).filter(
            db.or_(
                ChamadoSuporte.assunto.ilike(f'%{busca}%'),
                Empresa.nome_fantasia.ilike(f'%{busca}%'),
            )
        )

    if aba == 'arquivados':
        query = query.filter(ChamadoSuporte.status_chamado == 'RESOLVIDO')
    else:
        query = query.filter(ChamadoSuporte.status_chamado != 'RESOLVIDO')

    tickets_lista = query.order_by(ordem_prioridade, ChamadoSuporte.data_criacao).all()

    return render_template('admin/tickets.html',
                           tickets=tickets_lista, aba=aba, busca=busca)


@admin_bp.route('/ticket/<int:id>')
@login_required
def ticket_detalhe(id):
    _requer_admin()
    chamado = ChamadoSuporte.query.get_or_404(id)
    mensagens = chamado.mensagens.all()
    return render_template('admin/ticket_detalhe.html',
                           chamado=chamado, mensagens=mensagens)


@admin_bp.route('/ticket/<int:id>/mensagem', methods=['POST'])
@login_required
def ticket_mensagem(id):
    _requer_admin()
    chamado = ChamadoSuporte.query.get_or_404(id)
    conteudo = request.form.get('conteudo', '').strip()

    if not conteudo:
        flash('Mensagem não pode ser vazia.', 'danger')
        return redirect(url_for('admin.ticket_detalhe', id=id))

    mensagem = MensagemSuporte(
        id_chamado=id,
        id_usuario_autor=current_user.id,
        conteudo=conteudo,
    )
    db.session.add(mensagem)
    chamado.data_atualizacao = datetime.utcnow()
    db.session.commit()
    flash('Resposta enviada.', 'success')
    return redirect(url_for('admin.ticket_detalhe', id=id))


@admin_bp.route('/ticket/<int:id>/status', methods=['POST'])
@login_required
def ticket_status(id):
    _requer_admin()
    chamado = ChamadoSuporte.query.get_or_404(id)
    novo_status = request.form.get('status_chamado', '').upper()

    STATUS_VALIDOS = ('ABERTO', 'EM_ANDAMENTO', 'RESPONDIDO', 'RESOLVIDO')
    if novo_status not in STATUS_VALIDOS:
        flash('Status inválido.', 'danger')
        return redirect(url_for('admin.ticket_detalhe', id=id))

    chamado.status_chamado = novo_status
    chamado.data_atualizacao = datetime.utcnow()
    db.session.commit()
    flash(f'Status atualizado para {novo_status}.', 'success')
    return redirect(url_for('admin.ticket_detalhe', id=id))
