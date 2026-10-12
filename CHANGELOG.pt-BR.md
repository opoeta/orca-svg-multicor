# Changelog

[English](CHANGELOG.md) · **Português (Brasil)**

## 3.13.0

### Novo
- **Pintar na superfície** ("No objeto", barra embaixo da vista):
  - **Pincel**: arraste para pintar; o traço usa a cor de onde começa,
    copiando a cor do lado (clicar numa cor a escolhe). Tamanho do pincel em
    mm.
  - **Balde**: clique numa área da superfície sem desenho (faixa da borda,
    canto, fresta): ela é preenchida com a cor que mais encosta nela.
  - O que for pintado vira parte daquelas cores e sai nas mesmas camadas do
    resto (espessura, primeira camada). Fica na superfície quando o desenho
    se move. Desfazer e limpar; uma superfície ou um objeto novo começa
    limpo.

## 3.12.0

### Novo
- **Preencher**: o desenho cobre a superfície inteira, proporcional e
  centralizado, sem sobrar borda (ao lado de *Centralizar*, e no último passo
  do assistente).
- **O desenho pode passar da superfície**, até cobri-la e mais 25%; o que
  passa da borda é cortado, como antes, e mover escolhe o que aparece. A
  linha de tamanho avisa ("passa da superfície").
- **Tamanho livre**: uma **Altura** própria ao lado da largura (vazio:
  proporcional), e **Shift + arrastar o canto** muda largura e altura
  independentes.
- **Girar a vista** (↻ acima do desenho): "No objeto" gira de 90 em 90°, com
  os lados da mesa em volta, a posição e a grade 3×3 do assistente seguindo a
  tela. Só a vista gira; o resultado não muda.

### Corrigido
- Os nomes em volta da superfície podiam ficar selecionados (marcados) ao
  arrastar fora do desenho.

## 3.11.1

### Corrigido
- A lista de Superfície do assistente continuava com as faces do objeto
  escolhido antes: depois de trocar de objeto, escolher uma superfície ali
  podia selecionar outra face do objeto novo (desde a 3.9.0). Agora ela
  acompanha a barra lateral.

## 3.11.0

