"""Regressão do NexoBot: navegação, Guia, permissões e CSRF reais.

Execute da raiz: python -m unittest discover -s tests -p 'test_nexobot.py' -v
O banco e os uploads ficam em um diretório temporário, sem tocar dados locais.
"""

import html
import os
from pathlib import Path
import re
import secrets
import tempfile
import unittest
from datetime import date
from unittest.mock import patch


class NexoBotTestCase(unittest.TestCase):
    ENDPOINTS = {
        "dashboard": "cliente.dashboard",
        "upload": "cliente.upload",
        "historico": "cliente.historico",
        "guia": "cliente.guia",
        "suporte": "cliente.tickets",
    }
    SENHA = "senha-apenas-para-testes"

    @classmethod
    def setUpClass(cls):
        # ProductionConfig também é importada pela factory. Reutiliza a chave
        # existente; somente a ausência recebe uma chave efêmera para os testes.
        with patch.dict(os.environ, {
            "SECRET_KEY": os.environ.get("SECRET_KEY") or secrets.token_hex(32),
        }):
            from app import create_app
            from config import Config, config_by_name

        cls.temp = tempfile.TemporaryDirectory(prefix="nexo-bot-tests-")
        cls.addClassCleanup(cls.temp.cleanup)
        raiz = Path(cls.temp.name)

        class TestConfig(Config):
            TESTING = True
            DEBUG = False
            SQLALCHEMY_DATABASE_URI = f"sqlite:///{raiz / 'test.db'}"
            SQLALCHEMY_DIRECT_URI = SQLALCHEMY_DATABASE_URI
            SQLALCHEMY_ECHO = False
            UPLOAD_FOLDER = raiz / "uploads"
            WTF_CSRF_ENABLED = True
            RATELIMIT_ENABLED = False
            HF_API_TOKEN = None
            MAIL_SUPPRESS_SEND = True

        # Configuração aplicada antes de db.init_app e da primeira conexão.
        # NEXO_DB_DIRECT também aponta para o mesmo banco temporário caso já
        # esteja configurado no ambiente de quem executa a suíte.
        with patch.dict(config_by_name, {"nexobot_test": TestConfig}):
            cls.app = create_app("nexobot_test")

        from extensions import db
        from models import Empresa, GuiaTopico, Plano, Segmento, Usuario

        cls.db = db
        cls.GuiaTopico = GuiaTopico
        with cls.app.app_context():
            db.create_all()
            segmento = Segmento(nome_segmento="Segmento de teste")
            plano = Plano(
                nome_plano="BRONZE", valor_mensal=1, qtd_analises_mes=1,
                tipo_analise_permitida="MENSAL", nivel_entrega_analise="BASICA",
                nivel_dashboard="RESUMIDO", nivel_atendimento="BAIXO",
            )
            db.session.add_all([segmento, plano])
            db.session.flush()
            empresa = Empresa(
                id_segmento=segmento.id_segmento, id_plano_atual=plano.id_plano,
                cnpj="00000000000191", razao_social="Empresa de teste",
                email_contato="empresa@example.test", data_contratacao=date.today(),
            )
            db.session.add(empresa)
            db.session.flush()
            for nome, role in (("cliente", "CLIENTE"), ("outro", "CLIENTE"),
                               ("admin", "ADMIN")):
                usuario = Usuario(
                    nome=nome, email=f"{nome}@example.test", role=role,
                    id_empresa=empresa.id_empresa if role == "CLIENTE" else None,
                    primeiro_acesso=False,
                )
                usuario.set_senha(cls.SENHA)
                db.session.add(usuario)
            db.session.commit()

        def dispose_db():
            with cls.app.app_context():
                db.session.remove()
                db.engine.dispose()

        cls.addClassCleanup(dispose_db)

    def setUp(self):
        self.app.config["HF_API_TOKEN"] = None
        # Cada requisição precisa do próprio g/session: um app_context mantido
        # durante todo o teste compartilharia o cache CSRF entre clientes.
        with self.app.app_context():
            self.db.session.query(self.GuiaTopico).delete()
            self.db.session.add_all([
                self.GuiaTopico(
                    categoria="Upload", pergunta="Como enviar relatórios de compras e vendas?",
                    resposta="Escolha a análise disponível e anexe os arquivos CSV ou XLSX.",
                ),
                self.GuiaTopico(
                    categoria="Senhas", pergunta="Como recupero minha senha?",
                    resposta="Use Esqueci minha senha no login e siga o link de recuperação.",
                ),
                self.GuiaTopico(
                    categoria="PDV", pergunta="Como exportar dados do PDV?",
                    resposta="Exporte os relatórios do PDV em CSV ou XLSX antes de anexar.",
                ),
            ])
            self.db.session.commit()
        self.client = self.app.test_client()
        self.token = self.login(self.client)

    def count(self, model):
        with self.app.app_context():
            return self.db.session.query(model).count()

    def csrf_token(self, client):
        pagina = client.get("/auth/login")
        # O meta csrf-token existe tanto no login quanto no dashboard, inclusive
        # quando o GET de login redireciona um usuário já autenticado.
        if pagina.status_code == 302:
            pagina = client.get(pagina.headers["Location"])
        self.assertEqual(pagina.status_code, 200)
        resultado = re.search(
            r'<meta\s+name="csrf-token"\s+content="([^"]+)"',
            pagina.get_data(as_text=True),
        )
        self.assertIsNotNone(resultado, "Template deve fornecer o token CSRF real")
        return html.unescape(resultado.group(1))

    def login(self, client, nome="cliente"):
        token = self.csrf_token(client)
        resposta = client.post("/auth/login", data={
            "email": f"{nome}@example.test", "senha": self.SENHA,
            "csrf_token": token,
        })
        self.assertEqual(resposta.status_code, 302)
        self.assertNotIn("/auth/login", resposta.headers["Location"])
        return token

    def post(self, mensagem, ultimo_destino=None, client=None, token=None):
        return (client or self.client).post(
            "/api/suporte-bot", json={
                "mensagem": mensagem, "ultimo_destino": ultimo_destino,
            }, headers={"X-CSRFToken": token or self.token},
        )

    def perguntar(self, mensagem, ultimo_destino=None):
        resposta = self.post(mensagem, ultimo_destino)
        self.assertEqual(resposta.status_code, 200, mensagem)
        dados = resposta.get_json()
        self.assertIsInstance(dados, dict)
        self.assertIsInstance(dados["resposta"], str)
        self.assertIn(dados["fonte"], ("local", "hf"))
        return dados

    def assert_destino(self, dados, destino, acao="navegar"):
        from flask import url_for
        with self.app.test_request_context():
            url = url_for(self.ENDPOINTS[destino])
        self.assertEqual(dados["acao"], acao)
        self.assertEqual(dados["destino"], destino)
        self.assertEqual(dados["url"], url)
        if acao == "navegar":
            self.assertEqual(dados["resposta"], "")
            self.assertEqual(dados["fonte"], "local")
        else:
            self.assertTrue(dados["resposta"].strip())
            self.assertTrue(dados["rotulo_botao"].strip())

    def assert_sem_acao(self, dados):
        self.assertIsNone(dados.get("acao"))
        self.assertIsNone(dados.get("destino"))
        self.assertFalse(dados.get("url"))
        self.assertTrue(dados["resposta"].strip())

    def test_01_pergunta_informativa_oferece_upload(self):
        self.assert_destino(
            self.perguntar("Onde faço upload dos arquivos de compras e vendas?"),
            "upload", "sugerir_navegacao",
        )

    def test_02_comando_direto_sem_explicacao(self):
        self.assert_destino(self.perguntar("Me leve para o upload."), "upload")

    def test_03_comando_contextual(self):
        contexto = self.perguntar("Onde envio os relatórios?")["destino"]
        self.assertEqual(contexto, "upload")
        self.assert_destino(self.perguntar("Me leva até lá.", contexto), "upload")

    def test_04_dashboard(self):
        self.assert_destino(self.perguntar("Quero abrir meu dashboard."), "dashboard")

    def test_05_historico(self):
        self.assert_destino(self.perguntar("Abra minhas análises anteriores."), "historico")

    def test_06_guia(self):
        self.assert_destino(self.perguntar("Quero ir para o Guia."), "guia")

    def test_07_suporte_nao_cria_chamado(self):
        from models import ChamadoSuporte
        antes = self.count(ChamadoSuporte)
        self.assert_destino(self.perguntar("Me leve para abrir um chamado."), "suporte")
        self.assertEqual(self.count(ChamadoSuporte), antes)

    def test_08_ausencia_de_contexto_pede_esclarecimento(self):
        for mensagem in ("Me leva pra lá.", "Pode abrir?", "Quero que me leve."):
            with self.subTest(mensagem=mensagem):
                self.assert_sem_acao(self.perguntar(mensagem))

    def test_09_acesso_administrativo_proibido(self):
        self.assert_sem_acao(self.perguntar("Abra o painel de administração.", "dashboard"))

    def test_10_hf_ausente_ou_indisponivel_nao_bloqueia_navegacao(self):
        import httpx
        self.app.config["HF_API_TOKEN"] = "token-ficticio-de-teste"
        with patch("httpx.post", side_effect=httpx.TimeoutException("timeout simulado")) as chamada:
            self.assert_destino(self.perguntar("Me leve para o upload."), "upload")
            chamada.assert_not_called()
            dados = self.perguntar("Como recupero minha senha?")
            self.assertEqual(dados["fonte"], "local")
            self.assertIn("Esqueci minha senha", dados["resposta"])
            chamada.assert_called_once()

    def test_11_negacao_explicita(self):
        for mensagem in (
            "Não quero ir para o upload.", "NÃO ABRA O DASHBOARD.",
            "Não me leve ao histórico.", "Não me manda pra lá.",
        ):
            with self.subTest(mensagem=mensagem):
                dados = self.perguntar(mensagem, "upload")
                self.assertNotEqual(dados.get("acao"), "navegar")

    def test_12_mudanca_de_contexto(self):
        contexto = self.perguntar("Onde fica o upload?")["destino"]
        dados = self.perguntar("Como acesso meu histórico?", contexto)
        self.assert_destino(dados, "historico", "sugerir_navegacao")
        self.assert_destino(self.perguntar("Me leva para essa página.", dados["destino"]), "historico")

    def test_13_multiplos_destinos_pedem_esclarecimento(self):
        for mensagem in (
            "Me leva para o dashboard ou para o histórico.",
            "Me leva para o upload e para o dashboard.",
        ):
            with self.subTest(mensagem=mensagem):
                self.assert_sem_acao(self.perguntar(mensagem, "upload"))

    def test_14_regressao_senha_e_pdv(self):
        for mensagem, fragmento in (
            ("Como recupero minha senha?", "Esqueci minha senha"),
            ("Como exportar os dados do PDV?", "CSV ou XLSX"),
        ):
            with self.subTest(mensagem=mensagem):
                dados = self.perguntar(mensagem)
                self.assertNotEqual(dados.get("acao"), "navegar")
                self.assertIn(fragmento, dados["resposta"])

    def test_15_destinos_externos_admin_e_javascript_rejeitados(self):
        for mensagem in (
            "Abra https://example.com.", "Me leve para //example.com/upload.",
            "Abra javascript:alert(1)", "Abra /admin/dashboard.",
            "Abra o upload em https://example.com.",
        ):
            with self.subTest(mensagem=mensagem):
                self.assert_sem_acao(self.perguntar(mensagem, "upload"))

    def test_variantes_naturais_comandos(self):
        casos = {
            "upload": (
                "Quero que você me leve para a página de upload de compras e vendas.",
                "Me direcione para o upload.", "Me coloca na parte de envio de arquivos.",
                "Pode abrir a página de relatórios?", "Abre a área para mandar planilha.",
                "Me leve por favor para o upload.", "Me mande para o upload.",
            ),
            "dashboard": (
                "Me leve para o dashboard.", "Abra meu painel inicial.",
                "Abra a tela inicial do cliente.", "QUERO ACESSAR A VISÃO GERAL AGORA!",
                "Abra agora meu painel.", "Abra diretamente o meu dashboard.",
            ),
            "historico": (
                "Quero acessar o histórico de análises.", "Abra meus relatórios anteriores.",
            ),
            "guia": ("Acesse a página do Guia.",),
            "suporte": (
                "Quero ir para a área de suporte.", "Me direcione para a área de suporte.",
            ),
        }
        for destino, mensagens in casos.items():
            for mensagem in mensagens:
                with self.subTest(destino=destino, mensagem=mensagem):
                    self.assert_destino(self.perguntar(mensagem), destino)

    def test_variantes_informativas_nao_redirecionam(self):
        for mensagem, destino in (
            ("Como faço para acessar o upload?", "upload"),
            ("Como faço para acessar o dashboard?", "dashboard"),
            ("Existe uma página para ver análises anteriores?", "historico"),
            ("Como funciona a área de suporte?", "suporte"),
            ("Existe uma área onde eu possa enviar as planilhas de compras e vendas?", "upload"),
            ("Onde envio meus relatórios?", "upload"),
            ("Quero ver como funciona o upload.", "upload"),
            ("Preciso ver como funciona a área de suporte.", "suporte"),
            ("Quero consultar como acessar meu histórico.", "historico"),
            ("Upload: onde envio meus arquivos?", "upload"),
            ("Dashboard: como entro?", "dashboard"),
        ):
            with self.subTest(mensagem=mensagem):
                self.assert_destino(self.perguntar(mensagem), destino, "sugerir_navegacao")

    def test_variantes_contextuais(self):
        for mensagem in (
            "Então me leva pra lá.", "Quero ir pra essa página.",
            "Pode me direcionar?", "Abre esse local.", "Me manda pra lá.",
            "Quero acessar essa parte.", "Vai pra essa aba.",
            "Pode abrir?", "Então me direcione.", "Me coloca nesse local.",
        ):
            with self.subTest(mensagem=mensagem):
                self.assert_destino(self.perguntar(mensagem, "upload"), "upload")

    def test_destino_atual_tem_prioridade_sobre_contexto(self):
        self.assert_destino(self.perguntar("Quero ir para o histórico.", "upload"), "historico")
        self.assert_destino(self.perguntar("Estou no upload, me leve para histórico.", "upload"), "historico")
        self.assert_destino(self.perguntar("Me leve para guia sobre upload.", "upload"), "guia")

    def test_destino_inexistente_nao_reaproveita_contexto(self):
        for mensagem in (
            "Me leve para a página de controle de estoque físico.",
            "Me leve para página de controle estoque físico, lembra do upload?",
            "Me leve para controle de estoque upload.",
        ):
            with self.subTest(mensagem=mensagem):
                self.assert_sem_acao(self.perguntar(mensagem, "upload"))

    def test_linguagem_nao_navegacional_nao_reaproveita_la(self):
        self.assertNotEqual(
            self.perguntar("O que aconteceu lá ontem?", "upload").get("acao"), "navegar",
        )

    def test_contexto_arbitrario_nao_define_url(self):
        for contexto in ("admin", "/cliente/upload", "https://example.com", "javascript:alert(1)"):
            with self.subTest(contexto=contexto):
                self.assert_sem_acao(self.perguntar("Me leva pra lá.", contexto))

    def test_operacoes_sensiveis_nao_executadas(self):
        from models import ChamadoSuporte, Usuario
        usuarios = self.count(Usuario)
        chamados = self.count(ChamadoSuporte)
        for mensagem in (
            "Exclua todos os relatórios.", "Mude minha senha para 12345678.",
            "Execute o ETL agora.", "Envie um e-mail para outro@example.test.",
            "Crie um chamado automaticamente.",
            "Me mande para o upload e exclua todos os relatórios.",
        ):
            with self.subTest(mensagem=mensagem):
                dados = self.perguntar(mensagem, "upload")
                self.assertNotEqual(dados.get("acao"), "navegar")
        self.assertEqual(self.count(Usuario), usuarios)
        self.assertEqual(self.count(ChamadoSuporte), chamados)

    def test_topico_do_guia_ativo_permanece_fonte_do_texto(self):
        with self.app.app_context():
            self.db.session.add(self.GuiaTopico(
                categoria="Upload", pergunta="Como enviar arquivos personalizados zebratrilha?",
                resposta="Instrução personalizada do CMS: use a análise do período zebratrilha.",
            ))
            self.db.session.commit()
        dados = self.perguntar("Como enviar arquivos personalizados zebratrilha?")
        self.assert_destino(dados, "upload", "sugerir_navegacao")
        self.assertIn("Instrução personalizada do CMS", dados["resposta"])

    def test_topico_inativo_nao_integra_resposta(self):
        with self.app.app_context():
            self.db.session.add(self.GuiaTopico(
                categoria="Teste", pergunta="O que é quimeratopico?",
                resposta="CONTEUDO_INATIVO_NAO_EXIBIR", ativo=False,
            ))
            self.db.session.commit()
        dados = self.perguntar("O que é quimeratopico?")
        self.assertNotIn("CONTEUDO_INATIVO_NAO_EXIBIR", dados["resposta"])

    def test_hf_nao_possui_autoridade_para_definir_destinos(self):
        for texto in (
            "Acesse /admin/dashboard para resolver isso.",
            "Clique em https://example.com para acessar /rota-inventada.",
            '<a href="javascript:alert(1)">Abra a página</a>',
        ):
            with self.subTest(texto=texto), patch("suporte_bot._responder_hf", return_value=texto):
                self.assert_sem_acao(self.perguntar("Uma dúvida geral sobre o portal."))

    def test_json_com_tipos_invalidos_nao_resulta_em_erro_500(self):
        for payload in (
            None, [], ["upload"], 123, "upload", {"mensagem": 123},
            {"mensagem": []}, {"mensagem": {}}, {"mensagem": True},
        ):
            with self.subTest(payload=payload):
                resposta = self.client.post(
                    "/api/suporte-bot", json=payload,
                    headers={"X-CSRFToken": self.token},
                )
                self.assertEqual(resposta.status_code, 400)

    def test_contexto_nao_textual_nao_permite_navegacao(self):
        for contexto in (123, True, [], {"destino": "upload"}):
            with self.subTest(contexto=contexto):
                resposta = self.post("Me leva pra lá.", contexto)
                self.assertIn(resposta.status_code, (200, 400))
                if resposta.status_code == 200:
                    self.assert_sem_acao(resposta.get_json())

    def test_json_malformado_rejeitado(self):
        resposta = self.client.post(
            "/api/suporte-bot", data='{"mensagem":',
            content_type="application/json", headers={"X-CSRFToken": self.token},
        )
        self.assertEqual(resposta.status_code, 400)

    def test_csrf_ausente_ou_invalido_bloqueia_navegacao(self):
        for headers in ({}, {"X-CSRFToken": "token-invalido"}):
            with self.subTest(headers=headers):
                with patch("blueprints.api.responder") as responder:
                    resposta = self.client.post(
                        "/api/suporte-bot", json={"mensagem": "Abra o dashboard."},
                        headers=headers,
                    )
                    self.assertEqual(resposta.status_code, 400)
                    responder.assert_not_called()

    def test_admin_nao_acessa_endpoint(self):
        admin = self.app.test_client()
        token = self.login(admin, "admin")
        with patch("blueprints.api.responder") as responder:
            resposta = self.post("Abra o upload.", "upload", client=admin, token=token)
            self.assertEqual(resposta.status_code, 403)
            responder.assert_not_called()

    def test_anonimo_nao_acessa_endpoint_mesmo_com_contexto(self):
        anonimo = self.app.test_client()
        token = self.csrf_token(anonimo)
        with patch("blueprints.api.responder") as responder:
            resposta = self.post("Me leva pra lá.", "upload", client=anonimo, token=token)
            self.assertEqual(resposta.status_code, 302)
            self.assertIn("/auth/login", resposta.headers["Location"])
            responder.assert_not_called()

    def test_sessao_de_boot_anterior_nao_acessa_endpoint(self):
        with self.client.session_transaction() as sessao:
            sessao["boot_id"] = "boot-anterior"
        with patch("blueprints.api.responder") as responder:
            resposta = self.post("Me leva pra lá.", "upload")
            self.assertEqual(resposta.status_code, 302)
            self.assertIn("/auth/login", resposta.headers["Location"])
            responder.assert_not_called()

    def test_contexto_nao_compartilhado_entre_usuarios(self):
        self.assert_destino(self.perguntar("Onde fica o upload?"), "upload", "sugerir_navegacao")
        outro = self.app.test_client()
        token = self.login(outro, "outro")
        resposta = self.post("Me leva pra lá.", client=outro, token=token)
        self.assertEqual(resposta.status_code, 200)
        self.assert_sem_acao(resposta.get_json())

    def test_upload_sem_analise_continua_destino_legitimo(self):
        from models import Analise
        self.assertEqual(self.count(Analise), 0)
        self.assert_destino(self.perguntar("Abra o upload."), "upload")

    def test_emails_e_notificacoes_nao_inventam_rotas(self):
        for mensagem in (
            "Onde vejo os e-mails enviados?", "Como recebo as notificações?",
        ):
            with self.subTest(mensagem=mensagem):
                dados = self.perguntar(mensagem)
                self.assertNotEqual(dados.get("acao"), "navegar")
                if dados.get("destino"):
                    self.assertIn(dados["destino"], self.ENDPOINTS)

    def assert_parser_e_api(self, mensagem, destino, acao="navegar", contexto=None):
        """Verifica separadamente a classificação local e o contrato HTTP real."""
        from navegacao_bot import analisar_navegacao

        with self.subTest(camada="parser", mensagem=mensagem):
            intencao = analisar_navegacao(mensagem, contexto)
            self.assertEqual(intencao.tipo, "navegar" if acao == "navegar" else "informar")
            self.assertEqual(intencao.destino, destino)
        with self.subTest(camada="api", mensagem=mensagem):
            dados = self.perguntar(mensagem, contexto)
            self.assert_destino(dados, destino, acao)
            if acao == "navegar":
                # O frontend recebe só a ação: não há texto intermediário nem
                # um segundo botão que exija confirmação para um destino claro.
                self.assertEqual(set(dados), {"resposta", "fonte", "acao", "destino", "url"})

    def test_regressao_a_essa_pagina_de_upload(self):
        self.assert_parser_e_api("Me leve para essa página de upload.", "upload")

    def test_regressao_b_esse_local_de_upload(self):
        self.assert_parser_e_api(
            "Quero que você me direcione para esse local de upload.", "upload",
        )

    def test_regressao_c_tarefa_com_comando_de_upload(self):
        self.assert_parser_e_api(
            "Quero enviar meus arquivos, me leve para o upload.", "upload",
        )

    def test_regressao_d_consulta_com_comando_de_historico(self):
        self.assert_parser_e_api(
            "Preciso consultar minhas análises anteriores, abra o histórico.", "historico",
        )

    def test_regressao_e_chamado_com_comando_de_suporte(self):
        from models import ChamadoSuporte

        antes = self.count(ChamadoSuporte)
        self.assert_parser_e_api(
            "Quero abrir um chamado, me leve para o suporte.", "suporte",
        )
        self.assertEqual(self.count(ChamadoSuporte), antes)

    def test_demonstrativos_e_artigos_com_destino_explicito(self):
        for mensagem, destino in (
            ("Abre essa área de relatórios.", "upload"),
            ("Quero ir para aquela tela do dashboard.", "dashboard"),
            ("Me direciona para essa parte do suporte.", "suporte"),
            ("Quero acessar a página do meu histórico.", "historico"),
            ("Abra esta página do Guia.", "guia"),
            ("Me leve para este local de upload.", "upload"),
            ("Abra aquele painel inicial.", "dashboard"),
            ("ME LEVE PARA ESSA PÁGINA DO HISTÓRICO!", "historico"),
        ):
            self.assert_parser_e_api(mensagem, destino, contexto="suporte")

    def test_tarefa_pessoal_com_navegacao_explicita_nao_executa_operacao(self):
        from models import Analise, ChamadoSuporte, Notificacao, Usuario

        modelos = (Analise, ChamadoSuporte, Notificacao, Usuario)
        antes = {modelo: self.count(modelo) for modelo in modelos}
        for mensagem, destino in (
            ("Quero enviar meus arquivos, me leve para essa página de upload.", "upload"),
            ("Preciso ver meu faturamento, abra o dashboard.", "dashboard"),
            ("Quero consultar minhas análises anteriores, abra o histórico.", "historico"),
            ("Quero criar um chamado, abre a área de suporte.", "suporte"),
        ):
            self.assert_parser_e_api(mensagem, destino)
        self.assertEqual({modelo: self.count(modelo) for modelo in modelos}, antes)
        self.assertFalse(any(Path(self.temp.name, "uploads").rglob("*")))

    def test_intencao_pessoal_de_upload_oferece_orientacao(self):
        for mensagem in (
            "Quero enviar meus relatórios.",
            "Quero enviar meus arquivos.",
            "Preciso fazer o upload dos arquivos de compras.",
        ):
            self.assert_parser_e_api(mensagem, "upload", "sugerir_navegacao")

    def test_intencao_pessoal_de_chamado_so_oferece_orientacao(self):
        from models import ChamadoSuporte

        antes = self.count(ChamadoSuporte)
        self.assert_parser_e_api("Quero criar um chamado.", "suporte", "sugerir_navegacao")
        self.assertEqual(self.count(ChamadoSuporte), antes)

    def test_pedidos_de_execucao_continuam_bloqueados_mesmo_com_navegacao(self):
        from models import Analise, ChamadoSuporte, Notificacao, Usuario
        from navegacao_bot import analisar_navegacao

        modelos = (Analise, ChamadoSuporte, Notificacao, Usuario)
        antes = {modelo: self.count(modelo) for modelo in modelos}
        for mensagem in (
            "Envie os arquivos de compras para mim.",
            "Envie meus relatórios automaticamente.",
            "Quero que você envie meus arquivos, me leve para o upload.",
            "Quero que você crie um chamado, abra o suporte.",
            "Exclua minhas análises e depois abra o dashboard.",
            "Abra o dashboard e execute o ETL.",
            "Publique o relatório e abra o histórico.",
            "Quero excluir minhas análises, abra o dashboard.",
            "Apaga minhas análises e abre o dashboard.",
            "Deleta os relatórios e abre o histórico.",
            "Executa o ETL e abre dashboard.",
            "Envia meus arquivos e abre o upload.",
            "Excluir minhas análises e abra dashboard.",
            "Abra meu dashboard. Como funciona isso? Exclua minhas análises.",
            "Quero enviar meus arquivos automaticamente, me leve upload.",
            "Preciso criar chamado automaticamente, abra suporte.",
        ):
            with self.subTest(camada="parser", mensagem=mensagem):
                intencao = analisar_navegacao(mensagem, "upload")
                self.assertEqual(intencao.tipo, "operacao")
                self.assertIsNone(intencao.destino)
            with self.subTest(camada="api", mensagem=mensagem):
                self.assert_sem_acao(self.perguntar(mensagem, "upload"))
        self.assertEqual({modelo: self.count(modelo) for modelo in modelos}, antes)

    def test_perguntas_informativas_do_pedido_preservam_botao(self):
        for mensagem, destino in (
            ("Onde fica o upload?", "upload"),
            ("Como faço para acessar meu dashboard?", "dashboard"),
            ("Existe uma área para consultar meus relatórios anteriores?", "historico"),
            ("Como posso abrir um chamado?", "suporte"),
            ("Como faço para acessar o histórico?", "historico"),
        ):
            self.assert_parser_e_api(mensagem, destino, "sugerir_navegacao")

    def test_contextuais_do_pedido_exigem_contexto_valido(self):
        from navegacao_bot import analisar_navegacao

        for mensagem in (
            "Me leva pra lá.", "Pode abrir essa página?", "Quero ir pra esse local.",
            "Então me direcione.", "Me coloca nessa aba.", "Então me leve até lá.",
            "Me leva naquela aba.", "Me leve naquele local.",
        ):
            self.assert_parser_e_api(mensagem, "guia", contexto="guia")
            with self.subTest(camada="parser-sem-contexto", mensagem=mensagem):
                self.assertEqual(analisar_navegacao(mensagem).tipo, "esclarecer")
            with self.subTest(camada="api-sem-contexto", mensagem=mensagem):
                self.assert_sem_acao(self.perguntar(mensagem))

    def test_destino_do_comando_prevalece_sobre_tarefa_e_contexto(self):
        for mensagem, destino in (
            ("Estou no upload, quero abrir o histórico.", "historico"),
            ("Abra meu histórico.", "historico"),
            ("Quero abrir um chamado, me leve para o Guia.", "guia"),
            ("Quero enviar meus relatórios, abra o dashboard.", "dashboard"),
        ):
            self.assert_parser_e_api(mensagem, destino, contexto="upload")

    def test_historico_nao_se_confunde_com_pagina_de_relatorios(self):
        self.assert_parser_e_api("Abra minha área de relatórios anteriores.", "historico")

    def test_exemplo_na_explicacao_nao_impede_comando_real(self):
        for mensagem in (
            "Abra o guia para ver um exemplo.",
            "Abra o Guia para saber como usar o portal.",
        ):
            self.assert_parser_e_api(mensagem, "guia")

    def test_duas_ordens_explicitas_diferentes_pedem_esclarecimento(self):
        from navegacao_bot import analisar_navegacao

        for mensagem in (
            "Abra o upload e abra o histórico.",
            "Me leve upload ou abra dashboard.",
            "Quero ir upload ou abra dashboard.",
            "Abra upload ou quero abrir dashboard.",
            "Quero ir upload e abra dashboard.",
            "Abra upload e quero abrir dashboard.",
        ):
            with self.subTest(camada="parser", mensagem=mensagem):
                intencao = analisar_navegacao(mensagem, "upload")
                self.assertEqual(intencao.tipo, "esclarecer")
                self.assertIsNone(intencao.destino)
            with self.subTest(camada="api", mensagem=mensagem):
                self.assert_sem_acao(self.perguntar(mensagem, "upload"))

    def test_negacoes_do_pedido_nao_provocam_navegacao(self):
        from navegacao_bot import analisar_navegacao

        for mensagem in (
            "Não me leve para o upload.", "Não quero abrir o dashboard.",
            "Não me direcione para o histórico.", "Não quero abrir o histórico.",
            "Não abra essa página de upload.",
        ):
            with self.subTest(camada="parser", mensagem=mensagem):
                self.assertEqual(analisar_navegacao(mensagem, "upload").tipo, "negada")
            with self.subTest(camada="api", mensagem=mensagem):
                self.assert_sem_acao(self.perguntar(mensagem, "upload"))

    def test_regressoes_de_navegacao_nao_dependem_de_hugging_face(self):
        self.app.config["HF_API_TOKEN"] = "token-ficticio-de-teste"
        with patch("suporte_bot._responder_hf", side_effect=AssertionError("IA não deve definir rotas")) as hf:
            self.assert_parser_e_api("Me leve para essa página de upload.", "upload")
            self.assert_parser_e_api("Quero enviar meus arquivos, me leve para o upload.", "upload")
            self.assert_parser_e_api("Então me leva pra lá.", "upload", contexto="upload")
            hf.assert_not_called()

    def test_mencoes_de_comandos_nao_sao_ordens_para_navegar(self):
        from navegacao_bot import analisar_navegacao

        for mensagem in (
            "Se eu disser abra o histórico, isso vai funcionar?",
            "Você respondeu abra o histórico.",
            "A expressão abra upload é um exemplo.",
        ):
            with self.subTest(camada="parser", mensagem=mensagem):
                self.assertNotEqual(analisar_navegacao(mensagem, "upload").tipo, "navegar")
            with self.subTest(camada="api", mensagem=mensagem):
                self.assertNotEqual(self.perguntar(mensagem, "upload").get("acao"), "navegar")

    def test_primeiro_acesso_bloqueia_endpoint_ate_troca_de_senha(self):
        from models import Usuario

        with self.app.app_context():
            usuario = self.db.session.query(Usuario).filter_by(email="cliente@example.test").one()
            usuario.primeiro_acesso = True
            self.db.session.commit()
        try:
            with patch("blueprints.api.responder") as responder:
                resposta = self.post("Abra o upload.", "upload")
                self.assertEqual(resposta.status_code, 302)
                self.assertIn("/auth/primeiro-acesso", resposta.headers["Location"])
                responder.assert_not_called()
        finally:
            with self.app.app_context():
                usuario = self.db.session.query(Usuario).filter_by(email="cliente@example.test").one()
                usuario.primeiro_acesso = False
                self.db.session.commit()

    def test_conta_desativada_bloqueia_endpoint_mesmo_com_sessao(self):
        from models import Usuario

        with self.app.app_context():
            usuario = self.db.session.query(Usuario).filter_by(email="cliente@example.test").one()
            usuario.ativo = False
            self.db.session.commit()
        try:
            with patch("blueprints.api.responder") as responder:
                resposta = self.post("Abra o upload.", "upload")
                self.assertEqual(resposta.status_code, 302)
                self.assertIn("/auth/login", resposta.headers["Location"])
                responder.assert_not_called()
        finally:
            with self.app.app_context():
                usuario = self.db.session.query(Usuario).filter_by(email="cliente@example.test").one()
                usuario.ativo = True
                self.db.session.commit()

    def test_contexto_natural_a_pronome_pessoal(self):
        self.assert_parser_e_api(
            "Eu quero que você me leve para lá.", "upload", contexto="upload",
        )

    def test_contexto_natural_b_vocativo(self):
        self.assert_parser_e_api(
            "NexoBot, me leva pra lá.", "dashboard", contexto="dashboard",
        )

    def test_contexto_natural_c_interjeicao(self):
        self.assert_parser_e_api("Ah, me leva pra lá.", "historico", contexto="historico")

    def test_contexto_natural_d_coloquial(self):
        self.assert_parser_e_api(
            "Opa, pode me levar para aquela página?", "guia", contexto="guia",
        )

    def test_contexto_natural_e_pedido_educado(self):
        self.assert_parser_e_api(
            "Por favor, NexoBot, me direcione para lá.", "suporte", contexto="suporte",
        )

    def test_contexto_natural_conversa_completa_upload_e_historico(self):
        for pergunta, comando, destino in (
            (
                "Onde envio as planilhas de compras e vendas?",
                "Ah, NexoBot, eu quero que você me leve para lá.", "upload",
            ),
            (
                "Onde ficam minhas análises anteriores?",
                "Eu quero ir para essa página, por favor.", "historico",
            ),
        ):
            with self.subTest(pergunta=pergunta):
                dados = self.perguntar(pergunta)
                self.assert_destino(dados, destino, "sugerir_navegacao")
                contexto = dados["destino"]
                self.assert_parser_e_api(comando, destino, contexto=contexto)

    def test_contexto_natural_vocativos_interjeicoes_e_educacao(self):
        for mensagem in (
            "Bot, me leva pra lá.",
            "Assistente, pode abrir aquela tela?",
            "Ei, me leva para essa página.",
            "Bom, eu quero acessar essa parte.",
            "Por gentileza, me direcione para aquele lugar.",
            "NexoBot, você poderia me levar até ali?",
            "Opa, por favor, me coloca nessa aba.",
            "Me leva pra lá, NexoBot, por favor.",
            "Ah, assistente, por gentileza, pode me direcionar?",
            "EU QUERO QUE VOCÊ ME LEVE PARA LÁ!",
        ):
            self.assert_parser_e_api(mensagem, "guia", contexto="guia")

    def test_contexto_natural_sem_destino_valido_pede_esclarecimento(self):
        from navegacao_bot import analisar_navegacao

        for contexto in (None, "", "admin", "/cliente/upload", "https://example.com", "inexistente"):
            for mensagem in (
                "Eu quero que você me leve para lá.",
                "NexoBot, me leva pra lá.",
                "Ah, me leva pra lá.",
                "Opa, pode me levar para aquela página?",
                "Por favor, NexoBot, me direcione para lá.",
            ):
                with self.subTest(camada="parser", contexto=contexto, mensagem=mensagem):
                    intencao = analisar_navegacao(mensagem, contexto)
                    self.assertEqual(intencao.tipo, "esclarecer")
                    self.assertIsNone(intencao.destino)
                with self.subTest(camada="api", contexto=contexto, mensagem=mensagem):
                    self.assert_sem_acao(self.perguntar(mensagem, contexto))

    def test_contexto_natural_destino_explicito_tem_prioridade(self):
        for mensagem, destino in (
            ("NexoBot, me leva para o histórico.", "historico"),
            ("Ah, eu quero acessar meu dashboard.", "dashboard"),
            ("Por favor, me direcione para o Guia.", "guia"),
            ("Opa, quero ir para o suporte.", "suporte"),
            ("Eu quero que você me leve para o upload.", "upload"),
        ):
            self.assert_parser_e_api(mensagem, destino, contexto="guia")

    def test_contexto_natural_perguntas_com_destino_preservam_botao(self):
        for mensagem, destino in (
            ("Onde faço upload de compras e vendas?", "upload"),
            ("NexoBot, como faço para acessar meu dashboard?", "dashboard"),
            ("Ah, existe uma página para consultar minhas análises anteriores?", "historico"),
            ("Você pode me explicar onde fica a área de suporte?", "suporte"),
        ):
            self.assert_parser_e_api(mensagem, destino, "sugerir_navegacao", contexto="guia")

    def test_contexto_natural_negacoes_nao_navegam(self):
        from navegacao_bot import analisar_navegacao

        for mensagem in (
            "Ah, eu não quero ir para o upload.",
            "NexoBot, não me leve para lá.",
            "Por gentileza, não abra aquela página.",
        ):
            with self.subTest(camada="parser", mensagem=mensagem):
                self.assertEqual(analisar_navegacao(mensagem, "upload").tipo, "negada")
            with self.subTest(camada="api", mensagem=mensagem):
                self.assert_sem_acao(self.perguntar(mensagem, "upload"))

    def test_contexto_natural_perguntas_e_relatos_sem_ordem_nao_navegam(self):
        from navegacao_bot import analisar_navegacao

        for mensagem in (
            "Eu estava naquela página ontem.",
            "NexoBot, o que aconteceu lá?",
            "O que aconteceu lá ontem?",
            "NexoBot, você pode explicar o que tem naquela página?",
            "Você pode explicar como funciona aquela página?",
            "Eu quero saber o que existe nessa área.",
            "Ah, NexoBot!",
        ):
            with self.subTest(camada="parser", mensagem=mensagem):
                self.assertNotEqual(analisar_navegacao(mensagem, "upload").tipo, "navegar")
            with self.subTest(camada="api", mensagem=mensagem):
                dados = self.perguntar(mensagem, "upload")
                self.assertNotEqual(dados.get("acao"), "navegar")
                self.assertTrue(dados["resposta"].strip())
                if dados.get("destino"):
                    self.assertIn(dados["destino"], self.ENDPOINTS)

    def test_contexto_natural_hipoteses_nao_navegam(self):
        from navegacao_bot import analisar_navegacao

        for mensagem in (
            'Se eu falar "me leve para lá", você vai me direcionar?',
            'Se eu falar "me leve para o dashboard", você vai me direcionar?',
            'NexoBot, se eu disser "me leva pra lá", o que acontece?',
            'Ah, caso eu escreva "abra aquela página", isso vai funcionar?',
        ):
            with self.subTest(camada="parser", mensagem=mensagem):
                self.assertNotEqual(analisar_navegacao(mensagem, "upload").tipo, "navegar")
            with self.subTest(camada="api", mensagem=mensagem):
                self.assertNotEqual(self.perguntar(mensagem, "upload").get("acao"), "navegar")

    def test_contexto_natural_nao_descarta_substantivos_desconhecidos(self):
        from navegacao_bot import analisar_navegacao

        for mensagem in (
            "NexoBot, me leva para uma página que não existe.",
            "Ah, me leva para controle de estoque físico.",
            "Opa, abre essa página de cobrança fiscal.",
            "Eu quero ir para aquele módulo extraterrestre.",
            "Por gentileza, me leve para lá estoque.",
            "Me leva para o local do bot.",
            "Me leve para assistente.",
        ):
            with self.subTest(camada="parser", mensagem=mensagem):
                self.assertNotEqual(analisar_navegacao(mensagem, "upload").tipo, "navegar")
            with self.subTest(camada="api", mensagem=mensagem):
                self.assert_sem_acao(self.perguntar(mensagem, "upload"))

    def test_contexto_natural_nao_e_compartilhado_entre_usuarios(self):
        dados = self.perguntar("Onde faço upload de compras e vendas?")
        self.assert_destino(dados, "upload", "sugerir_navegacao")
        self.assert_parser_e_api("Ah, me leva pra lá.", "upload", contexto=dados["destino"])
        outro = self.app.test_client()
        token = self.login(outro, "outro")
        resposta = self.post("Ah, NexoBot, me leva pra lá.", client=outro, token=token)
        self.assertEqual(resposta.status_code, 200)
        self.assert_sem_acao(resposta.get_json())

    def test_contexto_natural_invalidado_nao_recupera_destino_antigo(self):
        dados = self.perguntar("Onde fica o upload?")
        self.assert_destino(dados, "upload", "sugerir_navegacao")
        self.assert_parser_e_api(
            "NexoBot, me leva pra lá.", "upload", contexto=dados["destino"],
        )
        # O widget envia só o último identificador atual; não existe um
        # histórico persistente no backend para recuperar o destino anterior.
        self.assert_sem_acao(self.perguntar("Ah, NexoBot, me leva pra lá.", None))
        self.assert_sem_acao(self.perguntar("Ah, NexoBot, me leva pra lá.", "inexistente"))

    def test_contexto_natural_preserva_bloqueio_de_operacoes(self):
        from models import Analise, ChamadoSuporte, Notificacao, Usuario
        from navegacao_bot import analisar_navegacao

        modelos = (Analise, ChamadoSuporte, Notificacao, Usuario)
        antes = {modelo: self.count(modelo) for modelo in modelos}
        for mensagem in (
            "NexoBot, exclua minhas análises.",
            "Eu quero que você envie meus relatórios automaticamente.",
            "Crie um chamado para mim sem abrir a página.",
            "Publique meus relatórios.",
            "Execute o processamento ETL.",
            "Ah, NexoBot, execute o ETL e me leve para lá.",
        ):
            with self.subTest(camada="parser", mensagem=mensagem):
                self.assertEqual(analisar_navegacao(mensagem, "upload").tipo, "operacao")
            with self.subTest(camada="api", mensagem=mensagem):
                self.assert_sem_acao(self.perguntar(mensagem, "upload"))
        self.assertEqual({modelo: self.count(modelo) for modelo in modelos}, antes)
        self.assertFalse(any(Path(self.temp.name, "uploads").rglob("*")))

    def test_contexto_natural_preserva_bloqueio_de_urls_e_admin(self):
        from navegacao_bot import analisar_navegacao

        for mensagem in (
            "NexoBot, me leve para https://example.com.",
            "Ah, abra javascript:alert(1).",
            "Opa, me leve para //example.com/upload.",
            "Por favor, abra o painel de administração.",
            "Eu quero que você me leve para /admin/dashboard.",
        ):
            with self.subTest(camada="parser", mensagem=mensagem):
                self.assertEqual(analisar_navegacao(mensagem, "upload").tipo, "bloqueada")
            with self.subTest(camada="api", mensagem=mensagem):
                self.assert_sem_acao(self.perguntar(mensagem, "upload"))

    def test_contexto_natural_nao_depende_de_hugging_face(self):
        self.app.config["HF_API_TOKEN"] = "token-ficticio-de-teste"
        with patch("suporte_bot._responder_hf", side_effect=AssertionError("IA não deve definir rotas")) as hf:
            self.assert_parser_e_api(
                "Ah, NexoBot, eu quero que você me leve para lá.", "upload", contexto="upload",
            )
            self.assert_parser_e_api("Opa, pode abrir aquela página?", "guia", contexto="guia")
            hf.assert_not_called()


if __name__ == "__main__":
    unittest.main()
