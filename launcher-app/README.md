# Platina Reluzente Launcher

Launcher multiplataforma para o porte nativo comunitário de Pokémon Platinum.

## Windows e Linux

O pacote desktop completo inclui o executável nativo e os recursos do jogo. Abra o launcher, importe sua ROM \`.nds\` e use **Iniciar jogo**. Não é necessário localizar ou selecionar um executável separado. A ROM é validada e guardada no armazenamento privado; o motor nativo usa o caminho importado para ler o cabeçalho.

## Android

O APK integrado reúne a interface, o importador de ROM, o runtime nativo ARM64, SDL2 e os recursos do jogo. Importe sua ROM \`.nds\`; ao tocar em **Iniciar jogo**, o aplicativo valida a ROM, prepara os recursos no armazenamento privado e abre a atividade SDL incluída no mesmo APK. Não é necessário instalar um segundo APK nem selecionar um executável.

O empacotamento combinado só é liberado quando Windows, Linux e Android passam no mesmo commit. O runtime Android exige ARM64 e Android API 24 ou superior. A compilação do APK não substitui o teste em dispositivo real: execução gráfica, toque, áudio e salvamentos ainda precisam de validação em aparelho.

A ROM permanece local e não é incluída nos artefatos. Use apenas arquivos que você tenha direito de utilizar. Os artefatos de CI expiram após 14 dias.
