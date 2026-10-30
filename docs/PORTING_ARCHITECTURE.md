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

## Dependências reproduzíveis

A versão fixada do porte desktop contém arquivos Meson `.wrap` que apontam para a branch móvel `main` das bibliotecas libntr. O script `scripts/pin_native_dependencies.py` substitui essas referências por commits verificados e compatíveis com a revisão do porte usada neste projeto. O script só altera quatro arquivos conhecidos, valida todas as URLs e revisões antes de escrever, falha de forma explícita em valores desconhecidos e oferece uma operação de restauração. Os scripts de build e os jobs de CI restauram as referências ao final, inclusive após falhas, para não deixar o checkout externo com alterações locais.

A compilação no GitHub Actions prepara o código upstream como um checkout Git independente, porque um gerador de cabeçalho do upstream consulta os hashes Git da árvore principal e da libntr. Essa preparação evita depender de caminhos internos da metadata de um submódulo aninhado.

## Fluxo atual de importação, preparação e boot

O fluxo adota o princípio do Gen1Recomp de não bloquear o loop gráfico com a preparação inicial dos dados, mas mantém a execução do jogo em C/C++ nativo.

1. **Importação da ROM:** o launcher verifica tamanho, cabeçalho e SHA-1 integral da revisão suportada. A cópia privada é gravada com SHA-256 e metadados; a troca de ROM/metadados usa arquivos temporários, backup e recuperação de uma transação interrompida.
2. **Preparação do runtime:** o pacote nativo é validado por manifesto SHA-256, copiado para uma pasta gravável do usuário em staging e revalidado antes da promoção. O payload também é verificado contra links simbólicos e código executável não listado.
3. **Extração pré-boot:** o launcher executa o mesmo binário com `--platina-prepare`, sem criar a janela do jogo. O runtime extrai os dados da ROM para uma pasta privada de staging e reporta progresso ao launcher.
4. **Contrato do cache V2:** os caminhos esperados vêm de um manifesto de caminhos versionado. Cada arquivo extraído e overlay é validado; o manifesto de conclusão liga os dados ao SHA-256 da ROM e ao build ID SHA-256 do payload nativo (executável e bibliotecas). Os tamanhos e CRC-32 também são registrados. Só depois da validação completa os arquivos e o manifesto são publicados. Mudança da ROM, runtime ou arquivos obrigatórios exige nova preparação.
5. **Boot nativo:** somente após a preparação bem-sucedida o launcher executa o runtime com `--platina-prepared`. O runtime verifica novamente que os dados não mudaram desde a preparação. A janela SDL fica oculta até o primeiro frame completo do jogo chegar ao ponto de apresentação.
6. **Diagnóstico:** logs persistentes, marcadores de etapa, primeira imagem e heartbeat de frames distinguem preparação incompleta, boot que não apresenta imagem e interrupção de renderização. Um heartbeat perdido restaura o launcher sem matar automaticamente o processo, protegendo possíveis gravações de save.

A extração fornece recursos locais ao runtime reconstruído; não executa uma máquina virtual de instruções ARM e não emula a CPU do Nintendo DS. O código do jogo compilado pelo toolchain do host continua sendo o código executado durante a partida. O launcher não empacota ROMs nem arquivos extraídos.

A inspiração do fluxo de importação e cache é o [Gen1Recomp](https://github.com/bryanthaboi/gen1recomp), mas ele próprio é uma recriação Lua/LÖVE e não uma recompilação nativa equivalente. O que se reutiliza são os princípios de ROM validada, preparação separada, cache privado versionado, contrato de prontidão e testes sem dados protegidos — não o motor, o renderer ou a implementação Lua.

## Alvos suportados: Windows e Linux

O upstream já possui alvos `win64` e `linux` em Meson. Este repositório os aciona por scripts e CI. O desenvolvimento agora se concentra exclusivamente nesses dois alvos. A compilação e o smoke test pré-ROM são etapas necessárias, mas a inicialização do jogo e o gameplay ainda precisam de validação manual com uma cópia local válida.

## Launcher com múltiplos portes

O launcher passa a ter uma biblioteca que pode listar mais de um projeto, mas cada jogo deve manter uma camada de execução própria. O backend atual continua exclusivo de Platinum: valida Pokémon Platinum USA Rev. 1 por SHA-1 e resolve o runtime Platinum. A entrada Black permanece informativa até existir runtime próprio.

A integração futura deve separar, por identificador de jogo, o hash de ROM aceito, o extrator, o executável/runtime, as configurações, os recursos extraídos, os logs e os saves. Não se deve compartilhar metadados de importação entre jogos nem enviar uma ROM Black ao validador de Platinum. As duas entradas da biblioteca não significam que ambos os jogos estejam prontos para jogar.

Para Black, as bases públicas [Project-Holon/aletheia](https://github.com/Project-Holon/aletheia) e [Project-Holon/eidos](https://github.com/Project-Holon/eidos) serão auditadas antes da adoção. O processo deve registrar commits exatos, licenças e dependências, e resolver a compatibilidade de 32/64 bits antes de incorporar código. Os detalhes e critérios de aceite ficam em [POKEMON_BLACK_PORT.md](POKEMON_BLACK_PORT.md).

## Gestão de dados do jogo

ROM, conteúdo extraído, bancos NARC, save files e demais dados proprietários ficam fora do Git. Os testes devem receber caminhos locais e falhar com mensagens claras quando a cópia necessária não estiver disponível. Artefatos de CI serão usados para validar a compilação, não para distribuir conteúdo do jogo.
