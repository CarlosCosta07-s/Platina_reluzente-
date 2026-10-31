# Plano Desktop-first — Pokémon Platinum

**Estado:** Desktop Windows x64 e Linux x86-64 em desenvolvimento ativo. Android e iOS pausados até a aprovação de todos os gates deste documento.

## Objetivo

Concluir uma versão nativa de Pokémon Platinum que funcione de forma reproduzível em Windows e Linux, aproveitando o código C reconstruído do jogo e o runtime nativo existente. O porte não deve depender de emulador de Nintendo DS nem de interpretador de instruções ARM.

A ROM e os recursos do jogo continuam sendo fornecidos e mantidos localmente pelo usuário. Nenhuma ROM, firmware, arquivo extraído, save ou patch com conteúdo protegido deve entrar no Git, nos workflows ou nos artefatos públicos.

## Aplicativo unificado e launcher central

O launcher não é um utilitário externo nem uma etapa descartável: launcher-app é a aplicação Desktop que contém e integra os dois jogos. A biblioteca reúne **Pokémon Platinum** e **Pokémon Black Version** na mesma janela Electron. PT-BR é uma localização de Platinum, não um terceiro título. Cada jogo mantém ROM, cache, saves, configurações e logs isolados, enquanto compartilha a biblioteca, o gerenciamento de sessões, a importação segura, o diagnóstico, o protocolo de primeiro frame, o watchdog e a recuperação da interface.

O runtime nativo é componente interno do aplicativo: o usuário não escolhe nem abre outro executável. O launcher mantém uma única sessão ativa, minimiza depois do primeiro frame realmente apresentado, restaura sua própria janela em falhas de renderização e no término do processo, e encaminha o progresso ao painel do título correto. O contrato completo está em [LAUNCHER_INTEGRATION_CONTRACT.md](LAUNCHER_INTEGRATION_CONTRACT.md).

**Regra de build:** pushes normais executam apenas verificações e testes de fonte. Os builds completos dos runtimes e o empacotamento integrado Windows/Linux ficam bloqueados por padrão e só poderão ser despachados manualmente com autorização explícita na fase final, depois da implementação e dos testes concluídos.

## Auditoria atual do runtime

O ciclo de vida de encerramento e os dados de identificação OpenGL foram auditados em [DESKTOP_RUNTIME_AUDIT.md](DESKTOP_RUNTIME_AUDIT.md). O upstream encerra com `exit(0)` dentro de `SIM_Render`, acionado no caminho de VBlank, enquanto `NitroMain` tem loop infinito. Não fazer uma substituição superficial por `return`; primeiro mapear o estado de saves e a parada das threads. O diagnóstico OpenGL deverá registrar vendor, renderer, versão da API e GLSL antes do primeiro frame, com tratamento para strings nulas. Esta auditoria não marca o shutdown como implementado.

## Como aproveitamos as três referências

As referências são guias de arquitetura e critérios de qualidade. Não copiamos código, assets, decompilações ou dependências de terceiros sem uma licença compatível. Cada ideia é adaptada ao formato NDS, ao runtime C/C++ e à nossa versão Desktop.

### Gen1Recomp — importação, armazenamento e ciclo de vida

Aplicar os seguintes padrões também no Desktop:

- Importar a ROM selecionada pelo usuário para uma área privada do aplicativo, com metadados de identidade SHA-1/SHA-256.
- Fazer a substituição por staging, validação, backup e recuperação de transações interrompidas; nunca apagar a cópia anterior antes de validar a nova.
- Preparar os arquivos antes de iniciar a janela e o loop SDL/OpenGL, exibindo progresso e erros no launcher.
- Vincular o cache de extração à identidade completa da ROM e ao build ID do runtime; verificar manifesto, tamanhos e integridade dos arquivos antes do boot.
- Preservar saves, configurações e dados do usuário durante a atualização do runtime.
- Encerrar/retomar processos e limpar entradas presas ao perder foco ou fechar a janela; registrar diagnóstico em log persistente.

**O que não adotamos:** o motor Lua/LÖVE do Gen1Recomp. O núcleo do jogo continua sendo o código C/C++ nativo recompilado.

Referências internas: [Gen1Recomp — Desktop](GEN1RECOMP_REFERENCE.md) e [Gen1Recomp — mobile](GEN1RECOMP_MOBILE_REFERENCE.md). A segunda fica preservada para a futura retomada mobile, mas não abre trabalho móvel nesta fase.

### Black Xbox — identidade do executável, boot e sincronização

Aplicar os princípios de confiança do boot, ajustados ao NDS:

