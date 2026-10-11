# Testes isolados do NEXO — DEV-02

Use Python 3.12 e as dependências de `requirements.txt` em um ambiente virtual.
Execute os comandos a partir da raiz do repositório:

```bash
python -m unittest discover -s tests -p 'test_*.py' -v
python -m unittest tests.test_infrastructure -v
python -m unittest tests.test_nexobot -v
python -m unittest tests.test_company_status -v
```

`test_etl.py` é um script separado que exige arquivos de entrada. Não é parte
da descoberta acima; estes testes não exigem relatórios reais.

## Organização

- `support/environment.py`: ciclo de vida da factory real, SQLite, uploads e
  recursos temporários, configuração segura e bloqueio de rede.
- `support/base.py`: `IsolatedTestCase`, com um ambiente novo por método e
  cleanup registrado antes da inicialização.
- `support/factories.py`: dados sintéticos para Plano, Segmento, Empresa,
  Usuario e Analise; sem commits implícitos.
- `support/http.py`: CSRF extraído da interface real, login e logout HTTP.
- `support/services.py`: SMTP, Anthropic, Hugging Face e emissão Socket.IO
  simulados, com argumentos e falhas observáveis.
- `test_infrastructure.py`: verifica os contratos desta infraestrutura.
- `test_nexobot.py`: regressões existentes; mantém seus cenários e asserções.
- `test_company_status.py`: regras de empresas ATIVAS, SUSPENSAS e CANCELADAS,
  com login/CSRF reais, consultas publicadas e criação administrativa de análises.
- `COMPANY_STATUS_FINDINGS.md`: evidências e cenários pendentes de DEV-05,
  DEV-06 e DEV-07, sem antecipar suas correções.

## Aplicação e banco temporários

```python
from tests.support.environment import TestEnvironment

with TestEnvironment() as env:
    client = env.create_client()
    assert client.get('/healthz').status_code == 200
    with env.app.app_context():
        assert env.db.engine.url.database == str(env.database_path)
```

A inicialização usa `app.create_app()`, as extensões e os modelos de produção.
O schema é criado com `db.create_all()` exclusivamente no SQLite temporário;
nenhuma migration, seed ou inicializador destrutivo é executado.

Cada ambiente possui chave efêmera própria, arquivo SQLite absoluto, diretório
de uploads e diretório instance temporários. Ao sair, remove a sessão, encerra
as conexões e descarta os arquivos, inclusive quando o corpo do teste falha.
Não mantenha `app_context()` aberto entre requisições HTTP: isso pode
compartilhar o cache CSRF entre clientes.

## Dados sintéticos e novos testes

```python
from tests.support.base import IsolatedTestCase
from tests.support.factories import DataFactory
from tests.support.http import csrf_token, login, logout

class MeuTeste(IsolatedTestCase):
    def test_cliente_autenticado(self):
        with self.app.app_context():
            dados = DataFactory(self.db.session)
            bronze = dados.plano('BRONZE')
            empresa_a = dados.empresa(plano=bronze, status_conta='ATIVA')
            empresa_b = dados.empresa(status_conta='SUSPENSA')
            cliente = dados.usuario(empresa=empresa_a)
            admin = dados.usuario(role='ADMIN')
            dados.analise(empresa_a, admin=admin)
            email = cliente.email
            self.assertNotEqual(empresa_a.id_empresa, empresa_b.id_empresa)
            self.assertIsNone(admin.id_empresa)
            self.db.session.commit()

        client = self.env.create_client()
        self.assertEqual(login(client, email).status_code, 302)
        token = csrf_token(client)
        resposta = client.post(
            '/api/suporte-bot', json={'mensagem': 'Olá'},
            headers={'X-CSRFToken': token},
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(logout(client).status_code, 302)
```

As fábricas adicionam e fazem flush dos registros, sem commit: o teste decide
quando confirmar ou reverter. Planos de mesmo nome são reutilizados no banco
atual. Empresas/CNPJs, segmentos e e-mails padrão são sintéticos e únicos.
Os parâmetros permitem definir plano, status empresarial, perfil, senha e
primeiro acesso. ADMIN não recebe empresa; CLIENTE fica associado a uma empresa
válida, criada automaticamente quando o argumento `empresa` é omitido.
Análises quinzenais exigem OURO e quinzena válida. Estes cuidados criam
fixtures válidas; não substituem a validação das rotas de produção.

Um `create_client()` novo tem cookies e sessão independentes. `login()` usa
o formulário real com CSRF e retorna a resposta sem presumir sucesso: testes
futuros podem verificar rejeição de login. Nenhum helper escreve `_user_id`
ou BOOT_ID diretamente na sessão.

CSRF fica habilitado por padrão. `TestEnvironment(csrf_enabled=False)` é uma
opção explícita para um teste que não avalia CSRF; justifique seu uso no teste.
Para exercitar recusa, faça a requisição diretamente sem token ou com um valor
inválido, em vez de usar um helper que forneça um token válido.

## Serviços externos

Os mocks ficam ativos durante o ambiente e podem receber respostas ou
`side_effect`. Eles não substituem autorização, CSRF nem operações do banco.

```python
with TestEnvironment() as env:
    with env.app.app_context():
        from extensions import socketio
        socketio.emit('evento-ficticio', {'ok': True}, room='user_123')
    env.services.socket_emit.assert_called_once_with(
        'evento-ficticio', {'ok': True}, room='user_123',
    )
    env.services.mail_send.side_effect = RuntimeError('SMTP simulado indisponível')
    env.services.messages_create.side_effect = RuntimeError('IA simulada indisponível')
```

