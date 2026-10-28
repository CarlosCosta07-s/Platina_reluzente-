# Guia de compilação

Este guia compila a base nativa real de Pokémon Platinum. Ele não inclui nem baixa automaticamente uma ROM comercial, firmware ou arquivos de jogo para o repositório. Use apenas uma cópia obtida legalmente e mantenha os dados extraídos localmente.

## Requisitos comuns

- Git e acesso à internet para baixar os projetos e as ferramentas necessárias;
- Python 3, Make, compilador C/C++, Ninja e Meson (o Makefile também prepara a versão Meson usada pelo upstream);
- NASM, Flex, Bison e o compilador ARM bare-metal usado por utilitários de build do projeto;
- SDL2, ENet, libpng e pkg-config.

## Linux — build nativo no sistema

Em Ubuntu/Debian, um conjunto inicial de pacotes é:

    sudo apt-get update
    sudo apt-get install -y build-essential git python3 wget ca-certificates pkg-config ninja-build nasm flex bison gcc-arm-none-eabi libsdl2-dev libenet-dev libpng-dev

Na raiz do repositório:

    git submodule update --init --recursive
    python3 -m unittest discover -s tools/tests -v
    ./scripts/build-native.sh linux

O script valida e fixa as revisões conhecidas dos quatro arquivos Meson wrap antes de chamar o Makefile do porte. Se o build falhar por uma dependência de sistema ausente, instale o pacote correspondente apontado pelo erro e repita a compilação; não remova etapas de verificação para forçar o sucesso.

A CI deste repositório também constrói Linux com o caminho Docker disponibilizado pelo projeto de referência. Esse caminho é verificado separadamente do build nativo no sistema do desenvolvedor.

## Windows x64

Abra o PowerShell na raiz do repositório. Instale o ambiente MSYS2 mantido pela base nativa uma vez:

    cd vendor/pokeplatinum-native
    .\Install_MSys2.ps1

Depois volte à raiz:

    cd ..\..
    .\scripts\build-native.ps1

A primeira instalação baixa ferramentas do MSYS2 e pode levar algum tempo. A compilação seguinte reutiliza esse ambiente. O script do projeto fixa as revisões Meson antes de iniciar o alvo win64.

## Testes de manutenção

Os testes do importador e do fixador de dependências não precisam de ROM:

    python3 -m py_compile tools/import_localization.py scripts/pin_native_dependencies.py scripts/audit_android_graphics.py
    python3 -m unittest discover -s tools/tests -v

A auditoria Android depende de a configuração do build já ter baixado o subprojeto libntr:

    python3 scripts/audit_android_graphics.py --source-root vendor/pokeplatinum-native --format markdown

## Teste com uma cópia local

Uma compilação bem-sucedida não prova que o jogo inicia. O extrator nativo grava os arquivos no diretório de trabalho atual. Execute `main`/`main.exe` a partir de `build_linux/pokeplatinum` ou `build_win64/pokeplatinum`, selecione a sua cópia original USA Rev. 1 e confirme inicialização, tela inicial, áudio, entrada e criação dos arquivos de dados.

Depois que o porte extrair os dados, feche o jogo e valide o diretório local:

    python3 tools/check_runtime_data.py --runtime-dir vendor/pokeplatinum-native/build_linux/pokeplatinum

Para exigir também os sete NARC da versão PT-BR de referência após a importação (estrutura NARC e SHA-256 correspondentes):

    python3 tools/check_runtime_data.py --runtime-dir vendor/pokeplatinum-native/build_linux/pokeplatinum --require-localized-resources

O verificador apenas confirma a presença e a estrutura básica dos arquivos; não inicia o jogo nem comprova que ele é jogável. Depois disso, use o importador para substituir localmente os sete recursos NARC allowlisted.

Não copie ROMs, bancos NARC extraídos, saves ou outros recursos derivados para o Git. Os workflows não publicam executáveis nem conteúdo do jogo. Consulte o [aviso legal](LEGAL.md) antes de distribuir qualquer binário.