- Validar versão/revisão e hash integral da ROM importada, além do cabeçalho NDS; não confiar apenas em extensão, nome ou tamanho.
- Validar o pacote nativo e as bibliotecas antes da execução; executar apenas o runtime que corresponde ao build ID aprovado.
- Fazer extração em staging e só promover os dados quando manifesto, arquivos obrigatórios, tamanhos e checksums estiverem corretos.
- Nunca extrair recursos de forma síncrona durante o loop de jogo nem marcar uma preparação parcial como concluída.
- Tratar sincronização entre preparação, boot, renderização, salvamento e encerramento com limites claros; medir antes de introduzir threads adicionais.

**Diferença importante:** Black Xbox monta uma imagem de disco Xbox para o runtime acessar os dados do XBE. Pokémon Platinum é NDS e atualmente usa um pipeline de extração para arquivos locais. Não devemos copiar XISO, parser de XBE nem o modelo de montagem de disco do Xbox.

Referência interna: [Black Xbox port reference](BLACK_XBOX_PORT_REFERENCE.md).

### BT3 Decomp — dois renderers, GPU/driver e desempenho medido

Depois de estabilizar OpenGL no Desktop:

- Manter OpenGL 4.2 Core e implementar Vulkan como backend verdadeiramente independente.
- Expor Automático, OpenGL e Vulkan; persistir a preferência do jogador e informar qual backend está realmente ativo.
- Identificar GPU, driver e versão da API. Perfis automáticos só podem ser criados a partir de resultados reproduzidos, nunca de uma regra fixa por marca.
- Em falha Vulkan, destruir device/surface/swapchain e todos os recursos parciais antes do fallback para OpenGL; registrar motivo e resultado.
- Comparar os dois renderers com as mesmas cenas sintéticas e exigir equivalência visual antes de aceitar ganhos de FPS.
- Medir frametime p50/p95/p99, CPU/GPU, memória e comportamento após sessões longas; não assumir que Vulkan é sempre mais rápido.

**Adaptação Desktop:** os benchmarks e perfis serão coletados em PCs Windows/Linux e GPUs/driver reais dessas plataformas. Os aparelhos e resultados Android do BT3 são evidência metodológica, não valores que possamos transportar diretamente para o Desktop.

Referência interna: [BT3 Decomp port reference](BT3_PORT_REFERENCE.md).

### Síntese da arquitetura

O fluxo esperado para cada título é: selecionar na biblioteca única → importar e identificar a ROM → preparar e verificar os dados privados daquele jogo → validar o runtime interno correspondente → iniciar a sessão pelo gerenciador compartilhado → confirmar o primeiro frame → monitorar renderização/saves → restaurar o launcher e encerrar com estado consistente. OpenGL permanece como baseline; Vulkan entra depois como backend selecionável. Nenhuma dessas decisões autoriza builds móveis enquanto a pausa estiver vigente.


## Ordem obrigatória de execução

### Gate 0 — baseline Desktop reproduzível

- Confirmar o commit fixado do código nativo e das dependências Meson.
- Executar a suíte ROM-free completa e validar scripts de preparação, pacote e launcher.
- Compilar Linux x86-64 e Windows x64 a partir de ambientes limpos.
- Verificar os pacotes contra o manifesto upstream, incluindo caminhos, tamanhos, hashes e arquivos obrigatórios.
- Empacotar o runtime e o launcher para cada sistema sem ROM, firmware ou recursos extraídos.
- Guardar logs e hashes dos artefatos; não considerar sucesso parcial de uma plataforma como sucesso de ambas.

**Situação conhecida:** já existem builds e smoke tests históricos para partes do fluxo. O smoke test Linux sem ROM confirmou a abertura de uma janela, mas isso não prova inicialização do jogo. A documentação do projeto também registra falhas anteriores de dependências/rede no Windows. A revisão mais recente que injeta os preparadores de renderer/input no build Desktop precisa ser validada; não assumir que passou sem consultar a execução correspondente.

### Gate 1 — OpenGL Desktop estável

Manter o renderer atual como caminho funcional de referência: OpenGL 4.2 Core no Desktop. Antes de adicionar outro backend, garantir:

- criação e destruição corretas do contexto e da janela;
- composição das duas telas do DS, proporção, escala e layouts;
- resize, alta densidade de pixels, fullscreen e restauração após perda de foco;
- teclado, mouse, arrastar para a tela sensível ao toque e controles/gamepad;
- temporização consistente, sem travamentos ou deadlocks na inicialização;
- mensagens de erro úteis para shaders, contexto, arquivos e recursos ausentes.

As mudanças devem ser pequenas e cobertas por testes de regressão. Não alterar shaders ou estado gráfico apenas para melhorar FPS sem uma cena de referência que prove equivalência visual.

### Gate 2 — inicialização e gameplay reais

Com uma cópia legal e local de Pokémon Platinum USA Rev. 1, provar manualmente:

