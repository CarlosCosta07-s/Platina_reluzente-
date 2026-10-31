# Auditoria da entrada tátil móvel

**Base inspecionada:** `cybervisi0n/libntr` no commit `1555d911ac80c0190ac1c321f99f1323de8b3c09`, usado pela revisão nativa fixada no porte.

**Estado:** o módulo source-only `mobile/input/touch_input_router.hpp` foi criado e passou por seis cenários de contrato C++ host-only no workflow [41153036719](https://github.com/CarlosCosta07-s/Platina_reluzente-/actions/runs/41153036719). Ainda não foi conectado ao loop SDL do submódulo, não existe overlay visual implementado e não há compilação móvel nesta fase.

## 1. Caminho de entrada encontrado na revisão fixada

O arquivo `libraries/sim/src/sim_main.cpp` já calcula `s_TouchPanelCoords[4]` a partir de:

- `SDL_GetWindowSize` e do viewport ajustado à proporção das telas;
- `screenLayout` vertical, horizontal ou large;
- `swapScreens`, que troca a região correspondente à tela inferior.

O caminho atual de toque é essencialmente um único ponteiro do mouse:

1. `SDL_MOUSEBUTTONDOWN/UP` atualiza `s_tpData.touch`;
2. `SDL_GetMouseState` obtém a posição do ponteiro;
3. a posição é convertida para coordenadas DS somente quando está dentro de `s_TouchPanelCoords`;
4. fora da região, o estado de toque é limpo.

Não encontrei tratamento explícito de `SDL_FINGERDOWN`, `SDL_FINGERMOTION` ou `SDL_FINGERUP` nessa revisão. O modelo atual não guarda IDs de dedos e não consegue representar, por si só, um dedo no overlay enquanto outro controla o stylus.

## 2. Contrato do TouchInputRouter

O módulo novo é independente de SDL e recebe IDs e coordenadas já normalizadas pelo adaptador de plataforma. Isso permite testar as regras de captura antes de alterar o loop nativo.

- **Identidade:** cada ponteiro é identificado por origem (finger ou mouse), ID do dispositivo e ID do ponteiro. Dois dispositivos podem reutilizar o mesmo ID de dedo sem colisão.
- **Primeira recusa do overlay:** o adaptador consulta primeiro o hit-test dos controles virtuais. Quando o overlay reivindica um toque, o router não o encaminha à tela DS, mesmo que as regiões se sobreponham.
- **Captura estável:** o destino escolhido no início não muda durante o gesto. Um toque iniciado fora das regiões aceitas não vira stylus apenas por arrastar para dentro; um toque capturado pelo overlay não vaza para o jogo.
- **Stylus exclusivo:** no máximo um ponteiro é proprietário do stylus DS. Outro toque na tela DS enquanto o stylus está ocupado é ignorado e não é promovido automaticamente depois.
- **Multitouch:** um ponteiro pode permanecer no overlay enquanto outro controla o stylus DS.
- **Saída temporária da tela:** o proprietário do stylus mantém sua identidade ao sair da região; o contato DS fica inativo enquanto estiver fora e pode ser reativado quando o mesmo dedo retornar.
- **Cancelamento:** `CancelAll` devolve uma notificação de encerramento para cada ponteiro capturado, limpa a propriedade do stylus e permite reutilizar os IDs após interrupções.

A conversão usa o retângulo atual calculado pelo runtime e limita as coordenadas ao intervalo válido `0..screenWidth-1` / `0..screenHeight-1`. Assim, o módulo não recalcula nem substitui a geometria existente de `s_TouchPanelCoords`.

## 3. Evidência host-only

O workflow [41153036719](https://github.com/CarlosCosta07-s/Platina_reluzente-/actions/runs/41153036719) compilou o teste C++ com avisos tratados como erros e executou seis cenários:

1. prioridade do overlay sobre a tela DS;
2. uso simultâneo do overlay e do stylus;
3. exclusividade, permanência e reentrada do proprietário do stylus;
4. IDs distintos entre dispositivos e fontes;
5. mapeamento e limites das coordenadas DS;
6. cancelamento total, liberação e reutilização dos IDs.

O teste não usa SDL, ROM, dados extraídos nem renderer. Ele prova o contrato de roteamento do módulo, não a entrega de eventos de um aparelho nem a integração final do jogo.

## 4. Integração ainda necessária no SDL

1. Adaptar `SDL_FINGERDOWN`, `SDL_FINGERMOTION` e `SDL_FINGERUP`, preservando o par `touchId/fingerId`. As coordenadas normalizadas do SDL devem ser convertidas para o mesmo espaço de janela usado pelo cálculo atual de `s_TouchPanelCoords`.
2. Encaminhar também `SDL_MOUSEBUTTONDOWN`, `SDL_MOUSEMOTION` e `SDL_MOUSEBUTTONUP` ao router sem alterar a experiência Desktop. Ao tratar eventos de dedo, evitar processar uma segunda vez eventos de mouse sintetizados pelo SDL para o mesmo toque.
3. Executar o hit-test do overlay antes de tentar adquirir o stylus DS. A interface e as zonas de toque do overlay ainda precisam ser implementadas.
4. Traduzir atualizações do destino `DsStylus` para `s_tpData.x`, `s_tpData.y`, `s_tpData.touch` e `s_tpData.validity`, respeitando a semântica exata do runtime.
5. No foco perdido, suspensão, ocultação da janela ou interrupção do app, chamar o cancelamento global e liberar todos os botões virtuais e o estado do stylus.
6. Testar as três geometrias, `swapScreens`, redimensionamento da janela, dedos simultâneos, troca de orientação, perda de foco e coexistência com gamepad/teclado.

## 5. Limite de avanço

O módulo está aprovado apenas como lógica de roteamento host-only. Não marcar a paridade de controles como concluída até que a integração SDL esteja aplicada ao commit exato de `libntr`, os eventos sejam exercitados com testes e o overlay esteja conectado ao mesmo estado de input do jogo. Nenhum APK, AAB ou IPA deve ser gerado antes da paridade funcional 1:1 definida em `MOBILE_PARITY_CONTRACT.md`.
