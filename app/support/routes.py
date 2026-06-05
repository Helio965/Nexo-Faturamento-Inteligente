"""Blueprint de suporte — sem rotas próprias no MVP.
Roteamento de tickets está em admin.routes e client.routes."""
from flask import Blueprint

support_bp = Blueprint('support', __name__)
