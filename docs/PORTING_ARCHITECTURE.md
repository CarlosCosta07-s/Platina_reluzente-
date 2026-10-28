# Arquitetura do porte nativo

## Objetivo

Executar a lógica reconstruída de Pokémon Platinum como código nativo em Windows x64, Linux x86-64 e Android arm64-v8a. O alvo é preservar o jogo original; a aplicação não deve exigir que um emulador de Nintendo DS rode por baixo nem interpretar instruções ARM do DS em tempo de execução.

## Base escolhida

A árvore de trabalho usa, como dependência externa e imutável por padrão, o porte desktop em [cybervisi0n/pokeplatinum](https://github.com/cybervisi0n/pokeplatinum), fixado no commit `35067868f64f23d25d17ac3e536cfdd9a7f40523`. Essa base parte da decompilação C em [pret/pokeplatinum](https://github.com/pret/pokeplatinum) e usa [libntr](https://github.com/cybervisi0n/libntr) para substituir chamadas comuns do NitroSDK e fornecer APIs gráficas para o host.

Isso é preferível a reconstruir as mecânicas do zero em uma engine genérica. Não adotaremos Godot/Unity como engine do jogo: a prioridade é compilar e portar a lógica original disponível.

## Linguagens e ferramentas

| Componente | Escolha | Responsabilidade |
|---|---|---|
| Lógica do jogo | C | Código reconstruído a partir do jogo |
| Integrações e bibliotecas | C/C++ | APIs nativas e dependências existentes |
| Build desktop | Meson + Ninja, orquestrados por Make | Configuração e compilação reproduzível |
| Compatibilidade com SDK | libntr / camada do porte | Substituir serviços do NitroSDK usados pelo jogo |
| Windows/Linux | Binário nativo de host | Execução sem emulação da CPU do DS |
| Android | Android NDK + backend gráfico compatível | Compilar para ARM64 e integrar ciclo de vida, entrada e armazenamento |
| Entrada/áudio/ciclo de vida móveis | Avaliar SDL3 onde isso não conflitar com a camada existente | APIs portáveis de plataforma; não será usada como engine substituta |

## Fluxo de execução planejado

1. O código C/C++ é compilado pelo toolchain do sistema-alvo.
2. As funções de compatibilidade fornecem ao jogo as operações de sistema e renderização esperadas.
3. A camada gráfica traduz as chamadas do jogo para a API gráfica do host.
4. Os dados do jogo são fornecidos localmente pelo usuário; o repositório não distribui ROMs nem arquivos extraídos.
5. Testes automatizados verificam compilação e comportamento de subsistemas. Testes de jogo exigem uma cópia local e são separados da CI sem dados proprietários.

A camada de compatibilidade implementa comportamento de APIs do DS; isso não é o mesmo que emular a CPU do DS. O critério do projeto é que a lógica compilada rode como código nativo, sem um interpretador ou máquina virtual de instruções do DS.

## Windows/Linux agora

O upstream já possui alvos `win64` e `linux` em Meson. Este repositório os aciona por scripts e CI, sem publicar executáveis ou recursos do jogo. Primeiro validaremos uma compilação limpa de cada alvo; depois será necessário smoke test manual com uma cópia local válida.

## Android — trabalho necessário

O caminho de desktop utiliza OpenGL 4.2; não devemos presumir que essa API esteja disponível em dispositivos Android. Antes de adicionar um alvo Android real, é necessário:

1. mapear todos os usos de APIs OpenGL desktop e identificar requisitos de shaders, buffers, sincronização e framebuffer;
2. implementar e testar um backend OpenGL ES adequado ou optar por Vulkan caso os requisitos não possam ser atendidos de forma robusta;
3. integrar eventos de pausa/retomada, toque, controladores, áudio e armazenamento com o Android NDK;
4. compilar um APK arm64-v8a em CI;
5. testar inicialização, tela inicial, áudio, salvamento e retomada em dispositivo/emulador **de sistema Android**. Um emulador de Android pode ser usado para testar o aplicativo Android; não será usado como emulador de Nintendo DS.

Não declare Android concluído até os critérios acima serem atendidos. Não introduza stubs que simplesmente retornem sucesso para APIs gráficas essenciais.

## Gestão de dados do jogo

ROM, conteúdo extraído, bancos NARC, save files e demais dados proprietários ficam fora do Git. Os testes devem receber caminhos locais e falhar com mensagens claras quando a cópia necessária não estiver disponível. Artefatos de CI serão usados para validar a compilação, não para distribuir conteúdo do jogo.
