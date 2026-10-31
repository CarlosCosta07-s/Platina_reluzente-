# Platina Reluzente — biblioteca de portes nativos

> **Projeto comunitário de preservação e estudo, sem fins comerciais.** Não é um produto oficial nem possui vínculo com Nintendo, Game Freak ou The Pokémon Company.

O projeto reúne uma biblioteca experimental de portes nativos comunitários para **Windows e Linux**, com a trilha Android/iOS reaberta em desenvolvimento source-only. O desenvolvimento principal continua sendo o porte de **Pokémon Platinum**, que já possui runtimes desktop e um launcher integrado em fase de testes. Em paralelo, o porte nativo de **Pokémon Black Version** avançou da auditoria para uma etapa de validação de código e compilação: o workflow [Pokémon Black native source validation (no game data)](.github/workflows/pokemon-black-native-check.yml) verifica revisões fixadas de [Aletheia](https://github.com/Project-Holon/aletheia) e [Eidos](https://github.com/Project-Holon/eidos) em Windows x64 e Linux x86-64 sem ROM ou recursos do jogo. O launcher usa uma biblioteca única para os dois projetos e já oferece a importação local de Black, mas não pede ao usuário que procure ou execute outro programa. O runtime de Black ainda não é incluído no pacote; o botão de iniciar permanece bloqueado até que a integração interna seja distribuível legalmente. O teste de compilação sem ROM valida apenas a compilação, não a tela de título nem a jogabilidade com uma ROM. A distribuição de código ou binários derivados de Aletheia continua bloqueada até revisão jurídica. Nenhuma ROM, firmware ou recurso protegido do jogo será incluído nos releases.

## Pokémon Black — etapa técnica

O porte paralelo está agora fixado nas revisões compatíveis do [aletheia](https://github.com/Project-Holon/aletheia/tree/6c2aae879f123bcbc028cf6a8b7f8df614402ac8) e do [eidos](https://github.com/Project-Holon/eidos/tree/b79123f967980d1bb758161891205c03d606dec7). O workflow [Pokémon Black native source validation](.github/workflows/pokemon-black-native-check.yml) compila/testa sem ROM e não publica executáveis. A licença de `aletheia/src/` não concede licença do código reconstruído; a distribuição de binários Black fica bloqueada até análise jurídica adequada. Veja o [plano técnico](docs/POKEMON_BLACK_PORT.md).

## Projetos da biblioteca

- **Pokémon Platinum** — porte nativo principal em Windows/Linux. O launcher integrado já pode ser compilado, mas tela de título e jogabilidade ainda precisam ser confirmadas com uma cópia local compatível.
- **Pokémon Black Version** — porte nativo paralelo baseado nas revisões fixadas de Aletheia/Eidos, apresentado na mesma biblioteca do launcher. A importação local da ROM é implementada e mantém armazenamento isolado de Platinum; o runtime será localizado internamente no recurso `black-runtime` do pacote, nunca selecionado manualmente pelo usuário. O pacote ainda não contém esse runtime e o botão de iniciar permanece bloqueado enquanto a distribuição de código/binários derivados de Aletheia não estiver autorizada. Os builds host Windows x64 e Linux x86-64 e os testes upstream sem ROM passaram na execução [Pokémon Black native source validation](https://github.com/CarlosCosta07-s/Platina_reluzente-/actions/runs/40905769682); isso não confirma tela de título nem jogabilidade com uma ROM. Consulte o [plano técnico](docs/POKEMON_BLACK_PORT.md), o [guia de build local](docs/POKEMON_BLACK_LOCAL_BUILD.md), o [contrato do runtime](docs/POKEMON_BLACK_RUNTIME_CONTRACT.md) e o [workflow sem dados do jogo](.github/workflows/pokemon-black-native-check.yml).

## Estado real do projeto

- **Base nativa desktop:** vinculada como checkout externo e fixada em um commit específico do porte de PC baseado na decompilação pret/pokeplatinum.
- **Linux x86-64 e Windows x64:** a base desktop anterior compilou nos dois alvos e passou pela verificação dos 340 caminhos do manifesto upstream. Na revisão de localização de 30/10/2026, a suíte Python passou e o build Linux compilou, verificou o pacote e abriu a interface sem ROM ([execução 41047480079](https://github.com/CarlosCosta07-s/Platina_reluzente-/actions/runs/41047480079)). O build Windows não chegou ao compilador: falhou ao baixar `metroskrew` do GitHub (erro de rede do `wget`). O preparador agora inclui tentativas adicionais e fallback via `curl`; a revisão com correção dos finais de linha LF para MSYS2 está em validação ([execução 41130771002](https://github.com/CarlosCosta07-s/Platina_reluzente-/actions/runs/41130771002)). Ainda não se afirma que a revisão mais recente compila nas duas plataformas.
- **Escopo de plataforma:** Windows x64 e Linux x86-64 permanecem como referência Desktop. Android e iOS estão em desenvolvimento source-only: arquitetura, núcleo compartilhado, shells nativos e testes ROM-free podem avançar, mas nenhum alvo móvel será compilado nem APK/AAB/IPA gerado até a paridade funcional 1:1 com o Desktop. Consulte o [contrato de paridade móvel](docs/MOBILE_PARITY_CONTRACT.md) e a [auditoria do renderer](docs/MOBILE_RENDERER_AUDIT.md). As falhas ARM64 históricas continuam registradas na [auditoria móvel](docs/MOBILE_PORT_AUDIT.md) e precisam ser resolvidas antes do primeiro build autorizado.
- **Inicialização da interface Linux:** o AppImage nativo abriu uma janela visível e permaneceu ativo por 15 segundos no teste [40691585390](https://github.com/CarlosCosta07-s/Platina_reluzente-/actions/runs/40691585390), usando um diretório temporário vazio e sem ROM. Isso confirma somente que a interface inicia; **não** comprova que uma ROM foi extraída, que a tela de título apareceu ou que o jogo está jogável.
- **ROM aceita pelo launcher:** o runtime está fixado em Pokémon Platinum USA Rev. 1. O launcher verifica o cabeçalho e o SHA-1 integral `0862ec35b24de5c7e2dcb88c9eea0873110d755c`; a USA Rev. 0 enviada em 29/10/2026 (`ce81046eda7d232513069519cb2085349896dec7`, CRC-32 `9253921D`) é reconhecida como Rev. 0 e recusada porque ainda não há um build Rev. 0 validado.
- **Português brasileiro:** a ferramenta gera um pacote isolado com manifesto e hashes dos sete NARC aprovados. O launcher já permite importar essa pasta, validar manifesto/estrutura/hashes, instalar uma cópia privada e selecionar English ou Português (Brasil). O `FS_OpenFile` nativo consulta os sete caminhos autorizados sem substituir os arquivos-base; a ausência de um recurso PT-BR bloqueia a abertura, sem fallback silencioso para inglês. O patch Xdelta v1.2.0 continua sem compatibilidade comprovada com a Rev. 1. A integração técnica e os testes automatizados não comprovam a renderização correta dos textos; ainda faltam validação visual e gameplay em execução. Veja a [documentação técnica](docs/LOCALIZATION.md).

**Próximo objetivo de execução:** provar que o binário desktop consegue abrir com uma cópia local válida da ROM USA Rev. 1 e chegar à tela inicial; depois validar uma sequência mínima de gameplay e salvamento.

Não anunciamos o porte como concluído nem jogável do início ao fim antes de termos compilação e testes reproduzíveis.

## Compilação e validação

Depois de compilar o runtime nativo, o launcher inclui apenas o executável portátil e as bibliotecas necessárias: a AppImage nativa no Linux ou `main.exe` e DLLs no Windows. Ele não empacota `header.bin`, firmware, NARC ou outros dados do jogo. Após importar a ROM USA Rev. 1 compatível, o primeiro início prepara os recursos que faltarem na pasta gravável privada do aplicativo. Os comandos completos estão no [guia de compilação](docs/BUILDING.md). ROMs e dados extraídos permanecem locais.

A CI testa a lógica de importação, compila o runtime nativo para Windows/Linux e empacota o launcher desktop integrado. O pipeline principal é **[Native desktop build and localization checks](https://github.com/CarlosCosta07-s/Platina_reluzente-/actions/workflows/native-desktop.yml)**. Os workflows de empacotamento separados já publicaram ambos os launchers: [Linux — execução #3](https://github.com/CarlosCosta07-s/Platina_reluzente-/actions/runs/40892855183), artefato `Platina-Reluzente-Launcher-Linux-x64`, e [Windows — execução #4](https://github.com/CarlosCosta07-s/Platina_reluzente-/actions/runs/40894404142), artefato `Platina-Reluzente-Launcher-Windows-x64`. Abra a execução correspondente e baixe o artefato na seção **Artifacts**. Eles expiram em 14 dias e incluem hashes SHA-256 e instruções iniciais. Nenhum pacote deve conter ROM, firmware, arquivos NARC, recursos extraídos, saves ou patches: importe uma cópia legal e compatível de Pokémon Platinum USA Rev. 1 no launcher, e os dados ausentes deverão ser extraídos localmente no primeiro início. São builds experimentais, não releases finais. A CI comprovou que a interface nativa Linux abre sem ROM; a tela de título e a jogabilidade com uma ROM ainda não foram confirmadas. O launcher registra stdout/stderr em `native-startup.log` dentro dos dados privados do aplicativo.

Baixe um artefato do launcher somente de uma execução bem-sucedida na aba Actions. No Windows, execute o arquivo `.exe` portátil; no Linux, dê permissão de execução à AppImage, se necessário, e abra-a. Importe uma cópia compatível USA Rev. 1 obtida legalmente. A ROM não é alterada nem enviada ao GitHub. Se a inicialização falhar, envie somente `native-startup.log`, nunca a ROM ou os dados extraídos. O smoke test automático confirma apenas a criação de uma janela Linux sem ROM; não comprova tela de título ou jogabilidade. Para PT-BR, gere o pacote isolado conforme a seção abaixo e instale-o pela interface do launcher; a tradução dentro do jogo ainda exige validação.

## Decisão técnica

**Não usaremos Godot, Unity, emulador de Nintendo DS nem interpretador de instruções ARM.** Uma engine genérica obrigaria a reconstruir o jogo em vez de aproveitar a lógica real existente.

A rota escolhida é:

- **C** para a lógica original reconstruída de Pokémon Platinum;
- **C/C++** onde as bibliotecas nativas existentes exigirem;
- **Meson + Ninja** para a compilação do porte de PC;
- **libntr** e a camada nativa do projeto de referência para substituir APIs do NitroSDK no host;
- **OpenGL de desktop** para Windows/Linux na base existente;

A camada de compatibilidade recria serviços e chamadas gráficas que o jogo espera, mas **não executa uma CPU de DS emulada nem interpreta o código ARM do jogo durante a partida**: o código recompilado é compilado pelo toolchain do sistema-alvo.

Veja o [guia de compilação](docs/BUILDING.md), a [arquitetura](docs/PORTING_ARCHITECTURE.md), o [roteiro geral](docs/ROADMAP.md), o [plano técnico de Pokémon Black](docs/POKEMON_BLACK_PORT.md), a [estratégia PT-BR](docs/LOCALIZATION.md) e o [aviso legal](docs/LEGAL.md).

## Referências técnicas e correções da versão 0.2.0

O Launcher 0.2.0 prepara a extração da ROM antes de inicializar a janela SDL/OpenGL, mantém um marcador local vinculado ao SHA-256 da ROM e configura as duas telas do Nintendo DS horizontalmente, lado a lado. A extração deixa de depender do loop gráfico para começar; ainda é necessário validar manualmente que o runtime chega à tela de título com uma ROM compatível.

As decisões de importação local, cache recuperável e testes sem dados protegidos são informadas pelo [Gen1Recomp](https://github.com/bryanthaboi/gen1recomp) e seu [guia de desenvolvimento e testes](https://github.com/bryanthaboi/gen1recomp/wiki/Guide-Developer-Setup). O renderizador e a lógica original de Platinum continuam baseados em C/C++, [pret/pokeplatinum](https://github.com/pret/pokeplatinum) e na camada desktop [libntr](https://github.com/cybervisi0n/libntr); não importamos o motor Lua/LÖVE do Gen1Recomp. Veja a [nota de referências técnicas](docs/GEN1RECOMP_REFERENCE.md).

## Auditoria nativa e segurança

O runtime parte da decompilação em C de [pret/pokeplatinum](https://github.com/pret/pokeplatinum), por meio do porte desktop fixado em [cybervisi0n/pokeplatinum](https://github.com/cybervisi0n/pokeplatinum). Essa árvore é uma reconstrução comunitária em andamento, não o código-fonte oficial fornecido pela Game Freak. A licença do projeto não substitui as licenças e permissões de cada dependência externa; a distribuição de código derivado e binários depende de revisão específica.

O procedimento de investigação do executável com **REA** está em [docs/REA_AUDIT_WORKFLOW.md](docs/REA_AUDIT_WORKFLOW.md). O REA deve complementar a leitura do C, as análises estáticas e os testes de regressão; não é uma certificação de segurança. Consulte [SECURITY.md](SECURITY.md) para relatos privados de vulnerabilidades. ROMs, firmware, arquivos extraídos, saves e dumps não devem ser enviados ao REA, à CI ou ao repositório.

## Código de referência e compilação

A base desktop usada como referência está em [cybervisi0n/pokeplatinum](https://github.com/cybervisi0n/pokeplatinum), baseada na [decompilação pret/pokeplatinum](https://github.com/pret/pokeplatinum) e na biblioteca [libntr](https://github.com/cybervisi0n/libntr). Ela é vinculada como dependência externa fixada e não é modificada permanentemente por este projeto sem revisão específica das condições do upstream.

Clone o repositório e inicialize as dependências de código:

    git clone https://github.com/CarlosCosta07-s/Platina_reluzente-.git
    cd Platina_reluzente-
    git submodule update --init --recursive

Linux:

    ./scripts/build-native.sh linux

Windows (PowerShell; instale o ambiente MSYS2 do submódulo uma vez antes da primeira compilação):

    cd vendor/pokeplatinum-native
    .\Install_MSys2.ps1
    cd ..\..
    .\scripts\build-native.ps1

Após a compilação, `scripts/verify_native_package.py` compara os 340 caminhos de `platinum.us/filesys.csv` com o pacote runtime e a CI também exige os arquivos de animação de batalha. Isso evita que uma compilação incompleta seja marcada como pacote completo. O verificador não executa o jogo.

Os builds de desktop **compilam o código**; eles não executam testes de jogo automaticamente. Para jogar, use somente uma cópia obtida legalmente e mantenha ROMs e recursos extraídos fora deste repositório. Consulte os documentos legais antes de distribuir qualquer compilação.

## Gerar e instalar o pacote PT-BR

A tradução não altera a ROM USA Rev. 1 nem sobrescreve os arquivos ingleses do runtime. A ferramenta de importação produz uma pasta isolada com somente estes sete recursos NARC, acompanhados por `localization-manifest.json`:

- `battle/graphic/pl_b_plist_gra.narc`
- `data/slot.narc`
- `demo/title/op_demo.narc`
- `graphic/pl_bag_gra.narc`
- `graphic/pl_plist_gra.narc`
- `graphic/pl_pst_gra.narc`
- `msgdata/pl_msg.narc`

A ferramenta aceita somente a ROM PT-BR de referência aprovada, confere o SHA-256 dos sete recursos e valida seus cabeçalhos NARC. O pacote resultante continua local e não é incluído no Git ou na CI.

Linux:

```sh
python3 tools/import_localization.py \
  --rom "/caminho/local/PK Plat [PT-BR].nds" \
  --package "$HOME/.local/share/PlatinaReluzente/localizations/pt-BR"
```

Windows (PowerShell):

```powershell
python tools/import_localization.py `
  --rom "C:\ROMs\PK Plat [PT-BR].nds" `
  --package "$env:APPDATA\PlatinaReluzente\localizations\pt-BR"
```

Depois de gerar o pacote, abra o launcher, selecione **Pokémon Platinum** e use **Importar pacote PT-BR**. Escolha a pasta criada pelo comando. O launcher verifica novamente o manifesto, os sete hashes e a estrutura exata; então instala uma cópia na pasta privada do aplicativo e seleciona Português (Brasil). A preferência fica salva localmente. Também é possível voltar para **English (original)** sem remover o pacote.

Antes de cada inicialização em PT-BR, o launcher verifica o pacote novamente. O filesystem nativo redireciona somente os sete caminhos autorizados para a pasta traduzida. Se um recurso estiver ausente ou inválido, o jogo não inicia nesse idioma e não troca silenciosamente para inglês. Os arquivos originais permanecem intactos.

A integração comprova a validação e a resolução dos arquivos, mas ainda não prova a renderização correta em jogo. É necessário testar acentuação, fontes, menus, tela de título, diálogos, batalhas, progressão e salvamentos. O patch Xdelta v1.2.0 não foi comprovado como aplicável diretamente à ROM USA Rev. 1; não o aplique presumindo compatibilidade.

Execute os testes automatizados sem precisar de ROM:

```sh
python3 scripts/test.py --full
```

## Regra do repositório

O desenvolvimento será feito diretamente na branch main; não serão criadas branches de trabalho. A CI acompanha apenas a main.

## Links

- [Arquitetura técnica](docs/PORTING_ARCHITECTURE.md)
- [Contrato de paridade Android/iOS](docs/MOBILE_PARITY_CONTRACT.md)
- [Auditoria do renderer móvel](docs/MOBILE_RENDERER_AUDIT.md)
- [Roteiro e critérios de aceite](docs/ROADMAP.md)
- [Compatibilidade PT-BR e original](docs/LOCALIZATION.md)
- [Preservação, direitos e distribuição](docs/LEGAL.md)
- [Decompilação base (pret)](https://github.com/pret/pokeplatinum)
- [Porte nativo PC de referência](https://github.com/cybervisi0n/pokeplatinum)