### Novo
- **Onde a face fica no objeto, em "No objeto".** Em volta da face, o objeto
  inteiro visto daquele lado (tracejado: abas, encaixes e contorno, que não
  fazem parte da face), os lados da mesa (Frente, Trás, Esquerda, Direita, ou
  Topo e Fundo numa parede) e qual vista do OrcaSlicer mostra igual, com o
  atalho (Ctrl+1 a Ctrl+6, por exemplo "Visto de baixo, como a vista de
  baixo do OrcaSlicer (Ctrl+2)").

### Mudou
- **Uma pergunta de permissão por projeto em vez de duas.** O OrcaSlicer
  pergunta antes de um plugin ler um arquivo e pergunta de novo antes de
  gravá-lo; agora o projeto já é aberto para leitura e gravação, porque
  aplicar grava nele. Um projeto somente leitura continua sendo lido; um
  "Não" continua sendo "Não". O OrcaSlicer ainda pergunta uma vez para cada
  arquivo novo, e de novo a cada atualização do plugin (ele apaga as
  permissões da versão anterior).

## 3.10.2

### Corrigido
- **Um canto da superfície cortado na diagonal** (o canto arredondado de uma
  tampa, e o desenho recortado junto). Malhas exportadas de CAD muitas vezes
  têm vértices a poucos décimos de milésimo de milímetro um do outro onde
  deveriam ser um só; os triângulos do canto arredondado então só tocavam o
  resto da face em pontos, e o canto era descartado como um pedaço pequeno
  demais. Agora a face é fechada em 0,01 mm antes de ser recortada, o que os
  junta e não muda o contorno de forma que uma impressora perceba.
- Listar as superfícies de um objeto com muitas faces planas pequenas (uma
  bandeja com cem furos) levava cerca de 13 s, com o OrcaSlicer travado;
  agora leva menos de um segundo, com a mesma lista.

## 3.10.1

### Corrigido
- **"O projeto aberto tem alterações não salvas" mesmo logo depois do
  Ctrl+S.** O OrcaSlicer conta presets alterados e não salvos como preset
  como alterações do projeto, e salvar o projeto não limpa isso. Quando só os
  presets estão pendentes e todos os objetos da mesa estão onde o projeto
  salvo os tem (mesmos objetos, peças e posição), dá para aplicar; a linha da
  mesa avisa. Se algum objeto foi movido, girado, adicionado ou removido desde
  o último salvamento, a página continua pedindo para salvar antes, porque
  reabrir o arquivo perderia isso.

## 3.10.0

### Mudou
- **De início fica a face apoiada na mesa** (o desenho nas primeiras
  camadas); antes, a maior face virada para cima.
- **O desenho segue o objeto como ele está na mesa.** "No objeto" mostra a
  face como o OrcaSlicer mostra, girada como o objeto está na mesa, e o
  desenho alinhado às bordas do objeto, com o topo na borda mais próxima do
  "para cima" da vista do OrcaSlicer para aquela face: o topo visto de cima,
  as paredes em pé, o fundo como na vista de baixo do OrcaSlicer (a frente da
  mesa para cima). Arrastar e redimensionar funcionam na vista girada.
- Na face de baixo, o desenho saía de cabeça para baixo em relação à vista de
  baixo do OrcaSlicer. Se você usava Rotação 180° para compensar, volte para
  0°.

## 3.9.1

### Corrigido
- **Procurar… abria na pasta de dados do plugin.** Agora abre onde está o SVG
  atual, senão de onde veio o último (lembrado entre uma sessão e outra),
  senão em Downloads.
- **Um pedido de permissão a cada "Aplicar na mesa"**: a cópia de segurança
  do projeto tinha um nome novo a cada vez, e o OrcaSlicer perguntava sobre o
  projeto e essa cópia juntos. Agora a cópia é gravada sozinha na pasta de
  dados, que não precisa de permissão: o mesmo trabalho não pergunta nada na
  segunda vez. Um teste roda cada ação duas vezes com as regras de permissão
  do OrcaSlicer para manter assim.
- Escolher uma pasta de saída fora da pasta de dados não pede mais para criar
  e apagar um arquivo de teste nela.
- Reabrir o projeto não inicia mais uma thread (versões recentes do
  OrcaSlicer perguntam antes de um plugin iniciar uma): o arquivo vai direto
  para o OrcaSlicer.
- Um OrcaSlicer portátil, ou iniciado com `--datadir`, guarda os arquivos do
  plugin na própria pasta de dados.

### Mudou
- **Instalado pela OrcaCloud**, o OrcaSlicer mostra a imagem do plugin em
  *Plugin Info* e as novidades na aba *Changelog* (ele só preenche isso para
  plugins da OrcaCloud), e a aba Config não repete mais o changelog.
  Instalado por arquivo, a aba Config continua com ele, fechado. As notas
  enviadas à OrcaCloud vão em texto simples, uma linha por item, como a aba
  Changelog mostra.
- As configurações também ficam guardadas na pasta de dados, então instalar
  de novo (ou pela OrcaCloud em vez de por arquivo) as mantém; "Restaurar
  padrões" continua restaurando os padrões.

## 3.9.0

### Novo
- **Um assistente passo a passo** ao lado do desenho (abre quando você
  escolhe um SVG; a varinha ao lado de *Procurar…* o traz de volta):
  1. **Desenho**: escolha quais **camadas do arquivo** usar (camadas do
     Illustrator e do Inkscape; uma camada escondida não muda o tamanho nem o
     lugar do desenho), o tamanho e **Espelhar** (esquerda ↔ direita).
  2. **Cores**: quantas cores, como antes.
  3. **Filamentos**: um filamento para cada cor e **Cores do desenho nos
     filamentos do projeto**: ao aplicar na mesa, cada filamento usado fica
     com a cor da sua peça (a maior, se dividirem o filamento), no próprio
     projeto. Também fica na barra lateral, em *Aplicar em*.
  4. **Acabamento**: arestas *Detalhado*, *Normal* ou *Simplificado* (ajustes
     prontos de precisão e de limpeza de pontas e lascas), a espessura das
     cores e, num objeto, a superfície, a primeira camada, a **posição** na
     face (grade 3×3: cantos, lados, centro) e a rotação.
- A barra lateral mostra quantas camadas do arquivo estão em uso, com
  *Escolher*, e uma caixa **Espelhar** abaixo do tamanho.

## 3.8.1

### Corrigido
- "Arestas não-manifold" nas peças no OrcaSlicer (3.8.0, com a limpeza nova):
  a triangulação deixa de fora pontos que ficam sobre uma aresta reta, e as
  paredes ainda os usavam, então as arestas delas não encontravam as da
  tampa. Agora as paredes seguem os pontos que a tampa usa. Contornos que se
  tocam num único ponto (um furo encostando em outro contorno, duas partes de
  uma cor encostando) são afastados por um centésimo de milésimo de
  milímetro, para que as paredes também não se encontrem ali, mesmo quando o
  fatiador junta vértices iguais.

## 3.8.0

### Mudou
- **Detalhes finos e pontas agudas são limpos por padrão** (Avançado,
  "Limpar detalhes e pontas abaixo de", 0,4 mm): linhas e pontas de agulha
  que um bico de 0,4 mm não imprime passam para a cor vizinha, sem frestas, e
  os cantos arredondam com 0,2 mm. São os pontinhos e lascas que o fatiador
  imprimia mal entre as cores. A limpeza agora usa uma ferramenta redonda: a
  anterior engrossava as cores de volta com cantos em ponta e recriava as
  pontas que tinha tirado (num desenho real, o que um bico de 0,4 mm não
  alcança ia de 46 mm² para 34 mm² antes, e para 11 mm² agora), e leva cerca
  de um segundo. Configurações que ainda tinham o padrão antigo, desligado,
  passam para 0,4 mm uma vez.

### Corrigido
- Uma cor cujas peças se tocavam num único ponto era exportada com malha não
  manifold (as peças dividiam uma aresta vertical); agora cada peça é uma
  casca fechada própria.

## 3.7.1

### Corrigido
- Os objetos ficavam duplicados na mesa depois de aplicar: quando o projeto
  reabre numa mesa que tem objetos, o OrcaSlicer pergunta como carregá-lo e
  já deixa marcada a última escolha, e "Importar somente geometria" soma os
  objetos de novo. O plugin não pode responder por você (as configurações do
  OrcaSlicer são fechadas aos plugins), então a página e a mensagem de
  reabertura agora dizem para escolher "Abrir como projeto". Ctrl+Z desfaz uma
  importação duplicada.

## 3.7.0

### Mudou
- **Aplicar num objeto da mesa atualiza o próprio projeto** em vez de gravar
  um `*_svg.3mf` novo: o resultado substitui o projeto salvo, que reabre já
  com as peças novas. Antes, a versão anterior é copiada para
  `<pasta de dados do OrcaSlicer>/svg_multicor/backups` (ficam as últimas 20).
  "Gravar em" (na página e na aba Config) ainda oferece a cópia. A API de
  plugins do OrcaSlicer só lê a mesa, então o caminho é o arquivo do projeto.

### Corrigido
- "A mesa está vazia" quando a página lia a mesa antes de um projeto ser
  aberto: agora a página relê a mesa a cada poucos segundos enquanto "Um
  objeto da mesa" está escolhido, redesenhando só o que mudou.

## 3.6.0

### Novo
- **Reenquadrar o desenho no objeto**: em "No objeto", arraste o desenho para
  mover e puxe o canto para mudar o tamanho. Ele fica sempre dentro da
  superfície: não pode ser maior que a face nem passar das bordas (o plugin
  também garante isso). "Centralizar" volta ao meio.
- **Espessura em camadas**: "Espessura das cores" em mm ou em camadas. A
  altura de camada é a do projeto (aplicando na mesa) ou a do perfil da
  impressora (objeto novo), ou a definida em Avançado; na mesa, a altura da
  1ª camada vale para a primeira delas. A página mostra o resultado em mm.
- **Primeira camada**: na face apoiada na mesa, escolha se o desenho começa
  na 1ª camada ou logo acima dela, com a 1ª camada inteira da cor do objeto.

### Mudou
- Um desenho maior que a superfície escolhida é reduzido para caber, em vez
  de ser cortado nas bordas.

## 3.5.1

### Corrigido
- Um objeto novo saía com metade do tamanho do desenho: o tamanho padrão era
  "Largura 100 mm". Agora o padrão é **o tamanho do próprio arquivo**, e as
  configurações que ainda tinham o padrão antigo (largura, 100 mm) passam para
  ele uma vez.
- O tamanho real de SVGs exportados pelo Adobe Illustrator: eles não têm
  largura nem altura e mantêm as 72 unidades por polegada do Illustrator,
  então uma prancheta de 201 mm era lida como 150,75 mm. Os arquivos do
  Illustrator são reconhecidos pelos metadados.
- A página mostra o tamanho do arquivo sob "Tamanho" ("Arquivo: 201 × 201 mm").

## 3.5.0

### Novo
- **Quantas cores?** Ao abrir um SVG, o desenho aparece com 2, 3 ... 12 cores
  lado a lado, com o número dos seus filamentos marcado; um clique define o
  "Máx. de cores". O botão ao lado de "Máx. de cores" traz a escolha de volta;
  a aba Config pode desligá-la ("Perguntar quantas cores ao abrir um SVG").
- **Clique numa cor do desenho** para escolher o filamento dela; Ctrl+clique
  (ou Shift+clique) seleciona várias, e a escolha vale para todas. O desenho
  passa a mostrar a cor do filamento. O mesmo menu tem "Outra cor…" e "Não
  imprimir".

## 3.4.2

### Corrigido
- A redução de cores perdia cores pequenas mas diferentes: com "Máx. de cores"
  abaixo das cores do desenho, a menor cor sempre se juntava à mais parecida,
  e um pouco de verde virava azul-claro. Agora se junta o par que menos muda o
  desenho (a área que muda de cor vezes o quanto ela muda): cores parecidas,
  como dois azuis, se juntam primeiro, e uma cor pequena e diferente fica.

## 3.4.1

### Corrigido
- A 3.4.0 chegou ao GitHub mas não à OrcaCloud: as notas dela têm ponto e
  vírgula, e a etapa de publicação cortava os dados da versão ali. Esta versão
  leva para a OrcaCloud as mudanças da 3.4.0: mudar a cor de uma peça (clique
  no quadrado da cor) e os nomes inteiros dos filamentos na lista de cores.

## 3.4.0

### Novo
- **Mudar a cor de uma peça**: clique no quadrado da cor na página e escolha
  outra. A peça sai e aparece nessa cor; o nome e o filamento sugerido
  acompanham a cor nova, a menos que você os tenha mudado, e o ↺ volta à cor
  original.

### Corrigido
- Os nomes dos filamentos ficavam cortados na lista de cores: agora o filamento
  tem uma linha só para ele, os detalhes (formas, tons, fundo) vão logo abaixo,
  e passar o mouse mostra o nome inteiro.

## 3.3.3

### Mudou
- As versões são publicadas na OrcaCloud quando a release do GitHub é
  publicada, como a OrcaCloud exige: uma tag deixa um rascunho de release com
  o wheel e as notas, e publicar o rascunho publica a versão no GitHub e na
  OrcaCloud.

## 3.3.2

### Mudou
- A aba Config mostra as novidades em português quando o OrcaSlicer está em
  português (`CHANGELOG.pt-BR.md`, que agora vai junto com o plugin); nos
  outros idiomas continua o changelog em inglês.
- As notas das versões no GitHub e na OrcaCloud saem em inglês e em português.
- Prints novas na documentação.

## 3.3.1

### Corrigido
- Depois de reiniciar o OrcaSlicer, ler um SVG falhava com "O OrcaSlicer
  bloqueou o acesso do plugin a um arquivo (Plugin attempted an audited
  operation without permission)". O OrcaSlicer recusa aos plugins qualquer
  caminho com "conf" no nome, e o numpy não pode ser importado sem ler
  `numpy/__config__.py`; o plugin importava o numpy só na hora de usar, e isso
  o OrcaSlicer audita. Agora as bibliotecas são carregadas enquanto o
  OrcaSlicer carrega o plugin, etapa que ele não audita, e por isso também não
  é preciso pedir permissão depois para os módulos da biblioteca padrão que o
  plugin usa. Se ainda assim falhar, a mensagem diz para reiniciar o
  OrcaSlicer.

## 3.3.0

### Novo
- **Escolha da superfície**: ao aplicar num objeto da mesa, a página oferece
  todas as faces planas do objeto, com os nomes que você vê na mesa (Topo,
  Fundo, Frente, Trás, Esquerda, Direita, Inclinada) e o tamanho, e o lado de
  dentro de uma parede como "Frente (interna)" e assim por diante. O desenho vai
  na face escolhida, na direção dela: embutido no objeto ou em relevo sobre
  ela, recortado pelo contorno da face.
- **Rotação** do desenho na face (0, 90, 180 ou 270 graus).
- Visualização **No objeto**: a face escolhida com o desenho em cima, no
  tamanho que ele vai ter; o que sobra para fora da face aparece apagado, e o
  tamanho fica laranja quando o desenho é maior que a face.

### Corrigido
- Num objeto oco (uma bandeja, uma caixa) o desenho ia para o ponto mais alto,
  flutuando sobre a cavidade, na borda. A superfície oferecida primeiro agora é
  a maior face virada para cima que fica mesmo do lado de fora (o fundo da
  bandeja), e as faces onde duas peças do objeto se encostam não são
  oferecidas.
- "Embutido" e "em relevo" não falam mais em "topo", e o desenho não segue mais
  a caixa envolvente do objeto, que num objeto girado ou irregular não era uma
  superfície dele.

## 3.2.0

### Mudou
- O resultado chega ao OrcaSlicer pelo mesmo canal que o próprio inicializador
  dele usa quando roda em instância única (no Windows, uma mensagem para a
  janela principal), como outros plugins fazem: nenhum processo é iniciado,
  então não há pedido de permissão. Iniciar o executável do OrcaSlicer fica
  como alternativa.

### Novo
- As versões podem ser publicadas na OrcaCloud automaticamente (publicação
  confiável pelo GitHub). A janela de Plugins do OrcaSlicer só mostra a imagem
  e o changelog de plugins instalados pela OrcaCloud; `docs/orcacloud/README.md`
  explica a configuração, feita uma vez só.

## 3.1.1

### Corrigido
- A página de configurações da aba Config não abria ("PermissionError: Plugin
  attempted an audited operation without permission"). O OrcaSlicer recusa aos
  plugins qualquer caminho com "conf", "cert" ou "secret" no nome de um arquivo
  ou pasta, e o arquivo da página se chamava `config.html`; agora é
  `settings.html`, e os testes e a verificação do pacote rejeitam esses nomes.
- Um SVG, projeto ou pasta de saída com uma dessas palavras no caminho agora
  recebe uma mensagem clara dizendo por que o OrcaSlicer o bloqueia, em vez de
  um erro inesperado; o mesmo vale para qualquer outra permissão que o
  OrcaSlicer negar.

## 3.1.0

### Mudou: agora ele se comporta como um plugin
- A página segue o layout da aba Preparar do OrcaSlicer (configurações à
  esquerda, a visualização à direita, a ação principal no alto), com o tema e
  os estilos padrão de plugins do próprio OrcaSlicer, no idioma do OrcaSlicer.
  Saíram: o cabeçalho próprio da página, o seletor de idioma, o painel de log,
  a lista de pastas de entrada, as abas e os botões "salvar como padrão".
- As configurações ficam na aba **Config** da janela de Plugins, numa página
  traduzida que também mostra as novidades. A página lembra os valores que você
  muda nela, e a capacidade de lote usa as mesmas configurações.
- O resultado sempre volta para o OrcaSlicer.
- A capacidade "janela" só aparece em versões do OrcaSlicer sem páginas de
  plugin.

### Novo
- **Aplicar num objeto da mesa**: escolha um objeto do projeto aberto em
  Preparar; o desenho é aplicado no projeto salvo, que reabre no OrcaSlicer já
  com as peças novas. A API de plugins do OrcaSlicer não altera a mesa
  diretamente, então salve o projeto (Ctrl+S) antes; a página avisa quando há
  alterações não salvas ou objetos que ainda não estão no arquivo salvo.
- **Adicionar como objeto novo**: o 3MF novo abre no OrcaSlicer.
- Os arquivos são abertos pelo próprio OrcaSlicer (o executável dele, que os
  entrega à janela já aberta) em vez da associação de arquivos do sistema, que
  pode apontar para outro programa.
- As mensagens do plugin também vão para o log Python do OrcaSlicer.

### Removido
- Aplicar num outro arquivo `.3mf` salvo a partir da página (a mesa cobre esse
  caso), a opção "abrir ao terminar" e o link "usar a pasta do projeto".

## 3.0.1

### Corrigido
- Procurar um arquivo fazia o OrcaSlicer perguntar sobre um evento Python
  "open" sem destino. Ele vinha do pipe que o Python abre para ler a resposta
  do seletor; agora o seletor grava a resposta num arquivo na pasta de dados do
  plugin, que não precisa de permissão. (Iniciar o processo do seletor ainda
  pode ser perguntado uma vez.)
- O numpy e o shapely eram importados assim que o plugin carregava, através
  das funções de cor; agora só carregam quando um desenho é processado.
- Os testes e o servidor de desenvolvimento gravavam no log real do plugin.

### Novo
- Um ícone SVG nítido para a aba da página do plugin.
- `docs/orcacloud/`: imagem de capa e textos para publicar na OrcaCloud, a
  única fonte que o OrcaSlicer usa para a imagem e o changelog da janela de
  Plugins.

## 3.0.0

Uma reescrita focada em resultados corretos, nos projetos que os fatiadores
salvam hoje e numa interface em 13 idiomas.

### Corrigido
- **As cores se sobrepunham em 3D.** Cada cor era a união de todas as suas
  formas, ignorando o que era pintado por cima, então um logo branco num
  quadrado preto gerava um quadrado preto inteiro mais uma peça branca no mesmo
  volume. Agora as formas são resolvidas como o navegador as pinta: as formas
  pintadas depois recortam as anteriores e as peças se encaixam lado a lado.
- **"Aplicar num projeto" não funcionava com projetos salvos pelo OrcaSlicer ou
  pelo Bambu Studio.** Esses projetos guardam as malhas em `3D/Objects/*.model`
  por trás de componentes, que o plugin rejeitava ("feito de componentes").
  Agora são suportados, e o tamanho do objeto inclui as transformações dos
  componentes.
- **Os prefixos de namespace eram reescritos nos projetos salvos.**
  Reserializar o `3dmodel.model` com o ElementTree trocava prefixos como `p:`
  por prefixos automáticos (`ns0:`), enquanto o OrcaSlicer procura `p:path` e
  `p:UUID` literalmente. Agora os arquivos são editados só inserindo texto.
- **"Aplicar" usava o projeto errado.** O caminho de projeto digitado ou lido da
  mesa não era enviado; usava-se o primeiro arquivo da lista da pasta de
  entrada, junto com o id de um objeto do outro arquivo.
- Caminhos abertos perdiam o primeiro ponto ("M0,0 L10,0 L10,10" não gerava
  nada).
- Ilhas dentro de furos sumiam com a regra nonzero; anéis sobrepostos eram
  unidos em vez de recortados com a regra evenodd. As duas regras agora são
  exatas.
- Gradientes saíam pretos; agora usam a média das suas cores.
- Formas com `opacity="0"`, `fill-opacity="0"` ou cores totalmente
  transparentes eram impressas.
- A amostragem de curvas e a simplificação trabalhavam em unidades do SVG,
  então viewBoxes pequenos perdiam detalhe e grandes geravam arquivos enormes.
  Agora as duas trabalham em milímetros.
- Nomes de presets de filamento e de cores eram inseridos na página como HTML;
  um nome com `<` ou `"` podia quebrar a lista de cores. Agora a página monta
  cada elemento por chamadas do DOM.
- Duas peças com o mesmo nome recebiam o mesmo filamento (os filamentos eram
  associados pelo nome).
- A lista de filamentos ficava limitada ao valor de "máx. de cores".
- O plugin reescrevia o `icon.png` dentro do pacote instalado sempre que o
  OrcaSlicer pedia o ícone (trocando o ícone de 256 px por um de 64 px).
- O modo lote abria uma caixa de mensagem por arquivo convertido.
- A janela de progresso nativa não conseguia cancelar nada.

### Novo
- Interface em English, Português (Brasil), Español, Français, Deutsch,
  Italiano, Polski, Türkçe, Русский, Українська, 简体中文, 日本語 e 한국어,
  seguindo o idioma do OrcaSlicer ou escolhida na página.
- Painel novo: pré-visualização ao vivo (resultado e original), passar o mouse
  para destacar uma cor, nome, filamento e liga/desliga por cor, amostras de
  filamento, barra de progresso, log, temas claro e escuro, layout responsivo.
- Contornos (strokes) viram áreas imprimíveis (junções, pontas e limite de
  miter respeitados).
- Placa de base (seguindo o contorno ou em retângulo arredondado) para 3MF
  novos.
- "Remover detalhes mais finos que": lascas impossíveis de imprimir vão para a
  cor vizinha, sem deixar buracos.
- Distância de cor perceptual (CIEDE2000) para juntar e reduzir cores e casar
  filamentos; nomes de cores melhores.
- "Tamanho original" a partir das unidades físicas do SVG.
- A saída 3MF padrão leva as cores (`basematerials`).
- Seletores de arquivo nativos para SVG e projetos (não só pastas), sempre na
  frente.
- Avisos para texto, imagens bitmap, recortes/máscaras, tracejados,
  transparência.
- As configurações podem ser salvas como padrão; a pasta de saída é lembrada.
- Testes (87), um servidor de desenvolvimento para rodar o painel no
  navegador, CI e releases no GitHub.

### Mudou
- As bibliotecas pesadas só são importadas quando necessárias, então o
  OrcaSlicer abre mais rápido com o plugin ativado.
- Os nomes das capacidades agora são `SVG Multicolor`, `SVG Multicolor - window`
  e `SVG Multicolor - batch`; as chaves de configuração estão em inglês.
- O log é `<dados>/svg_multicor/plugin.log`, com rotação em 1 MB, em vez de um
  `registro.txt` gravado na pasta de saída.
- O modo lote não aplica mais o primeiro SVG num projeto.

## 2.9.0

Versão original de Israel Fernandes.
