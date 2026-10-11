"""DEV-05: novos logins de CLIENTES de empresas CANCELADAS são recusados.

Execute: python -m unittest tests.test_cancelled_login -v
Usa a infraestrutura DEV-02, SQLite temporário, login HTTP e CSRF reais.
Sessões previamente autenticadas e tokens de recuperação não pertencem à DEV-05.
"""

from datetime import datetime
from http.cookies import SimpleCookie
import unittest
from urllib.parse import urlencode, urlsplit

from tests.support.base import IsolatedTestCase


class CancelledLoginTests(IsolatedTestCase):
    def setUp(self):
        super().setUp()
        from models import RelatorioAnalise
        from tests.support.factories import DataFactory

        self.contas = {}
        with self.app.app_context():
            factory = DataFactory(self.db.session)
            admin = factory.usuario(role="ADMIN", ativo=True, primeiro_acesso=False)
            self.admin = {"id": admin.id_usuario, "email": admin.email}
            for status, plano in (("ATIVA", "BRONZE"), ("SUSPENSA", "PRATA"),
                                  ("CANCELADA", "OURO")):
                empresa = factory.empresa(plano=factory.plano(plano), status_conta=status)
                usuario = factory.usuario(empresa=empresa, ativo=True, primeiro_acesso=False)
                analise = factory.analise(
                    empresa, admin=admin, status_analise="CONCLUIDO",
                    data_conclusao=datetime(2026, 1, 31, 12, 0),
                )
                self.db.session.add(RelatorioAnalise(
                    id_analise=analise.id_analise, titulo=f"Histórico sintético DEV-05 {status}",
                    resumo_executivo="Resumo sintético.", pontos_positivos="Pontos sintéticos.",
                    pontos_de_alerta="Alertas sintéticos.", recomendacoes="Recomendações sintéticas.",
                    conclusao_estrategica="Conclusão sintética de teste.",
                    publicado=True, data_publicacao=datetime(2026, 1, 31, 12, 0),
                ))
                self.contas[status] = {
                    "id": usuario.id_usuario, "email": usuario.email,
                    "empresa_id": empresa.id_empresa, "cnpj": empresa.cnpj,
                    "empresa_nome": empresa.razao_social, "plano": plano,
                    "empresa_email": empresa.email_contato, "analise_id": analise.id_analise,
                }
            self.db.session.commit()

    def login_http(self, conta, *, client=None, **kwargs):
        from tests.support.http import login

        client = client or self.env.create_client()
        return client, login(client, conta["email"], **kwargs)

    def assert_sem_autenticacao(self, client, resposta):
        """Asserções não imprimem cookies/tokens nem exigem uma sessão vazia."""
        with client.session_transaction() as sessao:
            self.assertFalse("_user_id" in sessao, "Login recusado não deve criar _user_id.")
            self.assertFalse("boot_id" in sessao, "Login recusado não deve criar boot_id autenticado.")
        remember_name = self.app.config.get("REMEMBER_COOKIE_NAME", "remember_token")
        self.assertFalse(client.get_cookie(remember_name) is not None,
                         "Login recusado não deve criar cookie persistente de autenticação.")
        for header in resposta.headers.getlist("Set-Cookie"):
            cookies = SimpleCookie()
            cookies.load(header)
            self.assertFalse(remember_name in cookies, "Resposta não deve emitir cookie remember.")
            session_cookie = cookies.get(self.app.config["SESSION_COOKIE_NAME"])
            if session_cookie is not None:
                self.assertFalse(bool(session_cookie["expires"] or session_cookie["max-age"]),
                                 "Sessão CSRF/flash permitida não deve ser persistente.")

    def assert_login_recusado(self, client, resposta):
        self.assert_sem_autenticacao(client, resposta)
        self.assertIn(resposta.status_code, (200, 302))
        if resposta.status_code == 302:
            self.assertEqual(urlsplit(resposta.headers["Location"]).path, "/auth/login")
        else:
            self.assertTrue('action="/auth/login"' in resposta.get_data(as_text=True),
                            "Recusa deve apresentar o formulário de login.")
        for path in ("/cliente/dashboard", "/cliente/historico", "/auth/primeiro-acesso"):
            with self.subTest(rota_protegida=path):
                protegida = client.get(path)
                self.assertEqual(protegida.status_code, 302)
                self.assertEqual(urlsplit(protegida.headers["Location"]).path, "/auth/login")

    def assert_login_autorizado(self, conta, destino="/cliente/dashboard", **kwargs):
        client, resposta = self.login_http(conta, **kwargs)
        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(resposta.headers["Location"], destino)
        with client.session_transaction() as sessao:
            self.assertTrue(sessao.get("_user_id") == str(conta["id"]),
                            "Login autorizado deve autenticar o usuário correto.")
            self.assertTrue(sessao.get("boot_id") == self.app.config["BOOT_ID"],
                            "Login autorizado deve usar o BOOT_ID atual.")
        return client

    def alterar_usuario(self, conta, **atributos):
        from models import Usuario

        with self.app.app_context():
            usuario = self.db.session.get(Usuario, conta["id"])
            for nome, valor in atributos.items():
                setattr(usuario, nome, valor)
            self.db.session.commit()

    def snapshot(self):
        """Compara campos de todas as tabelas, incluindo senha, status e histórico."""
        from sqlalchemy import select

        with self.app.app_context():
            return {
                tabela.name: tuple(tuple(linha) for linha in self.db.session.execute(
                    select(tabela).order_by(*tabela.primary_key.columns)
                ).all())
                for tabela in self.db.metadata.sorted_tables
            }

    def test_ativa_credenciais_validas_permite_login(self):
        """CLIENTE de empresa ATIVA autentica e consulta dashboard/histórico."""
        client = self.assert_login_autorizado(self.contas["ATIVA"])
        self.assertEqual(client.get("/cliente/dashboard").status_code, 200)
        self.assertEqual(client.get("/cliente/historico").status_code, 200)

    def test_suspensa_credenciais_validas_permite_login(self):
        """CLIENTE ativo de empresa SUSPENSA continua autorizado a consultar."""
        client = self.assert_login_autorizado(self.contas["SUSPENSA"])
        self.assertEqual(client.get("/cliente/dashboard").status_code, 200)
        self.assertEqual(client.get("/cliente/historico").status_code, 200)

    def test_cancelada_senha_valida_nao_cria_sessao_autenticada(self):
        """CANCELADA com senha correta não cria autenticação nem acessa rotas protegidas."""
        client, resposta = self.login_http(self.contas["CANCELADA"])
        self.assert_login_recusado(client, resposta)

    def test_cancelada_senha_incorreta_preserva_mensagem_generica(self):
        """Senha incorreta recusa credenciais sem revelar cancelamento empresarial."""
        client, resposta = self.login_http(self.contas["CANCELADA"], senha="senha-errada-de-teste")
        self.assert_login_recusado(client, resposta)
        pagina = resposta.get_data(as_text=True)
        self.assertTrue("E-mail ou senha incorretos." in pagina,
                        "Credenciais inválidas devem manter a mensagem genérica.")
        self.assertFalse("cancelad" in pagina.lower(),
                         "Senha incorreta não deve informar cancelamento empresarial.")

    def test_cancelada_usuario_inativo_permanece_bloqueado(self):
        """Conta individual inativa permanece recusada antes do fluxo autenticado."""
        conta = self.contas["CANCELADA"]
        self.alterar_usuario(conta, ativo=False)
        client, resposta = self.login_http(conta)
        self.assert_login_recusado(client, resposta)
        self.assertTrue("conta está desativada" in resposta.get_data(as_text=True),
                        "Recusa deve preservar a mensagem de inativação individual.")

    def test_cancelada_primeiro_acesso_pendente_nao_libera_troca(self):
        """CANCELADA não autentica nem libera primeiro acesso com senha válida."""
        conta = self.contas["CANCELADA"]
        self.alterar_usuario(conta, primeiro_acesso=True)
        client, resposta = self.login_http(conta)
        self.assert_login_recusado(client, resposta)

    def test_admin_ativo_sem_empresa_continua_autorizado(self):
        """ADMIN ativo e id_empresa NULL mantém login e acesso administrativo."""
        from models import Usuario

        with self.app.app_context():
            self.assertIsNone(self.db.session.get(Usuario, self.admin["id"]).id_empresa)
        client = self.assert_login_autorizado(self.admin, destino="/admin/dashboard")
        self.assertEqual(client.get("/admin/dashboard").status_code, 200)

    def test_admin_inativo_permanece_bloqueado(self):
        """ADMIN individualmente inativo continua recusado pela autenticação real."""
        self.alterar_usuario(self.admin, ativo=False)
        client, resposta = self.login_http(self.admin)
        self.assert_login_recusado(client, resposta)
        self.assertTrue("conta está desativada" in resposta.get_data(as_text=True),
                        "ADMIN inativo deve receber a mensagem de inativação individual.")

    def test_cancelada_next_protegido_nao_contorna_bloqueio(self):
        """next local protegido não autentica CANCELADA nem concede primeiro acesso."""
        for destino in ("/cliente/dashboard", "/cliente/historico", "/auth/primeiro-acesso"):
            with self.subTest(next=destino):
                path = "/auth/login?" + urlencode({"next": destino})
                client, resposta = self.login_http(self.contas["CANCELADA"], path=path)
                self.assert_login_recusado(client, resposta)

    def test_cancelada_recusa_preserva_usuario_empresa_e_historicos(self):
        """Recusa mantém senha/ativo/status/publicações e dados de todas as empresas."""
        from models import Analise, Empresa, Usuario

        conta = self.contas["CANCELADA"]
        with self.app.app_context():
            usuario = self.db.session.get(Usuario, conta["id"])
            empresa = self.db.session.get(Empresa, conta["empresa_id"])
            analise = self.db.session.get(Analise, conta["analise_id"])
            self.assertTrue(usuario.ativo)
            self.assertEqual(empresa.status_conta, "CANCELADA")
            self.assertIsNone(empresa.deletado_em)
            self.assertEqual(analise.status_analise, "CONCLUIDO")
            self.assertTrue(analise.relatorio.publicado)
        antes = self.snapshot()
        client, resposta = self.login_http(conta)
        self.assert_login_recusado(client, resposta)
        self.assertTrue(self.snapshot() == antes, "Recusa não deve alterar nenhuma tabela.")

    def test_login_csrf_ausente_ou_invalido_nao_autentica(self):
        """CSRF real recusa token ausente/inválido, inclusive credenciais autorizadas."""
        from tests.support.factories import TEST_PASSWORD
        from tests.support.http import csrf_token

        self.assertTrue(self.app.config["WTF_CSRF_ENABLED"])
        for status in ("ATIVA", "CANCELADA"):
            for token_invalido in (None, "csrf-invalido-de-teste"):
                with self.subTest(status=status, token_invalido=token_invalido is not None):
                    client = self.env.create_client()
                    csrf_token(client)
                    dados = {"email": self.contas[status]["email"], "senha": TEST_PASSWORD}
                    if token_invalido is not None:
                        dados["csrf_token"] = token_invalido
                    antes = self.snapshot()
                    resposta = client.post("/auth/login", data=dados)
                    self.assertEqual(resposta.status_code, 400)
                    self.assert_sem_autenticacao(client, resposta)
                    self.assertTrue(self.snapshot() == antes, "Falha CSRF não deve alterar o banco.")

    def test_autorizadas_next_local_seguro_continua_funcionando(self):
        """ATIVA/SUSPENSA preservam next local autorizado após login real."""
        path = "/auth/login?" + urlencode({"next": "/cliente/historico"})
        for status in ("ATIVA", "SUSPENSA"):
            with self.subTest(status=status):
                client = self.assert_login_autorizado(
                    self.contas[status], destino="/cliente/historico", path=path,
                )
                self.assertEqual(client.get("/cliente/historico").status_code, 200)

    def test_autorizadas_primeiro_acesso_preserva_fluxo_atual(self):
        """ATIVA/SUSPENSA com primeiro acesso autentica e exige definir senha."""
        for status in ("ATIVA", "SUSPENSA"):
            with self.subTest(status=status):
                conta = self.contas[status]
                self.alterar_usuario(conta, primeiro_acesso=True)
                client = self.assert_login_autorizado(conta)
                resposta = client.get("/cliente/dashboard")
                self.assertEqual(resposta.status_code, 302)
                self.assertEqual(resposta.headers["Location"], "/auth/primeiro-acesso")
                self.assertEqual(client.get("/auth/primeiro-acesso").status_code, 200)

    def test_autorizadas_next_externo_nao_redireciona_para_fora(self):
        """ATIVA/SUSPENSA ignoram next externo ou protocol-relative e usam dashboard."""
        for status in ("ATIVA", "SUSPENSA"):
            for destino in ("https://example.test/", "//example.test/", "/\\example.test/"):
                with self.subTest(status=status, next=destino):
                    path = "/auth/login?" + urlencode({"next": destino})
                    client = self.assert_login_autorizado(self.contas[status], path=path)
                    self.assertEqual(client.get("/cliente/dashboard").status_code, 200)

    def test_email_desconhecido_preserva_recusa_generica(self):
        """E-mail inexistente recusa credenciais sem consultar publicamente uma empresa."""
        client, resposta = self.login_http({"email": "inexistente-dev05@example.test"})
        self.assert_login_recusado(client, resposta)
        self.assertTrue("E-mail ou senha incorretos." in resposta.get_data(as_text=True),
                        "E-mail desconhecido deve manter a mensagem genérica.")

    def test_ativa_usuario_inativo_continua_bloqueado(self):
        """Empresa ATIVA não libera conta individualmente inativa."""
        conta = self.contas["ATIVA"]
        self.alterar_usuario(conta, ativo=False)
        client, resposta = self.login_http(conta)
        self.assert_login_recusado(client, resposta)

    def test_suspensa_usuario_inativo_continua_bloqueado(self):
        """SUSPENSA mantém distinção entre consulta permitida e usuário inativo."""
        conta = self.contas["SUSPENSA"]
        self.alterar_usuario(conta, ativo=False)
        client, resposta = self.login_http(conta)
        self.assert_login_recusado(client, resposta)

    def test_cancelada_bloqueio_independe_do_plano(self):
        """CANCELADA é recusada nos planos BRONZE/PRATA/OURO por status do banco."""
        from tests.support.factories import DataFactory

        contas = [self.contas["CANCELADA"]]
        with self.app.app_context():
            factory = DataFactory(self.db.session)
            for plano in ("BRONZE", "PRATA"):
                empresa = factory.empresa(plano=factory.plano(plano), status_conta="CANCELADA")
                usuario = factory.usuario(empresa=empresa, ativo=True, primeiro_acesso=False)
                contas.append({"id": usuario.id_usuario, "email": usuario.email})
            self.db.session.commit()
        antes = self.snapshot()
        for conta in contas:
            with self.subTest(usuario_sintetico=conta["id"]):
                client, resposta = self.login_http(conta)
                self.assert_login_recusado(client, resposta)
        self.assertTrue(self.snapshot() == antes, "Recusas nos três planos não devem alterar o banco.")

    def test_cancelada_recusa_nao_expoe_cadastro_ou_plano(self):
        """Mensagem de recusa não expõe CNPJ, plano, nome ou contato empresarial."""
        conta = self.contas["CANCELADA"]
        client, resposta = self.login_http(conta)
        self.assert_login_recusado(client, resposta)
        pagina = resposta.get_data(as_text=True)
        for dado in (conta["cnpj"], conta["empresa_nome"], conta["empresa_email"], conta["plano"]):
            self.assertFalse(dado in pagina, "Recusa não deve expor dados empresariais.")

    def test_limite_real_de_dez_tentativas_por_minuto_e_preservado(self):
        """Limiter real aceita dez POSTs e recusa o décimo primeiro com HTTP 429."""
        from extensions import limiter
        from tests.support.factories import TEST_PASSWORD
        from tests.support.http import csrf_token

        # DEV-02 deixa o limite desligado para a suíte geral. Este único caso
        # o habilita antes de qualquer request usando somente a API pública.
        self.app.config["RATELIMIT_ENABLED"] = True
        limiter.init_app(self.app)
        client = self.env.create_client()
        token = csrf_token(client)
        dados = {"email": "limite-dev05@example.test", "senha": TEST_PASSWORD, "csrf_token": token}
        antes = self.snapshot()
        for tentativa in range(10):
            with self.subTest(tentativa=tentativa + 1):
                resposta = client.post("/auth/login", data=dados)
                self.assertEqual(resposta.status_code, 200)
                self.assert_sem_autenticacao(client, resposta)
        resposta = client.post("/auth/login", data=dados)
        self.assertEqual(resposta.status_code, 429)
        self.assert_sem_autenticacao(client, resposta)
        self.assertTrue(self.snapshot() == antes, "Limitação de tentativas não deve alterar o banco.")


if __name__ == "__main__":
    unittest.main()
