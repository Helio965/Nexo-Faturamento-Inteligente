# Estados empresariais — pendências DEV-05, DEV-06 e DEV-07

Diagnóstico realizado em **11 de outubro de 2026**, sobre a base comercial
`a9d8e2b065dde5b4231b38beb821f53fb5def8a5`. A DEV-04 acrescenta testes e
documentação; as correções de produção abaixo pertencem às próximas etapas.

## Método e resultados observados

Foram utilizados dois ambientes independentes de `TestEnvironment`, SQLite e
uploads temporários, `DataFactory`, usuários fictícios e autenticação HTTP com
o helper `tests.support.http.login`. O CSRF permaneceu habilitado. A
infraestrutura impediu acesso à rede e ao `.env`, simulou serviços externos e
removeu os diretórios temporários ao encerrar cada ambiente.

O CLIENTE tinha `ativo=True` e `primeiro_acesso=False`. O cenário inicialmente
CANCELADA usou plano OURO; o cenário de transição ATIVA → CANCELADA usou BRONZE.
O cancelamento do segundo cenário foi aplicado e confirmado no banco
temporário antes de novas requisições, mantendo o usuário individual ativo.
Não foi alterada a sessão à mão para autenticar os clientes.

| Diagnóstico | Resultado observado |
| --- | --- |
| Novo login de CLIENTE de empresa CANCELADA | POST com CSRF retornou 302 para `/cliente/dashboard`; a sessão continha o usuário autenticado |
| Consulta após esse login | GET `/cliente/dashboard` e `/cliente/historico` retornaram 200 |
| Login inicial de empresa ATIVA | POST retornou 302; dashboard e histórico retornaram 200 |
| Mesma sessão após mudar a empresa para CANCELADA | Dashboard e histórico continuaram retornando 200; a sessão permaneceu autenticada |
| Socket.IO de CLIENTE de empresa já CANCELADA | O test client foi aceito: `is_connected()` retornou `True` |
| Socket.IO conectado antes do cancelamento | Continuou conectado após a alteração empresarial e as requisições HTTP |
| Nova conexão Socket.IO após o cancelamento | Foi aceita com a sessão existente |
| Controle Socket.IO anônimo | Conexão recusada: `is_connected()` retornou `False` |
| Controle de desativação individual | Após `Usuario.ativo=False`, GET do dashboard retornou 302 para login e removeu a autenticação da sessão |

As verificações de reprodução terminaram sem erros e confirmaram esses
resultados. Elas descrevem o comportamento atual; os cenários desejados que
ainda falham não foram adicionados como testes ignorados ou `expectedFailure`.

## DEV-05 — Bloquear novos logins de empresas CANCELADAS

**Comportamento esperado:** um CLIENTE vinculado a empresa CANCELADA não deve
iniciar uma sessão autenticada, mesmo com senha válida, usuário individual
ativo e primeiro acesso concluído. ATIVA e SUSPENSA devem manter o login
permitido; ADMIN deve manter suas permissões gerais.

**Comportamento atual comprovado:** o login da empresa CANCELADA foi aceito e
as duas rotas de consulta responderam 200. O cenário demonstra a ausência da
restrição empresarial no início da sessão.

**Evidência no código:**