1. Importação e validação do SHA-1 integral esperado pelo launcher.
2. Preparação/extração dos dados para a pasta privada/local, com progresso e falhas recuperáveis.
3. Inicialização do executável nativo até a tela de título.
4. Início de uma nova partida e execução de uma sequência mínima de gameplay.
5. Funcionamento de áudio, teclado, mouse e gamepad.
6. Criação de save, encerramento normal, reinício e carregamento do save.

A CI permanece ROM-free. Logs de inicialização e manifestos de teste são evidência aceitável para as etapas automatizáveis; a tela de título e o gameplay precisam de validação real com dados locais. Uma janela vazia, processo criado ou pacote íntegro não conta como gameplay validado.

### Gate 3 — idioma original e Português (Brasil)

- Validar English/original com a ROM Rev. 1 suportada.
- Validar o pacote PT-BR pela allowlist, manifesto e hashes aprovados.
- Conferir visualmente fontes, acentos, menus, diálogos, tela de título, batalhas e eventos.
- Alternar idioma sem perder progresso nem corromper saves.
- Confirmar que recursos PT-BR ausentes ou incompatíveis falham explicitamente, sem fallback silencioso para inglês.

A importação e os testes estruturais não provam que a tradução aparece corretamente no jogo; a validação visual e a sequência de gameplay são obrigatórias.

### Gate 4 — Vulkan Desktop como segundo renderer

Somente depois de o OpenGL Desktop estar estável, implementar Vulkan como backend independente para Windows e Linux.

- Preservar OpenGL; não substituí-lo nem envolvê-lo em uma camada que apenas finja ser Vulkan.
- Definir uma interface de renderer clara para recursos, texturas, buffers, passes, blending, profundidade/stencil, sincronização, apresentação, resize e encerramento.
- Disponibilizar ao jogador **Automático**, **OpenGL** e **Vulkan**, ocultando opções indisponíveis no sistema.
- Persistir a preferência e exibir o backend realmente ativo, GPU, driver, versão da API e eventual motivo do fallback.
- Se Vulkan falhar durante a inicialização, liberar completamente dispositivo, surface, swapchain e recursos parciais antes de tentar OpenGL. Não deixar a janela em estado inválido ou tela preta.
- Trocar backend no próximo início do runtime, não no meio da partida.
- Manter recursos opcionais como otimizações condicionais, com verificação de capacidades e caminho alternativo.

Critérios de validação:
- Build host-only Vulkan em Windows/Linux.
- As mesmas cenas sintéticas são renderizadas em OpenGL e Vulkan.
- Comparação RGBA para as duas telas, blending, alpha, prioridades BG/OBJ, fog, texturas e layouts.
- Testes de falhas simuladas em cada fase de inicialização e de fallback Vulkan → OpenGL.
- Benchmark com workloads idênticos, registrando p50/p95/p99 de frametime, CPU/GPU, memória e versão do driver.
- Nenhuma regressão visual é aceita em troca de FPS maior.

### Gate 5 — prontidão do Desktop

A frente Desktop só será marcada como pronta quando todos os itens abaixo tiverem evidência:

- [ ] Build limpo Windows x64 concluído.
- [ ] Build limpo Linux x86-64 concluído.
- [ ] Pacotes e launchers dos dois sistemas verificados e reproduzíveis.
- [ ] OpenGL estável nas duas plataformas.
- [ ] Importação/preparação local de ROM validada.
- [ ] Tela de título e sequência mínima de gameplay confirmadas.
- [ ] Áudio, entrada e controles testados.
- [ ] Save e carregamento após reinício confirmados.
- [ ] English e PT-BR validados visualmente e em gameplay.
- [ ] Vulkan implementado como backend independente nos dois sistemas.
- [ ] Seleção Automático/OpenGL/Vulkan e fallback limpo testados.
- [ ] Comparação visual OpenGL × Vulkan aprovada.
- [ ] Revisão de licenças, avisos e conteúdo dos pacotes concluída.

## Regra para retomar Android/iOS

Apenas depois da aprovação do Gate 5 a trilha móvel poderá ser reaberta. A retomada começa com uma nova auditoria de paridade contra o comportamento Desktop aprovado; não se presume que os testes móveis históricos substituam a validação da versão atual.

Até lá:
- não compilar alvos Android ou iOS;
- não rodar NDK/Xcode;
- não criar APK, AAB ou IPA;
- não acrescentar novos trabalhos móveis aos workflows;
- preservar documentos, fontes e testes móveis existentes como referência histórica.

## Regras de engenharia

- Trabalhar somente na branch `main`; não criar branches.
- Fazer uma mudança pequena por vez e revisar o diff antes de gravar.
- Não declarar build, teste, tela de título, gameplay ou dispositivo validado sem evidência.
- Não adicionar ROMs, firmware, recursos extraídos ou saves ao repositório ou à CI.
- Não otimizar antes de ter uma baseline funcional e mensurável.
- Manter o código original reconstruído e o runtime separados de dados protegidos do usuário.
