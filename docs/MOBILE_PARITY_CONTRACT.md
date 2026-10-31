# Contrato de paridade — Android e iOS

**Estado:** desenvolvimento móvel reaberto em modo source-only. A implementação de arquitetura, APIs compartilhadas, testes de contrato e provas gráficas em host está autorizada. **Builds de aplicação Android/iOS estão bloqueados** até que a matriz de paridade deste documento esteja integralmente implementada e aprovada.

**Escopo:** Pokémon Platinum USA Rev. 1. Pokémon Black permanece fora do runtime móvel e não pode ser ativado enquanto a análise jurídica da distribuição do código reconstruído não for concluída.

## 1. Regra de compilação

Não executar builds de alvo Android ou iOS, não gerar APK, AAB ou IPA, não publicar artefatos móveis e não adicionar workflows que compilem esses alvos antes do gate de paridade.

É permitido durante esta etapa:
- editar código C/C++ compartilhado e adaptadores de plataforma;
- preparar os projetos Kotlin/Compose e Swift/SwiftUI como código-fonte, sem compilar os alvos móveis;
- executar testes ROM-free de contratos e armazenamento no host;
- validar shaders e renderizar cenas sintéticas em host desktop (Mesa/EGL/ANGLE), desde que isso não gere uma aplicação Android/iOS;
- comparar imagens sintéticas com o renderer desktop de referência.

A primeira compilação Android/iOS só será autorizada quando **todas** as capacidades da matriz abaixo estiverem implementadas e passarem por testes reproduzíveis, sem stubs que simulem sucesso. Essa autorização apenas inicia a validação de plataforma; não declara paridade concluída em hardware.

## 2. Arquitetura obrigatória

O jogo continua sendo o código C/C++ nativo já usado pelo porte desktop. Não introduzir emulador de DS, intérprete ARM, Unity ou Godot.

- **Núcleo compartilhado:** C/C++ com API C estável para criar, iniciar, pausar, retomar, solicitar encerramento, consultar estado e destruir uma sessão.
- **Android:** shell Kotlin/Jetpack Compose; ponte JNI para o núcleo; Storage Access Framework para seleção; cópia privada transacional; SDL2 para a superfície, áudio e entrada do runtime quando compatível com o ciclo de vida Android.
- **iOS:** shell Swift/SwiftUI; ponte C/Objective-C++; Document Picker e acesso coordenado à URL; cópia para Application Support; camada gráfica validada para Metal.
- **Serviços de host:** adaptadores explícitos para caminhos privados, relógio, arquivos, armazenamento, progresso, logs, áudio, controles e ciclo de vida. O núcleo não deve depender de caminhos arbitrários herdados do processo.
- **Renderer:** contrato mínimo GLES 3.0 / GLSL ES 3.00 como primeira hipótese comum. Android usa GLES nativo. Para iOS, avaliar ANGLE sobre Metal; não depender de OpenGL ES legado da Apple. Se a prova de equivalência falhar, avaliar um backend Metal próprio antes de continuar.
- **Desktop permanece referência:** preservar o renderer GL 4.2 e o comportamento Desktop; não substituir a implementação atual por uma abstração mais fraca só para atender ao mobile.

A escolha de shells nativos separados mantém o acesso às APIs específicas de armazenamento, ciclo de vida, controles e diagnósticos sem duplicar a lógica do jogo.

## 3. Matriz obrigatória de paridade

