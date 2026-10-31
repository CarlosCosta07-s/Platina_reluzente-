# Auditoria da entrada tátil móvel

**Base inspecionada:** `cybervisi0n/libntr` no commit `1555d911ac80c0190ac1c321f99f1323de8b3c09`.

**Estado:** o núcleo source-only `mobile/input/touch_input_router.hpp` passou seis cenários C++ host-only. Um patch versionado adapta o `sim_main.cpp` fixado para `SDL_FINGER*` e `SDL_MOUSE*`; o preparador `scripts/prepare_mobile_input.py` aplica a mudança de forma fail-closed e idempotente. A CI aplicou primeiro a preparação GLES, depois o patch de input, repetiu ambos e aprovou a validação da fonte e os seis cenários no workflow [41153744631](https://github.com/CarlosCosta07-s/Platina_reluzente-/actions/runs/41153744631).

**Limite atual:** o patch foi validado em um checkout temporário do commit fixado. Não há ainda um alvo de build móvel que o consuma, o `sim_main.cpp` do upstream não é alterado diretamente, e o loop SDL modificado ainda não foi compilado/executado no jogo nem em aparelho. O hit-test do overlay continua intencionalmente como stub `false`; não há overlay visual funcional.

## 1. Caminho de entrada da revisão original

O arquivo `libraries/sim/src/sim_main.cpp` calcula `s_TouchPanelCoords[4]` usando:

- `SDL_GetWindowSize` e o viewport ajustado à proporção das telas;
- os layouts `screenLayout` vertical, horizontal ou large;
- `swapScreens`, que troca a região correspondente à tela inferior.

Na revisão original, a entrada tátil era essencialmente um único ponteiro do mouse: `SDL_MOUSEBUTTONDOWN/UP` atualizava `s_tpData.touch`, `SDL_GetMouseState` obtinha a posição e o código convertia a posição para coordenadas DS quando ela estava dentro de `s_TouchPanelCoords`. Não havia tratamento explícito de `SDL_FINGERDOWN`, `SDL_FINGERMOTION` ou `SDL_FINGERUP`, nem IDs independentes de dedos.

## 2. Contrato do TouchInputRouter

O módulo `mobile/input/touch_input_router.hpp` é independente de SDL. Recebe IDs e coordenadas de janela do adaptador e escolhe um destino no início de cada contato.

- **Identidade:** cada ponteiro é identificado pela origem (finger ou mouse), ID do dispositivo e ID do ponteiro. IDs de dedos iguais em dispositivos diferentes não colidem.
- **Primeira recusa do overlay:** `SIM_TouchOverlayClaims(position)` é consultado antes de tentar adquirir o stylus. O módulo prioriza o overlay mesmo quando as duas regiões se sobrepõem.
- **Captura estável:** o destino escolhido no início não muda durante o gesto. Um toque iniciado fora das regiões aceitas não vira stylus apenas por arrastar para dentro; um toque capturado pelo overlay não vaza para o jogo.
- **Stylus exclusivo:** no máximo um ponteiro é proprietário do stylus DS. Outro contato iniciado na tela DS enquanto o stylus está ocupado é ignorado e não é promovido automaticamente depois.
- **Multitouch:** um ponteiro pode permanecer no overlay enquanto outro controla o stylus DS.
- **Saída temporária da tela:** o proprietário mantém sua identidade ao sair da região; o contato DS fica inativo enquanto estiver fora e pode ser reativado quando o mesmo dedo retornar.
- **Cancelamento:** `CancelAll` devolve notificações de encerramento para todos os ponteiros e limpa a propriedade do stylus.

A conversão usa o retângulo atual de `s_TouchPanelCoords` e limita o resultado ao intervalo válido `0..screenWidth-1` / `0..screenHeight-1`. O patch não substitui a geometria existente.

## 3. Integração SDL preparada e validada

O patch [libntr-1555d911-touch-router.patch](../mobile/input/patches/libntr-1555d911-touch-router.patch) modifica o loop de eventos no commit fixado:

- `SDL_FINGERDOWN`, `SDL_FINGERMOTION` e `SDL_FINGERUP` entram com os pares `touchId/fingerId`; as coordenadas normalizadas são convertidas para o espaço de janela obtido por `SDL_GetWindowSize`.
- `SDL_MOUSEBUTTONDOWN`, `SDL_MOUSEMOTION` e `SDL_MOUSEBUTTONUP` passam pela mesma abstração, identificados pelo dispositivo de mouse. Isso substitui o polling antigo por `SDL_GetMouseState` na árvore preparada.
- Eventos de mouse sintetizados para o mesmo toque (`SDL_TOUCH_MOUSEID`) são filtrados para evitar um segundo contato duplicado.
- O estado do stylus é atualizado por `s_tpData.x`, `s_tpData.y`, `s_tpData.touch` e `s_tpData.validity`.
- Perda de foco, janela oculta/minimizada e eventos de background/terminação do app cancelam todos os contatos.
- O cálculo original de `s_TouchPanelCoords`, `screenLayout` e `swapScreens` permanece intacto.

O hook `SIM_TouchOverlayClaims` atualmente retorna `false`, de propósito. A prioridade do overlay está implementada e coberta por testes no módulo puro, mas o hit-test real só deve ser ligado quando o overlay visual e os seus botões existirem.

## 4. Evidência host-only

O workflow [41153744631](https://github.com/CarlosCosta07-s/Platina_reluzente-/actions/runs/41153744631) executou, em sequência:

1. checkout do commit fixado `1555d911ac80c0190ac1c321f99f1323de8b3c09`;
2. preparação do renderer GLES, duas vezes;
3. aplicação do patch de input, duas vezes, verificando idempotência;
4. validação dos eventos SDL, dos IDs e da preservação da geometria DS;
5. compilação do teste C++20 e execução de seis cenários.

Resultado dos logs: `Pinned SDL touch input source contract passed` e `TouchInputRouter host contract tests passed (6 scenarios)`.

Isso prova que o patch aplica ao código fixado e que o contrato de roteamento compila/executa no host. Não prova que a versão modificada de `sim_main.cpp` compila com todas as dependências do jogo, que o mouse Desktop mantém paridade visual/comportamental ou que eventos reais funcionam em Android/iOS.

## 5. Trabalho restante

1. Implementar o overlay visual e substituir `SIM_TouchOverlayClaims` por um hit-test real, incluindo D-pad, A/B/X/Y/L/R/Start/Select, portrait/landscape e safe area.
2. Compilar o alvo nativo com a preparação GLES + input combinadas; corrigir erros de integração antes de qualquer build de app.
3. Revalidar teclado, mouse e gamepad Desktop contra a versão anterior. A mudança de polling para eventos de mouse requer teste de regressão em runtime.
4. Exercitar eventos reais de multitouch, perda de foco, suspensão, retorno ao primeiro plano, mudança de orientação e redimensionamento.
5. Verificar a semântica de `s_tpData.validity` e `s_tpData.touch` durante gameplay; os testes atuais são de roteamento, não de Pokémon Platinum.
6. Só depois integrar os adaptadores Android/iOS, mantendo a regra de paridade funcional 1:1 antes de gerar APK, AAB ou IPA.

## 6. Limite de avanço

A preparação do código SDL está validada em host, mas os controles móveis não estão concluídos. O overlay, o build/execução do runtime preparado e os testes em aparelhos continuam pendentes. Nenhum APK, AAB ou IPA deve ser gerado nesta fase.
