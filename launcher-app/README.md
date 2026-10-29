# Platina Reluzente Launcher

Launcher experimental para o porte nativo comunitário de Pokémon Platinum.

## Windows e Linux

Compile primeiro o alvo nativo na raiz do repositório:
- Linux: `./scripts/build-native.sh linux`
- Windows (PowerShell): `.\\scripts\\build-native.ps1`

Depois, em `launcher-app`, execute `npm install` e:
- Linux: `npm run build:linux`
- Windows: `npm run build:windows`

Esses comandos agora preparam automaticamente o runtime do build local (`vendor/pokeplatinum-native/build_linux/pokeplatinum` ou `build_win64/pokeplatinum`) e o incluem no pacote do launcher. Não é necessário copiar os arquivos manualmente nem escolher um executável na interface. O staging verifica executável e recursos obrigatórios, recusa links simbólicos e arquivos ROM/patch e exclui saves e configurações locais. A pasta `launcher-app/runtime` é gerada localmente e fica ignorada pelo Git.

O launcher não pede para selecionar um executável separado: ele procura o binário incluído no pacote. A ROM é validada e armazenada no diretório privado do aplicativo. Esta versão do importador desktop aceita somente a ROM limpa Pokémon Platinum USA Rev. 1 (código `CPUE`, byte de versão `1` e SHA-1 integral conhecido); a USA Rev. 0 é recusada, pois o runtime nativo atual não foi validado para essa revisão. A localização PT-BR é uma etapa independente e ainda experimental.

## Dados e distribuição

A CI compila e valida código, mas não publica pacotes completos ou runtime de jogo para download. Não faça commit de ROMs, recursos NARC, firmware, saves, runtimes compilados ou pacotes que contenham dados derivados do jogo. Mantenha esses arquivos no ambiente local e consulte `docs/LEGAL.md` antes de distribuir qualquer compilação.

O launcher permanece experimental até que inicialização, entrada, áudio, gráficos e salvamentos tenham sido validados em Windows e Linux.
