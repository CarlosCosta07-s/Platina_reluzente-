# Platina Reluzente Launcher

Launcher multiplataforma de teste para o projeto **Platina Reluzente**. A interface segue o conceito de biblioteca de jogos do New Horizons Recomp sem copiar seu código-fonte.

## Builds de teste

O workflow de GitHub Actions gera:
- **Windows x64:** executável portátil `.exe` do launcher.
- **Linux x86-64:** AppImage e arquivo `.tar.gz` do launcher.
- **Android:** APK de depuração do launcher, assinado com a chave de depuração do Android.

Os artefatos ficam na aba **Actions**, na execução do workflow **Launcher packages for manual testing**.

## Como testar

No desktop, abra o launcher, selecione o executável do porte nativo (extraído do artefato `platina-reluzente-windows-x64` ou `platina-reluzente-linux-x86_64`) e clique em **Iniciar jogo**. O processo é iniciado na pasta do executável para preservar os caminhos relativos dos recursos.

Você também pode selecionar uma ROM `.nds` para conferir que o seletor local funciona. A ROM permanece no dispositivo: não é enviada para o GitHub nem incluída nos artefatos. **A seleção da ROM ainda não extrai nem importa seus dados para o motor do jogo.** A integração do lançador com a preparação de dados está pendente.

No Android, o APK permite testar manualmente a interface e o seletor de ROM. O motor de jogo ainda requer um porte gráfico para Android/OpenGL ES, portanto o botão de iniciar jogo fica indisponível nessa plataforma. Este APK é um **launcher para teste**, não uma versão jogável do Pokémon Platinum para Android.

Os builds são artefatos de CI com retenção temporária; não são releases permanentes. Não incluem ROM, firmware, nem recursos extraídos de ROM fornecida pelo usuário.