| Capacidade do Desktop | Equivalente móvel obrigatório | Evidência mínima antes do primeiro build móvel |
|---|---|---|
| Biblioteca e seleção de jogo | Tela da biblioteca com Platinum disponível e Black explicitamente bloqueado | Testes de estado/visibilidade e de bloqueio do runtime Black |
| Importar/trocar ROM | Seletor SAF/Document Picker; cópia privada; recuperação de importação interrompida | Testes com arquivos sintéticos, falhas de cópia e rollback |
| Identidade da ROM | Mesmas verificações de tamanho, cabeçalho, código CPUE, revisão 1 e SHA-1 aprovado; SHA-256 local | Vetores sintéticos válidos/inválidos e rejeição da revisão errada |
| Integridade do runtime | Manifesto, hashes, build ID, rejeição de links/arquivos inesperados e atualização segura | Testes ROM-free para manifesto adulterado, arquivo ausente e atualização |
| Preparação dos dados | Extração para diretório privado, manifesto de caminhos, validação CRC/tamanho, staging, promoção e recuperação | Testes de interrupção, cache incompatível e preservação de dados locais |
| Progresso de primeira execução | Estados claros para importação, extração, validação, inicialização e primeiro frame | Testes de sequência, erro, cancelamento e retomada do estado |
| Renderer e duas telas | Mesma ordem, proporção, composição, transparência, prioridades, brilho, fog e resultado visual; layout móvel adaptável sem mudar o conteúdo | Comparador de pixels GL 4.2 × GLES 3.0 para cenas sintéticas; ANGLE/Metal precisa passar pela mesma suíte |
| Controles | Todos os comandos aceitos pelo Desktop; overlay tátil D-pad/A/B/X/Y/L/R/Start/Select, toque na tela inferior e controles Bluetooth/USB/teclado físico | Testes de mapeamento, repetição, foco, desconexão e toque |
| Áudio | Mesmos eventos/canais e comportamento de pausa/retomada, usando saída do dispositivo | Testes de inicialização, perda/retorno de dispositivo e silêncio de fallback |
| Saves | Mesmo formato e semântica de save.bin; escrita atômica, flush, backup e recuperação; nunca apagar save em atualização | Testes de interrupção durante escrita, restauração e round-trip sintético |
| Configurações | Persistir idioma e preferências equivalentes a sim_config.ini; não sobrescrever valores do usuário | Testes de leitura, migração, corrupção e preservação |
| English / PT-BR | Mesma seleção; pacote PT-BR importado e validado por manifesto/hash; falha não pode trocar idioma silenciosamente | Testes de sete recursos autorizados, hashes errados, pacote incompleto e idioma selecionado |
| Inicialização e encerramento | Núcleo em processo, sem exit(0) encerrar o shell; lifecycle pause/resume/shutdown e recriação do contexto gráfico | Testes de chamadas repetidas, pausa, perda de superfície e shutdown |
| Diagnóstico | Log privado equivalente a native-startup.log, progresso, erro legível e cópia/compartilhamento do log | Testes de rotação/abertura, falha de escrita e remoção de dados sensíveis |
| Privacidade | ROM, dados extraídos, saves e pacotes locais ficam no sandbox; nada disso entra em GitHub/CI | Inspeção de pacote e testes de staging sem dados do jogo |

A paridade funcional não exige que a interface do launcher seja visualmente idêntica à janela desktop. Ela exige que os mesmos fluxos, opções, estados, informações, resultados e ações estejam disponíveis. Os controles táteis e adaptações de orientação são equivalentes de interação, não redução de funcionalidades.

## 4. Prova gráfica — primeiro gate técnico

O renderer atual foi escrito para OpenGL 4.2 Core: usa GLAD desktop, GLSL #version 420 core, funções glProgramUniform*, debug output e GL_CLAMP_TO_BORDER. Uma simples troca de versão de shader não resolve essas diferenças.

A primeira etapa técnica deve:
1. Criar arquivos de shader ES separados e um patch versionado para o commit fixado de libntr; nunca substituir o renderer desktop.
2. Resolver a seleção de samplers do G2 com índices literais/ramificações constantes. Não usar índice por fragmento em arrays de samplers.
3. Substituir chamadas glProgramUniform* por wrappers compatíveis com GLES 3.0, preservando o programa ativo e o estado GL.
4. Emular semântica de clamp-to-border no shader; não usar GL_CLAMP_TO_EDGE como substituição silenciosa.
5. Tratar debug output como capacidade opcional.
6. Criar cenas sintéticas ROM-free para BGs/prioridades, OBJ/windows, alpha, master brightness, backdrop, texturas 3D, fog, repeat/mirror/clamp e coordenadas na borda.
7. Renderizar exatamente os mesmos casos no desktop GL 4.2 e no GLES 3.0 em host, ler os pixels e comparar. Qualquer tolerância deve ser documentada por canal e por limite de pixels divergentes.
8. Executar a mesma suíte no ANGLE/Metal antes de considerar a rota iOS aprovada.

Não copiar o antigo script experimental de substituição textual como arquitetura final. Patches e variantes gráficas devem ser arquivos versionados, revisáveis e testáveis.

## 5. Sequência de implementação (source-only)

### Fase 0 — contrato e baseline
- [x] Inspecionar os fluxos atuais de ROM, runtime, preparação, idioma, logs e ciclo de processo no Desktop.
- [x] Registrar a matriz de paridade e a proibição de builds móveis antecipados.
- [ ] Converter cada linha da matriz em testes de contrato compartilhados.
- [ ] Registrar os resultados de gameplay Desktop com ROM quando o mantenedor voltar a ter acesso a um PC. A compilação, por si só, não substitui essa validação.

