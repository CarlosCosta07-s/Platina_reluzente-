# Auditoria da entrada tátil móvel

**Base inspecionada:** `cybervisi0n/libntr` no commit `1555d911ac80c0190ac1c321f99f1323de8b3c09`.

**Estado:** o roteador multitouch, o modelo dos controles virtuais e o renderer ImGui do overlay estão implementados como código-fonte versionado. Um patch fail-closed adapta o `sim_main.cpp` da revisão fixada para `SDL_FINGER*` e `SDL_MOUSE*`, encaminha os contatos ao overlay e aplica os botões virtuais aos registradores de input do DS. A preparação combinada com GLES foi repetida duas vezes e validada em host no workflow [41155710898](https://github.com/CarlosCosta07-s/Platina_reluzente-/actions/runs/41155710898).

**Evidência efetivamente obtida:** sete cenários C++ do roteador, nove cenários C++ dos controles virtuais, contrato estático da fonte preparada, aplicação/idempotência dos patches e compilação sintática do header de desenho com `SDK_BUILD_ANDROID` contra o ImGui 1.93 real da revisão fixada. **Isso ainda não compila nem executa o `sim_main.cpp` completo, não testa um jogo em runtime e não comprova eventos reais em aparelho.**

## 1. Caminho de entrada da revisão original

O arquivo `libraries/sim/src/sim_main.cpp` calcula `s_TouchPanelCoords[4]` a partir de:

- `SDL_GetWindowSize` e do viewport ajustado à proporção das telas;
- os layouts `screenLayout` vertical, horizontal ou large;
- `swapScreens`, que troca a região correspondente à tela inferior.

Na revisão original, a entrada DS era essencialmente um único ponteiro do mouse: `SDL_MOUSEBUTTONDOWN/UP` atualizava `s_tpData.touch`, `SDL_GetMouseState` obtinha a posição e o código convertia a posição para coordenadas DS quando ela estava dentro de `s_TouchPanelCoords`. Não havia tratamento explícito de `SDL_FINGERDOWN`, `SDL_FINGERMOTION` ou `SDL_FINGERUP`, nem IDs independentes de dedos.

## 2. TouchInputRouter

O módulo `mobile/input/touch_input_router.hpp` é independente de SDL. Recebe IDs e coordenadas de janela do adaptador e escolhe o destino no início de cada contato.

- **Identidade:** cada ponteiro é identificado pela origem (finger ou mouse), ID do dispositivo e ID do ponteiro; IDs iguais em dispositivos diferentes não colidem.
- **Primeira recusa do overlay:** o teste de hit-test dos controles virtuais acontece antes de tentar adquirir o stylus DS.
- **Captura estável:** o destino escolhido no início não muda durante o gesto; um contato iniciado no overlay não vaza para o stylus.
- **Stylus exclusivo:** no máximo um ponteiro é proprietário do stylus DS. Outro contato não toma a propriedade automaticamente enquanto o primeiro estiver ativo.
- **Multitouch:** um dedo pode permanecer nos controles virtuais enquanto outro controla o stylus DS.
- **Mouse Desktop:** o mouse pode iniciar fora da tela DS e arrastar para dentro, preservando o comportamento anterior de interação com a tela inferior. Esse contrato tem teste próprio; a regressão no runtime completo ainda precisa ser verificada.
- **Cancelamento:** `CancelAll` libera todos os ponteiros e a propriedade do stylus em eventos de lifecycle.

A conversão usa o retângulo existente de `s_TouchPanelCoords` e limita o resultado ao intervalo válido `0..screenWidth-1` / `0..screenHeight-1`. O patch não substitui a geometria de layout já existente.

## 3. Overlay tátil

O modelo `mobile/input/virtual_touch_controls.hpp` calcula as zonas de toque e o estado lógico:

- D-pad com oito direções e zona morta central;
- A, B, X, Y, L, R, Start e Select;
- retrato/paisagem com tamanhos adaptados ao lado menor do viewport;
- insets configuráveis de safe area;
- captura de ponteiros independentes, incluindo dois dedos em botões diferentes;
- estado agregado de um botão quando mais de um ponteiro o pressiona;
- drag dentro/fora da zona original e liberação em cancelamento.

O desenho foi extraído para `mobile/input/imgui_touch_overlay.hpp`. Ele usa o contexto ImGui que o simulador já abre, desenha no foreground draw list e só habilita o overlay visual sob `SDK_BUILD_ANDROID` ou `SDK_BUILD_IOS`. O caminho Desktop mantém a camada visual desativada.

O `sim_main.cpp` preparado configura o layout e chama `DrawVirtualTouchControls` no quadro ImGui do simulador. O hit-test real agora consulta `VirtualTouchControls::Claims`; os contatos capturados são atualizados/liberados pelo mesmo ID usado no roteador. O mask virtual é combinado com o estado-base de teclado/gamepad do quadro, em vez de substituir os botões físicos.

**Limite de safe area:** o modelo aceita insets, mas o patch SDL atualmente passa insets zero (`{}`). A ligação aos insets reais deve vir dos adaptadores Android/iOS, ainda não implementados.

## 4. Preparação e integração SDL versionadas

O patch [libntr-1555d911-touch-router.patch](../mobile/input/patches/libntr-1555d911-touch-router.patch) é aplicado por `scripts/prepare_mobile_input.py`, que recusa revisões diferentes do SHA fixado, valida os headers instalados, prepara todos os arquivos antes de aplicar e pode ser executado novamente sem duplicar alterações.

Na árvore preparada:

- `SDL_FINGERDOWN/MOTION/UP` preserva `touchId/fingerId`; coordenadas SDL normalizadas são convertidas para o espaço da janela.
- `SDL_MOUSEBUTTONDOWN/MOTION/UP` usa a mesma abstração, filtrando `SDL_TOUCH_MOUSEID` para evitar duplicação de mouse sintetizado pelo toque.
- O stylus DS atualiza `s_tpData.x/y/touch/validity`.
- Perda de foco, janela oculta/minimizada e eventos de background/terminação cancelam os contatos.
- O mask dos controles virtuais mapeia A/B/Select/Start/direções/L/R para `s_reg_PAD_KEYINPUT` (ativo-baixo) e X/Y para `HW_BUTTON_XY_BUF`.
- O estado físico base do teclado/gamepad é restaurado antes de cada quadro e preservado antes de aplicar o mask virtual.

O código upstream não é modificado diretamente por esta documentação; a CI cria um checkout temporário da revisão fixada e aplica o patch nele. Ainda falta compilar e executar todo o runtime resultante.

## 5. Evidência host-only

O workflow [41155710898](https://github.com/CarlosCosta07-s/Platina_reluzente-/actions/runs/41155710898) passou por todas as etapas:

1. checkout de `libntr` no commit `1555d911ac80c0190ac1c321f99f1323de8b3c09`;
2. preparação do renderer GLES, duas vezes;
3. aplicação do patch SDL/overlay, duas vezes, com verificação de idempotência;
4. contrato estático do `sim_main.cpp` preparado e dos três headers instalados;
5. compilação sintática do overlay com `-DSDK_BUILD_ANDROID`, usando o header ImGui 1.93 do próprio commit fixado;
6. sete cenários C++ do `TouchInputRouter`;
7. nove cenários C++ de `VirtualTouchControls`.

O teste ImGui usa `-fsyntax-only`: valida que a API de desenho chamada pelo overlay existe e compila com a branch móvel habilitada, mas não linka o simulador e não cria um binário Android.

## 6. Trabalho restante

1. Compilar o `sim_main.cpp` completo já preparado dentro do build nativo Desktop/host, com a preparação GLES + input combinadas; corrigir qualquer incompatibilidade de includes, símbolos ou estado de renderização.
2. Executar o runtime Desktop preparado para comprovar que teclado, mouse, gamepad e drag do mouse para a tela inferior continuam funcionando. Os testes de contrato ainda não substituem essa regressão em runtime.
3. Confirmar visualmente a composição do overlay sobre o jogo e revisar escala, legibilidade, sobreposição com menus/ImGui, transparência e layouts em diferentes proporções.
4. Ligar os insets reais de safe area aos serviços Android/iOS; atualmente o patch passa zeros.
5. Testar no hardware real multitouch, stylus simultâneo, interrupção, rotação, suspensão/retomada e gamepads Bluetooth/USB.
6. Integrar Activity/JNI Android e host/bridges iOS somente após estabilizar o runtime compartilhado.

## 7. Limite de avanço

A lógica de roteamento e o header de desenho ImGui passaram por validações host-only contra a revisão fixada, e o patch foi aplicado à árvore temporária de preparação. O runtime completo ainda não foi compilado/executado; os insets reais e os testes em aparelhos continuam pendentes. Não gerar APK, AAB ou IPA antes da matriz de paridade 1:1 do Desktop ser concluída.
