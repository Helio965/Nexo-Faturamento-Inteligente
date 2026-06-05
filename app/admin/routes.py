import os
from datetime import datetime, date
from calendar import monthrange
from flask import (Blueprint, render_template, redirect, url_for, flash,
                   request, abort, current_app)
from flask_login import login_required, current_user
from sqlalchemy import case, or_, desc, func
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


def _empresa_ativa(analise):
    """Entrega ao CLIENTE (upload/processamento/publicação) exige empresa ATIVA."""
    return analise.empresa.status_conta == 'ATIVA'


def _periodo_analise(mes, ano, tipo, quinzena):
    """Calcula periodo_inicio e periodo_fim conforme tipo e quinzena."""
    if tipo == 'QUINZENAL':
        if quinzena == 1:
            inicio = date(ano, mes, 1)
            fim = date(ano, mes, 15)
        else:
            inicio = date(ano, mes, 16)
            fim = date(ano, mes, monthrange(ano, mes)[1])
    else:
        inicio = date(ano, mes, 1)
        fim = date(ano, mes, monthrange(ano, mes)[1])
    return inicio, fim


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
        ChamadoSuporte.status_chamado.in_(['ABERTO', 'EM_ANDAMENTO', 'RESPONDIDO'])
    ).count()

    # Indicadores operacionais — empresas por status_conta
    empresas_por_status = {
        'ATIVA': total_ativas,
        'SUSPENSA': Empresa.query.filter_by(status_conta='SUSPENSA').count(),
        'CANCELADA': Empresa.query.filter_by(status_conta='CANCELADA').count(),
    }

    # Indicadores operacionais — empresas por plano
    contagem_planos = dict(
        db.session.query(Plano.nome_plano, func.count(Empresa.id_empresa))
        .outerjoin(Empresa, Empresa.id_plano_atual == Plano.id_plano)
        .group_by(Plano.nome_plano).all()
    )
    empresas_por_plano = {
        'BRONZE': contagem_planos.get('BRONZE', 0),
        'PRATA': contagem_planos.get('PRATA', 0),
        'OURO': contagem_planos.get('OURO', 0),
    }

    # Receita estimada mensal — soma de valor_mensal apenas de empresas ATIVAS.
    # Não é cobrança/faturamento real; é uma estimativa operacional.
    receita_estimada_mensal = (
        db.session.query(func.coalesce(func.sum(Plano.valor_mensal), 0))
        .join(Empresa, Empresa.id_plano_atual == Plano.id_plano)
        .filter(Empresa.status_conta == 'ATIVA')
        .scalar()
    )

    analises_recentes = (Analise.query
                         .order_by(Analise.data_criacao.desc())
                         .limit(5).all())
    tickets_recentes = (ChamadoSuporte.query
                        .order_by(ChamadoSuporte.data_abertura.desc())
                        .limit(5).all())

    return render_template('admin/dashboard.html',
                           total_empresas=total_empresas,
                           total_ativas=total_ativas,
                           analises_pendentes=analises_pendentes,
                           tickets_abertos=tickets_abertos,
                           empresas_por_status=empresas_por_status,
                           empresas_por_plano=empresas_por_plano,
                           receita_estimada_mensal=receita_estimada_mensal,
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
    segmentos = Segmento.query.filter_by(ativo=True).order_by(Segmento.nome_segmento).all()

    if request.method == 'POST':
        nome_fantasia = request.form.get('nome_fantasia', '').strip() or None
        razao_social = request.form.get('razao_social', '').strip()
        cnpj = request.form.get('cnpj', '').strip()
        email_contato = request.form.get('email_contato', '').strip()
        telefone_contato = request.form.get('telefone_contato', '').strip() or None
        id_plano = request.form.get('id_plano_atual')
        id_segmento = request.form.get('id_segmento')
        fat_base = request.form.get('faturamento_base_mensal', '').strip() or None
        data_contratacao_str = request.form.get('data_contratacao', '').strip()

        # Campos obrigatórios conforme DER V4.1
        if not (razao_social and cnpj and email_contato and id_plano
                and id_segmento and data_contratacao_str):
            flash('Razão social, CNPJ, e-mail, segmento, plano e data de '
                  'contratação são obrigatórios.', 'danger')
            return render_template('admin/empresa_form.html', planos=planos,
                                   segmentos=segmentos, empresa=None)

        try:
            data_contratacao = datetime.strptime(data_contratacao_str, '%Y-%m-%d').date()
        except ValueError:
            flash('Data de contratação inválida.', 'danger')
            return render_template('admin/empresa_form.html', planos=planos,
                                   segmentos=segmentos, empresa=None)

        empresa = Empresa(
            nome_fantasia=nome_fantasia,
            razao_social=razao_social,
            cnpj=cnpj,
            email_contato=email_contato,
            telefone_contato=telefone_contato,
            id_plano_atual=int(id_plano),
            id_segmento=int(id_segmento),
            faturamento_base_mensal=float(fat_base) if fat_base else None,
            data_contratacao=data_contratacao,
            status_conta='ATIVA',
        )
        db.session.add(empresa)
        db.session.commit()
        nome_exib = empresa.nome_fantasia or empresa.razao_social
        flash(f'Empresa "{nome_exib}" criada com sucesso.', 'success')
        return redirect(url_for('admin.empresa_detalhe', id=empresa.id_empresa))

    return render_template('admin/empresa_form.html', planos=planos,
                           segmentos=segmentos, empresa=None)


@admin_bp.route('/empresa/<int:id>')
@login_required
def empresa_detalhe(id):
    _requer_admin()
    empresa = db.session.get(Empresa, id) or abort(404)
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
    empresa = db.session.get(Empresa, id) or abort(404)
    planos = Plano.query.filter_by(ativo=True).all()
    segmentos = Segmento.query.filter_by(ativo=True).order_by(Segmento.nome_segmento).all()

    if request.method == 'POST':
        razao_social = request.form.get('razao_social', '').strip()
        cnpj = request.form.get('cnpj', '').strip()
        email_contato = request.form.get('email_contato', '').strip()
        id_plano = request.form.get('id_plano_atual')
        id_seg = request.form.get('id_segmento')
        data_contratacao_str = request.form.get('data_contratacao', '').strip()

        # Campos obrigatórios conforme DER V4.1
        if not (razao_social and cnpj and email_contato and id_plano
                and id_seg and data_contratacao_str):
            flash('Razão social, CNPJ, e-mail, segmento, plano e data de '
                  'contratação são obrigatórios.', 'danger')
            return render_template('admin/empresa_form.html', planos=planos,
                                   segmentos=segmentos, empresa=empresa)

        try:
            data_contratacao = datetime.strptime(data_contratacao_str, '%Y-%m-%d').date()
        except ValueError:
            flash('Data de contratação inválida.', 'danger')
            return render_template('admin/empresa_form.html', planos=planos,
                                   segmentos=segmentos, empresa=empresa)

        novo_status = request.form.get('status_conta', 'ATIVA')
        novo_plano = int(id_plano)
        # Empresa CANCELADA não pode trocar de plano enquanto continuar cancelada.
        # A troca só é liberada se for acompanhada de reativação (novo_status != CANCELADA).
        if (empresa.status_conta == 'CANCELADA' and novo_status == 'CANCELADA'
                and novo_plano != empresa.id_plano_atual):
            flash('Empresa CANCELADA não pode ter plano alterado. Reative a '
                  'empresa antes de alterar o plano.', 'danger')
            return render_template('admin/empresa_form.html', planos=planos,
                                   segmentos=segmentos, empresa=empresa)

        empresa.nome_fantasia = request.form.get('nome_fantasia', '').strip() or None
        empresa.razao_social = razao_social
        empresa.cnpj = cnpj
        empresa.email_contato = email_contato
        empresa.telefone_contato = request.form.get('telefone_contato', '').strip() or None
        empresa.id_plano_atual = novo_plano
        empresa.id_segmento = int(id_seg)
        empresa.status_conta = novo_status
        fat_base = request.form.get('faturamento_base_mensal', '').strip()
        empresa.faturamento_base_mensal = float(fat_base) if fat_base else None
        empresa.data_contratacao = data_contratacao

        db.session.commit()
        flash('Empresa atualizada.', 'success')
        return redirect(url_for('admin.empresa_detalhe', id=empresa.id_empresa))

    return render_template('admin/empresa_form.html', planos=planos,
                           segmentos=segmentos, empresa=empresa)


# ---------- Usuários CLIENTE -------------------------------------------------

@admin_bp.route('/empresa/<int:id_empresa>/usuario/novo', methods=['GET', 'POST'])
@login_required
def usuario_novo(id_empresa):
    _requer_admin()
    empresa = db.session.get(Empresa, id_empresa) or abort(404)

    # Empresa CANCELADA não recebe novos acessos de cliente.
    if empresa.status_conta == 'CANCELADA':
        flash('Não é permitido cadastrar novo CLIENTE para empresa CANCELADA.', 'danger')
        return redirect(url_for('admin.empresa_detalhe', id=empresa.id_empresa))

    if request.method == 'POST':
        nome = request.form.get('nome', '').strip()
        email = request.form.get('email', '').strip().lower()
        senha = request.form.get('senha', '')

        if not nome or not email or not senha:
            flash('Todos os campos são obrigatórios.', 'danger')
            return render_template('admin/usuario_form.html', empresa=empresa)

        # Regra PI2: no máximo um usuário CLIENTE ativo por empresa.
        cliente_ativo = Usuario.query.filter_by(
            id_empresa=empresa.id_empresa, role='CLIENTE', ativo=True).first()
        if cliente_ativo:
            flash('Esta empresa já possui um usuário CLIENTE ativo. Desative o '
                  'usuário atual antes de cadastrar outro responsável.', 'danger')
            return render_template('admin/usuario_form.html', empresa=empresa)

        if Usuario.query.filter_by(email=email).first():
            flash('E-mail já cadastrado.', 'danger')
            return render_template('admin/usuario_form.html', empresa=empresa)

        u = Usuario(nome=nome, email=email, role='CLIENTE',
                    id_empresa=empresa.id_empresa)
        u.set_password(senha)
        db.session.add(u)
        db.session.commit()
        flash(f'Usuário "{u.nome}" criado.', 'success')
        return redirect(url_for('admin.empresa_detalhe', id=empresa.id_empresa))

    return render_template('admin/usuario_form.html', empresa=empresa)


@admin_bp.route('/usuario/<int:id>/toggle', methods=['POST'])
@login_required
def usuario_toggle(id):
    _requer_admin()
    u = db.session.get(Usuario, id) or abort(404)
    if u.is_admin:
        flash('Não é possível desativar um administrador por aqui.', 'warning')
        return redirect(url_for('admin.dashboard'))

    vai_ativar = not u.ativo
    # Reativação de CLIENTE precisa respeitar as mesmas regras da criação:
    # empresa não CANCELADA e no máximo um CLIENTE ativo por empresa.
    if vai_ativar and u.role == 'CLIENTE':
        if u.empresa and u.empresa.status_conta == 'CANCELADA':
            flash('Não é possível reativar CLIENTE de empresa CANCELADA.', 'danger')
            return redirect(url_for('admin.empresa_detalhe', id=u.id_empresa))
        outro_ativo = Usuario.query.filter(
            Usuario.id_empresa == u.id_empresa,
            Usuario.role == 'CLIENTE',
            Usuario.ativo.is_(True),
            Usuario.id_usuario != u.id_usuario).first()
        if outro_ativo:
            flash('Esta empresa já possui outro usuário CLIENTE ativo. Desative '
                  'o usuário atual antes de reativar este.', 'danger')
            return redirect(url_for('admin.empresa_detalhe', id=u.id_empresa))

    u.ativo = vai_ativar
    db.session.commit()
    estado = 'ativado' if u.ativo else 'desativado'
    flash(f'Usuário {estado}.', 'success')
    return redirect(url_for('admin.empresa_detalhe', id=u.id_empresa))


# ---------- Análises ---------------------------------------------------------

@admin_bp.route('/analises')
@login_required
def analises():
    _requer_admin()
    lista = (Analise.query.order_by(Analise.data_criacao.desc()).all())
    return render_template('admin/analises.html', analises=lista)


@admin_bp.route('/analise/nova', methods=['GET', 'POST'])
@login_required
def analise_nova():
    _requer_admin()
    empresas_ativas = (Empresa.query.filter_by(status_conta='ATIVA')
                       .order_by(Empresa.nome_fantasia).all())

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

        empresa = db.session.get(Empresa, int(id_empresa)) or abort(404)

        if empresa.status_conta != 'ATIVA':
            flash('Empresa precisa estar ATIVA para receber análise.', 'danger')
            return render_template('admin/analise_form.html', empresas=empresas_ativas,
                                   now=datetime.utcnow())

        if tipo_analise == 'QUINZENAL' and empresa.plano_atual.nome_plano != 'OURO':
            flash('Análise quinzenal é exclusiva para empresas com plano OURO.', 'danger')
            return render_template('admin/analise_form.html', empresas=empresas_ativas,
                                   now=datetime.utcnow())

        mes_i = int(mes)
        ano_i = int(ano)
        quinzena_int = int(quinzena) if quinzena and tipo_analise == 'QUINZENAL' else None
        p_inicio, p_fim = _periodo_analise(mes_i, ano_i, tipo_analise, quinzena_int)

        analise = Analise(
            id_empresa=empresa.id_empresa,
            id_plano_referencia=empresa.id_plano_atual,
            id_usuario_admin_responsavel=current_user.id_usuario,
            tipo_analise=tipo_analise,
            mes_referencia=mes_i,
            ano_referencia=ano_i,
            quinzena_referencia=quinzena_int,
            periodo_inicio=p_inicio,
            periodo_fim=p_fim,
            status_analise='AGUARDANDO_RELATORIO',
        )
        db.session.add(analise)
        db.session.commit()
        flash('Análise criada. Faça o upload dos relatórios.', 'success')
        return redirect(url_for('admin.analise_detalhe', id=analise.id_analise))

    return render_template('admin/analise_form.html', empresas=empresas_ativas,
                           now=datetime.utcnow())


@admin_bp.route('/analise/<int:id>')
@login_required
def analise_detalhe(id):
    _requer_admin()
    analise = db.session.get(Analise, id) or abort(404)
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
    analise = db.session.get(Analise, id) or abort(404)

    if not _empresa_ativa(analise):
        flash('Não é possível enviar relatórios para empresa que não está ATIVA.', 'warning')
        return redirect(url_for('admin.analise_detalhe', id=id))

    # Relatório publicado precisa ser despublicado antes de receber novos arquivos.
    if analise.relatorio and analise.relatorio.publicado:
        flash('Despublique o relatório antes de enviar novos arquivos.', 'warning')
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

    # Re-upload: remove anterior
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
    hash_arq = sha256_arquivo(caminho)

    upload = UploadRelatorio(
        id_analise=id,
        id_usuario_admin=current_user.id_usuario,
        tipo_relatorio=tipo,
        nome_arquivo_original=nome_original,
        extensao_arquivo=ext_upper,
        caminho_arquivo=caminho,
        tamanho_arquivo=tamanho,
        hash_arquivo=hash_arq,
        status_processamento='PENDENTE',
    )
    db.session.add(upload)

    # Ambos os uploads presentes → RELATORIO_RECEBIDO
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
    analise = db.session.get(Analise, id) or abort(404)

    if not _empresa_ativa(analise):
        flash('Não é possível processar análise de empresa que não está ATIVA.', 'warning')
        return redirect(url_for('admin.analise_detalhe', id=id))

    # Relatório publicado bloqueia (re)processamento até despublicar.
    if (analise.relatorio and analise.relatorio.publicado) or analise.status_analise == 'CONCLUIDO':
        flash('Despublique o relatório antes de reprocessar a análise.', 'warning')
        return redirect(url_for('admin.analise_detalhe', id=id))

    # Processamento inicial em RELATORIO_RECEBIDO; reprocessamento após
    # despublicação ocorre em EM_ANALISE (a despublicação volta para esse status).
    if analise.status_analise not in ('RELATORIO_RECEBIDO', 'EM_ANALISE'):
        flash('Envie os relatórios de VENDAS e COMPRAS antes de processar.', 'warning')
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
            # Reprocessamento: incrementa a versão anterior (1:1, sem histórico).
            nova_versao = (indicador.versao_processamento or 0) + 1
            for k, v in resultado.items():
                setattr(indicador, k, v)
            indicador.versao_processamento = nova_versao
        else:
            # Primeiro processamento: versao_processamento = 1 (vem de resultado).
            indicador = IndicadorAnalise(id_analise=id, **resultado)
            db.session.add(indicador)

        agora = datetime.utcnow()
        upload_vendas.status_processamento = 'PROCESSADO'
        upload_vendas.data_processamento = agora
        upload_vendas.mensagem_erro = None
        upload_compras.status_processamento = 'PROCESSADO'
        upload_compras.data_processamento = agora
        upload_compras.mensagem_erro = None
        db.session.commit()
        flash('Processamento concluído. KPIs gerados.', 'success')
    except Exception as exc:
        db.session.rollback()
        agora = datetime.utcnow()
        analise.status_analise = 'RELATORIO_RECEBIDO'
        upload_vendas.status_processamento = 'ERRO'
        upload_vendas.data_processamento = agora
        upload_vendas.mensagem_erro = str(exc)[:500]
        upload_compras.status_processamento = 'ERRO'
        upload_compras.data_processamento = agora
        upload_compras.mensagem_erro = str(exc)[:500]
        db.session.commit()
        flash(f'Erro no processamento: {exc}', 'danger')

    return redirect(url_for('admin.analise_detalhe', id=id))


# ---------- Relatório estratégico --------------------------------------------

@admin_bp.route('/analise/<int:id>/relatorio', methods=['GET', 'POST'])
@login_required
def relatorio_editar(id):
    _requer_admin()
    analise = db.session.get(Analise, id) or abort(404)

    if analise.status_analise not in ('EM_ANALISE', 'CONCLUIDO'):
        flash('A análise precisa ser processada antes de redigir o relatório.', 'warning')
        return redirect(url_for('admin.analise_detalhe', id=id))

    relatorio = analise.relatorio

    # Relatório publicado é somente leitura: despublicar → editar → republicar.
    if relatorio and relatorio.publicado:
        flash('Despublique o relatório antes de editar a devolutiva.', 'warning')
        return redirect(url_for('admin.analise_detalhe', id=id))

    if request.method == 'POST':
        titulo = request.form.get('titulo', '').strip()
        conclusao = request.form.get('conclusao_estrategica', '').strip()

        if not titulo or not conclusao:
            flash('Título e conclusão estratégica são obrigatórios.', 'danger')
            return render_template('admin/relatorio_form.html',
                                   analise=analise, relatorio=relatorio)

        agora = datetime.utcnow()
        if relatorio:
            relatorio.titulo = titulo
            relatorio.resumo_executivo = request.form.get('resumo_executivo', '').strip() or None
            relatorio.pontos_positivos = request.form.get('pontos_positivos', '').strip() or None
            relatorio.pontos_de_alerta = request.form.get('pontos_de_alerta', '').strip() or None
            relatorio.recomendacoes = request.form.get('recomendacoes', '').strip() or None
            relatorio.conclusao_estrategica = conclusao
            relatorio.data_atualizacao = agora
        else:
            relatorio = RelatorioAnalise(
                id_analise=id,
                id_usuario_admin_autor=current_user.id_usuario,
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
    analise = db.session.get(Analise, id) or abort(404)
    relatorio = analise.relatorio

    if not _empresa_ativa(analise):
        flash('Não é possível publicar entrega para empresa que não está ATIVA.', 'warning')
        return redirect(url_for('admin.analise_detalhe', id=id))

    if not relatorio:
        flash('Crie o relatório estratégico antes de publicar.', 'warning')
        return redirect(url_for('admin.analise_detalhe', id=id))

    if not (relatorio.titulo or '').strip() or not (relatorio.conclusao_estrategica or '').strip():
        flash('Preencha título e conclusão estratégica antes de publicar.', 'warning')
        return redirect(url_for('admin.analise_detalhe', id=id))

    upload_vendas = UploadRelatorio.query.filter_by(
        id_analise=id, tipo_relatorio='VENDAS').first()
    upload_compras = UploadRelatorio.query.filter_by(
        id_analise=id, tipo_relatorio='COMPRAS').first()
    uploads = [u for u in (upload_vendas, upload_compras) if u]

    if not upload_vendas or not upload_compras:
        flash('Ambos os relatórios (VENDAS e COMPRAS) são necessários para publicar.', 'danger')
        return redirect(url_for('admin.analise_detalhe', id=id))

    if any(u.status_processamento in ('PENDENTE', 'ERRO') for u in uploads):
        flash('Não é possível publicar com relatório pendente ou com erro de processamento.', 'danger')
        return redirect(url_for('admin.analise_detalhe', id=id))

    indicador = analise.indicadores
    if not indicador:
        flash('Não é possível publicar sem KPIs gerados.', 'danger')
        return redirect(url_for('admin.analise_detalhe', id=id))

    # KPIs precisam ser posteriores ao último upload (evita publicar KPI obsoleto).
    ultimo_upload = max(u.data_upload for u in uploads)
    if indicador.data_geracao < ultimo_upload:
        flash('Reprocesse a análise após o último upload antes de publicar.', 'warning')
        return redirect(url_for('admin.analise_detalhe', id=id))

    agora = datetime.utcnow()
    relatorio.publicado = True
    relatorio.data_publicacao = agora
    analise.status_analise = 'CONCLUIDO'
    analise.data_conclusao = agora
    db.session.commit()
    flash('Análise publicada para o cliente.', 'success')
    return redirect(url_for('admin.analise_detalhe', id=id))


@admin_bp.route('/analise/<int:id>/despublicar', methods=['POST'])
@login_required
def analise_despublicar(id):
    _requer_admin()
    analise = db.session.get(Analise, id) or abort(404)
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

    # Ordenação explícita ALTA > MEDIA > BAIXA
    ordem_prioridade = case(
        (ChamadoSuporte.prioridade_atendimento == 'ALTA', 1),
        (ChamadoSuporte.prioridade_atendimento == 'MEDIA', 2),
        (ChamadoSuporte.prioridade_atendimento == 'BAIXA', 3),
        else_=4
    )

    query = ChamadoSuporte.query

    if busca:
        condicoes = [
            ChamadoSuporte.assunto.ilike(f'%{busca}%'),
            Empresa.nome_fantasia.ilike(f'%{busca}%'),
            Empresa.razao_social.ilike(f'%{busca}%'),
        ]
        # Busca numérica também casa o identificador do ticket
        if busca.isdigit():
            condicoes.append(ChamadoSuporte.id_chamado == int(busca))
        query = query.join(Empresa).filter(or_(*condicoes))

    if aba == 'arquivados':
        query = query.filter(ChamadoSuporte.status_chamado == 'RESOLVIDO')
    else:
        query = query.filter(ChamadoSuporte.status_chamado != 'RESOLVIDO')

    # Ordenação: prioridade (ALTA > MEDIA > BAIXA), depois mais recentes primeiro
    tickets_lista = query.order_by(
        ordem_prioridade,
        desc(ChamadoSuporte.data_atualizacao),
        desc(ChamadoSuporte.data_abertura),
    ).all()

    return render_template('admin/tickets.html',
                           tickets=tickets_lista, aba=aba, busca=busca)


@admin_bp.route('/ticket/<int:id>')
@login_required
def ticket_detalhe(id):
    _requer_admin()
    chamado = db.session.get(ChamadoSuporte, id) or abort(404)
    mensagens = chamado.mensagens.all()
    return render_template('admin/ticket_detalhe.html',
                           chamado=chamado, mensagens=mensagens)


@admin_bp.route('/ticket/<int:id>/mensagem', methods=['POST'])
@login_required
def ticket_mensagem(id):
    _requer_admin()
    chamado = db.session.get(ChamadoSuporte, id) or abort(404)
    conteudo = request.form.get('conteudo', '').strip()

    if not conteudo:
        flash('Mensagem não pode ser vazia.', 'danger')
        return redirect(url_for('admin.ticket_detalhe', id=id))

    mensagem = MensagemSuporte(
        id_chamado=id,
        id_usuario_autor=current_user.id_usuario,
        conteudo=conteudo,
    )
    db.session.add(mensagem)
    chamado.data_atualizacao = datetime.utcnow()
    # Resposta do ADMIN marca o ticket como RESPONDIDO.
    # Ticket RESOLVIDO não é reaberto automaticamente (só por mudança manual de status).
    if chamado.status_chamado != 'RESOLVIDO':
        chamado.status_chamado = 'RESPONDIDO'
    db.session.commit()
    flash('Resposta enviada.', 'success')
    return redirect(url_for('admin.ticket_detalhe', id=id))


@admin_bp.route('/ticket/<int:id>/status', methods=['POST'])
@login_required
def ticket_status(id):
    _requer_admin()
    chamado = db.session.get(ChamadoSuporte, id) or abort(404)
    novo_status = request.form.get('status_chamado', '').upper()

    STATUS_VALIDOS = ('ABERTO', 'EM_ANDAMENTO', 'RESPONDIDO', 'RESOLVIDO')
    if novo_status not in STATUS_VALIDOS:
        flash('Status inválido.', 'danger')
        return redirect(url_for('admin.ticket_detalhe', id=id))

    chamado.status_chamado = novo_status
    agora = datetime.utcnow()
    chamado.data_atualizacao = agora
    if novo_status == 'RESOLVIDO':
        chamado.data_fechamento = agora
    else:
        chamado.data_fechamento = None  # Reabertura limpa data_fechamento

    db.session.commit()
    flash(f'Status atualizado para {novo_status}.', 'success')
    return redirect(url_for('admin.ticket_detalhe', id=id))
