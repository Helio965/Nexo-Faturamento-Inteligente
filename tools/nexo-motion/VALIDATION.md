# Validação da produção NEXO

Execução em 8 de outubro de 2026, horário de São Paulo.

## Arquivos finais

| Arquivo | Especificação verificada | Tamanho |
|---|---|---:|
| `static/video/nexo_demo_motion.mp4` | 40,000 s · 1.200 frames · 1920×1080 · 30 fps · H.264 · yuv420p/TV · AAC · faststart | 11.996.145 bytes |
| `static/video/nexo_demo_preview.gif` | 6 s · 72 frames · 640×360 · loop infinito | 2.818.872 bytes |
| `static/video/nexo_demo_poster.png` | PNG · 1920×1080 · composição de encerramento | 1.381.547 bytes |

`ffprobe` confirmou os parâmetros acima. O MP4 e o GIF foram decodificados
integralmente por FFmpeg sem erros. A estrutura do MP4 tem `moov` antes de
`mdat`. O GIF possui extensão de loop com contador zero (infinito).

SHA-256 do MP4:
`f7756d2507356c2164409190d0d618d630dba2d83a7d2e012aa38ee909c888fb`

SHA-256 do GIF:
`f9400ab49d15fd79f64e772ff51ea509ebb545598b1f787d133aa4a51ccf3c84`

## Animação e conteúdo

As cinco cenas foram renderizadas. Comparações RGB entre 2/3 s, 8/9 s,
17/18 s, 25/26 s e 36/37 s comprovam movimento em todos os trechos.
Frames reais do MP4 foram extraídos e inspecionados nas cinco cenas,
incluindo IA, PDF e suporte, além da abertura e do último frame.
Não foram observados cortes de textos, sobreposições relevantes,
componentes ausentes ou gráficos quebrados.

Os valores são identificados como ilustrativos. Vendas somam R$ 142.800;
compras R$ 96.400; pressão de estoque é −R$ 46.400. A curva ABC soma
100%. As barras do PDF usam a mesma série de vendas do dashboard.
O conteúdo explicita acionamento do ETL pelo administrador, revisão e
publicação da IA pelo consultor, e tempo real somente para comunicação.

## Aplicação e README

27 verificações Flask passaram usando exclusivamente banco SQLite
temporário. Login ADMIN e CLIENTE com CSRF, redirecionamentos, dashboards,
permissões e logout passaram. As 41 rotas e 13 tabelas foram inspecionadas.
O banco de desenvolvimento existente não foi alterado pelos testes.

MP4, GIF e poster são públicos, com HTTP 200 e MIME correto. Requisição
Range do MP4 retornou HTTP 206 e os 1.024 bytes solicitados; os arquivos
servidos tiveram o mesmo SHA-256 dos arquivos locais.

Chromium 151 foi usado em larguras 390, 768 e 1440 px. O player manteve
16:9, sem overflow horizontal, com poster decodificado. Os controles
nativos passaram em reprodução, pausa, seek, reinício, mute, volume e
tela cheia. Áudio AAC foi decodificado. Login e seis âncoras existentes
continuaram acessíveis. Nenhuma exceção JavaScript foi observada.

O GIF clicável aparece na linha 3 do README. Arquivos e destinos foram
verificados; todas as linhas originais da documentação foram preservadas.
O player foi inserido antes do dashboard existente na seção pública
`#demonstracao`, sem duplicar IDs ou usar autoplay.

O script existente `test_etl.py` passou com fixtures sintéticas CSV e
XLSX. Não foi executada uma bateria com dados reais de clientes.

## Reprodutibilidade e preservação

`npm ci`, `npm run typecheck` e `npm run verify` passaram. A renderização
foi executada no ambiente com Remotion 4.0.534, React 19.1 e Node 24.
A saída de faixa completa do renderer foi convertida, preservando os
níveis reais, para yuv420p/TV pelo exportador. A cena 4 foi regenerada
após a conferência da versão compilada dos dados do PDF.

Somente a landing, seu CSS, README, arquivos de mídia e projeto audiovisual
foram adicionados/modificados. Backend, autenticação, models, migrations,
ETL, dashboards internos, templates de login, JavaScript existente e
dependências Python permaneceram com diff vazio em relação ao HEAD
inicial `215278167ffc59f2dd7bd3cda019e6f1bced46b4`.
Caches, frames intermediários, WAV e node_modules não são versionados.

## Limites da validação

A página foi validada no Flask deste ambiente, não em um deploy externo.
O navegador de teste encontrou bloqueios preexistentes do proxy para
Google Fonts; Bootstrap e Plotly foram usados a partir de cache obtido
com TLS verificado, com SRI do Bootstrap preservado. As fontes do filme
são locais e não dependem desses CDNs. Abortos de carregamento do MP4
durante navegação/preload/download foram esperados e não impediram playback.
Nenhuma verificação TLS ou de integridade foi desativada.
