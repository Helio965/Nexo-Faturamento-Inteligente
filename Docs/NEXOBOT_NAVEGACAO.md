# Navegação do NexoBot

O widget e o endpoint autenticado `POST /api/suporte-bot` continuam usando o Guia cadastrado pelo administrador, a integração opcional com Hugging Face e o fallback local. A navegação funciona sem token ou serviço de IA.

- **Informação:** “Onde envio os relatórios?” recebe uma explicação e o botão “Ir para Enviar Relatórios”, sem mudar de página.
- **Comando:** “Me leve para o upload” retorna uma ação local de navegação. O widget remove o indicador de digitação, fecha o painel e abre a página imediatamente, sem resposta intermediária ou confirmação.
- **Contexto:** depois de uma sugestão, “Me leva pra lá” usa o último destino relevante. Um novo destino explícito tem prioridade. Mensagens sem destino relevante, ambiguidades e falhas de comunicação limpam o contexto.

O catálogo em `navegacao_bot.py` contém exclusivamente os identificadores `dashboard`, `upload`, `historico`, `guia` e `suporte`. As URLs são geradas com `url_for()` para os endpoints existentes do cliente; `suporte` abre a lista/formulário de chamados e não cria um chamado. O mesmo catálogo fornece o mapa permitido ao JavaScript. Acrescentar uma página exige definir sua rota, termos de reconhecimento e orientação no catálogo, mantendo a revisão de permissões.

## Contrato da API

Entrada: `{"mensagem": "Me leva pra lá", "ultimo_destino": "upload"}`. `ultimo_destino` é opcional e só pode identificar páginas do catálogo. Não se transmite histórico de mensagens ou URLs de destino.

Os campos `resposta` e `fonte` permanecem presentes. `acao` pode ser `sugerir_navegacao`, `navegar` ou `null`. Uma ação válida inclui `destino` e `url`; sugestões também incluem `rotulo_botao`. Navegação direta retorna `resposta: ""`. Mensagens comuns, recusas e pedidos de esclarecimento retornam `acao: null` e `destino: null`.

## Limites e segurança

Autenticação, perfil CLIENTE, CSRF, primeiro acesso e invalidação de sessão seguem as regras existentes. O contexto fica somente na memória da instância do widget; não há alterações no banco, modelos ou migrations. O backend valida o identificador e gera a URL; o navegador exige correspondência exata com seu catálogo e mesma origem. A IA não escolhe rotas nem executa operações de negócio. Texto e rótulos são renderizados como texto, sem interpretar HTML. Envios simultâneos são bloqueados para preservar a ordem das respostas.

Negações e perguntas sobre como acessar uma página não causam navegação automática. Múltiplos destinos pedem esclarecimento. Páginas desconhecidas, URLs externas e áreas administrativas não são destinos válidos. Na página já aberta, o bot informa isso sem recarregar. O reconhecimento é local, por padrões de linguagem e sinônimos; frases não reconhecidas podem precisar ser reformuladas.

## Reconhecimento de frases naturais

Artigos, possessivos e demonstrativos não impedem um destino explícito: “Me leve para essa página de upload”, “Quero que você me direcione para esse local de upload” e “Quero acessar a página do meu histórico” são comandos diretos. Referências como “Me leva naquela aba” usam somente um contexto válido da conversa atual.

O parser examina o trecho após cada verbo de navegação, limitado pelo próximo comando. Assim, “Preciso ver meu faturamento, abra o dashboard” abre o dashboard, e “Estou no upload, quero abrir o histórico” abre o histórico. Não procura um destino arbitrário em toda a mensagem. Duas páginas solicitadas, inclusive em “Quero ir para upload ou abra dashboard”, pedem esclarecimento. A expressão “área de relatórios anteriores” identifica histórico, sem se confundir com a página de envio.

Desejos pessoais de enviar/anexar arquivos e criar um chamado recebem orientação e botão. Com uma ordem explícita, “Quero enviar meus arquivos, me leve para essa página de upload” abre upload. “Quero abrir um chamado, me leve para o Guia” abre o Guia: a tarefa mencionada antes não substitui a página solicitada. Nenhum desses pedidos envia arquivos ou cria chamados.

