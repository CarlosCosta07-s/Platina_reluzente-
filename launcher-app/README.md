# Platina Reluzente Launcher

Launcher multiplataforma para o porte nativo comunitário de Pokémon Platinum.

## Uso no PC

O launcher desktop inclui o executável nativo e os recursos no próprio pacote. Abra o launcher, importe sua ROM \`.nds\` e use **Iniciar jogo**; não é necessário selecionar um executável separado. A ROM é validada e copiada para o armazenamento privado do aplicativo.

## Uso no Android

O APK importador salva a ROM \`.nds\` no armazenamento privado do aplicativo e valida seu cabeçalho. A ponte de execução do motor SDL/NDK a partir da interface Capacitor ainda está em desenvolvimento, então o APK importador não deve ser tratado como uma versão jogável completa. O APK experimental nativo é distribuído no mesmo conjunto de artefatos quando a compilação Android passa.

O pacote completo é gerado apenas quando Windows, Linux e Android passam no mesmo commit. Os artefatos de CI expiram após 14 dias. A ROM permanece local; use somente arquivos que você tenha direito de utilizar.
