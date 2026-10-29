# Arquitetura do porte nativo

## Objetivo

Executar a lógica reconstruída de Pokémon Platinum como código nativo em Windows x64 e Linux x86-64. O alvo é preservar o jogo original; a aplicação não deve exigir que um emulador de Nintendo DS rode por baixo nem interpretar instruções ARM do DS em tempo de execução.

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
| Entrada/áudio/ciclo de vida móveis | Avaliar SDL3 onde isso não conflitar com a camada existente | APIs portáveis de plataforma; não será usada como engine substituta |

## Dependências reproduzíveis

A versão fixada do porte desktop contém arquivos Meson `.wrap` que apontam para a branch móvel `main` das bibliotecas libntr. O script `scripts/pin_native_dependencies.py` substitui essas referências por commits verificados e compatíveis com a revisão do porte usada neste projeto. O script só altera quatro arquivos conhecidos, valida todas as URLs e revisões antes de escrever, falha de forma explícita em valores desconhecidos e oferece uma operação de restauração. Os scripts de build e os jobs de CI restauram as referências ao final, inclusive após falhas, para não deixar o checkout externo com alterações locais.

A compilação no GitHub Actions prepara o código upstream como um checkout Git independente, porque um gerador de cabeçalho do upstream consulta os hashes Git da árvore principal e da libntr. Essa preparação evita depender de caminhos internos da metadata de um submódulo aninhado.

## Fluxo de execução planejado

1. O código C/C++ é compilado pelo toolchain do sistema-alvo.
2. As funções de compatibilidade fornecem ao jogo as operações de sistema e renderização esperadas.
3. A camada gráfica traduz as chamadas do jogo para a API gráfica do host.
4. Os dados do jogo são fornecidos localmente pelo usuário; o repositório não distribui ROMs nem arquivos extraídos.
5. Testes automatizados verificam compilação e comportamento de subsistemas. Testes de jogo exigem uma cópia local e são separados da CI sem dados proprietários.

A camada de compatibilidade implementa comportamento de APIs do DS; isso não é o mesmo que emular a CPU do DS. O critério do projeto é que a lógica compilada rode como código nativo, sem um interpretador ou máquina virtual de instruções do DS.

## Alvos suportados: Windows e Linux

O upstream já possui alvos `win64` e `linux` em Meson. Este repositório os aciona por scripts e CI. O desenvolvimento agora se concentra exclusivamente nesses dois alvos. A compilação e o smoke test pré-ROM são etapas necessárias, mas a inicialização do jogo e o gameplay ainda precisam de validação manual com uma cópia local válida.

## Launcher com múltiplos portes\n\nO launcher passa a ter uma biblioteca que pode listar mais de um projeto, mas cada jogo deve manter uma camada de execução própria. O backend atual continua exclusivo de Platinum: valida Pokémon Platinum USA Rev. 1 por SHA-1 e resolve o runtime Platinum. A entrada Black permanece informativa até existir runtime próprio.\n\nA integração futura deve separar, por identificador de jogo, o hash de ROM aceito, o extrator, o executável/runtime, as configurações, os recursos extraídos, os logs e os saves. Não se deve compartilhar metadados de importação entre jogos nem enviar uma ROM Black ao validador de Platinum. As duas entradas da biblioteca não significam que ambos os jogos estejam prontos para jogar.\n\nPara Black, as bases públicas [Project-Holon/aletheia](https://github.com/Project-Holon/aletheia) e [Project-Holon/eidos](https://github.com/Project-Holon/eidos) serão auditadas antes da adoção. O processo deve registrar commits exatos, licenças e dependências, e resolver a compatibilidade de 32/64 bits antes de incorporar código. Os detalhes e critérios de aceite ficam em [POKEMON_BLACK_PORT.md](POKEMON_BLACK_PORT.md).\n\n## Gestão de dados do jogo

ROM, conteúdo extraído, bancos NARC, save files e demais dados proprietários ficam fora do Git. Os testes devem receber caminhos locais e falhar com mensagens claras quando a cópia necessária não estiver disponível. Artefatos de CI serão usados para validar a compilação, não para distribuir conteúdo do jogo.
