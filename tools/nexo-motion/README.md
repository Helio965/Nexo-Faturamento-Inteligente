# NEXO — produção audiovisual

Filme de produto original, implementado em React, TypeScript e Remotion.
40 segundos, 1920 × 1080, 30 fps. Saída H.264/yuv420p com áudio AAC
original e MP4 preparado para streaming (`faststart`).

Resultados e limites dos testes estão em [VALIDATION.md](VALIDATION.md).

## Reproduzir

Pré-requisitos: Node.js 22 ou superior, npm, Python 3, FFmpeg/ffprobe e
Chromium. A instalação Python da aplicação Flask não é alterada.

```bash
cd tools/nexo-motion
npm ci
npm run typecheck
npm run render
npm run verify
```

O script detecta Chromium em `/usr/bin/chromium` ou Google Chrome em
`/usr/bin/google-chrome`. Para outro caminho, use `CHROME_PATH=/caminho/chrome`.
Sem navegador local, o renderer usa o mecanismo padrão do Remotion.
Não desative verificações TLS, assinaturas ou integridade para instalá-lo.

`npm run stills` gera apenas os sete frames de inspeção e o poster
(a trilha deve existir; execute `python3 scripts/audio.py` se necessário).
`npm run render` gera a trilha, inspecionáveis em `out/`, o MP4,
o GIF animado de 6 segundos e a capa. Os arquivos finais ficam em
`../../static/video/`. Diretórios temporários, WAV intermediário,
cache npm local e `node_modules` são ignorados pelo Git. O `.npmrc`
mantém o cache no projeto, permitindo instalar mesmo quando o diretório
home do ambiente é somente leitura. Renderização usa quatro workers;
o runtime da aplicação Flask não depende dessas bibliotecas.

## Estrutura e narrativa

- `src/NexoFilm.tsx`: composição e timeline determinística de 1.200 frames.
- `src/visual.tsx`: símbolo vetorial, paleta, partículas, grid e primitivas.
- `src/scenes/Brand.tsx`: abertura (0–6s), ETL (6–13s), encerramento (33–40s).
- `src/scenes/Dashboard.tsx`: indicadores, barras, histórico e ABC (13–23s).
- `src/scenes/Intelligence.tsx`: IA revisada, PDF, suporte e notificações (23–33s).
- `scripts/audio.py`: síntese original em Python, sem samples externos.
- `scripts/render.mjs`: render e exportação do MP4, GIF e poster.
- `scripts/export.mjs`: normalização para yuv420p/TV, faststart e GIF.
- `scripts/verify.mjs`: checagem dos arquivos finais e decodificação completa.

A linguagem de movimento da referência enviada orientou escala tipográfica,
contraste, perspectiva e ritmo. Nenhum frame, som ou marca de terceiros foi
incorporado. O cubo SVG é uma interpretação animável do símbolo oficial em
`static/img/nexo-logo.jpeg`; o roxo do projeto é `#a855f7`.
O laranja coral expressivo é restrito à campanha. A landing preserva seus
estilos e usa um player HTML5 na seção pública `#demonstracao`, sem autoplay.

## Dados e conteúdo

Todos os valores são ilustrativos, sem dados de clientes. No dashboard,
as séries de vendas são 18.000, 21.500, 24.800, 23.900, 26.100 e 28.500;
somam R$ 142.800. As compras são 14.000, 15.200, 16.000, 17.000, 16.500
e 17.700; somam R$ 96.400. Pressão de Estoque = compras − vendas =
−R$ 46.400. O gráfico histórico usa os mesmos valores de vendas. O exemplo
de ABC distribui o faturamento em A 77%, B 16%, C 7%; 248 é a contagem
ilustrativa de produtos. As barras do PDF são a mesma série de vendas,
normalizada para a altura da página. Nenhum indicador representa lucro,
margem contábil, previsão ou garantia financeira.

O ETL aparece como processamento acionado pelo administrador. A devolutiva
por IA depende de revisão/publicação do consultor. O tempo real é descrito
somente para comunicação e notificações. O filme funciona sem áudio.

## Licenças

Código e áudio originais seguem a licença do repositório. A fonte Inter
é distribuída via `@fontsource/inter` sob SIL Open Font License 1.1;
arquivos/licença permanecem no pacote da dependência. Remotion e demais
dependências mantêm suas respectivas licenças. O vídeo de referência
não é redistribuído no repositório.
