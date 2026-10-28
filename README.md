# Platina Reluzente — porte nativo de Pokémon Platinum

> **Projeto comunitário de preservação e estudo, sem fins comerciais.** Não é um produto oficial nem possui vínculo com Nintendo, Game Freak ou The Pokémon Company.

O objetivo é fazer **Pokémon Platinum executar como um aplicativo nativo** em **Windows, Linux e Android**, reutilizando o código C reconstruído pela comunidade a partir do jogo original. O projeto não pretende incluir ROMs, firmware ou arquivos de jogo nos releases.

## Estado real do projeto

- **Base nativa desktop:** vinculada como checkout externo e fixada em um commit específico do porte de PC baseado na decompilação pret/pokeplatinum.
- **Linux x86-64 e Windows x64:** ambos os alvos passaram na execução [40627263360 do GitHub Actions](https://github.com/CarlosCosta07-s/Platina_reluzente-/actions/runs/40627263360), em 28 de outubro de 2026. Isso valida a compilação dos dois alvos, não a inicialização nem a jogabilidade.
- **Android:** ainda não implementado nem validado. A auditoria encontrou um pedido de OpenGL 4.2 core, shaders GLSL 420 core e operações que precisam de adaptação para OpenGL ES. A primeira hipótese é SDL2 + OpenGL ES 3.2; isso continua sendo trabalho futuro.
- **Versão original:** o ponto de referência inicial é Pokémon Platinum USA Rev. 1, identificado no upstream por SHA-1 0862ec35b24de5c7e2dcb88c9eea0873110d755c.
- **Português brasileiro:** a variante PT-BR fornecida difere em dez entradas FAT em relação à ROM USA. O importador agora permite sete recursos NARC localizados, mas a execução do jogo com esses dados ainda precisa ser validada.

Não anunciamos o porte como concluído, jogável do início ao fim ou compatível com Android antes de termos compilação e testes reproduzíveis.

## Decisão técnica

**Não usaremos Godot, Unity, emulador de Nintendo DS nem interpretador de instruções ARM.** Uma engine genérica obrigaria a reconstruir o jogo em vez de aproveitar a lógica real existente.

A rota escolhida é:

- **C** para a lógica original reconstruída de Pokémon Platinum;
- **C/C++** onde as bibliotecas nativas existentes exigirem;
- **Meson + Ninja** para a compilação do porte de PC;
- **libntr** e a camada nativa do projeto de referência para substituir APIs do NitroSDK no host;
- **OpenGL de desktop** para Windows/Linux na base existente;
- **Android NDK** para gerar código ARM64 nativo no telefone, com um backend gráfico próprio para Android.

A camada de compatibilidade recria serviços e chamadas gráficas que o jogo espera, mas **não executa uma CPU de DS emulada nem interpreta o código ARM do jogo durante a partida**: o código recompilado é compilado pelo toolchain do sistema-alvo.

Veja o [guia de compilação](docs/BUILDING.md), a [arquitetura](docs/PORTING_ARCHITECTURE.md), o [roteiro](docs/ROADMAP.md), a [estratégia PT-BR](docs/LOCALIZATION.md) e o [aviso legal](docs/LEGAL.md).

## Código de referência e compilação

A base desktop usada como referência está em [cybervisi0n/pokeplatinum](https://github.com/cybervisi0n/pokeplatinum), baseada na [decompilação pret/pokeplatinum](https://github.com/pret/pokeplatinum) e na biblioteca [libntr](https://github.com/cybervisi0n/libntr). Ela é vinculada como dependência externa fixada e não é modificada permanentemente por este projeto sem revisão específica das condições do upstream.

Clone o repositório e inicialize as dependências de código:

    git clone https://github.com/CarlosCosta07-s/Platina_reluzente-.git
    cd Platina_reluzente-
    git submodule update --init --recursive

Linux:

    ./scripts/build-native.sh linux

Windows (PowerShell; instale o ambiente MSYS2 do submódulo uma vez antes da primeira compilação):

    cd vendor/pokeplatinum-native
    .\Install_MSys2.ps1
    cd ..\..
    .\scripts\build-native.ps1

Os builds de desktop **compilam o código**; eles não executam testes de jogo automaticamente. Para jogar, use somente uma cópia obtida legalmente e mantenha ROMs e recursos extraídos fora deste repositório. Consulte os documentos legais antes de distribuir qualquer compilação.

## Importar recursos localizados PT-BR localmente

A comparação das ROMs fornecidas identificou estes sete arquivos NARC localizados que podem ser selecionados explicitamente para importação:

- battle/graphic/pl_b_plist_gra.narc
- data/slot.narc
- demo/title/op_demo.narc
- graphic/pl_bag_gra.narc
- graphic/pl_plist_gra.narc
- graphic/pl_pst_gra.narc
- msgdata/pl_msg.narc

Os arquivos msgdata/msg.narc e msgdata/scenario/scr_msg.narc são idênticos entre as duas ROMs fornecidas, então não precisam ser substituídos. As entradas data/utility.bin, dwc/utility.bin e a entrada FAT sem caminho no FNT foram deliberadamente excluídas: não serão copiadas ao runtime sem análise de compatibilidade específica.

Após compilar e iniciar o porte uma vez para preparar os dados locais, feche o jogo e execute o importador, apontando para o diretório-raiz onde os recursos extraídos estão organizados:

    python3 tools/import_localization.py \
      --rom "/caminho/local/PK Plat [PT-BR].nds" \
      --destination "vendor/pokeplatinum-native/build_linux" \
      --force

Em Windows, use o diretório de trabalho do executável em build_win64. O extrator upstream usa o diretório de trabalho atual; por isso, execute o jogo a partir de build_linux ou build_win64, e não de outra pasta. A ferramenta modifica apenas os sete arquivos allowlisted no diretório de destino; não altera a ROM de origem nem faz upload. Ela valida a estrutura NARC e só recupera o tamanho declarado no NARC quando o intervalo adicional não se sobrepõe a outro arquivo FAT.

Depois da importação, confira os arquivos locais com `python3 tools/check_runtime_data.py --runtime-dir vendor/pokeplatinum-native/build_linux --require-localized-resources`. A validação confirma a presença e a estrutura básica dos arquivos, mas não inicia o jogo. A importação desses recursos ainda não prova que todas as telas e eventos funcionam em PT-BR. Confirme fontes, acentos, menus, diálogos, batalhas e salvamento dentro do jogo antes de considerar essa variante compatível. Veja a [documentação de localização](docs/LOCALIZATION.md).

Execute os testes automatizados sem precisar de ROM:

    python3 -m unittest discover -s tools/tests -v

## Regra do repositório

O desenvolvimento será feito diretamente na branch main; não serão criadas branches de trabalho. A CI acompanha apenas a main.

## Links

- [Arquitetura técnica](docs/PORTING_ARCHITECTURE.md)
- [Roteiro e critérios de aceite](docs/ROADMAP.md)
- [Compatibilidade PT-BR e original](docs/LOCALIZATION.md)
- [Preservação, direitos e distribuição](docs/LEGAL.md)
- [Decompilação base (pret)](https://github.com/pret/pokeplatinum)
- [Porte nativo PC de referência](https://github.com/cybervisi0n/pokeplatinum)
- [Guia oficial SDL2 para Android](https://wiki.libsdl.org/SDL2/README-android)
- [OpenGL ES no Android](https://developer.android.com/develop/ui/views/graphics/opengl/about-opengl)
