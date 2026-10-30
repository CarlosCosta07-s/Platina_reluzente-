# Roteiro de desenvolvimento

O foco é concluir e estabilizar a base nativa de **Windows x64 e Linux x86-64**, sem otimização prematura. Cada marco só muda para concluído com evidência reproduzível.

## Ordem obrigatória de plataformas

Até o porte de Pokémon Platinum para PC estar pronto e validado, **todo o desenvolvimento ativo de Platinum fica restrito a Windows x64 e Linux x86-64**. Android e iOS permanecem pausados: não iniciar backend gráfico móvel, shell mobile, builds ARM64/Xcode, workflows ou tarefas de paridade móvel neste período. A documentação móvel existente é apenas registro de pesquisa e não altera essa prioridade.

O retorno ao desenvolvimento móvel fica condicionado a todos estes critérios no PC:

- builds limpos e empacotados de Windows e Linux aprovados na CI atual, com testes ROM-free verdes;
- importação local da ROM Pokémon Platinum USA Rev. 1, preparação dos dados e chegada reproduzível à tela de título;
- sessão de jogo real com movimentação, menus, transições, batalha, áudio e entradas validadas;
- salvamento, encerramento, retomada e carregamento de progresso confirmados sem corrupção;
- launcher, logs e mensagens de erro validados nos dois sistemas; idioma original e pacote PT-BR testados sem regressão.

Compilação, smoke test sem ROM ou aprovação isolada de uma plataforma não satisfazem esse gate. Só depois da validação conjunta de Windows e Linux a trilha Android/iOS será reaberta.

O alvo Android foi encerrado em 29/10/2026 após falhas recorrentes na validação do pipeline ARM64; essa decisão histórica não muda a prioridade acima.

## Trilha paralela — Pokémon Black Version

