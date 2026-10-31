# Referência de portabilidade móvel — Gen1Recomp

**Referência analisada:** [bryanthaboi/gen1recomp](https://github.com/bryanthaboi/gen1recomp), branch dev, commit 0be34bc76cecf996e91d2f905d1b4bb5f14d43ae (30/10/2026).

**Objetivo:** registrar padrões arquiteturais que podem orientar Android/iOS no Platina Reluzente. Não é uma proposta de trocar o motor do Platinum por LÖVE, nem uma autorização para copiar código, assets ou o launcher do Gen1Recomp.

## 1. Como o Gen1Recomp organiza o mobile

O Gen1Recomp mantém o jogo e a lógica principal em Lua/LÖVE. Android e iOS acrescentam integrações nativas para recursos do sistema; não mantêm uma implementação separada do gameplay para cada plataforma.

### Android

Fontes consultadas:
- [mobile/ANDROID.md](https://github.com/bryanthaboi/gen1recomp/blob/dev/mobile/ANDROID.md)
- [GameActivity.java](https://github.com/bryanthaboi/gen1recomp/blob/dev/mobile/android/love/src/main/java/org/love2d/android/GameActivity.java)
- [android.cpp — ponte JNI](https://github.com/bryanthaboi/gen1recomp/blob/dev/mobile/android/love/src/jni/love/src/common/android.cpp)
- [build.gradle do app](https://github.com/bryanthaboi/gen1recomp/blob/dev/mobile/android/app/build.gradle)

O app Android usa uma Activity derivada de SDLActivity. A Activity é a fronteira com Android; SDL e o jogo continuam responsáveis pela janela, renderização e eventos. A ponte C++/JNI usa as funções do SDL para obter o ambiente JNI e a Activity atual, chama serviços Java e retorna resultados ao código nativo.

A camada Android concentra:
- ciclo de vida da Activity, foco, áudio e periféricos;
- Storage Access Framework (SAF), permissões e cópia dos arquivos escolhidos;
- orientação, área segura, densidade e recursos específicos do dispositivo;
- transporte HTTPS quando a plataforma não oferece o mesmo mecanismo de processo que o Desktop.

Um detalhe especialmente relevante: a ponte pergunta ao filesystem qual é o diretório de save que está realmente montado e passa esse caminho à Activity. Ela não presume que recalcular getExternalFilesDir() produzirá o mesmo caminho, pois volumes adotados ou combinados podem divergir.

O picker também é tratado como uma operação assíncrona, não como uma função que retorna imediatamente um caminho. A Activity mantém o nome de destino e o diretório da operação, protege o estado com uma máquina simples (IDLE → PICKING → RESULT → COPYING), ignora resultados duplicados e salva o estado pendente em onSaveInstanceState para sobreviver à recriação da Activity. Cancelamento, falha e conclusão são comunicados ao jogo por resultados/flags explícitos.

### iOS

Fontes consultadas:
- [mobile/ios/README.md](https://github.com/bryanthaboi/gen1recomp/blob/dev/mobile/ios/README.md)
- [patch_love_src.py](https://github.com/bryanthaboi/gen1recomp/blob/dev/mobile/ios/patch_love_src.py)
- [GRPickerBridge.swift](https://github.com/bryanthaboi/gen1recomp/blob/dev/mobile/ios/native/GRPickerBridge.swift)
- [GRBootstrap.m](https://github.com/bryanthaboi/gen1recomp/blob/dev/mobile/ios/native/GRBootstrap.m)
- [ios.mm — áudio e safe area](https://github.com/bryanthaboi/gen1recomp/blob/dev/mobile/android/love/src/jni/love/src/common/ios.mm)

O host iOS permanece em torno de SDL/LÖVE. Recursos da Apple são expostos por bridges Objective-C/Objective-C++ e Swift. O patch do Gen1Recomp adiciona as classes nativas ao target Xcode e expõe serviços ao código comum através do runtime Objective-C; o núcleo C++ não precisa conhecer diretamente tipos Swift.

A ponte de documentos usa UIDocumentPickerViewController. Ao receber uma URL, abre acesso security-scoped, copia o conteúdo para o diretório da aplicação e encerra o acesso coordenado. O delegate é retido enquanto o picker está aberto, porque UIKit mantém o delegate como referência fraca. Há também proteção contra duas apresentações, tratamento de cancelamento e de fechamento interativo do sheet.

O bootstrap iOS observa a ativação da aplicação para preparar o diretório de documentos e procurar arquivos que o utilizador tenha colocado pelo Files. A camada de áudio observa interrupções de AVAudioSession e reativa o contexto quando a aplicação volta a ficar ativa. A área segura é obtida dos insets da view UIKit e convertida para as unidades usadas pela janela SDL.

## 2. Toque, gamepad e input: uma única abstração

Fontes consultadas:
- [TouchControls.lua](https://github.com/bryanthaboi/gen1recomp/blob/dev/src/core/TouchControls.lua)
- [Input.lua](https://github.com/bryanthaboi/gen1recomp/blob/dev/src/core/Input.lua)
- [Game.lua — touch e lifecycle](https://github.com/bryanthaboi/gen1recomp/blob/dev/src/core/Game.lua)
- [Game2.lua — touch e lifecycle](https://github.com/bryanthaboi/gen1recomp/blob/dev/src/core/Game2.lua)
- [SafeArea.lua](https://github.com/bryanthaboi/gen1recomp/blob/dev/src/core/SafeArea.lua)

O Gen1Recomp não cria uma lógica de gameplay separada para toque. O overlay virtual gera os mesmos comandos da abstração de input que já recebe teclado e gamepad. Os controles táteis têm uma fonte própria, para que uma tecla física, um stick e um dedo possam manter o mesmo botão pressionado sem que a liberação de uma fonte solte a outra.

Detalhes que valem como referência:
- Cada dedo é identificado pelo seu ID de toque. O D-pad acompanha o movimento do dedo e troca a direção sem exigir soltar e tocar novamente.
- Os botões ficam pressionados até a liberação daquele dedo. Contadores/referências evitam que um segundo dedo solte prematuramente um botão que ainda está sendo usado.
- O overlay tem primeira prioridade sobre o evento de ponteiro: se o toque começar num botão virtual, pertence ao controle até terminar e não vaza para o jogo/mod; se começar fora, continua sendo um ponteiro normal mesmo que atravesse o overlay.
- Ao detectar um gamepad, o overlay pode esconder-se; volta quando o utilizador toca no ecrã ou quando o último controle é removido.
- Layouts e tamanhos de retrato e paisagem são guardados separadamente. As posições usam frações da área segura, e não pixels absolutos.
- Perda de foco, invisibilidade, interrupção do sistema ou perda de um dispositivo limpam os estados de input para não deixar um botão preso. O jogo também reconcilia o estado dos dispositivos quando necessário.
- O overlay é desenhado na camada da interface, depois dos passes de imagem do jogo; não altera o conteúdo interno do ecrã do jogo.

Os testes existentes cobrem o overlay da terceira geração, input de gamepad, orientação, segundo ecrã, lifecycle Android e picker iOS. Eles são uma boa referência de como transformar falhas reais de dispositivos em regressões automatizadas, em vez de validar apenas se o projeto compila.

## 3. Cruzamento com o input SDL atual do Platinum

**Fonte fixada:** [libntr/libraries/sim/src/sim_main.cpp](https://github.com/cybervisi0n/libntr/blob/1555d911ac80c0190ac1c321f99f1323de8b3c09/libraries/sim/src/sim_main.cpp), commit 1555d911ac80c0190ac1c321f99f1323de8b3c09.

O Platinum já tem a geometria do touchscreen DS. Em sim_main.cpp, s_TouchPanelCoords é recalculado conforme screenLayout, swapScreens e o viewport usado para desenhar as duas telas. O código converte as coordenadas do ponteiro para SIM_NDS_SCREEN_WIDTH × SIM_NDS_SCREEN_HEIGHT e atualiza s_tpData. Portanto, esse mapeamento de layouts deve ser preservado.

O limite atual é o tipo de evento: o loop processa SDL_MOUSEBUTTONDOWN/UP e consulta SDL_GetMouseState a cada frame. A revisão inspecionada não tem tratamento explícito de SDL_FINGERDOWN, SDL_FINGERMOTION ou SDL_FINGERUP. Assim, o input touch atual é essencialmente um único ponteiro estilo mouse; não há IDs de dedos independentes disponíveis ao router do jogo.

Isso ainda não prova que nenhum toque funcione em qualquer build SDL — SDL pode sintetizar eventos de mouse dependendo da configuração — mas não é suficiente para um overlay multi-touch robusto e para separar toque na tela inferior do DS.

### Adaptador recomendado para o Platinum

1. Criar um TouchInputRouter compartilhado no runtime SDL, sem JNI/Objective-C no caminho por frame.
2. Alimentar o router com SDL_FINGERDOWN/MOTION/UP e manter o caminho SDL_MOUSEBUTTON* para Desktop. Ambos passam pelo mesmo contrato de entrada.
3. Entregar cada novo dedo primeiro ao overlay virtual; se ele não o capturar, testar a região touchscreen DS calculada por s_TouchPanelCoords.
4. Preservar a transformação existente para coordenadas DS e respeitar screenLayout/swapScreens. Não duplicar a geometria em Java, Swift ou no launcher.
5. Manter os IDs de toque. O overlay pode ter vários dedos ativos; a tela DS tem um único stylus lógico, então o primeiro dedo aceito na região DS deve continuar proprietário até release/cancel, sem saltar para outro dedo.
6. Permitir que um dedo segure um botão virtual enquanto outro controla o touchscreen DS, como no console físico.
7. Tratar foco perdido, janela oculta, suspensão e cancelamento como cancelamento de todos os dedos ativos, soltando botões e stylus para não deixar estado preso.
8. Adicionar testes para mouse Desktop inalterado, finger lifecycle, roteamento overlay-vs-DS, dois dedos em subsistemas distintos, cancelamento e todos os layouts/swapScreens.

## 3. Ciclo de vida: separar sessão de jogo e processo

Fontes consultadas:
- [SessionLifecycle.lua](https://github.com/bryanthaboi/gen1recomp/blob/dev/src/core/SessionLifecycle.lua)
- [main.lua — focus, visible e áudio](https://github.com/bryanthaboi/gen1recomp/blob/dev/main.lua)
- [Game.lua](https://github.com/bryanthaboi/gen1recomp/blob/dev/src/core/Game.lua)
- [GameActivity.java](https://github.com/bryanthaboi/gen1recomp/blob/dev/mobile/android/love/src/main/java/org/love2d/android/GameActivity.java)

O Gen1Recomp distingue três níveis:
1. **Sessão montada:** descarregar dados, assets e recursos gráficos do jogo atualmente selecionado.
2. **Sessão do jogo:** parar áudio e reiniciar o estado do jogo ao voltar ao launcher, mantendo trabalhadores que pertencem ao processo.
3. **Processo:** encerrar trabalhadores e serviços globais somente quando a aplicação realmente termina.

Essa separação evita destruir um worker compartilhado ao apenas sair de um jogo. Também torna explícito que pause/resume do SO não é a mesma coisa que sair para o launcher nem que terminar o processo.

Para Platinum, a adaptação deve cobrir explicitamente:
- pause/resume da aplicação e perda/recriação da superfície gráfica;
- foco/visibilidade e limpeza dos estados de input;
- interrupção e retomada de áudio, incluindo perda/retorno do dispositivo;
- preservação de saves, configurações e estado de importação;
- encerramento cooperativo do núcleo sem fechar o processo host quando o sistema apenas suspende a aplicação.

## 4. O que podemos reaproveitar no Platina Reluzente

| Padrão observado | Aplicação recomendada no Platinum |
|---|---|
| Activity Android fina, derivada do host SDL | Manter o SDL como proprietário da janela e do loop. A Activity só coordena APIs Android e lifecycle. |
| Ponte JNI delimitada | Criar uma fronteira Android pequena para SAF, caminhos privados, haptics, áudio/foco e metadados de display. Não espalhar chamadas JNI pelo núcleo. |
| Bridge Objective-C/Swift no iOS | Expor Document Picker, URL handling, safe area, haptics e áudio através de uma ponte C/Objective-C++; manter C++ comum independente de Swift. |
| Um único Input com várias fontes | Mapear toque, gamepad, teclado e controles físicos para o mesmo estado de botões DS. Preservar IDs multi-touch e contagem por fonte. |
| Safe area e layouts por orientação | Desenhar o overlay tátil dentro da área utilizável, usando unidades lógicas SDL e configurações retrato/paisagem separadas. |
| Picker assíncrono com estado persistente | Importar ROM e pacotes por stream para staging privado; manter request ID/destino, evitar duplicatas e recuperar cancelamento, falha e recriação de Activity. |
| Teardown em níveis | Separar pause/resume, troca/saída de sessão de jogo e shutdown do processo no futuro contrato C do núcleo. |
| Bridges e regressões por plataforma | Testar no host as máquinas de estado e os contratos; adicionar suites próprias para lifecycle/picker/touch. A validação final também precisa de dispositivos reais. |

### Arquitetura que vamos adotar

**Não vamos portar o LÖVE/Lua para o Platinum nem trocar o motor atual.** O Gen1Recomp é uma referência de desenho das fronteiras móveis, não uma dependência.

O desenho recomendado para este repositório é:

- **Núcleo compartilhado:** código nativo C/C++ existente do Platinum/libntr, com API C de lifecycle e serviços injetados para caminhos, arquivos, progresso, logs, áudio, input e renderer.
- **Renderização e janela:** SDL continua a ser a superfície do jogo. Primeiro aprovamos a rota gráfica GLES/ANGLE/Metal por comparação com o Desktop; a interface tátil é uma camada de input/renderização adicional, sem alterar as duas telas do DS.
- **Android:** uma Activity Java/Kotlin integrada ao SDL Android host e uma ponte JNI delimitada. Não há necessidade de introduzir Jetpack Compose para desenhar a interface de jogo se ela já é apresentada pela superfície SDL.
- **iOS:** host Xcode/SDL com bridges Objective-C/Objective-C++ e Swift apenas para APIs nativas. Não há necessidade de substituir a janela do jogo por SwiftUI.
- **Serviços comuns:** o núcleo pergunta por capacidades disponíveis em vez de espalhar condicionais de sistema operacional pelo código de jogo.
- **Persistência:** os arquivos selecionados entram por SAF/Document Picker e são copiados de forma segura para o sandbox privado do app. O caminho recebido pelo importador deve ser o diretório que o runtime realmente montou, não uma suposição recalculada pela camada Java/Swift.

## 5. Diferenças que não devemos copiar literalmente

1. **Motores e versões:** o Gen1Recomp examinado usa LÖVE 11.5a/SDL2 no Android e LÖVE 12.0/SDL3 no iOS. Isso é uma particularidade do projeto LÖVE e não é uma razão para introduzir duas versões de SDL ou duas bases de runtime no Platinum. O nosso porte deve continuar ancorado no libntr e nas dependências fixadas que já pertencem ao projeto.
2. **Toolchain Android:** o Gen1Recomp documenta NDK 25.2.9519653. Não vamos copiar esse pin: a trilha Android do Platinum já exige compatibilidade com ELF/alinhamento de página de 16 KiB e precisa de NDK/dependências que cumpram esse requisito.
3. **Diretório público de documentos:** o Gen1Recomp escolhe expor o diretório de dados em Files no iOS. Isso é uma escolha de produto. No Platinum, ROMs, dados extraídos, saves e pacotes devem permanecer no sandbox privado por padrão; o picker é o mecanismo de entrada e saída controlada.
4. **Launcher:** o launcher do Gen1Recomp não é uma base para reutilizar. O contrato deste projeto é reaproveitar padrões arquiteturais, não transplantar o frontend.
5. **Renderer:** o fato de Gen1Recomp funcionar em SDL/LÖVE no telemóvel não resolve os usos OpenGL 4.2 específicos do renderer libntr. A prova GL 4.2 × GLES/ANGLE/Metal permanece obrigatória.

## 6. Licença e limites de reutilização

A licença do Gen1Recomp em LICENSE.MD é GPLv3 com termos adicionais de atribuição; ela declara explicitamente que o launcher é proprietário e não pode ser copiado/reutilizado em forks. Por isso, esta pesquisa registra padrões e referências, mas **não copia código, imagens, fontes de controle ou launcher**. Qualquer reutilização futura de código do upstream exige revisão de licença, atribuição e compatibilidade com a licença do Platina Reluzente.

## 7. Ordem de trabalho resultante

1. Concluir a prova visual do renderer GLES/ANGLE/Metal contra o Desktop.
2. Projetar a API C de lifecycle e o contrato de serviços nativos do núcleo.
3. Implementar o importador móvel como uma transferência assíncrona e transacional para o sandbox privado.
4. Implementar a camada Android SDL Activity/JNI e os serviços iOS Objective-C/Swift, sem compilar os alvos.
5. Implementar input tátil multi-touch integrado ao mesmo mapeamento dos comandos DS e aos gamepads.
6. Implementar pausa/retomada, áudio, safe area, orientação, persistência e diagnósticos.
7. Cobrir as linhas da matriz 1:1 em testes host-side e revisão de código. **Somente depois disso** será permitido compilar Android/iOS para validação em aparelhos.

A regra de não gerar APK/AAB/IPA antes da paridade funcional 1:1 com o Desktop permanece inalterada.