Ordens delegadas (“Quero que você envie”), pedidos de automação, exclusão, publicação e outras operações continuam recusados, mesmo acompanhados de navegação. As variantes informais “apaga”, “deleta”, “executa” e “envia” também são reconhecidas. Uma pergunta intermediária não libera uma operação posterior: “Abra meu dashboard. Como funciona isso? Exclua minhas análises” não navega.

Menções e hipóteses como “Se eu disser abra o histórico, isso vai funcionar?” não são ordens de navegação. O guard de menção considera o prefixo anterior ao verbo; “Abra o Guia para ver um exemplo” continua sendo um comando direto.

O reconhecimento permanece conservador: uma negação em uma mensagem direta impede a navegação. Uma pergunta anterior ao comando mantém o tratamento informativo ou pede esclarecimento. Frases complexas que não tenham destino inequívoco devem ser reformuladas; a IA não completa o catálogo de páginas.

### Expressões contextuais com tratamento

“Eu quero que você me leve para lá”, “NexoBot, me leva pra lá”, “Ah, me leva pra lá”, “Opa, pode abrir aquela página?” e “Por favor, NexoBot, me direcione para lá” usam o último destino válido. A checagem continua dependendo de uma intenção real de navegação, sem explicação, botão ou confirmação intermediária.

A função `_comando_contextual()` preserva a lista estrita de palavras do pedido. Acrescenta somente `eu` e `voces` à gramática e aceita `ah`, `opa`, `ei`, `bom`, `nexobot`, `bot` e `assistente` antes do primeiro verbo de navegação. Um vocativo no final precisa estar separado por vírgula, como “Me leva pra lá, NexoBot, por favor”. A locução completa “por gentileza” equivale a “por favor”; palavras desconhecidas não são descartadas. “Me leve para assistente” e “Me leva para o local do bot” continuam pedindo esclarecimento.

Perguntas, relatos, negações e hipóteses mantêm os guards anteriores. O guard de hipóteses também reconhece “Se eu falar…”, inclusive quando a fala citada contém um destino explícito. Um novo destino explícito continua prevalecendo sobre o contexto anterior. Sem contexto válido ou depois de sua invalidação, não há recuperação de destinos antigos.

Limites: os verbos de comando reconhecidos não foram ampliados. Tratamentos no meio do pedido ou vocativos finais sem a vírgula delimitadora podem exigir reformulação. A correção não remove palavras desconhecidas nem utiliza “lá” sozinho para inferir uma ordem.

## Testes

Na raiz do checkout, com as dependências existentes instaladas:

```bash
.venv/bin/python -m unittest discover -s tests -p 'test_nexobot.py' -v
```

Os testes usam SQLite temporário e não alteram o banco da aplicação. Cobrem intenções, contexto, respostas do Guia/IA, validação JSON, permissões e CSRF. A validação no navegador usa Chromium e Playwright como ferramentas de desenvolvimento opcionais, sem modificar as dependências da aplicação.

## Validação da correção — 9 de outubro de 2026

A auditoria partiu de `a19d46fe0f56b32835eed0c473b46099b4b9cf1b`, obtido da `main` oficial por atualização fast-forward. As alterações anteriores, incluindo o vídeo e a landing, foram preservadas.

| Etapa | Resultado |
| --- | --- |
| Suíte original antes da correção | 36 testes aprovados, zero falhas |
| Regressões antes da correção | 51 métodos: 42 aprovados e 9 reprovados; 42 falhas de subtestes, zero erros |
| Suíte final após a correção | 57 testes aprovados, zero falhas, erros ou testes ignorados |

Nos casos A–E do pedido, A (essa página), B (esse local) e C (desejo de envio + navegação) falhavam tanto no parser quanto na API. D (consulta + histórico) e E (abrir chamado + suporte) já funcionavam e foram mantidos. Os 36 testes e helpers originais permaneceram idênticos; foram adicionados 21 testes de regressão e segurança.

