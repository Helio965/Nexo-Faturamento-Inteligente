# Estados empresariais — diagnóstico DEV-04 e acompanhamento DEV-05

Diagnóstico realizado em **11 de outubro de 2026**, sobre a base comercial
`a9d8e2b065dde5b4231b38beb821f53fb5def8a5`. A DEV-04 acrescentou testes e
documentação e registrou as pendências abaixo. Essa evidência histórica foi
preservada; o acompanhamento da DEV-05 está separado do diagnóstico inicial.

## DEV-04 — Método e resultados observados

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
resultados. Elas descrevem o estado anterior à DEV-05; os cenários desejados que
ainda falham não foram adicionados como testes ignorados ou `expectedFailure`.

## DEV-05 — Bloquear novos logins de empresas CANCELADAS

**Comportamento esperado:** um CLIENTE vinculado a empresa CANCELADA não deve
iniciar uma sessão autenticada, mesmo com senha válida, usuário individual
ativo e primeiro acesso concluído. ATIVA e SUSPENSA devem manter o login
permitido; ADMIN deve manter suas permissões gerais.

**Comportamento anterior à DEV-05 comprovado:** o login da empresa CANCELADA foi aceito e
as duas rotas de consulta responderam 200. O cenário demonstra a ausência da
restrição empresarial no início da sessão.

**Evidência no código:**