O porte de Black será desenvolvido em paralelo ao de Platinum, sem misturar seus runtimes ou contratos de ROM. A etapa atual é a auditoria das bases públicas [aletheia](https://github.com/Project-Holon/aletheia) e [eidos](https://github.com/Project-Holon/eidos); ainda não há build de Black produzido por este repositório. O plano com dependências, riscos e critérios está em [POKEMON_BLACK_PORT.md](POKEMON_BLACK_PORT.md).

- [x] Auditar as licenças e fixar revisões compatíveis de `aletheia` (`6c2aae879f123bcbc028cf6a8b7f8df614402ac8`) e `eidos` (`b79123f967980d1bb758161891205c03d606dec7`).
- [ ] Concluir o workflow de validação Black sem ROM, incluindo fechamento das dependências nativas staged para Windows x64/Linux x86-64; corrigir falhas antes de considerar o marco compilável validado.
- [ ] Resolver a situação jurídica do código reconstruído de jogo antes de publicar executáveis Black.
- [ ] Auditar licença, árvore de dependências, commits e condições de build do upstream antes de incorporá-lo.
- [ ] Confirmar viabilidade de builds nativos Windows x64 e Linux x86-64, incluindo a transição de 32 para 64 bits se necessária.
- [ ] Implementar validador de ROM e gestão de dados próprios para Black; nunca reutilizar o hash ou o runtime de Platinum.
- [ ] Adicionar testes para o identificador `pokemon-black`, isolação de diretórios e preservação do fluxo atual de Platinum.
- [ ] Integrar o runtime ao launcher e habilitar importação somente após builds e testes por plataforma passarem.
- [ ] Confirmar tela de título e gameplay real com dados locais antes de anunciar jogabilidade.

A entrada de Black na interface é um anúncio de desenvolvimento, não uma funcionalidade já executável.

## Marco 0 — base real e processo de build

- [x] Escolher uma base que reutiliza código C reconstruído do jogo, em vez de uma recriação em engine genérica.
- [x] Fixar a revisão do porte desktop upstream e as revisões conhecidas das dependências Meson durante o build.
- [x] Restaurar referências temporariamente fixadas ao fim da compilação.
- [x] Criar scripts de build desktop e workflow de CI somente para main.
- [x] Documentar o escopo legal, a política de assets e a estratégia de localização.
- [x] Implementar um importador local com allowlist explícita de recursos NARC.
- [x] Adicionar testes sintéticos do importador, do fixador de dependências e da auditoria gráfica.
- [x] Confirmar compilação Linux x86-64 e Windows x64 e verificação dos pacotes na CI em 28/10/2026 ([execução 40647214112](https://github.com/CarlosCosta07-s/Platina_reluzente-/actions/runs/40647214112)).
- [x] Adicionar verificador local dos dados extraídos do runtime e dos sete NARC allowlisted.
- [x] Adicionar verificador do pacote runtime contra os 340 caminhos de `platinum.us/filesys.csv`, incluindo comparação SHA-256 e recursos de animação obrigatórios.

> O sucesso da compilação Linux prova que o alvo nativo é compilável pelo pipeline; não prova que o jogo inicia nem que seja jogável.

## Marco 1 — inicialização desktop reproduzível

- [x] Build limpo Linux x86-64 na CI, sem artefatos de build preexistentes.
- [x] Compilar o executável Windows x64 na CI.
- [x] Confirmar que os pacotes Linux e Windows contêm os arquivos de animação obrigatórios `wazaeffect/we.arc` e `battle/skill/waza_seq.narc` e passam pela verificação dos 340 caminhos do manifesto.
- [ ] Executar o jogo com a ROM local USA Rev. 1, confirmar extração dos dados, tela de título e início de uma nova partida; a execução atual da CI não fornece ROM.
- [x] Testar o AppImage Linux em diretório temporário vazio: a janela `libntr Application` foi encontrada e o processo permaneceu ativo por 15 segundos na execução [40691585390](https://github.com/CarlosCosta07-s/Platina_reluzente-/actions/runs/40691585390). Isso só cobre a interface pré-ROM.
- [x] Automatizar o staging do launcher para incluir somente o executável nativo portátil e bibliotecas necessárias, recusando ROMs, patches, saves, links simbólicos e entradas especiais; os recursos do jogo são extraídos localmente da ROM importada no primeiro início.
- [x] Testar staging binário-only para Linux/Windows: AppImage portátil ou executável+DLLs, sem NARC/firmware/arquivos do jogo, e preservação do destino anterior quando o executável falta. Os 27 testes da suíte do launcher passaram na execução [40890820802](https://github.com/CarlosCosta07-s/Platina_reluzente-/actions/runs/40890820802), em 29/10/2026.
- [ ] Reproduzir as instruções numa máquina limpa.
- [ ] Gerar e validar os launchers integrados Windows/Linux na CI, com o executável já incluído e artefatos sem recursos do jogo.
- [ ] Reproduzir o primeiro carregamento com uma cópia local válida da ROM USA Rev. 1 e verificar os erros de extração/carregamento.
- [ ] Confirmar que logs e erros de carregamento identificam os problemas.
- [x] Manter ROMs e recursos derivados fora do repositório e dos artefatos de CI.

## Marco 2 — original + PT-BR

### Decisão de arquitetura

- A versão de execução continua sendo a ROM original Pokémon Platinum USA Rev. 1; o jogador não precisa selecionar nem manter uma ROM modificada.
- O launcher terá um seletor de idioma antes da inicialização: **English (original)** e **Português (Brasil)**. A escolha ficará salva nas configurações locais do aplicativo.
- A tradução será uma camada/pacote de recursos separado, aplicada a um ambiente de execução local específico para o idioma. A ROM de origem e os recursos-base originais não devem ser alterados.
- O launcher deverá validar a versão e os hashes do pacote PT-BR, recusar pacotes incompletos/incompatíveis com uma mensagem clara e nunca fingir que o jogo foi traduzido se os recursos não estiverem disponíveis.
- A alternância de idioma deverá preservar os dados de progresso e os arquivos de configuração compartilhados; isso precisa de teste real de salvar, mudar idioma e carregar.
- O formato e a distribuição do pacote de tradução serão avaliados legalmente antes de qualquer inclusão em releases. ROMs e arquivos extraídos do jogo não serão colocados no Git ou nos artefatos públicos da CI.

### Inventário e trabalho restante

- [x] Comparar localmente 462 entradas FAT das ROMs de referência usadas na análise.
- [x] Identificar dez diferenças e separar sete recursos NARC localizados de dois utility.bin e uma entrada FAT sem caminho conhecido.
- [x] Definir allowlist dos sete recursos NARC não executáveis; os binários fora dessa lista continuam excluídos.
- [x] Verificar localmente que os sete NARC da referência PT-BR correspondem ao manifesto SHA-256 e têm blocos NARC essenciais válidos.
- [x] Comparar os caminhos das duas imagens: sete NARC localizados são permitidos; `data/utility.bin`, `dwc/utility.bin` e a entrada FAT sem caminho são excluídos.
- [x] Conferir que a ROM PT-BR de referência tem byte de revisão `0`, enquanto o launcher exige Rev. 1 (`0x1E == 1`).
- [x] Verificar o novo ZIP USA: SHA-1 `ce81046eda7d232513069519cb2085349896dec7`, CRC-32 `9253921D`, byte de revisão `0` — ROM oficial Rev. 0, recusada pelo alvo nativo Rev. 1.
- [x] Verificar que o CRC-base documentado pelo patch E4T (`1D8A5220`) não corresponde à ROM Rev. 0 enviada (`9253921D`) nem à Rev. 1 (`69D628E8`).
- [x] Comparar os sete NARC allowlisted entre a ROM Rev. 0 enviada e a referência PT-BR: os sete caminhos e IDs FAT coincidem, todos são NARC válidos e a referência traduzida passa nos hashes aprovados.
- [x] Endurecer o importador do launcher para exigir o SHA-1 integral exato da ROM Rev. 1 antes de instalar a cópia local; teste de regressão mantém a ROM anterior se o hash falhar.
- [x] Registrar stdout/stderr do runtime nativo em `native-startup.log` e mostrar o caminho no launcher quando o processo é iniciado; a mensagem deixa claro que isso não prova a tela de título.
- [x] Implementar fallback de extração automática a partir da ROM importada quando faltar um recurso local: tenta uma vez, reabre o recurso e encerra com log se continuar ausente; não chama um seletor de ROM duplicado nem mantém recursão infinita.
- [ ] Validar o patch Xdelta v1.2.0 contra uma ROM que corresponda à base documentada CRC-32 `1D8A5220`; essa aplicação ainda não foi executada.
- [ ] Criar e testar o pacote/overlay PT-BR isolado sem modificar a ROM original.
- [ ] Refatorar o importador atual, que ainda espera uma fonte PT-BR e substitui arquivos no runtime, para criar/validar uma camada de tradução isolada sem modificar a base original.
- [ ] Definir um manifesto versionado do pacote de idioma, com versão-base compatível, caminho permitido, tamanho e SHA-256 por recurso.
- [ ] Adicionar ao launcher o seletor English/PT-BR e persistir a preferência em armazenamento local do aplicativo.
- [ ] Aplicar os recursos PT-BR apenas ao ambiente de execução selecionado; manter intactos a ROM importada e os recursos originais.
- [ ] Impedir inicialização em PT-BR quando o pacote não estiver instalado, for incompleto ou falhar na validação; apresentar uma mensagem clara em vez de voltar silenciosamente para inglês.
- [ ] Validar execução com a ROM USA Rev. 1 e recursos originais antes de testar o pacote PT-BR.
- [ ] Testar fontes, acentos, menus, diálogos, tela de título, batalhas, eventos, salvamento e carregamento; confirmar que alternar idioma não perde progresso.
- [ ] Investigar separadamente diferenças fora da allowlist sem importar binários desconhecidos.

## Marco 3 — fidelidade e estabilidade

- [ ] Comparar telas e comportamento com a versão original.
- [ ] Corrigir renderização, temporização, áudio, entrada, carregamento e salvamento.
- [ ] Criar testes de regressão para correções.
- [ ] Só então avaliar resolução ampliada, escalonamento, melhorias visuais e desempenho.

## Marco 4 — distribuição responsável

- [ ] Auditar licenças do código original reconstruído e das dependências.
- [ ] Garantir que nenhum recurso protegido seja empacotado ou espelhado indevidamente.
- [ ] Preparar instruções que exijam dados locais do próprio usuário.
- [ ] Publicar somente artefatos cuja redistribuição e licenciamento tenham sido revisados.

## O que não conta como conclusão

Uma janela vazia, uma tela de teste isolada, um executável que não carrega os dados, stubs que fingem sucesso, ou um build que só funciona em ambiente preexistente não comprovam o porte. Os marcos exigem evidência concreta e testes registrados.
