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

    python3 -m py_compile tools/import_localization.py scripts/pin_native_dependencies.py scripts/verify_native_package.py scripts/prepare_native_runtime.py
    python3 -m unittest discover -s tools/tests -v

## Teste com uma cópia local

### Verificação do pacote gerado
### Diagnóstico de falhas de inicialização no launcher

O launcher desktop encaminha agora a saída padrão e a saída de erro do executável nativo para um log persistente chamado `native-startup.log`, no diretório privado de dados do aplicativo, dentro de `logs`. O launcher mostra o caminho exato no status depois de iniciar o processo. Se nenhuma janela do jogo aparecer, abra esse log e procure mensagens de inicialização do SDL/OpenGL, arquivos ausentes ou falhas do runtime.

A mensagem de sucesso do launcher significa somente que o sistema operacional criou o processo nativo; ela não comprova a tela de título nem a jogabilidade. A confirmação exige executar o jogo com a ROM USA Rev. 1 compatível e verificar a tela inicial e uma sessão mínima de jogo.

### Teste pré-ROM da interface no Linux

Na CI, o teste abaixo abre o executável num display X11 virtual com OpenGL por software, a partir de um diretório de trabalho temporário vazio, e exige que uma janela visível `libntr Application` seja criada e que o processo permaneça ativo por 15 segundos:

    bash scripts/smoke-test-native-startup.sh vendor/pokeplatinum-native/build_linux/pokeplatinum-x86_64.AppImage 15

O teste local usa o `pokeplatinum-x86_64.AppImage` dentro da árvore `build_linux` (a localização exata pode depender da tarefa Meson/AppImage). A CI localiza o artefato gerado pelo nome sob `build_linux` e falha explicitamente se não encontrar exatamente um. O AppImage é chamado pelo caminho absoluto com `--appimage-extract-and-run`, que permite executar o conteúdo sem depender da montagem FUSE; o diretório de trabalho fica temporariamente vazio. Assim, o teste não depende de uma cópia da ROM nem dos arquivos de jogo extraídos no diretório atual. Nenhuma ROM é fornecida e gameplay não é testado. A confirmação real depende de abrir o executável a partir de `build_linux/pokeplatinum`, selecionar a ROM local USA Rev. 1 na primeira abertura e confirmar a tela inicial. O teste pré-ROM não substitui essa etapa.


Depois de compilar, o verificador compara todos os caminhos do manifesto upstream `platinum.us/filesys.csv` com os arquivos de origem produzidos pelo build e os arquivos copiados para a pasta runtime. Ele detecta arquivos ausentes, cópias com tamanho/hash divergente e os arquivos de animação obrigatórios:

    python3 scripts/verify_native_package.py \
      --build-dir vendor/pokeplatinum-native/build_linux \
      --package-dir vendor/pokeplatinum-native/build_linux/pokeplatinum \
      --filesys-csv vendor/pokeplatinum-native/platinum.us/filesys.csv

Em seguida, para conferir os arquivos extraídos da ROM local:

    python3 tools/check_runtime_data.py --runtime-dir vendor/pokeplatinum-native/build_linux/pokeplatinum

Essas verificações validam a integridade dos arquivos do pacote, mas não substituem o teste de inicialização e gameplay.

Uma compilação bem-sucedida não prova que o jogo inicia. O extrator nativo grava os arquivos no diretório de trabalho atual. Execute `main`/`main.exe` a partir de `build_linux/pokeplatinum` ou `build_win64/pokeplatinum`, selecione a sua cópia original USA Rev. 1 e confirme inicialização, tela inicial, áudio, entrada e criação dos arquivos de dados.

Depois que o porte extrair os dados, feche o jogo e valide o diretório local:

    python3 tools/check_runtime_data.py --runtime-dir vendor/pokeplatinum-native/build_linux/pokeplatinum

Para exigir também os sete NARC da versão PT-BR de referência após a importação (estrutura NARC e SHA-256 correspondentes):

    python3 tools/check_runtime_data.py --runtime-dir vendor/pokeplatinum-native/build_linux/pokeplatinum --require-localized-resources

O verificador apenas confirma a presença e a estrutura básica dos arquivos; não inicia o jogo nem comprova que ele é jogável. O importador aceita somente os sete hashes definidos em `tools/localization_manifest.py` e valida todos antes da primeira escrita. Depois disso, use o importador para substituir localmente os sete recursos NARC allowlisted.

Não copie ROMs, bancos NARC extraídos, saves ou outros recursos derivados para o Git. Os workflows não publicam executáveis nem conteúdo do jogo. Consulte o [aviso legal](LEGAL.md) antes de distribuir qualquer binário.
