# Android port — experimental native ARM64 path

O projeto tem três verificações separadas para Android:

1. **Preparação gráfica GLES 3.2** — adapta as fontes do renderizador e valida os quatro shaders com `glslangValidator`. Essa etapa não compila o jogo.
2. **Android native ARM64 cross-build** — usa o Android NDK para compilar `libmain.so` e SDL2, verifica o símbolo `SDL_main`, a compatibilidade de alinhamento de páginas de 16 KB e os recursos nativos do runtime. O pacote de dados é comparado com `platinum.us/filesys.csv` e validado para detectar arquivos ausentes ou divergentes.
3. **Launcher packages** — combina a biblioteca ARM64, SDLActivity, recursos do jogo e o importador de ROM em um único APK de teste. O APK não inclui a ROM pessoal do usuário.

Uma compilação e a verificação do APK comprovam apenas a integridade do artefato. Ainda é necessário testar em um aparelho Android real: abertura da SDLActivity, leitura da ROM importada, tela de título, renderização GLES, toque/controles, áudio, ciclo de vida e gravações. Portanto, o porte Android permanece **experimental** até que esses testes sejam reproduzíveis.

O código específico de Android fica isolado por `SDK_BUILD_ANDROID` e não substitui o backend OpenGL 4.2 usado no desktop. Os builds devem continuar fixando as revisões upstream e falhar com mensagens claras quando uma dependência ou marcador esperado estiver ausente.
