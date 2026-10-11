"""Comprova a infraestrutura DEV-02 sem antecipar correções de negócio.

Todos os dados são sintéticos; somente bancos e arquivos temporários são usados.
Execute com ``python -m unittest tests.test_infrastructure -v``.
"""

import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import textwrap
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from tests.support.base import IsolatedTestCase
from tests.support.environment import TestEnvironment


class InfrastructureTests(IsolatedTestCase):
    def factory(self):
        # Modelos são importados pelas fábricas somente após o ambiente seguro.
        from tests.support.factories import DataFactory
        return DataFactory(self.db.session)

    def criar_usuario(self, role="CLIENTE"):
        with self.app.app_context():
            usuario = self.factory().usuario(role=role)
            email = usuario.email
            ident = usuario.id_usuario
            self.db.session.commit()
        return email, ident

    def test_flask_real_com_configuracao_de_teste(self):
        self.assertTrue(self.app.config["TESTING"])
        self.assertFalse(self.app.config["DEBUG"])
        self.assertFalse(self.app.config["SQLALCHEMY_ECHO"])
        self.assertTrue(self.app.config["WTF_CSRF_ENABLED"])
        self.assertEqual(set(self.app.blueprints), {
            "auth", "admin", "cliente", "notificacoes", "api",
        })
        endpoints = {regra.endpoint for regra in self.app.url_map.iter_rules()}
        self.assertTrue({"auth.login", "cliente.dashboard", "admin.dashboard",
                         "api.suporte_bot", "healthz"}.issubset(endpoints))
        resposta = self.env.create_client().get("/healthz")
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.get_json(), {"status": "ok"})

    def test_engine_real_aponta_para_arquivo_temporario(self):
        with self.app.app_context():
            self.assertEqual(self.db.engine.dialect.name, "sqlite")
            banco = Path(self.db.engine.url.database).resolve()
        self.assertEqual(banco, self.env.database_path)
        self.assertTrue(banco.is_file())
        self.assertTrue(banco.is_relative_to(self.env.root))
        self.assertNotEqual(banco, Path(__file__).resolve().parents[1] / "instance/nexo_mvp.db")
        self.assertTrue(Path(self.app.instance_path).is_relative_to(self.env.root))
        self.assertEqual(Path(self.app.config["UPLOAD_FOLDER"]), self.env.uploads_path)

    def test_schema_temporario_usa_os_treze_modelos_existentes(self):
        from sqlalchemy import inspect
        with self.app.app_context():
            tabelas = set(inspect(self.db.engine).get_table_names())
        self.assertEqual(tabelas, {
            "plano", "segmento", "empresa", "usuario", "analise",
            "upload_relatorio", "indicador_analise", "relatorio_analise",
            "produto_curva_abc", "chamado_suporte", "mensagem_suporte",
            "notificacao", "guia_topico",
        })

    def test_fk_ativa_rejeita_referencia_inexistente(self):
        from sqlalchemy import text
        from sqlalchemy.exc import IntegrityError
        with self.app.app_context():
            self.assertEqual(self.db.session.execute(text("PRAGMA foreign_keys")).scalar(), 1)
            empresa = self.factory().empresa()
            empresa.id_segmento = 99999999
            with self.assertRaises(IntegrityError):
                self.db.session.flush()
            self.db.session.rollback()

    def test_fabricas_criam_planos_e_empresas_independentes(self):
        with self.app.app_context():
            factory = self.factory()
            planos = {nome: factory.plano(nome) for nome in ("BRONZE", "PRATA", "OURO")}
            empresas = [
                factory.empresa(plano=planos[nome], status_conta=status)
                for nome, status in zip(planos, ("ATIVA", "SUSPENSA", "CANCELADA"))
            ]
            self.assertEqual(len({e.id_empresa for e in empresas}), 3)
            self.assertEqual(len({e.cnpj for e in empresas}), 3)
            self.assertEqual(len({e.email_contato for e in empresas}), 3)
            self.assertEqual([e.status_conta for e in empresas], ["ATIVA", "SUSPENSA", "CANCELADA"])
            self.assertEqual(planos["OURO"].tipo_analise_permitida, "QUINZENAL")
            self.assertEqual(planos["BRONZE"].tipo_analise_permitida, "MENSAL")
            self.assertEqual(planos["PRATA"].tipo_analise_permitida, "MENSAL")
            self.db.session.commit()

    def test_fabricas_respeitam_associacoes_e_criam_analises_validas(self):
        from tests.support.factories import TEST_PASSWORD
        with self.app.app_context():
            factory = self.factory()
            empresa_a = factory.empresa()
            empresa_b = factory.empresa(plano=factory.plano("OURO"))
            admin = factory.usuario(role="ADMIN")
            cliente_a = factory.usuario(empresa=empresa_a)
            cliente_b = factory.usuario(empresa=empresa_b)
            self.assertIsNone(admin.id_empresa)
            self.assertEqual(cliente_a.id_empresa, empresa_a.id_empresa)
            self.assertEqual(cliente_b.id_empresa, empresa_b.id_empresa)
            self.assertTrue(cliente_a.check_senha(TEST_PASSWORD))
            self.assertFalse(cliente_a.primeiro_acesso)
            mensal = factory.analise(empresa_a, admin=admin)
            quinzenal = factory.analise(
                empresa_b, admin=admin, tipo_analise="QUINZENAL", quinzena_referencia=1,
            )
            self.assertEqual(mensal.id_empresa, empresa_a.id_empresa)
            self.assertEqual(mensal.id_usuario_admin_responsavel, admin.id_usuario)
            self.assertEqual(mensal.id_plano_referencia, empresa_a.id_plano_atual)
            self.assertEqual(mensal.tipo_analise, "MENSAL")
            self.assertIsNone(mensal.quinzena_referencia)
            self.assertEqual(quinzenal.quinzena_referencia, 1)
            self.db.session.commit()

    def test_fabricas_nao_executam_commit_oculto(self):
        from models import Empresa, Plano, Segmento, Usuario, Analise
        with self.app.app_context():
            factory = self.factory()
            empresa = factory.empresa()
            factory.usuario(empresa=empresa)
            factory.analise(empresa)
            self.assertEqual(self.db.session.query(Empresa).count(), 1)
            self.db.session.rollback()
            for modelo in (Empresa, Plano, Segmento, Usuario, Analise):
                with self.subTest(modelo=modelo.__name__):
                    self.assertEqual(self.db.session.query(modelo).count(), 0)

    def test_fabricas_permitam_personalizacao_sem_reduzir_constraints(self):
        from sqlalchemy.exc import IntegrityError
        with self.app.app_context():
            factory = self.factory()
            empresa = factory.empresa(razao_social="Empresa Sintética Personalizada")
            cliente = factory.usuario(empresa=empresa, nome="Cliente Sintético", ativo=False)
            self.assertEqual(empresa.razao_social, "Empresa Sintética Personalizada")
            self.assertEqual(cliente.nome, "Cliente Sintético")
            self.assertFalse(cliente.ativo)
            plano = empresa.plano_atual
            segmento = empresa.segmento
            outro_plano = factory.plano("PRATA")
            outro_segmento = factory.segmento()
            outra_empresa = factory.empresa(
                id_plano_atual=plano.id_plano, id_segmento=segmento.id_segmento,
            )
            self.assertEqual(outra_empresa.id_plano_atual, plano.id_plano)
            self.assertEqual(outra_empresa.id_segmento, segmento.id_segmento)
            admin = factory.usuario(role="ADMIN")
            outro_admin = factory.usuario(role="ADMIN")
            analise = factory.analise(
                empresa, id_usuario_admin_responsavel=admin.id_usuario,
            )
            self.assertEqual(analise.id_usuario_admin_responsavel, admin.id_usuario)
            casos = (
                (factory.empresa, (), {"plano": plano, "id_plano_atual": outro_plano.id_plano}),
                (factory.empresa, (), {"segmento": segmento, "id_segmento": outro_segmento.id_segmento}),
                (factory.analise, (empresa,), {"admin": admin, "id_empresa": outra_empresa.id_empresa}),
                (factory.analise, (empresa,), {"admin": admin, "id_plano_referencia": outro_plano.id_plano}),
                (factory.analise, (empresa,), {"admin": admin, "id_usuario_admin_responsavel": outro_admin.id_usuario}),
            )
            for criar, args, attrs in casos:
                with self.subTest(fabrica=criar.__name__, atributos=tuple(attrs)):
                    with self.assertRaises(ValueError):
                        criar(*args, **attrs)
            cliente.role = "ADMIN"  # ADMIN com empresa viola o CHECK existente.
            with self.assertRaises(IntegrityError):
                self.db.session.flush()
            self.db.session.rollback()

    def test_aplicacoes_sequenciais_nao_herdam_dados(self):
        from models import Empresa
        with TestEnvironment() as primeiro:
            with primeiro.app.app_context():
                from tests.support.factories import DataFactory
                DataFactory(primeiro.db.session).empresa()
                primeiro.db.session.commit()
                self.assertEqual(primeiro.db.session.query(Empresa).count(), 1)
            primeiro_banco = primeiro.database_path
        self.assertFalse(primeiro.root.exists())
        with TestEnvironment() as segundo:
            with segundo.app.app_context():
                self.assertEqual(segundo.db.session.query(Empresa).count(), 0)
            self.assertNotEqual(primeiro_banco, segundo.database_path)

    def test_contextos_aninhados_selecionam_o_banco_correto(self):
        from flask import current_app
        from models import Empresa
        from tests.support.factories import DataFactory
        with self.app.app_context():
            DataFactory(self.db.session).empresa(razao_social="Ambiente externo")
            self.db.session.commit()
            engine_externo = self.db.engine
            with TestEnvironment() as interno:
                with interno.app.app_context():
                    self.assertIs(current_app._get_current_object(), interno.app)
                    self.assertIsNot(self.db.engine, engine_externo)
                    self.assertEqual(self.db.session.query(Empresa).count(), 0)
                    DataFactory(self.db.session).empresa(razao_social="Ambiente interno")
                    self.db.session.commit()
            self.assertIs(current_app._get_current_object(), self.app)
            self.assertIs(self.db.engine, engine_externo)
            self.assertEqual(self.db.session.query(Empresa).one().razao_social, "Ambiente externo")

    def test_limpeza_fecha_conexao_e_remove_arquivos(self):
        with self.app.app_context():
            with self.db.engine.connect() as conexao:
                driver = conexao.connection.driver_connection
        marcador = self.env.uploads_path / "arquivo-sintetico.txt"
        marcador.write_text("somente teste", encoding="utf-8")
        self.env.close()
        self.assertFalse(self.env.root.exists())
        with self.assertRaises(sqlite3.ProgrammingError):
            driver.execute("SELECT 1")
        self.env.close()  # cleanup também pode ser chamado pelo unittest.

    def test_extensoes_e_handlers_restaurados_apos_ambiente_aninhado(self):
        from extensions import limiter, socketio
        servidor_externo = socketio.server
        handlers_externos = {
            namespace: eventos.copy()
            for namespace, eventos in servidor_externo.handlers.items()
        }
        limiter_ativo = limiter.enabled
        self.assertTrue({"connect", "disconnect"}.issubset(handlers_externos["/"]))
        self.assertIs(socketio.emit, self.env.services.socket_emit)
        with TestEnvironment(csrf_enabled=False) as interno:
            self.assertIsNot(socketio.server, servidor_externo)
            self.assertTrue({"connect", "disconnect"}.issubset(socketio.server.handlers["/"]))
            self.assertIs(socketio.emit, interno.services.socket_emit)
            self.assertFalse(interno.app.config["WTF_CSRF_ENABLED"])
        self.assertIs(socketio.server, servidor_externo)
        self.assertEqual(socketio.server.handlers, handlers_externos)
        self.assertEqual(limiter.enabled, limiter_ativo)
        self.assertIs(socketio.emit, self.env.services.socket_emit)
        self.assertTrue(self.app.config["WTF_CSRF_ENABLED"])
        # As extensões reais continuam protegendo o app externo, sem token.
        resposta = self.env.create_client().post("/auth/login", data={
            "email": "inexistente@example.test", "senha": "somente-teste",
        })
        self.assertEqual(resposta.status_code, 400)

    def test_erro_no_corpo_do_teste_nao_impede_limpeza(self):
        ambiente = TestEnvironment()
        with self.assertRaisesRegex(RuntimeError, "erro sintético do teste"):
            with ambiente:
                marcador = ambiente.uploads_path / "arquivo.txt"
                marcador.write_text("teste", encoding="utf-8")
                raise RuntimeError("erro sintético do teste")
        self.assertFalse(ambiente.root.exists())
        self.assertEqual(self.env.create_client().get("/healthz").status_code, 200)

    def test_falha_na_inicializacao_libera_recursos_e_propaga_erro(self):
        ambiente = TestEnvironment()
        with patch.object(self.db, "create_all", side_effect=RuntimeError("falha sintética do schema")):
            with self.assertRaisesRegex(RuntimeError, "falha sintética do schema"):
                ambiente.start()
        self.assertIsNotNone(ambiente.root)
        self.assertFalse(ambiente.root.exists())
        self.assertEqual(self.env.create_client().get("/healthz").status_code, 200)

    def test_credenciais_hostis_sao_sobrepostas_e_ambiente_restaurado(self):
        hostil = {
            "DATABASE_URL": "postgresql://fake:fake@runtime.invalid/nexo",
            "DIRECT_URL": "postgresql://fake:fake@direct.invalid/nexo",
            "NEXO_DB_DIRECT": "1", "SECRET_KEY": "dev02-chave-hostil-ficticia",
            "ANTHROPIC_API_KEY": "dev02-ant-hostil-ficticia",
            "HF_API_TOKEN": "dev02-hf-hostil-ficticio",
            "MAIL_USERNAME": "fake@external.invalid", "MAIL_PASSWORD": "dev02-mail-ficticia",
        }
        with patch.dict(os.environ, hostil):
            with TestEnvironment() as ambiente:
                with ambiente.app.app_context():
                    self.assertEqual(Path(ambiente.db.engine.url.database), ambiente.database_path)
                    self.assertEqual(ambiente.db.engine.dialect.name, "sqlite")
                self.assertNotEqual(ambiente.app.config["SECRET_KEY"], hostil["SECRET_KEY"])
                self.assertIsNone(ambiente.app.config["ANTHROPIC_API_KEY"])
                self.assertIsNone(ambiente.app.config["HF_API_TOKEN"])
                self.assertIsNone(ambiente.app.config["MAIL_PASSWORD"])
            for nome, valor in hostil.items():
                self.assertEqual(os.environ[nome], valor)

    def test_primeira_importacao_sem_secret_key_ignora_dotenv_e_urls_remotas(self):
        # Processo limpo comprova o caminho anterior à importação de config.py;
        # não herda chaves comerciais, nem depende do cache de módulos da suíte.
        codigo = textwrap.dedent("""
            from pathlib import Path
            from unittest.mock import patch
            from tests.support.environment import TestEnvironment
            with patch('dotenv.load_dotenv', side_effect=AssertionError('dotenv real foi lido')) as leitura:
                with TestEnvironment() as env:
                    with env.app.app_context():
                        assert env.db.engine.dialect.name == 'sqlite'
                        assert Path(env.db.engine.url.database) == env.database_path
                    assert env.app.config['SECRET_KEY']
                    assert env.app.config['ANTHROPIC_API_KEY'] is None
                    assert env.app.config['HF_API_TOKEN'] is None
                    assert env.app.config['MAIL_PASSWORD'] is None
                assert not env.root.exists()
                leitura.assert_not_called()
            print('cold-start-isolated')
        """)
        ambiente = {nome: os.environ[nome] for nome in (
            "PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "LANG",
        ) if nome in os.environ}
        ambiente.update({
            "PYTHONDONTWRITEBYTECODE": "1",
            "DATABASE_URL": "postgresql://fake:fake@runtime.invalid/nexo",
            "DIRECT_URL": "postgresql://fake:fake@direct.invalid/nexo",
            "NEXO_DB_DIRECT": "1", "MAIL_PASSWORD": "dev02-fake-mail",
            "ANTHROPIC_API_KEY": "dev02-fake-ant", "HF_API_TOKEN": "dev02-fake-hf",
        })
        self.assertNotIn("SECRET_KEY", ambiente)
        resultado = subprocess.run(
            [sys.executable, "-B", "-c", codigo],
            cwd=Path(__file__).resolve().parents[1], env=ambiente,
            capture_output=True, text=True, timeout=30, check=False,
        )
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        self.assertEqual(resultado.stdout.strip(), "cold-start-isolated")

    def test_clientes_http_tem_cookies_independentes_e_login_logout_reais(self):
        from tests.support.http import login, logout
        from tests.support.factories import TEST_PASSWORD
        with self.app.app_context():
            factory = self.factory()
            usuarios = [factory.usuario(), factory.usuario(), factory.usuario(role="ADMIN")]
            contas = [(usuario.email, usuario.id_usuario) for usuario in usuarios]
            self.db.session.commit()
        clientes = [self.env.create_client() for _ in contas]
        for cliente, (email, ident), destino in zip(clientes, contas, (
            "/cliente/dashboard", "/cliente/dashboard", "/admin/dashboard",
        )):
            resposta = login(cliente, email, senha=TEST_PASSWORD)
            self.assertEqual(resposta.status_code, 302)
            self.assertTrue(resposta.headers["Location"].endswith(destino))
            with cliente.session_transaction() as sessao:
                self.assertEqual(sessao["_user_id"], str(ident))
                self.assertEqual(sessao["boot_id"], self.app.config["BOOT_ID"])
        self.assertEqual(logout(clientes[0]).status_code, 302)
        with clientes[0].session_transaction() as sessao:
            self.assertNotIn("_user_id", sessao)
        for cliente, (_, ident) in zip(clientes[1:], contas[1:]):
            with cliente.session_transaction() as sessao:
                self.assertEqual(sessao["_user_id"], str(ident))
        anonimo = self.env.create_client()
        with anonimo.session_transaction() as sessao:
            self.assertNotIn("_user_id", sessao)

    def test_csrf_real_aceita_token_valido_e_rejeita_ausente_ou_invalido(self):
        from tests.support.http import csrf_token, login
        email, _ = self.criar_usuario()
        cliente = self.env.create_client()
        self.assertEqual(login(cliente, email).status_code, 302)
        token = csrf_token(cliente, path="/cliente/dashboard")
        resposta = cliente.post(
            "/api/suporte-bot", json={"mensagem": "Olá!"},
            headers={"X-CSRFToken": token},
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertIsInstance(resposta.get_json()["resposta"], str)
        for headers in ({}, {"X-CSRFToken": "token-sintetico-invalido"}):
            with self.subTest(headers=headers):
                self.assertEqual(cliente.post(
                    "/api/suporte-bot", json={"mensagem": "Olá!"}, headers=headers,
                ).status_code, 400)

    def test_csrf_so_pode_ser_desativado_explicitamente_por_ambiente(self):
        self.assertTrue(self.app.config["WTF_CSRF_ENABLED"])
        with TestEnvironment(csrf_enabled=False) as sem_csrf:
            self.assertFalse(sem_csrf.app.config["WTF_CSRF_ENABLED"])
            resposta = sem_csrf.create_client().post("/auth/login", data={
                "email": "inexistente@example.test", "senha": "somente-teste",
            })
            self.assertEqual(resposta.status_code, 200)
        self.assertTrue(self.app.config["WTF_CSRF_ENABLED"])

    def test_storage_grava_le_resolve_e_remove_somente_arquivo_temporario(self):
        import storage
        conteudo = b"produto;quantidade\nProduto sintetico;2\n"
        with self.app.app_context():
            referencia = storage.salvar(conteudo, "relatorio-sintetico.csv")
            caminho = Path(referencia).resolve()
            self.assertTrue(caminho.is_relative_to(self.env.uploads_path))
            self.assertEqual(caminho.read_bytes(), conteudo)
            self.assertEqual(Path(storage.resolver(referencia)), caminho)
            storage.remover(referencia)
            self.assertFalse(caminho.exists())

    def test_smtp_mock_captura_mensagem_real_e_simula_falha(self):
        import emails
        from models import Usuario
        usuario = Usuario(nome="Cliente Sintético", email="cliente@example.test")
        self.app.config["MAIL_ATIVO"] = True
        link = "http://localhost/auth/redefinir-senha/token-sintetico"
        with self.app.test_request_context():
            self.assertTrue(emails.email_recuperacao_senha(usuario, link))
        self.env.services.mail_send.assert_called_once()
        mensagem = self.env.services.mail_send.call_args.args[0]
        self.assertEqual(mensagem.recipients, [usuario.email])
        self.assertIn("Redefinição de senha", mensagem.subject)
        self.assertIn(link, mensagem.html)
        self.env.services.mail_send.reset_mock()
        self.env.services.mail_send.side_effect = RuntimeError("SMTP sintético indisponível")
        with self.app.test_request_context(), self.assertLogs("emails", level="WARNING"):
            self.assertTrue(emails.email_recuperacao_senha(usuario, link))
        self.env.services.mail_send.assert_called_once()

    def test_anthropic_mock_recebe_contexto_e_permite_resposta_e_fallback(self):
        import ai_devolutiva
        from models import IndicadorAnalise
        textos = {
            "resumo_executivo": "Dados sintéticos do relatório analisados.",
            "conclusao_estrategica": "Revise periodicamente a disponibilidade de produtos.",
        }
        self.app.config["ANTHROPIC_API_KEY"] = "dev02-anthropic-token-ficticio"
        self.env.services.messages_create.side_effect = None
        self.env.services.messages_create.return_value = SimpleNamespace(
            stop_reason="end_turn", content=[SimpleNamespace(type="text", text=json.dumps(textos))],
        )
        with self.app.app_context():
            factory = self.factory()
            analise = factory.analise(factory.empresa())
            analise.indicador = IndicadorAnalise(
                faturamento_total=10000, total_comprado=12000,
                saldo_estimado_compras_vendas=2000,
            )
            resultado = ai_devolutiva.gerar_devolutiva_ia(analise)
            self.assertEqual(resultado["fonte"], "ia")
            self.assertEqual(resultado["resumo_executivo"], textos["resumo_executivo"])
            argumentos = self.env.services.messages_create.call_args.kwargs
            self.assertEqual(argumentos["model"], self.app.config["ANTHROPIC_MODEL"])
            self.assertEqual(argumentos["messages"][0]["role"], "user")
            self.assertIn("10.000", argumentos["messages"][0]["content"])
            self.env.services.messages_create.reset_mock()
            self.env.services.messages_create.side_effect = RuntimeError("IA sintética indisponível")
            with self.assertLogs("ai_devolutiva", level="WARNING"):
                fallback = ai_devolutiva.gerar_devolutiva_ia(analise)
            self.assertEqual(fallback["fonte"], "fallback")
            self.assertTrue(fallback["conclusao_estrategica"])
            self.env.services.messages_create.assert_called_once()

    def test_hf_mock_captura_requisicao_e_preserva_fallback_local(self):
        import suporte_bot
        from models import GuiaTopico
        self.app.config["HF_API_TOKEN"] = "dev02-hf-token-ficticio"
        resposta_http = Mock()
        resposta_http.json.return_value = [{"generated_text": "Orientação sintética sobre o portal."}]
        self.env.services.hf_post.side_effect = None
        self.env.services.hf_post.return_value = resposta_http
        with self.app.app_context():
            self.db.session.add(GuiaTopico(
                categoria="Portal", pergunta="Dúvida sintética geral sobre o portal",
                resposta="Instrução local sintética do Guia.", ativo=True,
            ))
            self.db.session.commit()
            dados = suporte_bot.responder("Uma dúvida sintética geral sobre o portal.")
            self.assertEqual(dados["fonte"], "hf")
            chamada = self.env.services.hf_post.call_args
            self.assertTrue(chamada.args[0].endswith(self.app.config["HF_MODEL"]))
            self.assertEqual(chamada.kwargs["headers"]["Authorization"], "Bearer dev02-hf-token-ficticio")
            self.assertEqual(chamada.kwargs["timeout"], 12.0)
            self.assertFalse(chamada.kwargs["json"]["parameters"]["return_full_text"])
            self.env.services.hf_post.reset_mock()
            self.env.services.hf_post.side_effect = RuntimeError("HF sintética indisponível")
            with self.assertLogs("suporte_bot", level="WARNING"):
                fallback = suporte_bot.responder("Uma dúvida sintética geral sobre o portal.")
            self.assertEqual(fallback["fonte"], "local")
            self.assertIn("Instrução local sintética", fallback["resposta"])
            self.env.services.hf_post.assert_called_once()

    def test_socket_mock_captura_evento_argumentos_e_falha(self):
        import notifications
        from models import Notificacao
        notificacao = Notificacao(
            id_notificacao=7, texto="Relatório disponível", link_destino="/cliente/historico",
        )
        with self.app.app_context():
            notifications._emitir_tempo_real(88, notificacao)
        chamada = self.env.services.socket_emit.call_args
        self.assertEqual(chamada.args[0], "nova_notificacao")
        self.assertEqual(chamada.args[1]["id"], 7)
        self.assertEqual(chamada.args[1]["texto"], notificacao.texto)
        self.assertEqual(chamada.kwargs["room"], "user_88")
        self.env.services.socket_emit.reset_mock()
        self.env.services.socket_emit.side_effect = RuntimeError("Socket sintético indisponível")
        with self.app.app_context(), self.assertLogs("notifications", level="WARNING"):
            notifications._emitir_tempo_real(88, notificacao)
        self.env.services.socket_emit.assert_called_once()

    def test_network_guard_bloqueia_tentativa_real_antes_da_conexao(self):
        # Endereço reservado para documentação; o guard deve impedir qualquer
        # conexão antes de DNS, SMTP ou transporte HTTP serem utilizados.
        with self.assertRaisesRegex(RuntimeError, "network access is disabled"):
            socket.create_connection(("203.0.113.10", 443), timeout=0.01)


if __name__ == "__main__":
    unittest.main()
