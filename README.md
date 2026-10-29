# Platina Reluzente — porte nativo de Pokémon Platinum

> **Projeto comunitário de preservação e estudo, sem fins comerciais.** Não é um produto oficial nem possui vínculo com Nintendo, Game Freak ou The Pokémon Company.

O objetivo é fazer **Pokémon Platinum executar como um aplicativo nativo** em **Windows e Linux**, reutilizando o código C reconstruído pela comunidade a partir do jogo original. O projeto não pretende incluir ROMs, firmware ou arquivos de jogo nos releases.

## Estado real do projeto

- **Base nativa desktop:** vinculada como checkout externo e fixada em um commit específico do porte de PC baseado na decompilação pret/pokeplatinum.
- **Linux x86-64 e Windows x64:** ambos os alvos passaram na execução [40647214112 do GitHub Actions](https://github.com/CarlosCosta07-s/Platina_reluzente-/actions/runs/40647214112), em 28 de outubro de 2026. Os testes automatizados também passaram e cada pacote foi validado contra os 340 caminhos do manifesto upstream, incluindo recursos de animação. Isso valida compilação e integridade do pacote, não a inicialização nem a jogabilidade.
- **Escopo de plataforma:** o suporte Android foi encerrado após falhas recorrentes na validação final do pipeline ARM64. O projeto e a CI ficam concentrados exclusivamente em Windows x64 e Linux x86-64.
- **Inicialização da interface Linux:** o AppImage nativo abriu uma janela visível e permaneceu ativo por 15 segundos no teste [40691585390](https://github.com/CarlosCosta07-s/Platina_reluzente-/actions/runs/40691585390), usando um diretório temporário vazio e sem ROM. Isso confirma somente que a interface inicia; **não** comprova que uma ROM foi extraída, que a tela de título apareceu ou que o jogo está jogável.
- **ROM aceita pelo launcher:** o runtime está fixado em Pokémon Platinum USA Rev. 1. O launcher verifica o cabeçalho e o SHA-1 integral `0862ec35b24de5c7e2dcb88c9eea0873110d755c`; a USA Rev. 0 enviada em 29/10/2026 (`ce81046eda7d232513069519cb2085349896dec7`, CRC-32 `9253921D`) é reconhecida como Rev. 0 e recusada porque ainda não há um build Rev. 0 validado.
- **Português brasileiro:** sete NARC da referência PT-BR correspondem aos hashes aprovados e passaram na verificação estrutural. O patch Xdelta v1.2.0 documenta uma base de CRC-32 `1D8A5220`, diferente da ROM USA Rev. 1 usada pelo projeto (CRC-32 `69D628E8`); sua aplicação direta à Rev. 1 não foi comprovada. O seletor de idioma ainda não foi implementado; veja a [verificação técnica](docs/LOCALIZATION.md).

**Próximo objetivo de execução:** provar que o binário desktop consegue abrir com uma cópia local válida da ROM USA Rev. 1 e chegar à tela inicial; depois validar uma sequência mínima de gameplay e salvamento.

Não anunciamos o porte como concluído nem jogável do início ao fim antes de termos compilação e testes reproduzíveis.

## Compilação e validação

A CI verifica testes de manutenção, compilação nativa e a inicialização pré-ROM da interface Linux. O launcher desktop registra as saídas stdout/stderr do runtime nativo em `native-startup.log` no diretório privado do aplicativo e mostra o caminho do arquivo em caso de diagnóstico. Isso ajuda a investigar falhas, mas não substitui a confirmação da tela de título e gameplay. A CI não publica executáveis, AppImages, APKs ou arquivos runtime que possam conter recursos derivados do jogo. Esses dados permanecem na área temporária do job e não são disponibilizados como artefatos para download.

Para teste manual, compile o porte localmente seguindo o [guia de compilação](docs/BUILDING.md), use uma cópia de ROM que você tenha direito de utilizar e mantenha os dados extraídos fora do Git. O smoke test automático confirma apenas a criação da janela sem ROM; não comprova que o jogo chega à tela inicial ou que seja jogável. A importação PT-BR é um passo local separado e ainda exige validação dentro do jogo.

## Decisão técnica

**Não usaremos Godot, Unity, emulador de Nintendo DS nem interpretador de instruções ARM.** Uma engine genérica obrigaria a reconstruir o jogo em vez de aproveitar a lógica real existente.

A rota escolhida é:

- **C** para a lógica original reconstruída de Pokémon Platinum;
- **C/C++** onde as bibliotecas nativas existentes exigirem;
- **Meson + Ninja** para a compilação do porte de PC;
- **libntr** e a camada nativa do projeto de referência para substituir APIs do NitroSDK no host;
- **OpenGL de desktop** para Windows/Linux na base existente;

A camada de compatibilidade recria serviços e chamadas gráficas que o jogo espera, mas **não executa uma CPU de DS emulada nem interpreta o código ARM do jogo durante a partida**: o código recompilado é compilado pelo toolchain do sistema-alvo.

Veja o [guia de compilação](docs/BUILDING.md), a [arquitetura](docs/PORTING_ARCHITECTURE.md), o [roteiro](docs/ROADMAP.md), a [estratégia PT-BR](docs/LOCALIZATION.md) e o [aviso legal](docs/LEGAL.md).

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

## Importar recursos localizados PT-BR localmente

> **Nota de desenvolvimento:** o comando abaixo é o fluxo provisório existente, não o comportamento final desejado. A próxima etapa é transformar os recursos numa camada de idioma isolada e selecionável no launcher; a ROM original e os recursos-base não deverão ser modificados. Consulte [a estratégia PT-BR](docs/LOCALIZATION.md).

A comparação das ROMs fornecidas identificou estes sete arquivos NARC localizados que podem ser selecionados explicitamente para importação:

- battle/graphic/pl_b_plist_gra.narc
- data/slot.narc
- demo/title/op_demo.narc
- graphic/pl_bag_gra.narc
- graphic/pl_plist_gra.narc
- graphic/pl_pst_gra.narc
- msgdata/pl_msg.narc

Os arquivos msgdata/msg.narc e msgdata/scenario/scr_msg.narc são idênticos entre as duas ROMs fornecidas, então não precisam ser substituídos. As entradas data/utility.bin, dwc/utility.bin e a entrada FAT sem caminho no FNT foram deliberadamente excluídas: não serão copiadas ao runtime sem análise de compatibilidade específica.

Após compilar e iniciar o porte uma vez para preparar os dados locais, feche o jogo e execute o importador, apontando para o diretório-raiz onde os recursos extraídos estão organizados:

    python3 tools/import_localization.py \
      --rom "/caminho/local/PK Plat [PT-BR].nds" \
      --destination "vendor/pokeplatinum-native/build_linux/pokeplatinum" \
      --force

Em Windows, use o diretório de trabalho do executável em build_win64/pokeplatinum. O extrator upstream usa o diretório de trabalho atual; execute o jogo a partir de build_linux/pokeplatinum ou build_win64/pokeplatinum, e não de outra pasta. A ferramenta modifica apenas os sete arquivos allowlisted no diretório de destino; não altera a ROM de origem nem faz upload. Ela valida a estrutura NARC, exige que o SHA-256 de cada um dos sete recursos corresponda ao manifesto da variante PT-BR aprovada e só recupera o tamanho declarado no NARC quando o intervalo adicional não se sobrepõe a outro arquivo FAT. A verificação dos sete hashes acontece antes de qualquer arquivo ser escrito, então uma ROM USA ou outra tradução é recusada sem alterar o runtime.

Depois da importação, confira os arquivos locais com `python3 tools/check_runtime_data.py --runtime-dir vendor/pokeplatinum-native/build_linux/pokeplatinum --require-localized-resources`. Além de validar a estrutura NARC, essa opção compara SHA-256 com a versão PT-BR específica usada como referência; um NARC estruturalmente válido, mas de outra versão, não será aceito. A validação não inicia o jogo. A importação desses recursos ainda não prova que todas as telas e eventos funcionam em PT-BR. Confirme fontes, acentos, menus, diálogos, batalhas e salvamento dentro do jogo antes de considerar essa variante compatível. Veja a [documentação de localização](docs/LOCALIZATION.md).

Execute os testes automatizados sem precisar de ROM:

    python3 -m unittest discover -s tools/tests -v

## Regra do repositório

O desenvolvimento será feito diretamente na branch main; não serão criadas branches de trabalho. A CI acompanha apenas a main.

## Links

- [Arquitetura técnica](docs/PORTING_ARCHITECTURE.md)
- [Roteiro e critérios de aceite](docs/ROADMAP.md)
- [Compatibilidade PT-BR e original](docs/LOCALIZATION.md)
- [Preservação, direitos e distribuição](docs/LEGAL.md)
- [Decompilação base (pret)](https://github.com/pret/pokeplatinum)
- [Porte nativo PC de referência](https://github.com/cybervisi0n/pokeplatinum)