### Fase 1 — renderer portátil
- [ ] Fechar o inventário de todos os usos GL no commit fixado de libntr.
- [x] Criar quatro variantes GLSL ES 3.00 separadas; testes ROM-free confirmam que os sampler arrays do G2 usam somente índices literais.
- [x] Compilar e linkar os programas G2 e G3 com glslangValidator em Linux host-only (workflow 41149162996).
- [x] Preparar helper GLES source-only para as quatro chamadas glProgramUniform, com teste C++ host usando GLES mock para verificar restauração de GL_CURRENT_PROGRAM.
- [ ] Integrar as variantes e o helper ao commit fixado; ligar uniforms clamp-to-border e preservar o estado no desenho normal e deferred.
- [ ] Criar o comparador sintético GL 4.2 × GLES 3.0 em host.
- [ ] Aprovar ANGLE/Metal pelo mesmo comparador.
- **Gate:** não avançar se houver discrepância visual sem explicação e limite aceito.

### Fase 2 — núcleo C/C++ como biblioteca
- [ ] Projetar a API C de lifecycle e estados.
- [ ] Remover encerramento global do processo e tornar a saída cooperativa.
- [ ] Injetar serviços de arquivos/caminhos/diagnósticos.
- [ ] Separar explicitamente diretórios de ROM, extração, saves, configurações, localização e logs.
- [ ] Testar em host todas as transições e erros sem ROM.

### Fase 3 — serviços móveis e shells
- [ ] Implementar camada Android para SAF, armazenamento privado, JNI, lifecycle e controles.
- [ ] Implementar camada iOS para Document Picker, security-scoped URLs, Application Support, lifecycle e ponte C.
- [ ] Implementar interface nativa de biblioteca, importação, idioma, progresso, diagnóstico e controles.
- [ ] Não adicionar tarefas de build Android/iOS nesta fase.

### Fase 4 — paridade de ponta a ponta
- [ ] Completar todas as linhas da matriz com testes e evidências.
- [ ] Verificar atualização de runtime sem perder saves/configuração.
- [ ] Verificar pausa/retomada e recuperação após encerramento pelo sistema.
- [ ] Verificar PT-BR e English e os dois layouts de tela.
- [ ] Revisar segurança, privacidade, licenças e conteúdo do pacote.

### Fase 5 — autorização para compilar
- [ ] Conferir que a matriz está 100% implementada e todos os testes host-side passam.
- [ ] Fazer revisão final do diff, dependências, toolchains e riscos jurídicos.
- [ ] Só então liberar builds Android ARM64 e iOS/Xcode, em workflows separados dos workflows Desktop.
- [ ] Depois do primeiro build autorizado, testar em aparelhos reais e corrigir divergências antes de chamar qualquer plataforma de paritária.

## 6. Restrições permanentes

- Trabalhar diretamente na branch main; não criar branches.
- Não alterar os workflows Desktop para acomodar a trilha móvel.
- Não incluir ROM, firmware, NARC extraído, save, dump ou pacote PT-BR nos artefatos.
- Fixar commits e hashes de todas as dependências nativas.
- Android deve validar alinhamento ELF de 16 KiB em **todas** as bibliotecas compartilhadas, inclusive pré-compiladas; NDK r28+ e dependências compatíveis são requisito de entrada, não prova final.
- Preservar alocadores e regras de memória do projeto; não trocar PPW_Allocator por allocator padrão sem demonstrar equivalência.
- Não tratar compilação, aceitação de shaders ou janela vazia como prova de gameplay.
- Não declarar paridade até haver evidência de todas as capacidades e testes em dispositivos reais.

## 7. Referências técnicas oficiais

- [Android — suporte a páginas de memória de 16 KB](https://developer.android.com/guide/practices/page-sizes)
- [Android — ciclo de vida de Activity](https://developer.android.com/guide/components/activities/activity-lifecycle)
- [SDL — plataformas oficialmente suportadas](https://github.com/libsdl-org/SDL)
- [ANGLE — matriz de suporte OpenGL ES / Metal / iOS](https://github.com/google/angle)
- [Apple — OpenGL ES deprecated e migração para Metal](https://developer.apple.com/documentation/metal/migrating-opengl-code-to-metal)

A auditoria do renderer fixado, as variantes GLSL ES 3.00 e os bloqueios de integração estão em [MOBILE_RENDERER_AUDIT.md](MOBILE_RENDERER_AUDIT.md). A auditoria MOBILE_PORT_AUDIT.md é o registro histórico das falhas e hipóteses avaliadas antes da reativação.
