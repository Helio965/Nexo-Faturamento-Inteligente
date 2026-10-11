"""Dados sintéticos válidos: cada fábrica faz flush, nunca commit.

Use dentro de um app_context curto e confirme a transação explicitamente antes
de realizar requests. Um plano comercial existente é reutilizado; overrides
conflitantes são rejeitados para não alterar outras fixtures silenciosamente.
"""

from calendar import monthrange
from datetime import date
from decimal import Decimal
from itertools import count

from sqlalchemy import select

from models import Analise, Empresa, Plano, Segmento, Usuario


TEST_PASSWORD = "senha-sintetica-apenas-para-testes"
_SEQUENCE = count(1)
_PLANOS = {
    "BRONZE": (1, "MENSAL", "BASICA", "RESUMIDO", "BAIXO"),
    "PRATA": (1, "MENSAL", "COMPLETA", "GERENCIAL", "MEDIO"),
    "OURO": (2, "QUINZENAL", "PREMIUM", "COMPLETO", "ALTO"),
}


def _cnpj(numero):
    """CNPJ sintético com dígitos verificadores, sem consulta cadastral."""
    base = f"99{numero:010d}"
    for pesos in ((5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2),
                  (6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)):
        resto = sum(int(digito) * peso for digito, peso in zip(base, pesos)) % 11
        base += str(0 if resto < 2 else 11 - resto)
    return base