Os testes finais verificam o contrato JSON, orientação com botão, navegação sem texto/botão intermediário, contexto válido/ausente/inválido, mudança de destino, negações, ambiguidades, URLs externas, área administrativa, operações sem efeitos nos dados e funcionamento sem Hugging Face. Login real com CSRF, bloqueios de ADMIN/anônimo, primeiro acesso, conta desativada e sessão de outro boot passaram. Todos os dados e uploads de teste ficam em diretórios temporários.

No navegador, Chromium/Playwright passou 81 de 81 verificações, sem falhas ou exceções JavaScript, em 1440 e 390 px. Os três fluxos reais (informação → botão, comando direto e comando contextual) abriram as cinco rotas com HTTP 200. O fechamento do painel foi observado antes de sair da página; perguntas permaneceram na página até o clique. Também passaram página já aberta sem reload, menu mobile, dois envios rápidos, falhas da API, sessão expirada por logout, contexto isolado, rejeição de ações/URLs inválidas e renderização de texto sem executar HTML. ADMIN recebeu 403 no endpoint e nas cinco rotas do cliente. As contagens das 13 tabelas do fixture permaneceram iguais antes e depois das interações do bot.

Uma revisão independente executou mais 27 sondagens do parser com assertions, todas aprovadas. A comparação com o commit inicial confirmou diff vazio nos componentes protegidos; `git diff --check` passou.

Limites: o navegador foi validado em um servidor Flask isolado, sem deploy externo ou dados reais. O proxy do ambiente bloqueia alguns CDNs; nos testes foram usados assets Bootstrap/Plotly/Socket.IO em cache obtidos com TLS verificado, preservando a integridade quando declarada. O bloqueio de Google Fonts é preexistente. Não foi feita chamada real à Hugging Face: ausência de token e indisponibilidade simulada foram testadas, e a integração opcional permaneceu intacta.

Somente o reconhecimento em `navegacao_bot.py`, os testes e esta documentação foram alterados. API, respostas do Guia/HF, frontend, CSS, autenticação, modelos, migrations, ETL, dashboards e landing permanecem sem alterações.

## Validação final contextual — 9 de outubro de 2026

HEAD inicial e `main` confirmados: `be7dc3f6f1da5f88f420f787727fb72ee77c3006`; checkout inicialmente limpo, sem alterações posteriores no remoto.

- Baseline: 57 de 57 testes aprovados.
- Regressões contra o parser original: 76 métodos, 65 aprovados e 11 reprovados; 44 falhas de subtestes e zero erros. Os casos A–E falhavam no parser e na API.
- Após a correção: 76 de 76 testes aprovados, zero falhas, erros ou testes ignorados. Foram acrescentados 19 métodos; os 57 métodos e helpers anteriores permaneceram idênticos por comparação AST.

Os novos testes incluem os cinco pedidos contextuais, conversas completas de upload e histórico, tratamento/educação em posições delimitadas, prioridade do destino explícito, perguntas com botão, negações, hipóteses, contexto ausente/inválido/isolado, palavras desconhecidas e bloqueios de operações, URLs externas e ADMIN. Os testes usam SQLite e uploads temporários. A navegação funciona sem token de Hugging Face, sem alterar o contrato JSON ou o frontend.

Chromium/Playwright passou 38 de 38 verificações em 1440 e 390 px, sem falhas ou exceções JavaScript. Os cinco fluxos solicitados passaram: pergunta de upload → “Eu quero que você me leve para lá”; pergunta de histórico → “Ah, NexoBot, me leva pra lá”; dashboard direto com vocativo; Guia informativo com botão, sem navegação; e negação com vocativo. O painel fechou antes dos redirecionamentos, sem texto intermediário. As cinco páginas CLIENTE retornaram 200 e ADMIN permaneceu bloqueado com 403. Contexto, falhas da API, sessão expirada, concorrência, página já aberta e menu mobile passaram; as contagens das 13 tabelas temporárias ficaram iguais.

O diff foi revisado e restrito aos três arquivos desta funcionalidade. Os componentes protegidos mantiveram diff vazio contra o HEAD inicial; `git diff --check` passou. A validação continua local, com SQLite temporário, sem deploy externo nem chamada real à Hugging Face. Os limites de CDN/cache verificado descritos na validação anterior também se aplicam a esta execução.
