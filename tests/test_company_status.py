"""DEV-04: estados empresariais pelas rotas reais e pela infraestrutura DEV-02.

Execute: python -m unittest tests.test_company_status -v
Login/sessões de empresas CANCELADAS ficam reservados às DEV-05/DEV-06;
esta suíte verifica somente suas restrições administrativas já implementadas.
"""

from datetime import date, datetime
import unittest

from tests.support.base import IsolatedTestCase


class CompanyStatusTests(IsolatedTestCase):
    NOVA_ANALISE = "/admin/analises/nova"

    def setUp(self):
        super().setUp()
        from models import RelatorioAnalise
        from tests.support.factories import DataFactory

        self.empresas = {}
        self.usuarios = {}
        self.publicadas = {}
        with self.app.app_context():
            factory = DataFactory(self.db.session)
            admin = factory.usuario(role="ADMIN", ativo=True, primeiro_acesso=False)
            self.admin = {"id": admin.id_usuario, "email": admin.email}
            for status, plano in (("ATIVA", "BRONZE"), ("SUSPENSA", "PRATA"),
                                  ("CANCELADA", "OURO")):
                empresa = factory.empresa(
                    plano=factory.plano(plano), status_conta=status,
                    razao_social=f"Empresa sintética DEV-04 {status}",
                )
                usuario = factory.usuario(
                    empresa=empresa, ativo=True, primeiro_acesso=False,
                )
                analise = factory.analise(
                    empresa, admin=admin, status_analise="CONCLUIDO",
                    data_conclusao=datetime(2026, 1, 31, 12, 0),
                )
                titulo = f"Histórico publicado sintético {status}"
                relatorio = RelatorioAnalise(
                    id_analise=analise.id_analise, titulo=titulo,
                    resumo_executivo="Resumo de teste sem dados reais.",
                    pontos_positivos="Pontos positivos sintéticos.",
                    pontos_de_alerta="Pontos de alerta sintéticos.",
                    recomendacoes="Recomendações sintéticas.",
                    conclusao_estrategica=f"Conclusão sintética {status}.",
                    publicado=True, data_publicacao=datetime(2026, 1, 31, 12, 0),
                )
                self.db.session.add(relatorio)
                self.empresas[status] = {
                    "id": empresa.id_empresa, "plano_id": empresa.id_plano_atual,
                    "nome": empresa.razao_social,
                }
                self.usuarios[status] = {"id": usuario.id_usuario, "email": usuario.email}
                self.publicadas[status] = {"id": analise.id_analise, "titulo": titulo}
            self.db.session.commit()

    def autenticar(self, status=None):
        from tests.support.http import login

        usuario = self.admin if status is None else self.usuarios[status]
        client = self.env.create_client()
        resposta = login(client, usuario["email"])
        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(
            resposta.headers["Location"],
            "/admin/dashboard" if status is None else "/cliente/dashboard",
        )
        with client.session_transaction() as sessao:
            self.assertEqual(sessao.get("_user_id"), str(usuario["id"]))
            self.assertEqual(sessao.get("boot_id"), self.app.config["BOOT_ID"])
        return client

    def formulario(self, client, empresa_id, **campos):
        from tests.support.http import csrf_token

        dados = {
            "id_empresa": str(empresa_id), "tipo_analise": "MENSAL",
            "periodo_inicio": "2026-02-01", "periodo_fim": "2026-02-28",
            "mes_referencia": "2", "ano_referencia": "2026",
            "csrf_token": csrf_token(client, self.NOVA_ANALISE),
        }
        dados.update(campos)
        return dados

    def snapshot(self):
        """Inclui todos os campos persistidos, não apenas contagens ou status."""
        from models import Analise, Empresa, Plano, RelatorioAnalise, Usuario
        from sqlalchemy import select

        with self.app.app_context():
            return {
                model.__tablename__: tuple(
                    tuple(linha)
                    for linha in self.db.session.execute(
                        select(model.__table__).order_by(*model.__table__.primary_key.columns)
                    ).all()
                )
                for model in (Empresa, Plano, Usuario, Analise, RelatorioAnalise)
            }

    def assert_historico(self, status):
        client = self.autenticar(status)
        resposta = client.get("/cliente/historico")
        self.assertEqual(resposta.status_code, 200)
        pagina = resposta.get_data(as_text=True)
        self.assertIn(f'href="/cliente/analise/{self.publicadas[status]["id"]}"', pagina)
        for outro, analise in self.publicadas.items():
            if outro != status:
                self.assertNotIn(f'href="/cliente/analise/{analise["id"]}"', pagina)

    def assert_detalhe_publicado(self, status):
        client = self.autenticar(status)
        publicada = self.publicadas[status]
        resposta = client.get(f'/cliente/analise/{publicada["id"]}')
        self.assertEqual(resposta.status_code, 200)
        self.assertIn(publicada["titulo"], resposta.get_data(as_text=True))
        self.assertIn(f"Conclusão sintética {status}.", resposta.get_data(as_text=True))

    def assert_criacao_recusada(self, status):
        client = self.autenticar()
        dados = self.formulario(client, self.empresas[status]["id"])
        antes = self.snapshot()
        resposta = client.post(self.NOVA_ANALISE, data=dados)
        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(resposta.headers["Location"], self.NOVA_ANALISE)
        pagina = client.get(resposta.headers["Location"])
        self.assertEqual(pagina.status_code, 200)
        self.assertIn(f"Empresa em status {status}", pagina.get_data(as_text=True))
        self.assertIn("novas análises bloqueadas", pagina.get_data(as_text=True))
        self.assertEqual(self.snapshot(), antes)

    def criar_empresa_ativa(self, plano):
        from tests.support.factories import DataFactory

        with self.app.app_context():
            factory = DataFactory(self.db.session)
            empresa = factory.empresa(plano=factory.plano(plano), status_conta="ATIVA")
            resultado = {"id": empresa.id_empresa, "plano_id": empresa.id_plano_atual}
            self.db.session.commit()
        return resultado

    def analises_ids(self):
        from models import Analise

        with self.app.app_context():
            return {linha.id_analise for linha in self.db.session.query(Analise).all()}

    def assert_nova_persistida(self, resposta, antes, empresa, tipo="MENSAL", quinzena=None):
        from models import Analise

        self.assertEqual(resposta.status_code, 302)
        novos = self.analises_ids() - antes
        self.assertEqual(len(novos), 1, "O POST deve criar exatamente uma análise no banco temporário")
        ident = novos.pop()
        self.assertEqual(resposta.headers["Location"], f"/admin/analise/{ident}/upload")
        with self.app.app_context():
            analise = self.db.session.get(Analise, ident)
            self.assertEqual(analise.id_empresa, empresa["id"])
            self.assertEqual(analise.id_plano_referencia, empresa["plano_id"])
            self.assertEqual(analise.id_usuario_admin_responsavel, self.admin["id"])
            self.assertEqual(analise.tipo_analise, tipo)
            self.assertEqual(analise.quinzena_referencia, quinzena)
            self.assertEqual(analise.periodo_inicio, date(2026, 2, 16 if quinzena == 2 else 1))
            self.assertEqual(analise.periodo_fim, date(2026, 2, 15 if quinzena == 1 else 28))
            self.assertEqual(analise.mes_referencia, 2)
            self.assertEqual(analise.ano_referencia, 2026)
            self.assertEqual(analise.status_analise, "AGUARDANDO_RELATORIO")
            self.assertIsNone(analise.relatorio)
            self.assertIsNone(analise.data_conclusao)
        return ident

    def test_fixtures_respeitam_estados_planos_e_associacoes(self):
        """Três empresas distintas, CLIENTES válidos e ADMIN sem empresa."""
        from models import Analise, Empresa, Usuario

        self.assertEqual(len({e["id"] for e in self.empresas.values()}), 3)
        with self.app.app_context():
            self.assertIsNone(self.db.session.get(Usuario, self.admin["id"]).id_empresa)
            for status, plano in (("ATIVA", "BRONZE"), ("SUSPENSA", "PRATA"), ("CANCELADA", "OURO")):
                with self.subTest(status=status):
                    empresa = self.db.session.get(Empresa, self.empresas[status]["id"])
                    usuario = self.db.session.get(Usuario, self.usuarios[status]["id"])
                    analise = self.db.session.get(Analise, self.publicadas[status]["id"])
                    self.assertEqual(empresa.status_conta, status)
                    self.assertIsNone(empresa.deletado_em)
                    self.assertEqual(empresa.plano_atual.nome_plano, plano)
                    self.assertEqual(usuario.id_empresa, empresa.id_empresa)
                    self.assertEqual(usuario.role, "CLIENTE")
                    self.assertTrue(usuario.ativo)
                    self.assertFalse(usuario.primeiro_acesso)
                    self.assertEqual(analise.id_empresa, empresa.id_empresa)
                    self.assertEqual(analise.id_plano_referencia, empresa.id_plano_atual)
                    self.assertEqual(analise.status_analise, "CONCLUIDO")
                    self.assertTrue(analise.relatorio.publicado)

    def test_ativa_cliente_realiza_login(self):
        """CLIENTE ativo de empresa ATIVA recebe sessão autenticada real."""
        self.autenticar("ATIVA")

    def test_ativa_cliente_acessa_dashboard(self):
        """Empresa ATIVA acessa seu dashboard autorizado."""
        resposta = self.autenticar("ATIVA").get("/cliente/dashboard")
        self.assertEqual(resposta.status_code, 200)
        self.assertIn(self.empresas["ATIVA"]["nome"], resposta.get_data(as_text=True))

    def test_ativa_historico_lista_publicadas_da_propria_empresa(self):
        """Histórico ATIVA inclui publicação própria e exclui outras empresas."""
        self.assert_historico("ATIVA")

    def test_ativa_cliente_consulta_detalhe_publicado(self):
        """Detalhe próprio CONCLUIDO/publicado fica acessível à empresa ATIVA."""
        self.assert_detalhe_publicado("ATIVA")

    def test_admin_cria_mensal_para_ativa_com_campos_persistidos(self):
        """POST real cria análise MENSAL, plano/admin/período e estado inicial corretos."""
        client = self.autenticar()
        empresa = self.empresas["ATIVA"]
        dados = self.formulario(client, empresa["id"])
        antes = self.analises_ids()
        resposta = client.post(self.NOVA_ANALISE, data=dados)
        self.assert_nova_persistida(resposta, antes, empresa)

    def test_criacao_para_ativa_preserva_outros_dados_e_historicos(self):
        """Criação válida mantém empresas, planos, usuários e históricos anteriores."""
        client = self.autenticar()
        dados = self.formulario(client, self.empresas["ATIVA"]["id"])
        antes = self.snapshot()
        ids = self.analises_ids()
        resposta = client.post(self.NOVA_ANALISE, data=dados)
        novo_id = self.assert_nova_persistida(resposta, ids, self.empresas["ATIVA"])
        depois = self.snapshot()
        for tabela in ("empresa", "plano", "usuario", "relatorio_analise"):
            self.assertEqual(depois[tabela], antes[tabela], tabela)
        self.assertEqual(tuple(linha for linha in depois["analise"] if linha[0] != novo_id), antes["analise"])

    def test_suspensa_cliente_realiza_login(self):
        """SUSPENSA não se confunde com usuário individualmente inativo."""
        self.autenticar("SUSPENSA")

    def test_suspensa_cliente_acessa_dashboard(self):
        """SUSPENSA preserva acesso autorizado para consultar o dashboard."""
        resposta = self.autenticar("SUSPENSA").get("/cliente/dashboard")
        self.assertEqual(resposta.status_code, 200)
        self.assertIn(self.empresas["SUSPENSA"]["nome"], resposta.get_data(as_text=True))

    def test_suspensa_historico_lista_publicadas_da_propria_empresa(self):
        """SUSPENSA consulta histórico realmente publicado da própria empresa."""
        self.assert_historico("SUSPENSA")

    def test_suspensa_cliente_consulta_detalhe_publicado(self):
        """SUSPENSA continua consultando o detalhe de uma devolutiva publicada."""
        self.assert_detalhe_publicado("SUSPENSA")

    def test_suspensa_recusa_nova_analise_sem_alterar_dados(self):
        """ADMIN recebe recusa SUSPENSA sem inserir/modificar registros ou status."""
        self.assert_criacao_recusada("SUSPENSA")

    def test_cancelada_recusa_nova_analise_sem_alterar_dados(self):
        """ADMIN recebe recusa CANCELADA preservando histórico e demais empresas."""
        self.assert_criacao_recusada("CANCELADA")

    def test_admin_mantem_permissoes_apos_recusas_empresariais(self):
        """Recusas SUSPENSA/CANCELADA não retiram permissões gerais do ADMIN."""
        client = self.autenticar()
        for status in ("SUSPENSA", "CANCELADA"):
            dados = self.formulario(client, self.empresas[status]["id"])
            antes = self.snapshot()
            resposta = client.post(self.NOVA_ANALISE, data=dados)
            self.assertEqual(resposta.headers["Location"], self.NOVA_ANALISE)
            self.assertEqual(self.snapshot(), antes)
        self.assertEqual(client.get("/admin/dashboard").status_code, 200)
        self.assertEqual(client.get("/admin/empresas").status_code, 200)
        dados = self.formulario(client, self.empresas["ATIVA"]["id"])
        antes = self.analises_ids()
        resposta = client.post(self.NOVA_ANALISE, data=dados)
        self.assert_nova_persistida(resposta, antes, self.empresas["ATIVA"])
        with client.session_transaction() as sessao:
            self.assertEqual(sessao.get("_user_id"), str(self.admin["id"]))

    def test_historico_e_detalhe_exigem_conclusao_e_publicacao(self):
        """CONCLUIDO sem publicação e publicado sem CONCLUIDO não ficam visíveis."""
        from models import Empresa, RelatorioAnalise, Usuario
        from tests.support.factories import DataFactory

        for status in ("ATIVA", "SUSPENSA"):
            with self.app.app_context():
                factory = DataFactory(self.db.session)
                empresa = self.db.session.get(Empresa, self.empresas[status]["id"])
                admin = self.db.session.get(Usuario, self.admin["id"])
                ocultas = []
                for estado, publicado in (("CONCLUIDO", False), ("EM_ANALISE", True)):
                    analise = factory.analise(empresa, admin=admin, status_analise=estado)
                    self.db.session.add(RelatorioAnalise(
                        id_analise=analise.id_analise, titulo="Relatório oculto sintético",
                        conclusao_estrategica="Conteúdo não disponibilizado.", publicado=publicado,
                    ))
                    ocultas.append(analise.id_analise)
                self.db.session.commit()
            client = self.autenticar(status)
            resposta = client.get("/cliente/historico")
            self.assertEqual(resposta.status_code, 200)
            pagina = resposta.get_data(as_text=True)
            self.assertIn(f'href="/cliente/analise/{self.publicadas[status]["id"]}"', pagina)
            for ident in ocultas:
                with self.subTest(status=status, analise=ident):
                    self.assertNotIn(f'href="/cliente/analise/{ident}"', pagina)
                    self.assertEqual(client.get(f"/cliente/analise/{ident}").status_code, 404)

    def test_detalhe_de_outra_empresa_nao_fica_acessivel(self):
        """Consulta autorizada não libera detalhe publicado de outra empresa."""
        for status in ("ATIVA", "SUSPENSA"):
            client = self.autenticar(status)
            for outro, analise in self.publicadas.items():
                if outro != status:
                    with self.subTest(cliente=status, empresa=outro):
                        self.assertEqual(client.get(f'/cliente/analise/{analise["id"]}').status_code, 404)

    def test_nova_analise_sem_csrf_real_e_bloqueada(self):
        """POST de ADMIN sem CSRF recebe HTTP 400 e não altera dados."""
        client = self.autenticar()
        dados = self.formulario(client, self.empresas["ATIVA"]["id"])
        dados.pop("csrf_token")
        antes = self.snapshot()
        self.assertTrue(self.app.config["WTF_CSRF_ENABLED"])
        self.assertEqual(client.post(self.NOVA_ANALISE, data=dados).status_code, 400)
        self.assertEqual(self.snapshot(), antes)

    def test_usuario_inativo_nao_inicia_sessao_em_ativa_ou_suspensa(self):
        """Inativação individual impede login sem modificar o estado empresarial."""
        from models import Usuario
        from tests.support.http import login

        for status in ("ATIVA", "SUSPENSA"):
            with self.app.app_context():
                usuario = self.db.session.get(Usuario, self.usuarios[status]["id"])
                usuario.ativo = False
                self.db.session.commit()
            antes = self.snapshot()
            client = self.env.create_client()
            resposta = login(client, self.usuarios[status]["email"])
            with self.subTest(status=status):
                self.assertEqual(resposta.status_code, 200)
                self.assertIn("conta está desativada", resposta.get_data(as_text=True))
                with client.session_transaction() as sessao:
                    self.assertNotIn("_user_id", sessao)
                protegida = client.get("/cliente/dashboard")
                self.assertEqual(protegida.status_code, 302)
                self.assertIn("/auth/login", protegida.headers["Location"])
                self.assertEqual(self.snapshot(), antes)

    def test_primeiro_acesso_respeita_fluxo_em_ativa_ou_suspensa(self):
        """Primeiro acesso pendente encaminha consultas para a troca de senha."""
        from models import Usuario

        for status in ("ATIVA", "SUSPENSA"):
            with self.app.app_context():
                usuario = self.db.session.get(Usuario, self.usuarios[status]["id"])
                usuario.primeiro_acesso = True
                self.db.session.commit()
            client = self.autenticar(status)
            for path in ("/cliente/dashboard", "/cliente/historico"):
                with self.subTest(status=status, path=path):
                    resposta = client.get(path)
                    self.assertEqual(resposta.status_code, 302)
                    self.assertEqual(resposta.headers["Location"], "/auth/primeiro-acesso")
            self.assertEqual(client.get("/auth/primeiro-acesso").status_code, 200)
            with self.app.app_context():
                self.assertTrue(self.db.session.get(Usuario, self.usuarios[status]["id"]).primeiro_acesso)

    def test_lixeira_e_cancelamento_sao_estados_distintos(self):
        """deletado_em separa listagens/lixeira sem converter ATIVA em CANCELADA."""
        from models import Empresa

        with self.app.app_context():
            empresa = self.db.session.get(Empresa, self.empresas["ATIVA"]["id"])
            empresa.deletado_em = datetime(2026, 2, 1, 12, 0)
            self.db.session.commit()
        client = self.autenticar()
        empresas = client.get("/admin/empresas")
        lixeira = client.get("/admin/lixeira")
        self.assertEqual(empresas.status_code, 200)
        self.assertEqual(lixeira.status_code, 200)
        self.assertNotIn(self.empresas["ATIVA"]["nome"], empresas.get_data(as_text=True))
        self.assertIn(self.empresas["CANCELADA"]["nome"], empresas.get_data(as_text=True))
        self.assertIn(self.empresas["ATIVA"]["nome"], lixeira.get_data(as_text=True))
        self.assertNotIn(self.empresas["CANCELADA"]["nome"], lixeira.get_data(as_text=True))
        with self.app.app_context():
            ativa = self.db.session.get(Empresa, self.empresas["ATIVA"]["id"])
            cancelada = self.db.session.get(Empresa, self.empresas["CANCELADA"]["id"])
            self.assertEqual(ativa.status_conta, "ATIVA")
            self.assertIsNotNone(ativa.deletado_em)
            self.assertEqual(cancelada.status_conta, "CANCELADA")
            self.assertIsNone(cancelada.deletado_em)

    def test_quinzenal_ouro_aceita_quinzenas_validas(self):
        """Empresa ATIVA/OURO aceita quinzenas 1 e 2 com períodos persistidos."""
        empresa = self.criar_empresa_ativa("OURO")
        client = self.autenticar()
        for quinzena in (1, 2):
            with self.subTest(quinzena=quinzena):
                dados = self.formulario(
                    client, empresa["id"], tipo_analise="QUINZENAL",
                    quinzena_referencia=str(quinzena),
                    periodo_inicio=f"2026-02-{'16' if quinzena == 2 else '01'}",
                    periodo_fim=f"2026-02-{'15' if quinzena == 1 else '28'}",
                )
                antes = self.analises_ids()
                resposta = client.post(self.NOVA_ANALISE, data=dados)
                self.assert_nova_persistida(resposta, antes, empresa, "QUINZENAL", quinzena)

    def test_quinzenal_bronze_e_prata_nao_criam_registros(self):
        """Somente OURO pode receber QUINZENAL, mesmo quando a empresa está ATIVA."""
        empresas = (self.empresas["ATIVA"], self.criar_empresa_ativa("PRATA"))
        client = self.autenticar()
        for empresa in empresas:
            with self.subTest(empresa=empresa["id"]):
                dados = self.formulario(
                    client, empresa["id"], tipo_analise="QUINZENAL", quinzena_referencia="1",
                    periodo_fim="2026-02-15",
                )
                antes = self.snapshot()
                resposta = client.post(self.NOVA_ANALISE, data=dados)
                self.assertEqual(resposta.status_code, 302)
                self.assertEqual(resposta.headers["Location"], self.NOVA_ANALISE)
                pagina = client.get(self.NOVA_ANALISE).get_data(as_text=True)
                self.assertIn("apenas para empresas do plano OURO", pagina)
                self.assertEqual(self.snapshot(), antes)

    def test_quinzenal_ouro_recusa_quinzena_invalida(self):
        """OURO recusa quinzena ausente, fora de 1/2 ou não numérica, sem efeitos."""
        empresa = self.criar_empresa_ativa("OURO")
        client = self.autenticar()
        for quinzena in (None, "", "0", "3", "invalida"):
            with self.subTest(quinzena=quinzena):
                dados = self.formulario(
                    client, empresa["id"], tipo_analise="QUINZENAL", periodo_fim="2026-02-15",
                )
                if quinzena is not None:
                    dados["quinzena_referencia"] = quinzena
                antes = self.snapshot()
                resposta = client.post(self.NOVA_ANALISE, data=dados)
                self.assertEqual(resposta.status_code, 302)
                self.assertEqual(resposta.headers["Location"], self.NOVA_ANALISE)
                self.assertEqual(self.snapshot(), antes)

    def test_cliente_nao_ganha_permissao_para_criar_analise(self):
        """CLIENTES ATIVA/SUSPENSA não podem executar a rota administrativa."""
        from tests.support.http import csrf_token

        for status in ("ATIVA", "SUSPENSA"):
            client = self.autenticar(status)
            dados = {
                "id_empresa": str(self.empresas[status]["id"]), "tipo_analise": "MENSAL",
                "periodo_inicio": "2026-02-01", "periodo_fim": "2026-02-28",
                "mes_referencia": "2", "ano_referencia": "2026",
                "csrf_token": csrf_token(client, "/cliente/dashboard"),
            }
            antes = self.snapshot()
            with self.subTest(status=status):
                self.assertEqual(client.post(self.NOVA_ANALISE, data=dados).status_code, 403)
                self.assertEqual(self.snapshot(), antes)


if __name__ == "__main__":
    unittest.main()
