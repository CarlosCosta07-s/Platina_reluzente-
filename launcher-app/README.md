# Platina Reluzente Launcher

Launcher experimental para o porte nativo comunitário de Pokémon Platinum.

## Windows e Linux

Os scripts de empacotamento desktop podem ser usados localmente quando você tiver compilado o runtime nativo. Coloque os arquivos do runtime da sua compilação em `launcher-app/runtime`, incluindo o executável `main` (Linux) ou `main.exe` (Windows) e os recursos exigidos pelo launcher. Em seguida, dentro de `launcher-app`, execute `npm install` e use `npm run build:linux` ou `npm run build:windows`.

O launcher não pede para selecionar um executável separado: ele procura o binário incluído no pacote. A ROM é validada e armazenada no diretório privado do aplicativo. Esta versão do importador desktop aceita Pokémon Platinum USA Rev. 1 (código `CPUE`, byte de versão `1`); a localização PT-BR é uma etapa independente.

## Android

A integração Android NDK/SDL2 é experimental. O APK local exige a biblioteca nativa ARM64, o código Java do SDL e o conjunto completo de recursos do runtime, preparados de acordo com os passos em `android/scripts` e `.github/workflows/android-native-cross-build.yml`. A simples compilação da biblioteca `libmain.so` não equivale a um APK integrado nem prova que o jogo inicializa num telefone.

## Dados e distribuição

A CI compila e valida código, mas não publica pacotes completos ou runtime de jogo para download. Não faça commit de ROMs, recursos NARC, firmware, saves, runtimes compilados ou pacotes que contenham dados derivados do jogo. Mantenha esses arquivos no ambiente local e consulte `docs/LEGAL.md` antes de distribuir qualquer compilação.

O launcher permanece experimental até que inicialização, controles, áudio, gráficos, salvamentos e retomada tenham sido validados em dispositivos reais.
