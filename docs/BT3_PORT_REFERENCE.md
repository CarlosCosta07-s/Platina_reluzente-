# Referência técnica — Dragon Ball Z: Budokai Tenkaichi 3 (PC e Android)

**Data da inspeção:** 30/10/2026.  
**Projetos consultados:** [Tenkaichi3Decomp (PC)](https://github.com/z3xox/Tenkaichi3Decomp) e [Tenkaichi3DecompAndroid / Dragon Rage](https://github.com/dfdx047/Tenkaichi3DecompAndroid).

**Objetivo:** estudar como um porte nativo de jogo de console mantém um núcleo de jogo compartilhado, prepara a imagem do usuário, lida com GPUs diferentes e oferece dois backends gráficos. Esta documentação registra padrões arquiteturais. Não reutiliza código, shaders, assets ou executáveis desses projetos.

## 1. O porte de PC

O [Tenkaichi3Decomp](https://github.com/z3xox/Tenkaichi3Decomp) é uma implementação nativa para PC baseada na descompilação correspondente de Budokai Tenkaichi 3. O código do jogo é compilado para a plataforma PC com novas camadas de renderização, áudio e entrada; o projeto não se apresenta como emulador.

O setup do PC recebe a ISO USA do próprio usuário (SLUS-21678), valida a imagem e extrai os dados necessários para a instalação. Depois disso, o jogo usa os dados instalados, sem precisar carregar a ISO a cada início.

### Renderização no PC

O projeto oferece dois caminhos gráficos:
- **Vulkan**, renderer principal.
- **OpenGL 3.3**, alternativa para máquinas cujo Vulkan não funciona corretamente.

O jogador pode escolher o renderer nas opções. O setup e o jogo tentam OpenGL quando não encontram um Vulkan utilizável; também existe uma variável de ambiente para pedir OpenGL desde o começo. O README informa que o renderer OpenGL é mais lento no cenário de referência do projeto, mas continua necessário para compatibilidade.

Fontes:
- [README PC — Tenkaichi3Decomp](https://github.com/z3xox/Tenkaichi3Decomp/blob/main/README.md)
- [Código do renderer / GS](https://github.com/z3xox/Tenkaichi3Decomp/tree/main/port/src/gs)
- [Setup da instalação](https://github.com/z3xox/Tenkaichi3Decomp/tree/main/port/setup)

## 2. O porte Android — Dragon Rage

O [Tenkaichi3DecompAndroid](https://github.com/dfdx047/Tenkaichi3DecompAndroid) é um porte Android baseado no mesmo projeto de PC. No estado descrito no README 0.9.0, o jogo completo (menus, história e batalhas) roda como código nativo ARM64 em Snapdragon, Mali, Xclipse e PowerVR, com a meta de manter os 30 quadros por segundo do jogo original nos dispositivos suportados.

O aplicativo é dividido em:
- launcher Android em Kotlin / Jetpack Compose;
- engine nativa construída como biblioteca `libbt3.so`;
- diretórios `src/`, `include/` e `port/` com o código de jogo descompilado e a camada de portabilidade.

A Activity Android integra a engine e as APIs do sistema. O código do jogo e o renderer permanecem nativos; o app não depende de uma máquina virtual de console para executar a lógica.

### Preparação e importação da ISO

O Android faz um fluxo diferente do Black Xbox:
1. O usuário escolhe a ISO USA pelo seletor de documentos do Android.
2. O app abre a imagem como fluxo/arquivo de leitura e analisa o filesystem ISO 9660.
3. Localiza o executável `SLUS_216.78` e os arquivos de dados relevantes, incluindo `BIN/DBZP.BIN` e `DATA/`.
4. Extrai as regiões executáveis do ELF e verifica hashes de identidade do jogo e do arquivo de dados principal.
5. Aceita dados modificados em alguns cenários somente após validações adicionais de compatibilidade.
6. Copia os arquivos necessários para o diretório privado `gamedata/`, grava um marcador de instalação e apresenta progresso/erros ao launcher.
7. O runtime usa a instalação local. A ISO original não é mantida como imagem montada para o gameplay.

A implementação também verifica espaço disponível e trata cancelamento de operações assíncronas. Um caso documentado de ISO escolhida via MediaStore mostrou que não se deve reabrir cegamente um caminho `/proc/self/fd/N`: a engine deve continuar lendo o descritor recebido, por exemplo com `pread`, respeitando as permissões concedidas pelo seletor.

Fontes:
- [README Android](https://github.com/dfdx047/Tenkaichi3DecompAndroid/blob/main/README.md)
- [IsoImage.kt — leitura de ISO 9660](https://github.com/dfdx047/Tenkaichi3DecompAndroid/blob/main/android/app/src/main/java/com/dfdx047/dragonrage/data/IsoImage.kt)
- [GameDataInstaller.kt — verificação e extração](https://github.com/dfdx047/Tenkaichi3DecompAndroid/blob/main/android/app/src/main/java/com/dfdx047/dragonrage/data/GameDataInstaller.kt)
- [MainActivity.kt](https://github.com/dfdx047/Tenkaichi3DecompAndroid/blob/main/android/app/src/main/java/com/dfdx047/dragonrage/MainActivity.kt)

### Renderização no Android

A versão Android disponibiliza:
- **Vulkan** como caminho preferido no estado atual do projeto;
- **OpenGL ES 3.2** como alternativa;
- fallback para o outro renderer quando o escolhido não consegue inicializar;
- seleção manual nas configurações;
- perfis de GPU que recomendam resolução interna e alguns recursos de qualidade/desempenho.

O código separa a preferência do usuário (automático, Vulkan ou OpenGL ES) da configuração efetiva passada à engine. O nome da GPU é identificado pelo driver OpenGL ES, guardado para diagnóstico e usado pelo sistema de perfis.

A estratégia de seleção evoluiu entre versões. Versões anteriores testaram selecionar OpenGL ES automaticamente em algumas GPUs Mali, enquanto o código/README 0.9.0 consultado usa Vulkan como preferência automática e mantém OpenGL ES como opção/fallback. A lição não é copiar uma regra fixa por fabricante: é medir e atualizar perfis com dados concretos de GPU e driver.

Fontes:
- [Renderer.kt — preferência e escolha](https://github.com/dfdx047/Tenkaichi3DecompAndroid/blob/main/android/app/src/main/java/com/dfdx047/dragonrage/data/Renderer.kt)
- [GpuProfiles.kt — perfis por GPU](https://github.com/dfdx047/Tenkaichi3DecompAndroid/blob/main/android/app/src/main/java/com/dfdx047/dragonrage/data/GpuProfiles.kt)
- [gs_gpu.c — backend Vulkan via SDL_GPU](https://github.com/dfdx047/Tenkaichi3DecompAndroid/blob/main/port/src/gs/gs_gpu.c)
- [gs_gl.c — backend OpenGL](https://github.com/dfdx047/Tenkaichi3DecompAndroid/blob/main/port/src/gs/gs_gl.c)

## 3. O que os testes de aparelhos ensinam

O projeto mantém um relatório de laboratório com medições em um RG Cube (Mali-G57 MC4) e um Retroid Pocket 5 (Adreno 650). O relatório deixa claro que o resultado depende da GPU, do driver, da resolução interna, dos passes e das opções gráficas.

Exemplos documentados:
- No Mali-G57 MC4, Vulkan em 1,5x manteve 30 FPS com pior quadro de aproximadamente 25 ms; OpenGL também manteve 30 FPS em 1,5x, com pior quadro de aproximadamente 24 ms.
- No mesmo Mali, o Vulkan em 2x ficou abaixo dos 30 FPS em uma configuração medida, e determinadas otimizações de passes sem profundidade melhoraram o resultado.
- No Adreno 650, Vulkan 2x manteve 30 FPS, mas o OpenGL sofreu muito antes de ativar buffers persistentes; com a correção, OpenGL 2x também chegou a 30 FPS.
- Uma extensão de framebuffer fetch no Mali produziu imagens incorretas e travamentos em determinados aparelhos; foi desativada por padrão.

Isso reforça que não podemos declarar Vulkan universalmente mais rápido, nem ativar extensões opcionais apenas porque existem. Cada otimização precisa passar por teste de imagem e benchmark no hardware relevante.

Fonte: [device-lab-2026-10.md](https://github.com/dfdx047/Tenkaichi3DecompAndroid/blob/main/docs/device-lab-2026-10.md).

## 4. O que vamos aproveitar no Platina Reluzente

| Área | Lição aproveitável |
|---|---|
| Código do jogo e plataforma | manter o núcleo C/C++ compartilhado, isolando janela, filesystem e renderer por interfaces de plataforma |
| Importação | escolher a ROM por SAF / Document Picker, validar identidade e tamanho, mostrar progresso e preparar os dados locais transacionalmente |
| ISO | estudar leitura aleatória e parsing da imagem, mas manter a extração/cache se o filesystem NDS atual exigir arquivos preparados |
| Renderização | manter os dois backends, permitir seleção manual e fallback real quando um deles falhar |
| GPUs | identificar adaptador/driver e manter perfis atualizáveis com medições reais, sem assumir que todos os chips de uma família se comportam igual |
| Otimização | priorizar reduzir passes desnecessários, evitar recompilações de shader durante gameplay e controlar orçamento de cache |
| Diagnóstico | guardar renderer escolhido/ativo, versão da API, GPU/driver, motivo de fallback e métricas de frame time no log |

## 5. Decisões para o Platina Reluzente

1. **A renderização OpenGL atual permanece.** O Desktop continua com GL 4.2 Core; o caminho móvel GLES 3.0/GLSL ES 3.00 permanece como backend de compatibilidade em desenvolvimento. Não substituiremos nem apagaremos as variantes que já passaram pelos comparadores sintéticos.
2. **Vulkan será adicionado como segundo backend real.** Não será apenas uma configuração visual ou uma camada que encaminha para OpenGL. Terá implementação própria de recursos, pipelines, sincronização, swapchain e apresentação.
3. **O jogador poderá selecionar Auto, OpenGL ou Vulkan** quando o backend estiver disponível naquela plataforma. A preferência fica persistida; o backend efetivamente ativo e o motivo da escolha/fallback também ficam visíveis no diagnóstico.
4. **Auto escolherá com base em compatibilidade e perfil medido**, não apenas no nome da GPU. A seleção considera API, extensões/recursos obrigatórios, formatos, driver e resultados de estabilidade.
5. **Falha Vulkan deve liberar completamente os recursos parciais** antes de criar o contexto OpenGL; não deixar janela, surface, swapchain ou device parcialmente vivos. Fallback não pode resultar em tela preta.
6. **O resultado visual deve ser equivalente.** Os dois backends consomem o mesmo contrato lógico de renderização e passam pelas mesmas cenas sintéticas de comparação.
7. **iOS requer uma rota própria.** Vulkan pode ser experimentado via MoltenVK sobre Metal; OpenGL poderá ser disponibilizado por uma camada ANGLE/Metal. Nenhuma das duas rotas será declarada estável sem passar pelas mesmas provas. Se um backend não for suportado ou validado no iOS, ele não aparecerá como opção selecionável nessa plataforma.

### Matriz pretendida por plataforma

| Plataforma | Backend OpenGL | Backend Vulkan |
|---|---|---|
| Windows | OpenGL 4.2 Core (atual) | Vulkan nativo (novo) |
| Linux | OpenGL 4.2 Core (atual) | Vulkan nativo (novo) |
| Android | OpenGL ES 3.0 (caminho móvel atual) | Vulkan nativo (novo) |
| iOS | ANGLE sobre Metal, após validação | MoltenVK sobre Metal, após validação |

A matriz descreve o objetivo arquitetural, não uma declaração de disponibilidade atual. Os caminhos Vulkan, ANGLE e MoltenVK ainda precisam ser implementados e validados no nosso projeto.

## 6. Limites de reutilização e licenças

Esta pesquisa aproveita conceitos e evidências públicas. Não copiamos o renderer, os shaders, as estruturas de instalação, a decompilação ou outros trechos de código desses projetos.

O README do Android declara que a camada própria do app Android está sob MIT, enquanto a camada de portabilidade do PC/engine passou a AGPL-3.0 no histórico indicado pelo projeto; dependências de terceiros mantêm suas próprias licenças, e o código do jogo descompilado continua pertencendo aos detentores dos direitos. Qualquer uso futuro de código exigiria uma revisão de licença independente. Esta pesquisa não é autorização para copiar ou relicenciar código.

## 7. Fontes primárias

- [Tenkaichi3Decomp — PC](https://github.com/z3xox/Tenkaichi3Decomp)
- [Tenkaichi3DecompAndroid — Android](https://github.com/dfdx047/Tenkaichi3DecompAndroid)
- [Android ISO reader](https://github.com/dfdx047/Tenkaichi3DecompAndroid/blob/main/android/app/src/main/java/com/dfdx047/dragonrage/data/IsoImage.kt)
- [Android installer](https://github.com/dfdx047/Tenkaichi3DecompAndroid/blob/main/android/app/src/main/java/com/dfdx047/dragonrage/data/GameDataInstaller.kt)
- [GPU profile report](https://github.com/dfdx047/Tenkaichi3DecompAndroid/blob/main/docs/device-lab-2026-10.md)

