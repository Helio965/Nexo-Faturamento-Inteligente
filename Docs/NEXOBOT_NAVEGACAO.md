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

## Testes

Na raiz do checkout, com as dependências existentes instaladas:

```bash
.venv/bin/python -m unittest discover -s tests -p 'test_nexobot.py' -v
```

Os testes usam SQLite temporário e não alteram o banco da aplicação. Cobrem intenções, contexto, respostas do Guia/IA, validação JSON, permissões e CSRF. A validação no navegador usa Chromium e Playwright como ferramentas de desenvolvimento opcionais, sem modificar as dependências da aplicação.
