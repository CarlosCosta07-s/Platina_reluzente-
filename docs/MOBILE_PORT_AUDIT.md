# Auditoria de viabilidade móvel — 30/10/2026

Este documento registra a verificação inicial exigida antes de reativar Android/iOS. Ele complementa [MOBILE_PORT.md](MOBILE_PORT.md), [GEN1RECOMP_REFERENCE.md](GEN1RECOMP_REFERENCE.md), [PORTING_ARCHITECTURE.md](PORTING_ARCHITECTURE.md) e [TROUBLESHOOTING.md](TROUBLESHOOTING.md).

**Escopo desta auditoria:** Pokémon Platinum apenas. Black continua desativado até existir autorização clara para redistribuir `aletheia/src/`. Nenhuma ROM, firmware, arquivo NARC extraído, save ou recurso derivado foi usado, adicionado ou enviado à CI.

## 1. Resultado executivo

- **Passo 0:** encontrado um fixture de teste desatualizado em `tools/tests/test_prepare_native_runtime.py`. A fixture não correspondia ao arquivo upstream fixado `35067868f64f23d25d17ac3e536cfdd9a7f40523`. Foi atualizada em `af2970db602eac6998401e577f3fd90a29db7d0a`; o patcher de produção não foi afrouxado. A CI desse commit ainda estava pendente durante esta auditoria. Portanto, a correção está commitada, mas **a aprovação do Passo 0 ainda não está confirmada**.
- **Windows/Linux:** a execução verde mais recente encontrada foi [run 41130771002](https://github.com/CarlosCosta07-s/Platina_reluzente-/actions/runs/41130771002). Na execução posterior [run 41140404682](https://github.com/CarlosCosta07-s/Platina_reluzente-/actions/runs/41140404682), os jobs avançaram por compilação nativa e verificação dos pacotes, mas os testes do launcher falharam ao esperar por fragmentos de log durante o teste de processo único. Isso não é evidência de falha do compilador C/C++.
- **Android:** as falhas ARM64 antigas foram classificadas em duas causas distintas. A primeira foi uma verificação ELF de alinhamento de 16 KiB em `libc++_shared.so` do NDK 28.2, depois que `libmain.so` havia sido compilada. A troca para NDK 30 ultrapassou esse bloqueio, mas encontrou um erro C++ em `PPW_Allocator` ao instanciar `std::map` em `dwci_lobbydata.cpp:118`. Nenhum APK integrado foi validado.
- **Renderizador:** o código sugere que um backend GLES 3.0 pode ser viável sem reescrever o renderer em Metal. Ainda não há protótipo de renderer executado nem comparação de pixels. A decisão fica **condicional** até a paridade sintética quadro a quadro.
- **iOS:** não existe alvo iOS ativo, build Xcode, framework ou teste em aparelho. A rota de menor custo a investigar é manter um contrato GLES 3.0 comum e testar ANGLE sobre Metal; backend Metal próprio é a alternativa de contingência, não a primeira escolha.

## 2. Passo 0 — fixtures, CI e causa Android

### 2.1 Fixture de configuração

O teste construía `UPSTREAM_PROJECT_SIM_CONFIG` com quatro espaços antes de `if(!SIM_Config_prj_LoadConfigFile...)`, enquanto o upstream pinado usa dois. O marcador literal de fallback existia uma vez no upstream e zero vezes na fixture. Como `_prepare_project_sim_config` valida marcadores exatos por segurança, a fixture fazia a preparação parar antes de chegar aos outros casos de teste.

Correção aplicada: substituir a fixture pela versão exata de `src/port/sim_config_prj.c` da revisão upstream pinada. Não foi alterada a regra de correspondência estrita do patcher.

**Evidência:** [commit af2970d](https://github.com/CarlosCosta07-s/Platina_reluzente-/commit/af2970db602eac6998401e577f3fd90a29db7d0a). A execução `Native desktop build and localization checks` para esse commit estava pendente; não tratar como teste aprovado até o job terminar.

### 2.2 Histórico do Android ARM64

1. **NDK 28.2.13676358:** SDL2 e `libmain.so` chegaram a compilar. A etapa de verificação ELF parou por falta de alinhamento de 16 KiB no segmento GNU_RELRO da `libc++_shared.so` distribuída com esse NDK. Foi uma falha na biblioteca C++ do toolchain, não no renderer nem no código do jogo.
   - [Execução histórica 40873587183](https://github.com/CarlosCosta07-s/Platina_reluzente-/actions/runs/40873587183).
2. **NDK 30.0.16248370:** a compilação foi mais longe, mas parou em `lib/ppwlobby/libraries/ilobby/src/dwci_lobbydata.cpp:118`, na expressão `unk_70[v0] = param0`. O erro de libc++ foi `static_cast from 'const int *' to 'void *' is not allowed`, durante a construção da chave `const int` do mapa.
   - A origem está no alocador customizado `PPW_Allocator` de `lib/ppwlobby/include/ilobby/dwci_lobbybase.h`: ele implementa apenas `construct(pointer, const T&)`, mas não o overload genérico necessário quando `allocator_traits` constrói o subobjeto `const int` da árvore de `std::map`.
   - [Execução histórica 40874776721](https://github.com/CarlosCosta07-s/Platina_reluzente-/actions/runs/40874776721).

**Correção futura requerida:** preservar a alocação pelo heap DWC e acrescentar um caminho C++03 correto de construção para o tipo solicitado pelo container (incluindo o caso de chave const), com teste ROM-free e build ARM64. Não trocar para allocator padrão sem provar que isso preserva as regras de memória do projeto. Depois, verificar o alinhamento de 16 KiB de todos os ELF efetivamente empacotados, incluindo a libc++ fornecida pelo NDK.

### 2.3 O que o antigo teste gráfico Android realmente comprovou

O workflow experimental [run 408694? — GLES source/shader validation](https://github.com/CarlosCosta07-s/Platina_reluzente-/actions) exportou quatro shaders GLES e passou `glslangValidator` nos dois shaders G2 e nos dois G3. Isso comprova apenas a tradução/compilação dos arquivos de shader naquele protótipo. Não comprova link dos programas com o renderer completo, chamadas de desenho, imagem apresentada, equivalência visual, APK ou execução em aparelho. O script experimental de preparação por strings Python não será reaproveitado como arquitetura final; alterações nativas devem ser arquivos `.patch`/ `.cpp` versionados.

## 3. Auditoria do renderer

Revisão upstream examinada: `cybervisi0n/libntr` em `1555d911ac80c0190ac1c321f99f1323de8b3c09`.

| Área | Uso encontrado | Consequência |
|---|---|---|
| Contexto | SDL pede OpenGL 4.2 Core | Mobile deve pedir perfil ES; a versão pedida hoje é maior que a necessidade API já identificada |
| Carregador | GLAD desktop em `sim_main.cpp` | Android/iOS precisam dos headers GLES e símbolos da plataforma/SDL; não incluir GLAD desktop |
| Shaders | quatro arquivos `#version 420 core` | Criar variantes GLES versionadas, sem alterar a variante desktop |
| Uniformes | `glProgramUniform1i/1f/4f/1fv` em G2/G3 | Exigem GLES 3.1; para base GLES 3.0, implementar compatibilidade com `glUseProgram` + `glUniform*` preservando o programa ativo anterior |
| Debug GL | `GL_DEBUG_OUTPUT`, `glDebugMessageCallback`, `glDebugMessageInsert` | Tratar como recurso opcional; a ausência não pode impedir o boot nem suprimir o log de diagnóstico Platina |
| Texturas G3 | `GL_CLAMP_TO_BORDER` em S/T quando repeat está desabilitado | Não existe no GLES 3.0 core. Não substituir silenciosamente por `GL_CLAMP_TO_EDGE`; emular a cor de borda real e comparar pixels |
| Render targets | VAO/VBO, FBO, `GL_RGBA8`, `GL_DEPTH24_STENCIL8`, textura 2D | São recursos da faixa GLES 3.0; validar alocação/completude do FBO no teste |
| Outros recursos GL 4.x | nesta inspeção, nenhum uso confirmado de compute shader, SSBO, image load/store ou layout(binding) | Não há evidência de que o renderer inteiro dependa de recursos exclusivos do GL 4.2 |

### 3.1 Recomendação de backend

O contrato comum a testar deve ser **OpenGL ES 3.0 / GLSL ES 3.00**. Android usará GLES nativo. Para iOS, ANGLE sobre Metal é uma hipótese realista apenas com esse contrato: a matriz pública atual do ANGLE marca ES 3.0 sobre Metal como completo e Metal em iOS 12+ como suportado, enquanto ES 3.1/3.2 sobre Metal não aparece como completo. Isso evita iniciar dois renderers separados. Fonte: [ANGLE README](https://github.com/google/angle).

GLSL ES 3.00 exige testar cuidadosamente os arrays de samplers, os índices derivados de uniforms e os bitwise operators que compõem a mistura G2. O compilador aceitar os quatro shaders não basta: os programas precisam linkar e renderizar os mesmos dados sintéticos.

### 3.2 Tratamento de CLAMP_TO_BORDER

O caminho de equivalência preferido é shader-side, não um fallback para edge clamp. A inspeção de `sim_g3_Texture.cpp` e `g3_draw.cpp` mostra filtros nearest nas texturas G3 e o uso de clamp-to-border quando `repeatS`/`repeatT` estão desligados. O shader pode receber dois flags de clamp e retornar a cor de borda transparente/preta para coordenadas fora da área válida, mantendo repeat/mirrored-repeat nas outras combinações. Antes de aceitar a implementação, o teste deve confirmar a semântica de coordenadas exatamente nos limites 0 e 1 e provar a paridade com o desktop. Se surgir qualquer discrepância, não liberar o renderer móvel nessa etapa.

### 3.3 Teste de paridade exigido

O protótipo deve aplicar um patch ao commit exato de libntr e renderizar cenas sintéticas sem ROM. Conjunto mínimo:

- quatro BGs com prioridades diferentes, janelas OBJ, transparência e alpha blending;
- master brightness, backdrop e a seleção de tela superior/inferior;
- geometria 3D com textura, cor de vértice, alpha, fog e as quatro combinações repeat/mirror/clamp em S/T;
- amostragem de coordenadas dentro, fora e exatamente nas bordas da textura.

O mesmo caso de teste deve renderizar no desktop GL 4.2 e em GLES 3.0 (Mesa/llvmpipe no CI), ler os pixels e comparar cada quadro. Exigir igualdade exata quando os cálculos permitirem; qualquer tolerância numérica precisa ser documentada por canal e acompanhada de limite máximo de pixels divergentes. O resultado e as imagens geradas devem ser artefatos de teste sem ROM. Este teste é o gate A; só depois dele se configura o alvo Android completo e o alvo iOS/ANGLE.

## 4. Arquitetura proposta por marco

### Marco 0 — estabilizar a base desktop e os testes

- Confirmar `python3 scripts/test.py --quick` (a CI atual executa a suíte `--full`; a execução do commit `af2970d` ainda precisa terminar).
- Corrigir as falhas restantes do launcher apenas com base nos logs completos. A falha observada foi timeout no teste que aguarda log do processo; não aumentar o timeout sem entender a ordem de eventos e os pontos de sincronização.
- Manter Linux x86-64 e Windows x64 verdes, com os smoke tests ROM-free já existentes.
- Nenhuma alteração mobile enquanto os testes comuns falharem.

### Marco A — renderer GLES 3.0 (gate de viabilidade)

1. Criar um patch versionado para a revisão pinada de libntr, mais arquivos de shader ES 3.00 e pequenas rotinas C/C++ de compatibilidade.
2. Retirar dependência obrigatória de GLAD desktop no build mobile, pedir contexto ES 3.0, condicionar debug GL e emular clamp-to-border sem alteração silenciosa.
3. Adicionar CI isolada para aplicar o patch, compilar/validar os quatro shaders e executar o comparador sintético GL 4.2 × GLES 3.0.
4. Só considerar Android viável após o comparador passar. Só considerar iOS/ANGLE após a mesma suíte passar em ANGLE/Metal num runner macOS com Xcode. Se a diferença de pixels não puder ser corrigida sem reescrever o renderer, reavaliar custo de Metal nativo antes de prosseguir.

### Marco B — núcleo C/C++ como biblioteca

- Expor uma API C estável de ciclo de vida (`create`, `resume`, `pause`, `request_shutdown`, `destroy`) e remover a dependência de um processo filho.
- Entrar com o diretório privado do app definido antes do extrator e do `FS_OpenFile`; não confiar no diretório de trabalho herdado.
- Manter `PLATINA_IMPORTED_ROM`, `PLATINA_IMPORTED_ROM_SHA256`, mensagens `[Platina-Progress]` e códigos 2/4, com resposta estruturada que o shell consiga ler sem parsear strings frágeis.
- Separar o caminho de saves do cache/runtime, fazer gravação atômica e backup rotativo; pausa/encerramento solicitam flush e o shutdown aguarda a confirmação. Nenhum `exit(0)` pode encerrar o processo inteiro do app.

### Marco C — apps nativos

Recomendação: **dois shells nativos finos**, Kotlin/Compose para Android e Swift/SwiftUI para iOS, compartilhando o núcleo C/C++ e os mesmos contratos/textos de estado. Escolher dois shells em vez de um framework UI multiplataforma reduz dependência de plugins para SAF, Document Picker/security-scoped URLs, ciclo de vida, bateria, hápticos e compartilhamento de log. Reutilizar regras de validação/cache do desktop conceitualmente, não o Electron.

- Android: Storage Access Framework, cópia privada transacional, WorkManager para preparo retomável quando a tarefa puder sobreviver ao processo, foreground progress quando necessário e JNI/SDL para o núcleo.
- iOS: document picker, acesso coordenado a URL de security scope, cópia para Application Support, preparação em tarefa apropriada ao ciclo de vida e ponte Objective-C++/C para o núcleo.
- Ambos: selecionar ROM, validar extensão/tamanho/header/SHA-1, exigir USA Rev. 1 `0862ec35b24de5c7e2dcb88c9eea0873110d755c`, armazenar cópia privada e SHA-256/metadados, recuperar transação interrompida, preparar cache com estados verificáveis e exibir progresso/logs.
- Idioma só muda para PT-BR quando o pacote local for verificado por manifest/hash. Se falhar, manter o idioma atual e explicar o erro; nunca mostrar “PT-BR pronto” sem pacote válido.
- Platinum ativo; Black apenas como entrada desativada “em desenvolvimento”, sem código ou dados de Black no bundle.

### Marco D — entrada e experiência

Implementar overlay D-pad/A/B/X/Y/L/R/Start/Select configurável, toque encaminhado à tela inferior, layouts vertical/horizontal/grande usando o modelo `ScreenLayout`, suporte a controles Bluetooth/USB e teclado físico, háptico opcional, orientação e safe areas. A interface precisa reagir a pausa, retomar contexto gráfico se perdido, respeitar economia de energia e reduzir qualidade/atividade sob pressão térmica sem danificar o save.

### Marco E — builds e CI

- Android: NDK ARM64 como alvo obrigatório; x86-64 só como auxiliar de emulador de sistema. Corrigir antes o allocator e a checagem ELF de 16 KiB. Não repetir o job ARM64 com o mesmo bloqueio.
- iOS: runner macOS/Xcode dedicado; compilar framework estático e app; assinatura/perfis documentados sem segredos em logs.
- Fixar SDL2, ENet e libpng com hash de origem e ferramentas por plataforma; ações GitHub por SHA imutável.
- Workflows móveis separados, concurrency groups próprios, sem cancelar/alterar os workflows desktop. Cada um deve compilar, testar ROM-free e verificar que o app abre na tela “Importar ROM”.
- Artefatos apenas binários genéricos e manifests de caminhos/hash de dependências; nunca conteúdo extraído do jogo.

### Marco F — distribuição e jurídico

- Android: APK/AAB fora da Play Store é uma primeira opção técnica; publicar na Play Store é outra análise de política e direitos.
- iOS: App Store continua possível somente mediante aprovação; TestFlight é beta, cada build fica testável por até 90 dias. Ad Hoc é para dispositivos registrados. O Apple Developer Program custa atualmente US$ 99/ano (preço local e impostos podem variar).
- Atualização importante para o Brasil: desde iOS 26.5 a Apple documenta distribuição por marketplaces alternativos para apps brasileiros. Isso não equivale a instalação aberta de um IPA por URL: o app precisa ser devidamente autenticado/notarizado e distribuído por um marketplace elegível. Operar o próprio marketplace exige conta de organização e entitlement/autorizações adicionais, portanto não é o plano inicial. Ver [mudanças no iOS no Brasil](https://developer.apple.com/support/app-distribution-in-brazil) e [requisitos para operar um marketplace no Brasil](https://developer.apple.com/br/support/alternative-app-marketplace-br/).
- A diretriz Apple 4.7 trata especificamente de mini apps e emuladores; este projeto não se descreve como emulador. Isso não garante aprovação nem resolve direitos autorais, marcas, licenças upstream ou política de conteúdo. A classificação deve ser confirmada com a Apple durante submissão e a estratégia jurídica deve ser revisada por advogado.

### Marco G — matriz de paridade e aparelhos

O estado inicial abaixo não confunde compilação com jogabilidade.

| Recurso | Windows | Linux | Android | iOS |
|---|---|---|---|---|
| Importação | Testado sem ROM na suíte do launcher | Testado sem ROM na suíte do launcher | Não feito | Não feito |
| Preparo/cache | Testado sem ROM em testes do contrato; confirmar CI atual | Testado sem ROM em testes do contrato; confirmar CI atual | Não feito; build histórico falhou antes do pacote | Não feito |
| Jogo | Executável compilado; sem validação com ROM nesta auditoria | Executável compilado; smoke de UI sem ROM; sem validação com ROM | Não compilado de forma concluída no pipeline histórico | Não feito |
| Saves | Não validado com jogo real nesta auditoria | Não validado com jogo real nesta auditoria | Não feito | Não feito |
| Idioma | Testes/empacotamento ROM-free existentes | Testes/empacotamento ROM-free existentes | Não feito | Não feito |
| Logs | Testes ROM-free do launcher; revisar flakiness do teste de processo | Testes ROM-free do launcher; revisar flakiness do teste de processo | Não feito | Não feito |
| Entrada | Sem validação de hardware nesta auditoria | Sem validação de hardware nesta auditoria | Não feito | Não feito |
| Desempenho/bateria | Não medido em aparelho de referência | Não medido em aparelho de referência | Não medido | Não medido |

Medições só começam quando o primeiro frame do jogo estiver comprovadamente em execução com uma ROM de teste fornecida pelo usuário e fora do repositório/CI. Registrar modelo, SoC/GPU, versão do SO, resolução, modo de tela, temperatura ambiente e build hash. Medir tempo de importação/preparo, tempo até o primeiro frame, FPS (média/1% low), memória pico e energia/bateria em aparelhos de baixo, médio e alto desempenho.

## 5. Critérios de conclusão

- **Compilado:** o toolchain produziu o alvo e as verificações do pacote passaram.
- **Testado sem ROM:** os contratos, importação simulada, cache, logs, UI de primeiro lançamento e testes gráficos sintéticos passaram; nenhum dado do jogo foi usado.
- **Validado com ROM:** o proprietário importou a própria cópia correta, o cache foi preparado, o jogo efetivamente exibiu frames e o funcionamento foi registrado em aparelho/sistema identificado.
- **Paridade visual:** além de compilar, o comparador sintético quadro a quadro passa e depois é confirmado visualmente no hardware de destino.

A paridade de recursos com PC só deve ser declarada quando cada linha da matriz tiver evidência reproduzível. Até lá, Android e iOS permanecem em pesquisa/prototipagem, não em suporte anunciado.
