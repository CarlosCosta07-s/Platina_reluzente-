# Platina Reluzente Launcher

Launcher experimental para o porte nativo comunitário de Pokémon Platinum.

## Windows e Linux

Os scripts de empacotamento desktop podem ser usados localmente quando você tiver compilado o runtime nativo. Coloque os arquivos do runtime da sua compilação em `launcher-app/runtime`, incluindo o executável `main` (Linux) ou `main.exe` (Windows) e os recursos exigidos pelo launcher. Em seguida, dentro de `launcher-app`, execute `npm install` e use `npm run build:linux` ou `npm run build:windows`.

O launcher não pede para selecionar um executável separado: ele procura o binário incluído no pacote. A ROM é validada e armazenada no diretório privado do aplicativo. Esta versão do importador desktop aceita somente a ROM limpa Pokémon Platinum USA Rev. 1 (código `CPUE`, byte de versão `1` e SHA-1 integral conhecido); a USA Rev. 0 é recusada, pois o runtime nativo atual não foi validado para essa revisão. A localização PT-BR é uma etapa independente e ainda experimental.

## Dados e distribuição

A CI compila e valida código, mas não publica pacotes completos ou runtime de jogo para download. Não faça commit de ROMs, recursos NARC, firmware, saves, runtimes compilados ou pacotes que contenham dados derivados do jogo. Mantenha esses arquivos no ambiente local e consulte `docs/LEGAL.md` antes de distribuir qualquer compilação.

O launcher permanece experimental até que inicialização, entrada, áudio, gráficos e salvamentos tenham sido validados em Windows e Linux.
