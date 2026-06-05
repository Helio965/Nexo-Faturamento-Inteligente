import json
from datetime import datetime
from flask import (Blueprint, render_template, redirect, url_for,
                   flash, request, abort)
from flask_login import login_required, current_user

from app import db
from app.models import (Empresa, Analise, IndicadorAnalise, RelatorioAnalise,
                         ChamadoSuporte, MensagemSuporte)

client_bp = Blueprint('client', __name__)


def _requer_cliente():
    if not current_user.is_authenticated or not current_user.is_cliente:
        abort(403)


def _empresa_cliente():
    empresa = current_user.empresa
    if empresa is None:
        abort(403)
    return empresa


# ---------- Dashboard --------------------------------------------------------

@client_bp.route('/')
@login_required
def dashboard():
    _requer_cliente()
    empresa = _empresa_cliente()

    ultima_analise = (Analise.query
                      .filter_by(id_empresa=empresa.id_empresa)
                      .join(RelatorioAnalise)
                      .filter(RelatorioAnalise.publicado == True)
                      .order_by(Analise.ano_referencia.desc(),
                                Analise.mes_referencia.desc())
                      .first())

    indicador = None
    relatorio = None
    chart_data = None

    if ultima_analise:
        indicador = ultima_analise.indicadores
        relatorio = ultima_analise.relatorio

        if indicador:
            nomes = []
            valores = []
            if indicador.produto_mais_vendido_nome:
                nomes.append(indicador.produto_mais_vendido_nome)
                valores.append(float(indicador.produto_mais_vendido_quantidade or 0))
            if indicador.produto_maior_faturamento_nome:
                nomes.append(indicador.produto_maior_faturamento_nome)
                valores.append(float(indicador.produto_maior_faturamento_valor or 0))
            chart_data = json.dumps({'nomes': nomes, 'valores': valores})

    tickets_abertos = (ChamadoSuporte.query
                       .filter_by(id_empresa=empresa.id_empresa)
                       .filter(ChamadoSuporte.status_chamado.in_(['ABERTO', 'EM_ANDAMENTO']))
                       .count())

    return render_template('client/dashboard.html',
                           empresa=empresa,
                           ultima_analise=ultima_analise,
                           indicador=indicador,
                           relatorio=relatorio,
                           chart_data=chart_data,
                           tickets_abertos=tickets_abertos)


# ---------- Análises ---------------------------------------------------------

@client_bp.route('/analises')
@login_required
def analises():
    _requer_cliente()
    empresa = _empresa_cliente()

    lista = (Analise.query
             .filter_by(id_empresa=empresa.id_empresa)
             .join(RelatorioAnalise)
             .filter(RelatorioAnalise.publicado == True)
             .order_by(Analise.ano_referencia.desc(), Analise.mes_referencia.desc())
             .all())

    return render_template('client/analises.html', analises=lista, empresa=empresa)


@client_bp.route('/analise/<int:id>')
@login_required
def analise_detalhe(id):
    _requer_cliente()
    empresa = _empresa_cliente()

    # Anti-IDOR: garante que a análise pertence à empresa do cliente
    analise = Analise.query.filter_by(id_analise=id, id_empresa=empresa.id_empresa).first_or_404()

    # Somente análises publicadas
    if not analise.relatorio or not analise.relatorio.publicado:
        abort(404)

    indicador = analise.indicadores
    chart_data = None

    if indicador:
        nomes = []
        valores = []
        if indicador.produto_mais_vendido_nome:
            nomes.append(f"+ Vendido\n{indicador.produto_mais_vendido_nome}")
            valores.append(float(indicador.produto_mais_vendido_quantidade or 0))
        if indicador.produto_maior_faturamento_nome:
            nomes.append(f"Maior Fat.\n{indicador.produto_maior_faturamento_nome}")
            valores.append(float(indicador.produto_maior_faturamento_valor or 0))
        if indicador.produto_maior_saldo_parado_nome and indicador.saldo_estimado_parado:
            nomes.append(f"Pressão Estoque\n{indicador.produto_maior_saldo_parado_nome}")
            valores.append(float(indicador.saldo_estimado_parado))
        chart_data = json.dumps({'nomes': nomes, 'valores': valores})

    return render_template('client/analise_detalhe.html',
                           analise=analise,
                           indicador=indicador,
                           relatorio=analise.relatorio,
                           chart_data=chart_data)