class DataFactory:
    """Cria os cinco modelos iniciais usando a sessão do banco temporário."""

    def __init__(self, session):
        self.session = session

    def _salvar(self, model, valores, attrs):
        valores.update(attrs)
        registro = model(**valores)
        self.session.add(registro)
        self.session.flush()
        return registro

    def plano(self, nome="BRONZE", **attrs):
        nome = nome.upper()
        if nome not in _PLANOS:
            raise ValueError("Plano deve ser BRONZE, PRATA ou OURO.")
        if attrs.get("nome_plano", nome) != nome:
            raise ValueError("nome_plano deve corresponder ao argumento nome.")
        if attrs.get("tipo_analise_permitida") == "QUINZENAL" and nome != "OURO":
            raise ValueError("Modalidade QUINZENAL exige plano OURO.")
        existente = self.session.execute(
            select(Plano).where(Plano.nome_plano == nome)
        ).scalar_one_or_none()
        if existente is not None:
            if any(getattr(existente, chave) != valor for chave, valor in attrs.items()):
                raise ValueError(f"Plano {nome} já existe com atributos diferentes.")
            return existente
        quantidade, tipo, entrega, dashboard, atendimento = _PLANOS[nome]
        return self._salvar(Plano, {
            "nome_plano": nome, "valor_mensal": Decimal("1.00"),
            "qtd_analises_mes": quantidade, "tipo_analise_permitida": tipo,
            "nivel_entrega_analise": entrega, "nivel_dashboard": dashboard,
            "nivel_atendimento": atendimento,
        }, attrs)

    def segmento(self, **attrs):
        return self._salvar(Segmento, {
            "nome_segmento": f"Segmento fictício {next(_SEQUENCE)}",
        }, attrs)

    def empresa(self, plano=None, segmento=None, status_conta="ATIVA", **attrs):
        if status_conta not in {"ATIVA", "SUSPENSA", "CANCELADA"}:
            raise ValueError("Status da empresa inválido.")
        if plano is None:
            plano = (self.session.get(Plano, attrs["id_plano_atual"])
                     if attrs.get("id_plano_atual") is not None else self.plano())
        if segmento is None:
            segmento = (self.session.get(Segmento, attrs["id_segmento"])
                        if attrs.get("id_segmento") is not None else self.segmento())
        if plano is None or segmento is None:
            raise ValueError("Empresa exige plano e segmento existentes.")
        if attrs.get("id_plano_atual", plano.id_plano) != plano.id_plano:
            raise ValueError("id_plano_atual deve corresponder ao plano informado.")
        if attrs.get("id_segmento", segmento.id_segmento) != segmento.id_segmento:
            raise ValueError("id_segmento deve corresponder ao segmento informado.")
        numero = next(_SEQUENCE)
        return self._salvar(Empresa, {
            "id_plano_atual": plano.id_plano, "id_segmento": segmento.id_segmento,
            "cnpj": _cnpj(numero), "razao_social": f"Empresa fictícia {numero}",
            "email_contato": f"empresa-{numero}@example.test",
            "data_contratacao": date(2026, 1, 1), "status_conta": status_conta,
        }, attrs)

    def usuario(self, role="CLIENTE", empresa=None, senha=TEST_PASSWORD,
                primeiro_acesso=False, **attrs):
        role = role.upper()
        if role not in {"ADMIN", "CLIENTE"}:
            raise ValueError("Perfil deve ser ADMIN ou CLIENTE.")
        if role == "ADMIN" and (empresa is not None or attrs.get("id_empresa") is not None):
            raise ValueError("ADMIN não pode estar associado a uma empresa.")
        if role == "CLIENTE" and empresa is None:
            id_empresa = attrs.get("id_empresa")
            empresa = (self.session.get(Empresa, id_empresa) if id_empresa is not None
                       else self.empresa())
            if empresa is None:
                raise ValueError("CLIENTE exige uma empresa existente.")
        id_empresa = empresa.id_empresa if empresa is not None else None
        if attrs.get("id_empresa", id_empresa) != id_empresa:
            raise ValueError("id_empresa deve corresponder à empresa informada.")
        numero = next(_SEQUENCE)
        valores = {
            "nome": f"Usuário fictício {numero}", "email": f"usuario-{numero}@example.test",
            "role": role, "id_empresa": id_empresa, "primeiro_acesso": primeiro_acesso,
        }
        valores.update(attrs)
        usuario = Usuario(**valores)
        usuario.set_senha(senha)
        self.session.add(usuario)
        self.session.flush()
        return usuario

    def analise(self, empresa, admin=None, **attrs):
        """Congela o plano atual; IDs não podem contradizer objetos informados."""
        if attrs.get("id_empresa", empresa.id_empresa) != empresa.id_empresa:
            raise ValueError("id_empresa deve corresponder à empresa informada.")
        if attrs.get("id_plano_referencia", empresa.id_plano_atual) != empresa.id_plano_atual:
            raise ValueError("A análise usa o plano atual da empresa como referência.")
        tipo = attrs.get("tipo_analise", "MENSAL")
        if tipo not in {"MENSAL", "QUINZENAL"}:
            raise ValueError("Tipo de análise inválido.")
        if tipo == "QUINZENAL" and empresa.plano_atual.nome_plano != "OURO":
            raise ValueError("Análise QUINZENAL exige plano OURO.")
        quinzena = attrs.get("quinzena_referencia", 1 if tipo == "QUINZENAL" else None)
        if (tipo == "MENSAL" and quinzena is not None or
                tipo == "QUINZENAL" and quinzena not in {1, 2}):
            raise ValueError("Quinzena incompatível com o tipo da análise.")
        if admin is None:
            admin = (self.session.get(Usuario, attrs["id_usuario_admin_responsavel"])
                     if attrs.get("id_usuario_admin_responsavel") is not None
                     else self.usuario(role="ADMIN"))
        if admin is None or not admin.is_admin:
            raise ValueError("Responsável pela análise deve ser ADMIN.")
        if attrs.get("id_usuario_admin_responsavel", admin.id_usuario) != admin.id_usuario:
            raise ValueError("id_usuario_admin_responsavel deve corresponder ao ADMIN informado.")
        mes, ano = attrs.get("mes_referencia", 1), attrs.get("ano_referencia", 2026)
        ultimo_dia = monthrange(ano, mes)[1]
        inicio = date(ano, mes, 16 if quinzena == 2 else 1)
        fim = date(ano, mes, 15 if quinzena == 1 else ultimo_dia)
        if attrs.get("periodo_inicio", inicio) > attrs.get("periodo_fim", fim):
            raise ValueError("Início do período não pode ser posterior ao fim.")
        return self._salvar(Analise, {
            "id_empresa": empresa.id_empresa,
            "id_plano_referencia": empresa.id_plano_atual,
            "id_usuario_admin_responsavel": admin.id_usuario,
            "periodo_inicio": inicio, "periodo_fim": fim,
            "mes_referencia": mes, "ano_referencia": ano,
            "tipo_analise": tipo, "quinzena_referencia": quinzena,
            "status_analise": "AGUARDANDO_RELATORIO",
        }, attrs)
