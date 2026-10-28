# Platina Reluzente — porte nativo de Pokémon Platinum

> **Projeto comunitário de preservação e estudo, sem fins comerciais.** Não é um produto oficial nem possui vínculo com Nintendo, Game Freak ou The Pokémon Company.

O objetivo é fazer **Pokémon Platinum executar como um aplicativo nativo** em **Windows, Linux e Android**, reutilizando o código C reconstruído pela comunidade a partir do jogo original. O projeto não pretende incluir ROMs, firmware ou arquivos de jogo nos releases.

## Estado real do projeto

- **Base nativa desktop:** vinculada como checkout externo e fixada em um commit específico do porte de PC baseado na decompilação pret/pokeplatinum.
- **Linux x86-64:** a compilação nativa passou no GitHub Actions em 28 de outubro de 2026, na execução [40625184953](https://github.com/CarlosCosta07-s/Platina_reluzente-/actions/runs/40625184953). Isso valida a compilação do alvo, não a inicialização nem a jogabilidade.
- **Windows x64:** a compilação ainda estava em execução na última verificação; não é considerada aprovada até o job terminar com sucesso.
- **Android:** ainda não implementado nem validado. O backend gráfico desktop usa shaders GLSL versão 420 core e APIs de desktop OpenGL; Android exige uma implementação real de renderização compatível, além de integração com ciclo de vida, entrada por toque, áudio e armazenamento.
- **Versão original:** o ponto de referência inicial é Pokémon Platinum USA Rev. 1, identificado no upstream por SHA-1 0862ec35b24de5c7e2dcb88c9eea0873110d755c.
- **Português brasileiro:** o importador local dos bancos de texto está implementado e foi testado com as duas cópias fornecidas; ainda falta validar a execução do jogo com os textos aplicados.

Não anunciamos o porte como concluído, jogável do início ao fim ou compatível com Android antes de termos compilação e testes reproduzíveis.

## Decisão técnica

**Não usaremos Godot, Unity, emulador de Nintendo DS nem interpretador de instruções ARM.** Uma engine genérica obrigaria a reconstruir o jogo em vez de aproveitar a lógica real existente.

A rota escolhida é:

- **C** para a lógica original reconstruída de Pokémon Platinum;
- **C/C++** onde as bibliotecas nativas existentes exigirem;
- **Meson + Ninja** para a compilação do porte de PC;
- **libntr** e a camada nativa do projeto de referência para substituir APIs do NitroSDK no host;
- **OpenGL de desktop** para Windows/Linux na base existente;
- **Android NDK** para gerar código ARM64 nativo no telefone. O backend gráfico e a integração de plataforma precisam ser portados e testados antes de declarar Android suportado.

A camada de compatibilidade recria serviços e chamadas gráficas que o jogo espera, mas **não executa uma CPU de DS emulada nem interpreta o código ARM do jogo durante a partida**: o código recompilado é compilado pelo toolchain do sistema-alvo.

Veja a [arquitetura](docs/PORTING_ARCHITECTURE.md), o [roteiro](docs/ROADMAP.md), a [estratégia PT-BR](docs/LOCALIZATION.md) e o [aviso legal](docs/LEGAL.md).

## Código de referência e compilação

A base desktop usada como referência está em [cybervisi0n/pokeplatinum](https://github.com/cybervisi0n/pokeplatinum), baseada na [decompilação pret/pokeplatinum](https://github.com/pret/pokeplatinum) e na biblioteca [libntr](https://github.com/cybervisi0n/libntr). Ela é vinculada como submódulo e não é modificada por este projeto sem revisão específica das condições do upstream.

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
    .\scripts/build-native.ps1

Os builds de desktop **compilam o código**; eles não executam testes de jogo automaticamente. Para jogar, use somente uma cópia obtida legalmente e mantenha ROMs e recursos extraídos fora deste repositório. Consulte os documentos legais antes de distribuir qualquer compilação.

## Importar os textos PT-BR localmente

Depois de compilar e abrir o porte uma vez com a cópia original para preparar os dados de jogo locais, feche o jogo e execute o importador. Exemplo para Linux:

    python3 tools/import_localization.py \
      --rom "/caminho/local/PK Plat [PT-BR].nds" \
      --destination "vendor/pokeplatinum-native/build_linux/pokeplatinum" \
      --force

Para Windows, use o diretório vendor/pokeplatinum-native/build_win64/pokeplatinum. O importador modifica apenas os três bancos de texto selecionados no diretório de destino; não altera a ROM de origem nem faz upload. Ele valida a estrutura NARC e recusa uma recuperação de tamanho que se sobreponha a outro arquivo da ROM. Veja a [documentação de localização](docs/LOCALIZATION.md).

Execute os testes automatizados da ferramenta sem precisar de ROM:

    python3 -m unittest discover -s tools/tests -v

## Regra do repositório

O desenvolvimento deste projeto será feito diretamente na branch main; não serão criadas branches de trabalho. O workflow de CI também acompanha apenas a main.

## Links

- [Arquitetura técnica](docs/PORTING_ARCHITECTURE.md)
- [Roteiro e critérios de aceite](docs/ROADMAP.md)
- [Compatibilidade PT-BR e original](docs/LOCALIZATION.md)
- [Preservação, direitos e distribuição](docs/LEGAL.md)
- [Decompilação base (pret)](https://github.com/pret/pokeplatinum)
- [Porte nativo PC de referência](https://github.com/cybervisi0n/pokeplatinum)
- [SDL3 — referência para integração móvel, sujeita à compatibilidade com a base atual](https://wiki.libsdl.org/SDL3/FrontPage)
