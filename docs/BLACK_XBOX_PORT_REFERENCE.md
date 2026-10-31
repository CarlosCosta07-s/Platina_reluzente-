# Referência de porte — Black (Xbox clássico) + Gen1Recomp

**Data da inspeção:** 30/10/2026.  
**Objetivo:** aproveitar padrões comprovados de recompilação, boot, acesso à imagem, renderização e otimização, mantendo o Gen1Recomp como referência obrigatória para as fronteiras móveis, importação e ciclo de vida.

Esta pesquisa não muda o contrato de paridade móvel, não autoriza builds Android/iOS e não propõe substituir o núcleo do Platina Reluzente por outro motor. Ela registra decisões de arquitetura para a etapa source-only.

## 1. Projetos de Black examinados

### PC — BLACK-XBERecomp

Repositório: [TGP482/BLACK-XBERecomp](https://github.com/TGP482/BLACK-XBERecomp).

É um porte nativo de Windows do Black original de Xbox por recompilação estática usando XboxXBE-Recomp. O README descreve a colocação de uma ISO ou arquivos extraídos em `assets/`; ao iniciar `BLACK.exe`, a primeira execução compila o código do jogo para o PC uma única vez. O backend gráfico anunciado é Direct3D 12.

Opções documentadas incluem resolução de renderização independente da resolução de saída (20–200%), limite de FPS, V-Sync, HDR10, MSAA, SMAA, filtragem anisotrópica, distância de desenho ampliada, oclusão de ambiente e substituição/extração de texturas. Essas opções são próprias de um jogo 3D de Xbox e não devem ser transplantadas automaticamente para um jogo de Nintendo DS.

Fontes:
- [README do porte PC](https://github.com/TGP482/BLACK-XBERecomp/blob/main/README.md)
- [Build script](https://github.com/TGP482/BLACK-XBERecomp/blob/main/build.bat)

### Android — Black-Android

Repositório: [RanggaCasper/Black-Android](https://github.com/RanggaCasper/Black-Android).

É o comparativo mais próximo do nosso objetivo móvel: recompila estaticamente o código x86 do XBE em C++, compila o resultado para ARM64 e usa Vulkan para desenhar. SDL3 cuida da janela, entrada e áudio. O projeto declara que não usa emulador. A compilação do código do jogo é feita no PC; o NDK compila as fontes C++ resultantes para ARM64.

O app Android:
- carrega SDL3 e a biblioteca nativa do jogo a partir de uma Activity derivada de SDLActivity;
- cria uma janela SDL Vulkan em tela cheia;
- inicializa configurações, input e interface;
- encontra a imagem/arquivos do jogo, monta o disco e chama o boot do runtime;
- trata eventos de suspensão/retomada, controladores e sensores;
- pausa o áudio e espera o retorno ao primeiro plano quando perde foco.

Fontes:
- [README Android](https://github.com/RanggaCasper/Black-Android/blob/main/README.md)
- [CMakeLists.txt](https://github.com/RanggaCasper/Black-Android/blob/main/CMakeLists.txt)
- [Activity Android](https://github.com/RanggaCasper/Black-Android/blob/main/app/src/main/java/com/racas/black/BlackActivity.java)
- [Host Android / loop SDL](https://github.com/RanggaCasper/Black-Android/blob/main/native/main.cpp)

### Uma segunda implementação de PC

[Spark198rus/black-pc](https://github.com/Spark198rus/black-pc) também foi consultado. É uma implementação diferente, com carregamento do XBE e execução do código x86 original, D3D9 no Windows e caminho Vulkan via DXVK no Linux/Wine. Serve como referência complementar de carregamento de XBE, mas não é a dupla PC/Android baseada na mesma recompilação estática que estamos usando como comparação principal.

## 2. Como Black encontra e inicializa uma ISO

O fluxo Android está implementado em `native/game_files.cpp`:

1. Procura primeiro arquivos extraídos (`default.xbe`) e depois imagens `.iso` nos diretórios que a aplicação conhece.
2. Para uma ISO, cria um objeto `kernel::Disc`, abre a imagem e lê somente o executável `default.xbe` para uma área de memória.
3. Calcula SHA-1 do XBE e compara com a identidade do executável usada para gerar o código nativo incluído na aplicação. Uma versão incompatível é rejeitada ou exige uma confirmação explícita.
4. Verifica os limites dos arquivos catalogados no disco em relação ao tamanho real da ISO, identificando imagens truncadas.
5. Mantém o disco montado com `kernel::MountDisc`. Em seguida, `native/main.cpp` chama `kernel::Boot`, passando o XBE, o diretório que contém os dados do jogo e o diretório persistente de HDD/saves.

**Conclusão importante:** o fluxo não copia automaticamente o conteúdo inteiro da ISO para dentro do APK nem extrai todos os arquivos para iniciar. O executável é lido para validação/boot e a imagem é montada como disco para que o runtime acesse os arquivos do jogo. O script de build também consegue extrair o XBE da ISO no PC, pois precisa recompilar o código antes da compilação ARM64.

Fontes:
- [game_files.cpp — busca, SHA-1, verificação e montagem do disco](https://github.com/RanggaCasper/Black-Android/blob/main/native/game_files.cpp)
- [main.cpp — sequência de inicialização e kernel::Boot](https://github.com/RanggaCasper/Black-Android/blob/main/native/main.cpp)
- [build.bat — extração do XBE e geração do código nativo](https://github.com/RanggaCasper/Black-Android/blob/main/build.bat)

### O que isso significa para a ROM de Platinum

A ISO de Xbox e a ROM de Nintendo DS são formatos e sistemas de arquivos diferentes. **Não devemos reutilizar o parser `kernel::Disc` nem o formato XISO.** O que podemos aproveitar é a ideia arquitetural:

- abrir a imagem do usuário como fonte somente leitura;
- validar identidade, versão, cabeçalho e limites antes de iniciar;
- expor leitura aleatória por uma interface de filesystem do runtime;
- não carregar a imagem completa na memória sem necessidade;
- separar a imagem escolhida dos dados persistentes de save/configuração.

Para Platinum, a montagem direta de `.nds` só será adotada depois de confirmar como o importador e o filesystem atuais do projeto consomem os dados. Se o runtime depender de dados extraídos, a preparação deve gerar um cache privado versionado, sem fingir que o modelo de disco montado de Black é diretamente compatível com NDS.

## 3. Renderização: PC versus Android

A divisão observada é clara:

| Plataforma | Backend no porte Black | Papel |
|---|---|---|
| Windows PC | Direct3D 12 | backend gráfico desktop |
| Android | Vulkan 1.1+ | backend gráfico móvel |
| Camada de jogo | chamadas D3D8 traduzidas pelo runtime | preservar o contrato gráfico esperado pelo jogo original |

No Android, as chamadas D3D8 são traduzidas para shaders HLSL e compiladas para SPIR-V com glslang. O backend Vulkan fornece renderização dinâmica quando disponível e cai para render passes quando não está. Usa timeline semaphores quando suportados e fences como alternativa. Também verifica suporte a texturas BC: usa compressão na GPU quando disponível e decodifica no CPU quando não.

O backend gerencia swapchain, imagens de apresentação e recursos gráficos, e não presume que todos os aparelhos tenham exatamente os mesmos recursos Vulkan.

Fontes:
- [vulkan.cpp — backend Vulkan e shaders](https://github.com/RanggaCasper/Black-Android/blob/main/native/vulkan.cpp)
- [vk_shader.cpp — compilação HLSL/SPIR-V](https://github.com/RanggaCasper/Black-Android/blob/main/native/vk_shader.cpp)
- [CMakeLists.txt — seleção dos componentes do runtime Android](https://github.com/RanggaCasper/Black-Android/blob/main/CMakeLists.txt)

### Decisão para Platina Reluzente

Não vamos trocar agora o caminho GLES 3.0 que já existe por Vulkan. O renderer atual já tem uma prova sintética host-side de equivalência Desktop GL 4.2 × GLES 3.0 em 24 cenas, mas ainda falta a integração/execução do runtime completo e os testes em aparelhos. Essa evidência é valiosa e deve ser preservada.

A sequência correta é:
1. integrar e estabilizar o backend GLES atual no runtime compartilhado;
2. testar o fluxo real de duas telas, composição, transparência, prioridades, fog, textura e touchscreen;
3. somente então construir uma comparação técnica de GLES versus Vulkan no Android, usando as mesmas cenas sintéticas e métricas;
4. avaliar a rota iOS separadamente: Metal ou ANGLE/Metal. Não assumir que Vulkan Android define a solução iOS.

Vulkan é uma opção que merece benchmark, não uma melhoria garantida por definição. A escolha deve depender de compatibilidade de drivers, custo de manutenção, consumo, latência e resultados medidos no mesmo aparelho.

## 4. Otimizações de Black que merecem estudo

### Cache de pipelines e recursos

O backend salva o cache de pipelines Vulkan em `shadercache/pipelines.bin` e reutiliza-o em execuções posteriores para reduzir engasgos causados pela criação dos pipelines. Também usa três frames em voo e buffers de upload por frame. É um padrão relevante para reduzir picos de compilação/criação de recursos, desde que o cache seja identificado por GPU/driver/versão do shader, invalidado quando incompatível e guardado no diretório privado.

### Renderização em thread separada

`src/d3d/render_thread.cpp` captura comandos e estado no momento em que o jogo faz a chamada gráfica, agrupa comandos e executa o trabalho gráfico em uma thread própria. A implementação trata dependências de recursos e sincronização de locks/fences para preservar a semântica esperada pelo console.

A ideia de separar submissão e execução pode ser útil, mas não deve ser copiada sem primeiro mapear a sincronização do libntr. No nosso projeto, a ordem de prioridade é corrigir sincronização, recuperação de falhas e ciclo de vida de recursos antes de tentar paralelizar mais trabalho. Um render thread mal sincronizado pode gerar corrupção visual e travamentos intermitentes.

### Resolução dinâmica

`native/dynamic_resolution.cpp` mede o FPS em janelas de um segundo, ignora frames muito longos que parecem carregamento/pausa, espera após cada alteração e muda a resolução em passos de 5%. Quando a taxa cai abaixo do alvo, reduz a resolução proporcionalmente ao custo estimado dos pixels; só aumenta novamente quando a taxa permanece estável. Se um aumento provoca queda imediata, impõe um limite temporário para não oscilar.

Esse algoritmo é referência para conteúdo 3D sensível à GPU. No Platinum, não devemos reduzir indiscriminadamente a resolução de texto, menus, sprites 2D ou pixels das telas DS. Qualquer escala adaptativa precisa preservar proporções e regras de composição, e atuar apenas onde a arquitetura permitir sem alterar o resultado do jogo.

### Perfil de qualidade

Black separa opções de desempenho e qualidade, expondo resolução, FPS, V-Sync, filtragem e distância de desenho. A lição é oferecer perfis claros e opções com limites, não ativar tudo indiscriminadamente. Os valores devem vir de medições em dispositivos reais; não vamos assumir o mínimo de hardware do Black como requisito do Platinum.

Fontes:
- [dynamic_resolution.cpp](https://github.com/RanggaCasper/Black-Android/blob/main/native/dynamic_resolution.cpp)
- [render_thread.cpp](https://github.com/RanggaCasper/Black-Android/blob/main/src/d3d/render_thread.cpp)
- [README Android — opções e requisitos publicados](https://github.com/RanggaCasper/Black-Android/blob/main/README.md)

## 5. O que manter do Gen1Recomp

A análise existente continua válida e não será substituída. [GEN1RECOMP_MOBILE_REFERENCE.md](GEN1RECOMP_MOBILE_REFERENCE.md) segue como referência para:

- Activity Android integrada ao host SDL e ponte JNI delimitada;
- SAF para selecionar arquivos sem exigir acesso geral ao armazenamento;
- importação assíncrona, cópia transacional para a área privada e recuperação de cancelamento/falha;
- Document Picker no iOS, URLs security-scoped e cópia controlada para o sandbox;
- safe areas, orientação, interrupções de áudio e lifecycle;
- um único modelo de input com teclado, gamepad e toque como fontes independentes;
- separação entre sessão de jogo e processo da aplicação.

Uma diferença de produto importa: Black Android pede acesso amplo a arquivos para localizar ISOs em pastas compartilhadas e cartões SD. **Não adotaremos essa permissão ampla como padrão.** O Platinum seguirá o modelo de importação escolhida pelo usuário via SAF/Document Picker e armazenamento privado, como já definido no contrato móvel.

## 6. Arquitetura combinada escolhida

| Área | Referência principal | Decisão para Platina Reluzente |
|---|---|---|
| Núcleo nativo e separação host/runtime | Black | preservar o núcleo C/C++ existente e manter os serviços de plataforma fora da lógica do jogo |
| Boot e identidade do jogo | Black + Gen1 | validar a ROM antes de iniciar; usar identidade criptográfica e estado explícito de boot |
| Seleção/importação de ROM | Gen1Recomp | SAF/Document Picker, cópia segura, staging, progresso e recuperação |
| Acesso aos dados | Black + Gen1 | decidir entre leitura aleatória da ROM e cache extraído após auditar o filesystem atual; em ambos os casos, dados locais privados e verificáveis |
| Renderização Android | Black como comparação futura | manter GLES 3.0 atual; Vulkan só após benchmark e prova visual equivalente |
| Renderização iOS | contrato atual | avaliar ANGLE/Metal ou Metal nativo, sem presumir equivalência automática |
| Otimização | Black | estudar cache de pipelines, buffers por frame e resolução dinâmica somente depois da estabilidade e com métricas |
| Lifecycle e input | Gen1Recomp | manter Activity/bridges finas, serviços assíncronos, safe areas e fontes de input independentes |

### Fluxo de boot proposto — ainda como contrato, não como código concluído

1. O usuário escolhe a ROM por SAF (Android) ou Document Picker (iOS).
2. O app copia o arquivo para um staging privado, calcula hashes enquanto copia e valida o tamanho, o cabeçalho, o código do jogo e a revisão esperada.
3. A importação é promovida atomicamente para uma identidade local. Cancelamento, falha ou encerramento não podem deixar um jogo parcialmente marcado como pronto.
4. O preparador cria ou valida os dados/cache locais exigidos pela versão do runtime, com manifesto, hashes e versão do extrator.
5. O host inicializa os serviços SDL, a superfície gráfica e o núcleo C/C++.
6. O núcleo monta o filesystem/leitor da ROM ou abre o cache preparado — conforme o resultado da auditoria do filesystem atual — e inicia a sessão.
7. Saves e configurações ficam separados da ROM e do cache regenerável. Logs informam em qual fase ocorreu qualquer falha.

## 7. Limites de reutilização e licença

Esta pesquisa compara arquitetura e comportamento; não copia código, assets, executáveis, shaders ou conteúdo do jogo Black.

O repositório Black-Android e a revisão do XboxXBE-Recomp consultada publicam licença MIT. Isso não autoriza reutilizar o código do jogo Black, seus assets ou componentes de terceiros sem verificar suas licenças e condições. O repositório BLACK-XBERecomp não apresentou um arquivo LICENSE no caminho consultado; a licença efetiva de cada componente deve ser verificada antes de qualquer reutilização de código.

A referência Gen1Recomp permanece sujeita às condições específicas já descritas em sua própria documentação. Nesta etapa, adotamos padrões arquiteturais, não transplantamos código ou recursos visuais.

## 8. Ordem de trabalho resultante

1. Concluir a validação do renderer e a integração do caminho GLES no runtime Desktop/host.
2. Auditar o fluxo atual de importação, extração e abertura de arquivos NDS; decidir formalmente entre filesystem montado, cache extraído ou modelo híbrido.
3. Projetar a API C do núcleo para boot, pause, resume, shutdown, consulta de estado e serviços do host.
4. Implementar importação assíncrona e transacional conforme Gen1Recomp, sem permissão geral de arquivos.
5. Implementar o host Android SDL/JNI e a bridge iOS mantendo o núcleo C++ compartilhado.
6. Integrar e validar lifecycle, input, áudio, saves, logs e recuperação de superfície.
7. Medir cache de recursos, sincronização, consumo de memória e desempenho antes de decidir sobre Vulkan ou resolução dinâmica.
8. Fechar a matriz de paridade 1:1 com Desktop. Só depois disso autorizar a primeira compilação Android/iOS, seguida de testes em aparelhos reais.

**A regra atual continua inalterada: não compilar APK, AAB ou IPA antes da paridade funcional 1:1 com Desktop.**
