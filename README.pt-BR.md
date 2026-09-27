# SVG Multicor para OrcaSlicer

[![CI](https://github.com/opoeta/orca-svg-multicor/actions/workflows/ci.yml/badge.svg)](https://github.com/opoeta/orca-svg-multicor/actions/workflows/ci.yml)
[![Licença: MIT](https://img.shields.io/badge/licen%C3%A7a-MIT-green.svg)](LICENSE)
[![Versão](https://img.shields.io/github/v/release/opoeta/orca-svg-multicor)](https://github.com/opoeta/orca-svg-multicor/releases/latest)

**[Read in English](README.md)**

Plugin do OrcaSlicer que transforma um SVG colorido (logo, placa, adesivo) em
**uma peça imprimível por cor**, todas alinhadas no mesmo referencial e já
atribuídas aos seus filamentos.

![O painel do SVG Multicor](docs/screenshot-pt_BR.png)

## O que ele faz

- **3MF novo**: um objeto com uma peça por cor, com nome e filamento, opcionalmente
  sobre uma **placa de base** (seguindo o contorno ou em retângulo
  arredondado). Abre no OrcaSlicer / Bambu Studio pronto para fatiar. Também gera
  3MF padrão (com cores) para outros fatiadores e um STL por cor.
- **Aplicar num projeto**: acrescenta as cores como novas peças de um objeto de
  um projeto salvo, centradas na face superior, **embutidas** (mesma altura, as
  últimas camadas trocam de cor) ou **em relevo**. Funciona com os projetos que o
  OrcaSlicer e o Bambu Studio salvam hoje. O projeto original nunca é
  sobrescrito.
- **Enxerga o SVG como o navegador**: o que é pintado depois cobre o que veio
  antes, então as peças se encaixam em vez de se sobreporem; as regras de
  preenchimento (nonzero / evenodd) são exatas; contornos (stroke) viram áreas
  imprimíveis; gradientes usam a média das cores; formas ocultas ou totalmente
  transparentes são ignoradas; entende classes CSS, `<use>`, transformações e
  unidades físicas (`width="80mm"`).
- **Cabe na sua impressora**: limita o número de cores aos seus filamentos
  juntando as menos importantes na mais parecida (CIEDE2000), junta tons quase
  iguais e pode passar detalhes mais finos que o bico para a cor vizinha.
- **Lê os filamentos** do OrcaSlicer e casa cada cor com o mais próximo.
  Pré-visualização ao vivo, nome, filamento e liga/desliga por cor.
- **13 idiomas**, seguindo o idioma do OrcaSlicer automaticamente.

## Instalação

1. Baixe `orca_svg_multicor-<versão>-py3-none-any.whl` na
   [última versão](https://github.com/opoeta/orca-svg-multicor/releases/latest).
2. No OrcaSlicer, abra a janela de **Plugins** e instale o `.whl` como plugin
   local. O OrcaSlicer instala as dependências (numpy, shapely, svgelements,
   mapbox-earcut) sozinho.
3. Ative o plugin. Ele acrescenta:
   - **SVG Multicolor**: uma página ao lado de Preparar e Visualizar;
   - **SVG Multicolor - batch**: converte todos os SVGs da pasta de entrada com
     as mesmas configurações, pela ação Executar do diálogo de Plugins.

   Versões do OrcaSlicer sem páginas de plugin recebem **SVG Multicolor -
   window**: a mesma página numa janela.

> **Atualizando da 2.x**: remova o plugin antigo antes. As duas versões usam o
> mesmo nome de pacote Python e não podem ser carregadas juntas.

## Como usar

A página funciona como a aba Preparar: ajustes à esquerda, visualização à
direita e a ação principal no canto superior direito.

1. **Arquivo SVG**: *Procurar…* e escolha o SVG. As cores aparecem sozinhas.
2. **Cores**: passe o mouse numa linha para destacá-la na visualização.
   Renomeie as peças, desmarque o que não quer (um fundo, por exemplo; cores que
   ocupam o desenho inteiro recebem a etiqueta *fundo?*) e escolha o filamento
   de cada cor, ou deixe a varinha casar com os filamentos carregados no Orca.
3. **Aplicar em**:
   - **Um objeto da mesa**: salve o projeto (Ctrl+S), escolha o objeto, o
     encaixe (*embutido*: mesma altura, as últimas camadas mudam de cor; ou *em
     relevo*) e clique em **Aplicar na mesa**. A API de plugins do OrcaSlicer não
     altera a mesa diretamente, então o desenho vai para o projeto salvo, que
     reabre no OrcaSlicer já com as peças novas. O arquivo original é mantido; o
     resultado é salvo como `*_svg.3mf` na pasta de saída.
   - **Um objeto novo na mesa**: com ou sem placa de base, clique em
     **Adicionar à mesa**; o OrcaSlicer abre o 3MF novo.

A página lembra os valores que você muda. Os padrões, a pasta de saída, o
formato, o STL e o idioma ficam no diálogo de Plugins, aba **Config**, junto
com as novidades de cada versão.

### Bom saber

- **Texto** precisa ser convertido em curvas no editor; **imagens bitmap** são
  ignoradas; **máscaras e recortes** são ignorados. O painel avisa sobre tudo
  isso.
- A **janela de seleção de arquivo** roda como processo separado (PowerShell no
  Windows), e o resultado é aberto iniciando o executável do OrcaSlicer, que
  entrega o arquivo à janela já aberta. O OrcaSlicer pergunta uma vez se o
  plugin pode iniciar um processo; se você negar, a página oferece enviar uma
  cópia do SVG.
- A janela de **Plugins do OrcaSlicer só mostra imagem e changelog para plugins
  instalados pela OrcaCloud**; num `.whl` local os dois ficam vazios por projeto
  do Orca. Quando o plugin estiver na OrcaCloud, instale pela Plugin Hub para
  tê-los ([docs/orcacloud](docs/orcacloud/README.md)). O changelog também está
  na aba Config do plugin e em [CHANGELOG.md](CHANGELOG.md).
- Se o OrcaSlicer perguntar se o plugin pode iniciar um processo ao usar
  "Procurar…", pode responder Sim: é a janela nativa de seleção de arquivos.
- Os arquivos ficam em `<pasta de dados do OrcaSlicer>/svg_multicor/`
  (entrada, saída e `plugin.log`).

## Créditos

Criado por Israel Fernandes. Licença [MIT](LICENSE).