# ---------- Tickets ----------------------------------------------------------

@client_bp.route('/tickets')
@login_required
def tickets():
    _requer_cliente()
    empresa = _empresa_cliente()

    aba = request.args.get('aba', 'ativos')
    query = ChamadoSuporte.query.filter_by(id_empresa=empresa.id_empresa)

    if aba == 'resolvidos':
        query = query.filter_by(status_chamado='RESOLVIDO')
    else:
        query = query.filter(ChamadoSuporte.status_chamado != 'RESOLVIDO')

    lista = query.order_by(ChamadoSuporte.data_atualizacao.desc()).all()
    return render_template('client/tickets.html',
                           chamados=lista, aba=aba, empresa=empresa)


@client_bp.route('/ticket/novo', methods=['GET', 'POST'])
@login_required
def ticket_novo():
    _requer_cliente()
    empresa = _empresa_cliente()

    if empresa.status_conta == 'CANCELADA':
        flash('Empresas canceladas não podem abrir tickets.', 'danger')
        return redirect(url_for('client.tickets'))

    if request.method == 'POST':
        assunto = request.form.get('assunto', '').strip()
        conteudo = request.form.get('conteudo', '').strip()

        if not assunto or not conteudo:
            flash('Assunto e mensagem são obrigatórios.', 'danger')
            return render_template('client/ticket_novo.html', empresa=empresa)

        prioridade = empresa.plano_atual.prioridade_ticket

        chamado = ChamadoSuporte(
            id_empresa=empresa.id_empresa,
            id_usuario_cliente_autor=current_user.id_usuario,
            assunto=assunto,
            descricao=conteudo,
            prioridade_atendimento=prioridade,
            status_chamado='ABERTO',
        )
        db.session.add(chamado)
        db.session.flush()

        # Primeira mensagem na mesma transação
        mensagem = MensagemSuporte(
            id_chamado=chamado.id_chamado,
            id_usuario_autor=current_user.id_usuario,
            conteudo=conteudo,
        )
        db.session.add(mensagem)
        db.session.commit()

        flash('Ticket aberto com sucesso.', 'success')
        return redirect(url_for('client.ticket_detalhe', id=chamado.id_chamado))

    return render_template('client/ticket_novo.html', empresa=empresa)


@client_bp.route('/ticket/<int:id>')
@login_required
def ticket_detalhe(id):
    _requer_cliente()
    empresa = _empresa_cliente()

    # Anti-IDOR
    chamado = ChamadoSuporte.query.filter_by(
        id_chamado=id, id_empresa=empresa.id_empresa).first_or_404()
    mensagens = chamado.mensagens.all()

    return render_template('client/ticket_detalhe.html',
                           chamado=chamado, mensagens=mensagens, empresa=empresa)


@client_bp.route('/ticket/<int:id>/mensagem', methods=['POST'])
@login_required
def ticket_mensagem(id):
    _requer_cliente()
    empresa = _empresa_cliente()

    # Anti-IDOR
    chamado = ChamadoSuporte.query.filter_by(
        id_chamado=id, id_empresa=empresa.id_empresa).first_or_404()

    if chamado.status_chamado == 'RESOLVIDO':
        flash('Ticket resolvido é somente leitura. Abra um novo ticket se necessário.', 'warning')
        return redirect(url_for('client.ticket_detalhe', id=id))

    conteudo = request.form.get('conteudo', '').strip()
    if not conteudo:
        flash('Mensagem não pode ser vazia.', 'danger')
        return redirect(url_for('client.ticket_detalhe', id=id))

    mensagem = MensagemSuporte(
        id_chamado=id,
        id_usuario_autor=current_user.id_usuario,
        conteudo=conteudo,
    )
    db.session.add(mensagem)
    chamado.data_atualizacao = datetime.utcnow()
    db.session.commit()
    flash('Mensagem enviada.', 'success')
    return redirect(url_for('client.ticket_detalhe', id=id))
