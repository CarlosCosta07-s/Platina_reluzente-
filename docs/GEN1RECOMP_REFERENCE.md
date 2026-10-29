# Referências técnicas e padrões adotados

Este documento registra as referências usadas no Platina Reluzente Launcher 0.2.0. As referências orientam decisões de arquitetura e validação; não implicam que o projeto use o mesmo motor, licenças ou código-fonte.

## Gen1Recomp — fluxo de importação e manutenção

- Repositório: https://github.com/bryanthaboi/gen1recomp
- Guia de execução e importação: https://github.com/bryanthaboi/gen1recomp/wiki/Start-Playing
- Guia de desenvolvimento, cache e testes: https://github.com/bryanthaboi/gen1recomp/wiki/Guide-Developer-Setup

Padrões úteis adaptados ao contexto de Platinum:

1. **Validar a ROM antes da importação.** O launcher já restringe a imagem aceita à revisão suportada e valida a assinatura integral; o runtime não deve começar uma extração a partir de um arquivo simplesmente selecionado.
2. **Separar importação do loop de renderização.** A leitura de uma ROM pode demorar. O Launcher 0.2.0 prepara os dados extraídos antes de criar a janela SDL/OpenGL, em vez de bloquear o loop de eventos quando um recurso não é encontrado.
3. **Manter cache privado e recuperável.** A extração é local, o marcador `platina-rom-extraction.sha256` associa os dados à impressão SHA-256 da ROM importada, e a próxima inicialização reutiliza os dados quando o marcador e um recurso-chave estão presentes. Se a importação não terminar, o marcador não deve certificar uma extração bem-sucedida.
4. **Testar as regras sem compartilhar dados protegidos.** Testes automatizados usam arquivos temporários e fixtures sintéticas, sem incluir ROMs ou recursos extraídos no repositório. Os builds não devem empacotar conteúdo protegido do jogo.

Gen1Recomp é baseado em Lua/LÖVE e dá suporte a várias gerações de jogos Game Boy. Platinum usa código reconstruído C/C++ e a camada libntr/NitroSDK para um alvo desktop. Portanto, não copiamos o motor, o renderizador, as rotinas de importação de Game Boy nem suas estruturas internas. Adaptamos somente os princípios de importação local, cache, diagnóstico e testes.

## Atualizações do launcher: o que vale adaptar

O arquivo `docs/updater.md` do Gen1Recomp e a RFC 0008 do ZIP anexado documentam separação entre checagem, download, validação, cache e ativação. O Gen1Recomp pode montar um payload Lua mais novo sobre o engine em execução; esse mecanismo **não deve ser copiado literalmente** para o nosso executável nativo C/C++.

Mecânicas adequadas ao Platina Reluzente:

- **Metadados versionados:** cada pacote deve identificar versão do launcher, sistema-alvo e revisão do runtime nativo. O artefato Windows não pode reutilizar o runtime Linux, nem uma revisão antiga do motor.
- **Manifesto e SHA-256:** publicar os hashes dos pacotes e validar o arquivo baixado antes de substituir a versão instalada. Não confiar apenas no nome do arquivo ou em um cabeçalho da ROM.
- **Ativação segura após fechar o jogo:** separar a verificação/download da instalação. Não substituir DLLs, AppImage ou executável enquanto o runtime estiver aberto; instalar após reiniciar, ou usar um instalador/launcher auxiliar.
- **Rollback e atualização interrompida:** baixar para arquivo temporário, confirmar tamanho e hash, e só então promover o novo pacote. Se a verificação ou instalação falhar, manter o pacote anterior intacto e apresentar o log.
- **Cache com impressão da origem:** os dados extraídos são locais e associados ao SHA-256 da ROM; a mudança de ROM ou runtime deve invalidar apenas o cache afetado. Nunca incluir ROM ou arquivos extraídos em release artifacts.
- **CI por etapas:** primeiro executar testes e compilar o motor, depois validar o pacote nativo, e só então empacotar o launcher usando o artefato da mesma execução bem-sucedida. O workflow de empacotamento foi ajustado para rejeitar artefatos antigos de outra execução.

Esses são contratos e diretrizes para futuras atualizações automáticas, não uma afirmação de que o launcher já possui um atualizador integrado. Na versão 0.2.0, a melhoria implementada é a associação dos artefatos de empacotamento ao build nativo correspondente e o cache local da extração. Uma atualização automática de pacotes completos exige uma etapa separada com testes específicos de integridade, compatibilidade, reinício e rollback.

## Referências do porte nativo

- **cybervisi0n/pokeplatinum**, base de porte desktop: https://github.com/cybervisi0n/pokeplatinum/tree/35067868f64f23d25d17ac3e536cfdd9a7f40523
- **libntr**, camada de compatibilidade e simulador desktop, revisão usada pelo projeto: https://github.com/cybervisi0n/libntr/tree/1555d911ac80c0190ac1c321f99f1323de8b3c09
- **pret/pokeplatinum**, projeto de decompilação: https://github.com/pret/pokeplatinum

A camada libntr já dispõe do modo `horizontal` para as telas do Nintendo DS. O launcher escreve `ScreenLayout=horizontal` na seção `[General]` de `sim_config.ini`, preservando outras opções existentes. Assim, a mudança do layout usa o recurso presente na base nativa, em vez de duplicar a geometria do renderizador.

## Como validar as alterações

- Executar a suíte de testes do launcher (`npm test` no diretório `launcher-app`).
- Executar `python -m unittest discover -s tools/tests -v` a partir da raiz.
- Compilar Windows x64 e Linux x86-64 na CI.
- Testar manualmente uma ROM legalmente obtida e aceita pelo launcher: confirmar importação, a tela de título, entrada, salvamento e a apresentação horizontal.
- Em caso de falha, inspecionar `native-startup.log`. A criação do processo ou da janela, isoladamente, não comprova que o jogo chegou à tela de título.

A referência Gen1Recomp é inspiracional; a implementação e a validação de Platinum permanecem específicas deste repositório.
