# Porte móvel (Android e iOS) — arquitetura e execução por gates

**Estado atual:** desenvolvimento reaberto em modo source-only. O projeto pode avançar com arquitetura, código compartilhado, shells de plataforma como fonte, testes ROM-free e provas gráficas em host. **Nenhuma compilação de alvo Android/iOS, APK, AAB ou IPA será feita até existir paridade funcional 1:1 com o Desktop.** O contrato vinculante está em [MOBILE_PARITY_CONTRACT.md](MOBILE_PARITY_CONTRACT.md). A auditoria atual do renderer está em [MOBILE_RENDERER_AUDIT.md](MOBILE_RENDERER_AUDIT.md).

O Desktop continua sendo a referência de funcionalidades e comportamento. O mantenedor informou que Windows x64 e Linux x86-64 compilaram; a validação manual com ROM ainda depende de acesso a um PC. Não considerar uma build ou smoke test sem ROM como prova de gameplay.

O escopo desta trilha é Pokémon Platinum USA Rev. 1. Pokémon Black continua bloqueado para mobile até que a situação jurídica do código reconstruído e sua distribuição esteja resolvida.

## Meta

Paridade com o desktop: importar a ROM USA Rev. 1, preparar os dados localmente, jogar Platinum, salvar e retomar, trocar idioma (English / PT-BR) e ver logs de diagnóstico. Black segue o mesmo caminho só depois de resolvido o bloqueio jurídico de `aletheia/src/`.

## Bloqueios técnicos (verificados no código fixado)

1. **Renderizador desktop-only.** Os shaders do `libntr` declaram `#version 420 core`, o contexto pede OpenGL 4.2 core, o carregador é o glad desktop e há uso de `GL_DEBUG_OUTPUT`. Android oferece no máximo OpenGL ES 3.2; iOS não tem OpenGL desktop (OpenGL ES está obsoleto e o caminho recomendado é Metal). É preciso um backend novo ou uma camada de tradução, e o resultado precisa ser comparado quadro a quadro com o desktop.
2. **O launcher é Electron.** Não roda em Android/iOS. Precisa de um app novo (Kotlin/Compose, Swift/SwiftUI ou framework multiplataforma) que reproduza o fluxo: importar ROM, validar SHA-1/SHA-256, preparar dados com progresso, iniciar, ler logs.
3. **Biblioteca e processo.** O jogo hoje é um executável `main`/`main.exe` iniciado como processo filho. Em mobile ele vira uma biblioteca nativa carregada pelo app (SDL2 tem modelos de projeto para as duas plataformas), com `main` renomeado e ciclo de vida tratado (pausa, retomada, encerramento pelo sistema).
4. **Armazenamento da ROM e dos dados.** Android: Storage Access Framework (sem caminho de arquivo direto) e diretório privado do app. iOS: seletor de documentos e sandbox. O extrator e o `FS_OpenFile` assumem caminhos relativos ao diretório de trabalho; é preciso fixar o diretório de trabalho na pasta privada.
5. **Entrada.** O jogo mapeia teclado, joystick e mouse para a tela de toque do DS. Em mobile falta um overlay de botões na tela, suporte a controle Bluetooth e mapeamento de toque em duas telas.
6. **Desempenho, memória e energia.** Nunca medidos em dispositivo. O preparo de dados (extração + CRC) e o boot precisam de medição e de limites de memória.
7. **Save e ciclo de vida.** O sistema pode matar o app a qualquer momento. O save precisa ser gravado de forma atômica e fora da pasta do runtime. O `exit(0)` ao fechar a janela no desktop é um risco conhecido.
8. **Toolchains.** O build atual é Meson + Make + MSYS2/Docker para Windows e Linux. Android exige NDK (ARM64) e iOS exige Xcode em macOS (builders da CI com macOS). As dependências (SDL2, ENet, libpng) precisam de builds móveis.

## Distribuição e questões jurídicas

- A importação da ROM do próprio usuário e a ausência de dados protegidos no pacote continuam obrigatórias.
- **iOS:** a aprovação na App Store continua incerta e não deve ser presumida. TestFlight é somente beta: cada build fica disponível por até 90 dias. Ad Hoc exige dispositivos registrados. O Apple Developer Program custa atualmente US$ 99/ano, com preço local e impostos variáveis.
- **Brasil:** desde iOS 26.5, a Apple documenta distribuição de apps por marketplaces alternativos no Brasil, desde que o app esteja devidamente autenticado/notarizado e o marketplace seja elegível. Isso não é instalação livre de um IPA por URL. Operar o próprio marketplace exige conta de organização, entitlement e aprovação da Apple; não será presumido como o caminho deste projeto.
- A diretriz Apple 4.7 descreve mini apps e emuladores. Este projeto mantém o núcleo C/C++ nativo e não usa emulador de DS; isso não garante aprovação nem resolve direitos autorais, marcas, licenças ou políticas de conteúdo. A classificação final depende da análise da Apple.
- **Android:** distribuição por APK/AAB fora da Play Store é uma opção técnica; distribuir pela Play Store exige uma análise separada de suas políticas.
- Esta documentação não é aconselhamento jurídico; é necessária revisão por advogado.

## Marcos source-only e gate de compilação

1. **Renderer portátil:** variantes GLSL ES 3.00 separadas, wrappers de API GL e emulação verificada das capacidades ausentes; provas de compilação/link e comparação de pixels no host. A [auditoria do renderer](MOBILE_RENDERER_AUDIT.md) descreve o estado atual.
2. **Núcleo compartilhado:** API C/C++ de ciclo de vida, serviços de armazenamento e diagnóstico injetáveis, sem depender de caminhos herdados do Desktop.
3. **Serviços móveis:** código-fonte Kotlin/Compose e Swift/SwiftUI para importação, sandbox, lifecycle, controles, áudio, idioma, progresso e logs.
4. **Paridade completa:** cada linha de MOBILE_PARITY_CONTRACT.md implementada e coberta por testes ROM-free; revisão de segurança, licenças, privacidade e preservação de saves.
5. **Gate de compilação móvel:** somente depois da paridade 1:1 aprovada, autorizar builds Android ARM64 e iOS/Xcode. A primeira compilação será uma fase de validação de plataforma, não evidência automática de paridade final.
6. **Validação em aparelhos:** testar em aparelhos reais, corrigir divergências e só depois considerar os alvos móveis estáveis.

Cada marco só é concluído com evidência reproduzível, como no restante do projeto.
