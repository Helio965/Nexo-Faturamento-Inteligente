"""
NEXO - Blueprint de API interna (JSON)
======================================
Endpoints leves consumidos via Fetch pelo front-end. Hoje: o NexoBot.
"""

from flask import Blueprint, request, jsonify, abort
from flask_login import login_required, current_user

from suporte_bot import responder
from navegacao_bot import urls_destinos, validar_destino

api_bp = Blueprint("api", __name__, url_prefix="/api")


@api_bp.app_context_processor
def destinos_nexobot():
    """O widget valida ações usando o mesmo catálogo fechado do backend."""
    if current_user.is_authenticated and current_user.is_cliente:
        return {"nexobot_destinos": urls_destinos()}
    return {"nexobot_destinos": {}}


@api_bp.route("/suporte-bot", methods=["POST"])
@login_required
def suporte_bot():
    """Recebe mensagem/contexto leve e devolve texto e ação (cliente apenas)."""
    if not current_user.is_cliente:
        abort(403)
    dados = request.get_json(silent=True)
    if not isinstance(dados, dict) or not isinstance(dados.get("mensagem", ""), str):
        return jsonify(resposta="Envie uma mensagem de texto em um objeto JSON.",
                       fonte="local", acao=None, destino=None), 400
    mensagem = dados.get("mensagem", "").strip()[:1000]
    ultimo_destino = validar_destino(dados.get("ultimo_destino"))
    return jsonify(responder(mensagem, ultimo_destino=ultimo_destino))