- [blueprints/auth.py na base DEV-04, linhas 95–105](https://github.com/Helio965/Nexo-Faturamento-Inteligente/blob/a9d8e2b065dde5b4231b38beb821f53fb5def8a5/blueprints/auth.py#L95): após validar a senha, o login verifica `usuario.ativo` e chama `login_user`; ainda não verifica `empresa.status_conta`.
- [models.py, linhas 161–163](../models.py#L161): `Usuario.is_active` retorna somente `self.ativo`.
- [models.py, linhas 96 e 112–114](../models.py#L96): `Empresa.status_conta` é um estado distinto, limitado a ATIVA, SUSPENSA e CANCELADA.

**Risco observado na DEV-04:** um CLIENTE individualmente ativo continuava obtendo uma sessão e
acessando rotas privadas após o cancelamento empresarial. Os diagnósticos
consultaram páginas sem análises publicadas; não demonstram o conteúdo de um
relatório específico nem acesso a dados de outra empresa.

**Escopo definido para DEV-05:** acrescentar cenários para senha válida e
inválida em CANCELADA, usuário individual ativo e inativo, primeiro acesso,
URL `next` para rota protegida e ausência de sessão autenticada após a recusa.
Confirmar também que os logins de ATIVA, SUSPENSA e ADMIN continuam funcionando
e que empresas ou usuários de outros cenários não são modificados.

### Acompanhamento DEV-05

A correção parte da base comercial
`3ff335480cc31c599061126ee85bfb280c02adb7`, com os 125 testes anteriores.
Seu escopo é o início de novas sessões por `POST /auth/login`: verificar o
perfil CLIENTE e o estado CANCELADA do relacionamento `usuario.empresa` antes
de `login_user()`, preservando os controles individuais e as empresas ATIVA e
SUSPENSA. Cancelamento empresarial e lixeira administrativa continuam sendo
condições distintas.

**Resultado observado após a correção:** o novo login da empresa CANCELADA foi
recusado antes da criação da autenticação. Uma reprodução independente em
11 de outubro de 2026, com Python 3.12.14, repetiu os cenários abaixo usando
dois `TestEnvironment`, CSRF real e serviços externos simulados. Ambos os
ambientes temporários foram removidos ao terminar.

| Cenário | Antes da DEV-05 | Após a correção DEV-05 |
| --- | --- | --- |
| Novo login CANCELADA, senha válida e usuário ativo | 302 para dashboard e sessão autenticada | 200 no formulário de login, sem `Location`, `_user_id`, `boot_id` ou `_remember` |
| CANCELADA com `next=/cliente/historico` | O login permitia autenticação | Tentativa recusada; `next` não executado |
| GET protegido com o cliente do login recusado | Dashboard e histórico respondiam 200 | GET do dashboard redirecionou para login com HTTP 302 |
| Login ATIVA, SUSPENSA e ADMIN | Permitidos | Login 302 e dashboard do perfil com HTTP 200 |
| Sessão ATIVA criada antes de cancelar a empresa | Continuava autenticada | Continua autenticada; dashboard e histórico com HTTP 200, pendência DEV-06 |
| Novo login após cancelar a empresa com sessão antiga ainda aberta | Permitido | Novo cliente recusado; o bloqueio não revoga a sessão antiga |

O estado individual ativo, a senha armazenada e o status empresarial das
fixtures permaneceram iguais após as tentativas de novos logins. A recusa não
exige que a sessão inteira fique vazia: token CSRF e dados não autenticados
continuam permitidos. Os diagnósticos não imprimiram cookies, tokens ou
credenciais.

**Evidência atual no código:**

- [blueprints/auth.py, linhas 95–107](../blueprints/auth.py#L95): após validar credenciais e usuário ativo, a condição de recusa verifica perfil CLIENTE e o estado CANCELADA de `usuario.empresa`.
- [blueprints/auth.py, linhas 109–119](../blueprints/auth.py#L109): `login_user()`, o carimbo `boot_id` e o redirecionamento `next` ocorrem depois da recusa empresarial.
- [blueprints/auth.py, linhas 126–127](../blueprints/auth.py#L126): senha incorreta continua recebendo a mensagem genérica de credenciais inválidas.

A mensagem da recusa empresarial informa que o acesso não está autorizado,
sem incluir CNPJ, identificadores ou plano. O diagnóstico independente confirma
o comportamento em execução. O mesmo teste principal que reproduziu a falha
antes da correção passou sem flexibilizar as asserções. Os resultados locais
confirmados nesta etapa foram:

| Execução local | Resultado |
| --- | --- |
| Teste principal após a correção | 1 teste aprovado em 1,676 s |
| Suíte específica DEV-05 | 20 testes aprovados em 11,553 s |
| Suíte completa | 145 testes aprovados em 36,613 s, sem falhas, erros ou testes ignorados |

Esses resultados são locais. A validação do GitHub Actions da feature e o estado
da Pull Request devem ser conferidos separadamente no relatório desta execução.

A DEV-05 não revoga sessões previamente autenticadas, não altera Socket.IO e
não modifica os fluxos de tokens. As pendências DEV-06 e DEV-07 abaixo continuam
separadas dessa correção.

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

**Rechecagem após DEV-05:** o diagnóstico independente confirmou novamente
que a sessão anterior ao cancelamento permanece autenticada e obtém HTTP 200
no dashboard e histórico, embora um novo cliente com as mesmas credenciais
seja recusado. Essa diferença mantém a revogação de sessões no escopo da DEV-06.

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

**Comportamento comprovado na DEV-04:** usando o `socketio.test_client` em memória
e os handlers reais da aplicação, um CLIENTE da empresa CANCELADA conectou;
uma conexão da empresa ATIVA permaneceu conectada após cancelamento; e uma
nova conexão com a sessão existente também foi aceita. O controle anônimo foi
recusado.

**Rechecagem após DEV-05:** a conexão já aberta permaneceu conectada após
cancelamento e outra conexão usando a sessão antiga também foi aceita. Um
cliente sem autenticação, após o novo login recusado pela DEV-05, teve o
handshake recusado. O bloqueio do login reduz esse caminho de obtenção de uma
nova sessão; o handler Socket.IO e a revogação das conexões antigas continuam
sem correção nesta etapa.

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
clientes de teste em processo. Não houve banco comercial, credencial real ou
conexão de navegador em produção. Os diagnósticos não modificaram o código de
produção; a correção DEV-05 acrescentou somente a recusa empresarial no login.
`ExternalServices` simula `socketio.emit`: os resultados comprovam a decisão
de conexão e sua permanência, mas não a entrega de notificações. Transporte
WebSocket/polling, origens, infraestrutura distribuída e dados publicados
permanecem cenários das próximas etapas.

A restrição administrativa já existente de nova análise para empresas não
ATIVA fica em [blueprints/admin.py, linhas 215–221](../blueprints/admin.py#L215).
Sua validação automatizada pertence à DEV-04 e não resolve as pendências de
sessão e tempo real DEV-06/DEV-07. Essa restrição administrativa não substituía
a correção de novos logins implementada na DEV-05.

## DEV-11 — Revisão futura dos tokens de autenticação

A revisão dos tokens de ativação/primeiro acesso e recuperação de senha
permanece pendente. A DEV-05 trata novos logins por e-mail e senha; os fluxos de
tokens ficam sem alterações. Expiração, consumo, reutilização e autorização
empresarial nesses fluxos devem ser avaliados na DEV-11. Não foi executado um
diagnóstico desses tokens nesta etapa, nem se afirma uma vulnerabilidade
adicional sem reprodução.
