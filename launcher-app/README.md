# Platina Reluzente Launcher

Launcher experimental para o porte nativo comunitário de Pokémon Platinum.

## Windows e Linux

Compile primeiro o alvo nativo na raiz do repositório:
- Linux: `./scripts/build-native.sh linux`
- Windows (PowerShell): `.\\scripts\\build-native.ps1`

Depois, em `launcher-app`, execute `npm install` e:
- Linux: `npm run build:linux`
- Windows: `npm run build:windows`

Esses comandos preparam automaticamente o runtime nativo e o incluem no launcher, sem pedir ao usuário para localizar um executável. O pacote contém somente a AppImage nativa portátil no Linux ou `main.exe` e DLLs no Windows. Firmware, arquivos NARC e demais recursos do jogo são excluídos; o primeiro início usa a ROM importada para extrair os arquivos necessários no diretório privado e gravável do usuário. O staging recusa links simbólicos e arquivos ROM/patch, e a pasta `launcher-app/runtime` fica ignorada pelo Git.

O launcher não pede para selecionar um executável separado: ele procura o binário incluído no pacote. A ROM é validada e armazenada no diretório privado do aplicativo. Esta versão do importador desktop aceita somente a ROM limpa Pokémon Platinum USA Rev. 1 (código `CPUE`, byte de versão `1` e SHA-1 integral conhecido); a USA Rev. 0 é recusada, pois o runtime nativo atual não foi validado para essa revisão. A localização PT-BR é uma etapa independente e ainda experimental.

## Dados e distribuição

A CI publica artefatos temporários de teste: os binários do runtime nativo e, após a etapa de empacotamento integrado, os launchers desktop. Eles não devem conter ROMs, firmware, recursos NARC, saves ou outros dados extraídos do jogo. Não faça commit desses arquivos; mantenha ROM e recursos extraídos no ambiente local e consulte `docs/LEGAL.md` antes de distribuir qualquer compilação.

O launcher permanece experimental até que inicialização, entrada, áudio, gráficos e salvamentos tenham sido validados em Windows e Linux.