SMTP usa captura de `mail.send` e execução determinística somente do despacho
de e-mail, sem thread de envio pendente após o cleanup. Para exercitar esse
caminho, habilite `app.config['MAIL_ATIVO'] = True` no teste: o envio continua
simulado. Anthropic e HF ficam desabilitados na configuração por padrão;
para exercitar seus mocks, atribua uma chave/token **fictício** na config.
`hf_post` captura a requisição; o fallback local continua disponível.

Arquivos usam o `UPLOAD_FOLDER` temporário. `storage.salvar/resolver/remover`
continuam reais; isso permite verificar bytes e falhas sem tocar uploads locais.

## Isolamento e limites

- A leitura de `.env` é suprimida na importação controlada. Variáveis comerciais
  não fornecem a chave, o banco, uploads ou credenciais da aplicação de teste.
- `DATABASE_URL`, `DIRECT_URL` e `NEXO_DB_DIRECT` são neutralizados antes da
  factory; ambas as URIs configuradas apontam para o mesmo SQLite temporário.
- A URI efetiva do engine é conferida antes da criação do schema.
- Foreign keys SQLite continuam ativas; há teste de rejeição de FK inválida.
- Chamadas de rede não simuladas são bloqueadas durante o ambiente. Nenhuma
  chave real deve ser colocada em fixtures, config ou exemplos.
- Use ambientes aninhados em ordem LIFO e clientes fora de app contexts.
  As extensões são compartilhadas; não inicialize ambientes concorrentes em
  threads. Paralelismo em processos independentes não compartilha esse estado.
- SQLite não comprova locks, tipos ou concorrência específicos de PostgreSQL.

A DEV-02 valida a infraestrutura. Ela não corrige cancelamento empresarial,
reutilização de tokens, efeitos antes de commit, atomicidade de arquivos,
indicadores ou publicação. Testes completos dessas regras pertencem às etapas
seguintes.

## Integração contínua — DEV-03

O workflow `.github/workflows/tests.yml` executa os testes em um runner Linux
`ubuntu-24.04`, com Python 3.12 e as dependências de `requirements.txt`. Há um
único job, sem paralelismo entre os testes. A descoberta deve encontrar pelo
menos um teste; depois, a suíte completa é executada pelo mesmo comando local:

```bash
python -m unittest discover -s tests -p "test_*.py" -v
```

Não há quantidade fixa de testes: novos arquivos `test_*.py` em `tests/` e
métodos `test_*` em classes `unittest.TestCase` entram na descoberta. Use os
helpers descritos acima para manter os dados e serviços isolados.

O workflow inicia em:

- Push em `develop/comercial` ou em branches `feature/**`.
- Pull Requests destinadas a `develop/comercial` ou `main`; o filtro considera
  a branch de destino da PR.

As Pull Requests do desenvolvimento comercial devem ter **`develop/comercial`
como destino**. O push em `feature/dev-03-github-actions` permite verificar a
primeira execução antes de abrir a PR ou realizar qualquer merge.

Na aba **Actions** do repositório, selecione **NEXO - Testes automatizados**,
abra a execução correspondente ao commit e confira o job **unittest (Python
3.12)**. Os passos mostram a preparação do Python, a instalação das
dependências, a quantidade descoberta e o resultado da suíte. A primeira
validação só está concluída quando uma execução real no GitHub termina com
`success`; um resultado local não comprova a execução no GitHub. Confira também
o check da Pull Request e se houve uma execução do evento `pull_request`.

Erros de instalação, descoberta vazia e falhas ou erros nos testes reprovam o
job. No passo de execução, `FAIL` ou `ERROR` identifica o caso e o traceback
explica a falha; o resumo do unittest informa o total e eventuais testes
ignorados. Não ignore erros nem faça merge para forçar a validação.

O token do workflow tem somente `contents: read`, e o checkout não persiste
credenciais Git. Nenhum secret comercial é fornecido. A infraestrutura DEV-02
continua responsável pelo SQLite e arquivos temporários, pela configuração
segura e pelos serviços simulados. O workflow não executa migrations, deploy,
scripts de inicialização do banco ou alterações automáticas no repositório.

## Estados empresariais — DEV-04

Execute `python -m unittest tests.test_company_status -v` para a suíte focada e
o comando de descoberta acima para validar também os testes anteriores.
Cada método reutiliza `IsolatedTestCase`, `DataFactory` e os helpers HTTP da
DEV-02, mantendo SQLite temporário, CSRF habilitado e serviços externos simulados.

ATIVA/BRONZE e SUSPENSA/PRATA validam login de CLIENTE ativo, dashboard,
histórico e análise própria concluída com relatório publicado. CANCELADA/OURO
valida as restrições administrativas já implementadas. A criação permitida
confere os dados persistidos, inclusive plano congelado, ADMIN responsável,
período, modalidade, quinzena e status inicial. As recusas conferem preservação
dos registros anteriores e dos dados de outras empresas, além da resposta HTTP.

O bloqueio de login de empresa CANCELADA e a revogação de sessões existentes
pertencem a DEV-05/DEV-06. Não há testes ignorados ou falhas esperadas para
simular essas correções. Consulte `COMPANY_STATUS_FINDINGS.md` para evidências,
riscos e próximos cenários. Nenhuma regra de produção ou dependência é alterada.

O trabalho foi iniciado após a sincronização GIT-02 e aprovação real do CI na
branch comercial. A PR da DEV-04 deve apontar para `develop/comercial` e aguardar
revisão; sua integração não é automática.