- [blueprints/auth.py, linhas 95–105](../blueprints/auth.py#L95): após validar a senha, o login verifica `usuario.ativo` e chama `login_user`; não verifica `empresa.status_conta`.
- [models.py, linhas 161–163](../models.py#L161): `Usuario.is_active` retorna somente `self.ativo`.
- [models.py, linhas 96 e 112–114](../models.py#L96): `Empresa.status_conta` é um estado distinto, limitado a ATIVA, SUSPENSA e CANCELADA.

**Risco:** um CLIENTE individualmente ativo continua obtendo uma sessão e
acessando rotas privadas após o cancelamento empresarial. Os diagnósticos
consultaram páginas sem análises publicadas; não demonstram o conteúdo de um
relatório específico nem acesso a dados de outra empresa.

**Próxima etapa responsável: DEV-05.** Acrescentar cenários para senha válida e
inválida em CANCELADA, usuário individual ativo e inativo, primeiro acesso,
URL `next` para rota protegida e ausência de sessão autenticada após a recusa.
Confirmar também que os logins de ATIVA, SUSPENSA e ADMIN continuam funcionando
e que empresas ou usuários de outros cenários não são modificados.

## DEV-06 — Revogar sessões existentes após cancelamento

**Comportamento esperado:** quando a empresa passar a CANCELADA, seus CLIENTES
já autenticados devem perder acesso às rotas protegidas. A revogação não deve
depender de reiniciar o servidor ou alterar manualmente `Usuario.ativo`.

**Comportamento atual comprovado:** após login com empresa ATIVA, alteração
confirmada para CANCELADA e novas requisições com o mesmo cliente HTTP, o
dashboard e o histórico permaneceram acessíveis. A autenticação permaneceu na
sessão. O controle posterior com `Usuario.ativo=False` foi bloqueado, mostrando
que a guarda existente trata desativação individual, mas não esse cancelamento
empresarial isolado.

**Evidência no código:**

- [app.py, linhas 115–146](../app.py#L115): o carregamento e a guarda verificam usuário existente, `BOOT_ID` e `current_user.is_active`; não consultam o status empresarial.
- [blueprints/cliente.py, linhas 58–65](../blueprints/cliente.py#L58): `cliente_required` exige autenticação e perfil CLIENTE, sem condição empresarial própria.
- [blueprints/admin.py, linhas 414–418](../blueprints/admin.py#L414): a edição empresarial persiste `status_conta`; esse trecho não revoga sessões dos clientes.

**Risco:** cancelar a empresa mantém a autorização de sessões já abertas para
as rotas observadas. A revogação por outro boot ou desativação individual não
substitui a regra empresarial desejada.

**Próxima etapa responsável: DEV-06.** Testar cancelamento após login e acesso
subsequente ao dashboard, histórico, detalhe publicado, upload, suporte, Guia
e APIs protegidas; verificar limpeza da autenticação e recusa de operações
mutáveis sem efeitos no banco ou nos arquivos. Cobrir múltiplas sessões da mesma
empresa, preservar sessões de outras empresas e ADMIN, e manter a política
permitida para SUSPENSA. Definir explicitamente a política de uma eventual
reativação, sem restaurar automaticamente sessões revogadas.

## DEV-07 — Rever autorização e revogação Socket.IO

**Comportamento esperado:** conexões em tempo real de CLIENTES de empresas
CANCELADAS devem ser recusadas. Conexões existentes devem perder autorização
após o cancelamento, conforme a política de revogação definida. A comunicação
de usuários autorizados e o isolamento entre salas devem permanecer válidos.

**Comportamento atual comprovado:** usando o `socketio.test_client` em memória
e os handlers reais da aplicação, um CLIENTE da empresa CANCELADA conectou;
uma conexão da empresa ATIVA permaneceu conectada após cancelamento; e uma
nova conexão com a sessão existente também foi aceita. O controle anônimo foi
recusado.

**Evidência no código:**

- [realtime.py, linhas 27–34](../realtime.py#L27): o handshake verifica apenas `is_authenticated`, entra na sala `user_<id>` e retorna sucesso.
- [realtime.py, linhas 37–41](../realtime.py#L37): o handler de desconexão registra a saída; não há neste módulo revalidação do status empresarial ou revogação por cancelamento.
- [notifications.py, linhas 44–64](../notifications.py#L44): a emissão usa a sala do usuário-alvo; isso é uma proteção de direcionamento e não uma validação do estado empresarial.
- [app.py, linhas 120–146](../app.py#L120): a guarda descrita é de requisições HTTP; a decisão observada no handshake ocorreu pelo handler de `realtime.py`.

**Risco:** a regra empresarial desejada não impede a admissão ou permanência
das conexões observadas. A possibilidade de continuar recebendo eventos deve
ser investigada; entrega indevida de notificações não foi demonstrada neste
diagnóstico.

**Próxima etapa responsável: DEV-07.** Validar handshake em ATIVA, SUSPENSA e
CANCELADA, usuário individual inativo, sessão de outro boot, primeiro acesso e
sessão HTTP encerrada. Exercitar cancelamento e logout após a conexão,
reconexão, saída das salas e entrega de eventos após revogação; comprovar
isolamento entre usuários e empresas. Complementar com teste do transporte
real e da política de origens, sem ampliar as permissões ou fornecer credenciais
comerciais.

## Limites da evidência

As reproduções executaram as rotas Flask e os handlers Socket.IO reais com
clientes de teste em processo. Não houve banco comercial, credencial real,
conexão de navegador em produção ou alteração do código de produção.
`ExternalServices` simula `socketio.emit`: os resultados comprovam a decisão
de conexão e sua permanência, mas não a entrega de notificações. Transporte
WebSocket/polling, origens, infraestrutura distribuída e dados publicados
permanecem cenários das próximas etapas.

A restrição administrativa já existente de nova análise para empresas não
ATIVA fica em [blueprints/admin.py, linhas 215–221](../blueprints/admin.py#L215).
Sua validação automatizada pertence à DEV-04 e não resolve as pendências de
login, sessão ou tempo real descritas acima.
