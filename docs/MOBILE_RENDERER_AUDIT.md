# Auditoria do renderer móvel — fonte fixada

**Base inspecionada:** cybervisi0n/libntr, commit 1555d911ac80c0190ac1c321f99f1323de8b3c09, usado pelo porte Desktop fixado em cybervisi0n/pokeplatinum commit 35067868f64f23d25d17ac3e536cfdd9a7f40523.

**Estado:** quatro variantes GLSL ES 3.00 foram compiladas/linkadas no host; o preparador source-only foi aplicado duas vezes com sucesso à revisão real libntr `1555d911`; e os comparadores G3 (10 cenas) e G2 (14 cenas) passaram em Mesa/EGL com contextos forçados a Desktop GL 4.2 Core e OpenGL ES 3.0. As 24 cenas tiveram `max_delta=0` e zero pixels divergentes no workflow host-only [41152745126](https://github.com/CarlosCosta07-s/Platina_reluzente-/actions/runs/41152745126). A comparação usa fixtures sintéticas ROM-free: não valida gameplay nem substitui testes com drivers Android reais ou ANGLE/Metal no iOS. O renderer ainda não está integrado a um app móvel e não há build Android/iOS autorizado nesta fase.

## 1. Bloqueios encontrados na fonte exata

| Local | Uso Desktop atual | Implicação móvel |
|---|---|---|
| libraries/sim/src/sim_main.cpp | SDL solicita OpenGL 4.2 Core; carrega GLAD desktop | seleção de perfil ES 3.0 e carregador de símbolos por plataforma ainda necessários |
| libraries/sim/src/sim_main.cpp | GL_DEBUG_OUTPUT e glDebugMessageCallback são incondicionais | debug output tem de ser opcional; a ausência não pode impedir a inicialização |
| libraries/sim/src/sim_main.cpp | glProgramUniform1i, glProgramUniform1f e glProgramUniform4f | essas chamadas separadas não fazem parte da base GLES 3.0; requerem wrappers/estado de programa explícito |
| libraries/sim/src/g3_draw.cpp | glProgramUniform1i, glProgramUniform4f e glProgramUniform1fv | mesmo problema em toda a configuração de textura, polygon mode e fog |
| libraries/sim/src/g3_draw.cpp | GL_CLAMP_TO_BORDER nos eixos S/T quando repeat está desligado | GLES 3.0 core não tem border-clamp; emular transparente-preto no shader e sinalizar os eixos |
| libraries/sim/src/shaders/g2_fragment.glsl | bgTexture[bgNum], bgTexture[currentBgDrawn], objTexture[j] e objTexture[i] | arrays de samplers ESSL 3.00 não podem ser indexados por valores dinâmicos; todos os acessos precisam de índices literais |
| include/simulator/g3_draw.h e libraries/sim/src/sim_main.cpp | inclui simulator/glad/glad.h diretamente | incluir uma abstração GL comum, selecionando GLAD apenas em Desktop/NX e GLES3 nos alvos móveis |
| libraries/sim/src/imgui/imgui_impl_opengl3.cpp | backend já contém IMGUI_IMPL_OPENGL_ES3 e shader #version 300 es | o define de compilação, loader e integração SDL ainda precisam ser selecionados por alvo e testados |

O renderer também usa recursos que fazem parte da faixa GLES 3.0, como VAO/VBO, FBO, RGBA8 e depth-stencil, mas a presença desses recursos não prova a equivalência do renderer. O shader G3 continua a precisar de testes de fog, alpha, textura e coordenadas nas bordas.

## 2. Variantes GLSL ES 3.00 iniciadas

As fontes isoladas estão em mobile/renderer/gles300:

- g2_vertex.glsl
- g2_fragment.glsl
- g3_vertex.glsl
- g3_fragment.glsl

O shader G2 móvel mantém os arrays de samplers e a interface dos uniforms, mas encaminha a seleção por funções sampleBg/sampleObj com switch e índices literais. Isso cobre os quatro locais dinâmicos encontrados na revisão fixada: dois no array BG e dois no array OBJ. Os arrays de floats do fog no shader G3 podem continuar com índices dinâmicos, pois não são arrays de samplers.

O shader G3 móvel declara clampToBorderS/clampToBorderT e sampleG3Texture. Fora da faixa [0,1] no eixo marcado, ele devolve o valor de borda transparente-preto. A camada C++ ainda precisa:
1. definir as duas flags por textura/desenho;
2. selecionar GL_CLAMP_TO_EDGE no objeto quando a flag de border estiver ativa;
3. manter GL_REPEAT e GL_MIRRORED_REPEAT para as outras combinações;
4. preservar a diferença já existente no Desktop: o caminho de desenhos translúcidos adiados em G3SIM_DrawItems aplica REPEAT/MIRRORED_REPEAT conforme flipS/flipT e ignora repeatS/repeatT. Para paridade 1:1, manter clampToBorderS/T em zero nesse caminho até uma decisão separada sobre o comportamento Desktop;
5. comprovar a semântica nas coordenadas 0, 1, imediatamente dentro e imediatamente fora da borda.

Não declarar essa emulação equivalente até as cenas de teste confirmarem os pixels. Os filtros das texturas G3 fixadas são nearest; qualquer alteração para linear exige nova matriz de bordas.

## 3. Uniformes sem glProgramUniform

A conversão não pode simplesmente substituir glProgramUniform por glUniform sem garantir o programa ativo correto. O Desktop escreve uniformes de G3 e G2 em momentos distintos, e glProgramUniform permite escrever em um programa que não está ativo.

O helper inicial `mobile/renderer/gles300/program_uniform_compat.hpp` implementa a primeira estratégia com ScopedProgramBinding e cobre as chamadas 1i, 1f, 4f e 1fv. Um teste C++ de host usa uma API GLES simulada e confere restauração do programa. O header ainda não está incluído pelo submódulo pinado e não foi perfilado em GPU; é uma base de correção, não uma decisão final de desempenho.

A solução móvel deve escolher e testar uma destas estratégias:
- helpers que guardam GL_CURRENT_PROGRAM, ativam o programa-alvo, fazem glUniform* e restauram exatamente o programa anterior; ou
- estabelecer explicitamente o programa-alvo nos limites de cada passe (G3, G2) e usar uniformes normais dentro do passe.

A segunda opção pode ter menos chamadas de estado, mas só é aceitável depois de uma auditoria do caminho inteiro, incluindo desenhos translúcidos deferred. Não deixar o programa G2 ou G3 implicitamente ativo porque o último LinkShader o ativou durante o boot.

## 4. Integração GL por alvo

O código comum não deve incluir diretamente GLAD em cada header. O patch para a revisão fixada deve introduzir um cabeçalho central de GL que selecione os tipos/protótipos corretos pelo alvo:
- Windows/Linux: GLAD Desktop existente;
- Android: headers GLES3 e resolução de funções compatível com SDL/driver;
- iOS com ANGLE: headers/loader ANGLE fornecidos pela dependência fixada;
- iOS com Metal nativo: não reutilizar chamadas OpenGL, se a prova ANGLE falhar; isso abre um backend separado.

A revisão atual de sim_main.cpp inclui GLAD diretamente; g3_draw.h também depende do header GLAD. O inventário de includes deve ser completo antes da primeira mudança de integração, para que nenhum arquivo continue a compilar acidentalmente contra protótipos desktop.

O Dear ImGui backend contém código condicional IMGUI_IMPL_OPENGL_ES3 que evita chamadas desktop como glPolygonMode e gera GLSL ES 3.00. Ainda falta verificar o header de carregamento, o conjunto de funções utilizado e a compatibilidade do backend SDL com cada lifecycle. Não presumir que o define, sozinho, integra o ImGui.

## 5. Testes necessários

### Gate de fonte
- Testes ROM-free verificam #version 300 es, precisão, interfaces vertex/fragment e todos os índices de sampler como inteiros literais.
- Testes verificam clampToBorderS/T e o retorno transparente-preto para coordenadas fora da faixa.
- Os quatro shaders originais Desktop permanecem inalterados no submódulo fixado.

### Gate de compilação/link em host
- [x] glslangValidator compila os quatro shaders como ESSL 3.00 no host.
- [x] glslangValidator cria e linka os programas G2 e G3 (workflow host-only 41149162996).
- [x] Comparação G3 host-only em Mesa/EGL com versões mínimas forçadas: Desktop GL 4.2 Core × OpenGL ES 3.0; dez cenas, todas com `max_delta=0` e zero pixels divergentes (workflow 41152253802).
- [x] Comparação sintética G2 Desktop GL 4.2 × GLES 3.0 em Mesa/EGL: 14 cenas de backdrop, ordem/prioridade BG, blending, brilho, OBJ windows e composição 3D; igualdade exata em todas (workflow 41152745126).
- [x] Aplicar o preparador fail-closed à revisão real libntr `1555d911` e confirmar que a segunda execução é idempotente (workflow host-only 41150452186).

### Gate de paridade visual
- [x] G3 sintético: textura, cor de vértice, alpha discard, fog, transparent border S/T/S+T, repeat e mirror; 10/10 cenas com igualdade exata em Mesa GL 4.2 Core × ES 3.0 (workflow 41152253802).
- [x] G2: 14 cenas ROM-free cobrindo backdrop/top-bottom, ordem e prioridades BG, blending BG/backdrop/OBJ, brightness increase/decrease, master brightness, OBJ priorities/windows e BG0 3D alpha; igualdade exata em GL 4.2 Core × GLES 3.0 no host (workflow 41152745126).
- [ ] Coordenadas de borda dentro, fora e exatamente em 0 e 1 no G2; cena em que bgOrder muda entre pixels vizinhos.
- [ ] Dois layouts de tela e seleção superior/inferior com a composição real das duas telas.
- [ ] Repetir o conjunto no ANGLE/Metal para a rota iOS e em drivers de aparelho.

Cada cena precisa ser renderizada também no Desktop GL 4.2. Comparar imagens RGBA; exigir igualdade exata sempre que possível. Qualquer tolerância deve indicar canal, limiar e número máximo de pixels divergentes. O conjunto idêntico tem de passar no ANGLE/Metal para o caminho iOS.

## 6. Próximos passos de implementação

1. Fechar o inventário de headers GLAD e chamadas GL por todos os fontes comuns.
2. Criar um patch versionado que liga as quatro variantes shader ao commit pinado, sem tocar no renderer Desktop.
3. Implementar os uniforms de border clamp nos caminhos normais e deferred de G3.
4. Integrar o helper de uniforms existente no código pinado, testar a preservação de GL_CURRENT_PROGRAM com contexto real e reduzir as trocas de programa agrupando escritas quando isso não alterar o estado.
5. Selecionar o backend OpenGL ES 3.0 e o modo IMGUI_IMPL_OPENGL_ES3 por macro de alvo, com loader correto.
6. [x] Completar e executar o probe sintético G2: 14/14 cenas com igualdade exata em GL 4.2 Core × ES 3.0 no host (workflow 41152745126).
7. Só após aprovação visual iniciar o trabalho de API C lifecycle e integração com os shells.

O contrato completo de plataformas e o bloqueio dos builds móveis permanecem em docs/MOBILE_PARITY_CONTRACT.md.


## 9. Decisão posterior: manter OpenGL e adicionar Vulkan

A pesquisa complementar do [porte PC e Android do Budokai Tenkaichi 3](BT3_PORT_REFERENCE.md) confirma que manter dois renderers independentes é uma estratégia útil: o jogador escolhe Vulkan ou OpenGL/OpenGL ES; a seleção automática e o fallback tentam preservar a inicialização quando um driver falha.

**Decisão do projeto:** não remover o renderer OpenGL/GLES que já foi comparado no host. Adicionar Vulkan como backend paralelo, com seleção Automático / OpenGL / Vulkan e fallback testado. Essa é uma decisão de arquitetura; o backend Vulkan ainda não existe neste repositório.

A matriz planejada é:
- Windows/Linux: OpenGL 4.2 Core e Vulkan nativo.
- Android: OpenGL ES 3.0 e Vulkan nativo.
- iOS: ANGLE/Metal para o caminho OpenGL e MoltenVK para o caminho Vulkan, somente se ambos passarem pelas mesmas provas.

No BT3, a experiência publicada mostra que a escolha não deve ser feita por uma regra universal de fabricante. Um Mali-G57 MC4 e um Adreno 650 tiveram respostas diferentes em determinadas resoluções, e uma extensão de framebuffer fetch produziu imagens incorretas em uma GPU Mali. Vamos construir perfis apenas com benchmark reproduzível.

O novo gate Vulkan é independente da aprovação GLES já obtida:
1. renderer Vulkan compila e renderiza as mesmas fixtures host-only;
2. comparador OpenGL × Vulkan verifica pixels e estados de duas telas;
3. teardown completo e fallback Vulkan → OpenGL são testados em falhas simuladas;
4. recursos opcionais (timeline semaphores, dynamic rendering, formatos e compressão) têm alternativas;
5. o benchmark registra GPU/driver, p50/p95/p99, uso de CPU/GPU e memória.

Referência de implementação e contrato: [MOBILE_RENDERER_BACKENDS.md](MOBILE_RENDERER_BACKENDS.md).
