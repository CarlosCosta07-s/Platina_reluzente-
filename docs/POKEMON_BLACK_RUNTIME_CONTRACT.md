# Pokémon Black — contrato de integração com o launcher

**Estado em 29/10/2026:** o cartão de Black, a seleção de jogo e a importação local da ROM fazem parte da biblioteca única. A seleção externa de executáveis foi removida. O runtime ainda não é empacotado porque a licença de `aletheia/src/` não concede atualmente autorização clara para redistribuir o código reconstruído ou binários derivados; por isso o botão **Iniciar** permanece desativado.

## Princípios de integração

1. **Um único aplicativo.** O usuário abre Platina Reluzente, escolhe Platinum ou Black na biblioteca e inicia o jogo pelo próprio launcher. Nenhum seletor de pastas deve pedir que ele encontre `eidos.exe` ou `eidos`, e nenhum executável secundário deve ser apresentado como outro aplicativo. A implementação interna pode usar um processo filho para o runtime nativo, mas somente o launcher é uma ação visível ao usuário.
2. **Runtime interno do pacote.** A pasta de recurso reservada é `black-runtime/` no desenvolvimento e `process.resourcesPath/black-runtime` no pacote desktop. Depois de resolvida a situação de distribuição, o empacotamento poderá incluir ali o runtime de plataforma e as bibliotecas necessárias. Não copiar para essa pasta binários obtidos localmente enquanto não houver autorização jurídica.
3. **Sem emulador ou interpretador ARM.** O alvo é o porte nativo baseado no código C reconstruído e na cadeia de build de Eidos/Aletheia. O módulo de jogo é compilado em código nativo via a ferramenta de build do upstream; não queremos executar uma CPU Nintendo DS emulada durante a partida.
4. **Validar a ROM antes de usá-la.** O alvo fixado é Pokémon Black USA/Europe NDSi Enhanced, SHA-1 `26ad0b9967aa279c4a266ee69f52b9b2332399a5`, tamanho `268435456` bytes. O importador confere extensão, tamanho, cabeçalho e hash SHA-1 integral. A ROM permanece no dispositivo e não deve ser enviada para CI ou para o repositório.
5. **Sem segundo seletor de ROM.** Ao iniciar, passe o caminho da cópia privada importada pelo argumento `--rom`; passe `--data-root` para a extração local. O fluxo inicial do runtime não deve voltar a pedir ao usuário para selecionar a mesma ROM.
6. **Isolamento de dados.** ROM, extração, configuração, saves e logs de Black devem ficar separados de Platinum. Passe `EIDOS_HOME` à configuração e, para saves, use também `APPDATA` no Windows ou `XDG_DATA_HOME` no Linux apontando para raízes exclusivas de Black. Recuse `portable.txt`, pois o modo portátil do upstream pode contornar essa separação.
7. **Falha segura e estado honesto.** Se o runtime interno estiver ausente, a UI explica que a integração está bloqueada e mantém Iniciar desabilitado. Uma ROM importada não significa que o jogo esteja iniciável. O início de processo não significa que a tela de título foi atingida.

## Caminhos locais

| Dado | Windows | Linux |
|---|---|---|
| ROM e metadados | `%LOCALAPPDATA%\\Platina-Reluzente\\PokemonBlack\\roms` e `rom-import.json` | `$XDG_DATA_HOME/platina-reluzente/pokemon-black/roms` e `rom-import.json` |
| Extração | `%LOCALAPPDATA%\\Platina-Reluzente\\PokemonBlack\\extract` | `$XDG_DATA_HOME/platina-reluzente/pokemon-black/extract` |
| Configuração Eidos | `%LOCALAPPDATA%\\Platina-Reluzente\\PokemonBlack\\eidos-home` | `$XDG_DATA_HOME/platina-reluzente/pokemon-black/eidos-home` |
| Saves do processo filho | `%LOCALAPPDATA%\\Platina-Reluzente\\PokemonBlack\\process-appdata` | `$XDG_DATA_HOME/platina-reluzente/pokemon-black/process-data` |
| Log de inicialização | `%LOCALAPPDATA%\\Platina-Reluzente\\PokemonBlack\\logs\\native-startup.log` | `$XDG_DATA_HOME/platina-reluzente/pokemon-black/logs/native-startup.log` |

Estes caminhos descrevem a implementação atual do helper `blackPaths()`. ROMs e recursos extraídos não devem ser escritos na raiz do repositório.

## Estrutura do runtime empacotado (quando autorizado)

- Windows: `black-runtime/eidos.exe` e as DLLs necessárias (incluindo `SDL3.dll`, se fornecida pelo build selecionado).
- Linux: `black-runtime/eidos` executável, junto das bibliotecas dinâmicas necessárias ou de uma estratégia de dependências documentada.
- O runtime precisa ser compilado a partir dos commits upstream fixados e validado na CI para Windows x64 e Linux x86-64. Não substituir silenciosamente por executável, biblioteca ou recursos de Platinum.
- O launcher deve chamar o runtime com argumentos como array, `shell: false`, diretório de trabalho explícito e log separado; caminhos com espaços precisam funcionar sem quoting manual.

## Testes e critérios de aceite

- [x] O importador valida a identidade integral da ROM e persiste a cópia local de forma recuperável.
- [x] Os caminhos locais e metadados de Black não colidem com os de Platinum.
- [x] A UI apresenta Platinum e Black na mesma biblioteca, com navegação entre os cartões.
- [x] Não existe seletor de runtime externo no HTML, no preload nem nos handlers IPC.
- [x] O pacote reserva o caminho interno `black-runtime` sem incluir executáveis não autorizados.
- [ ] Resolver legalmente a distribuição do código derivado de Aletheia antes de incluir o runtime no pacote.
- [ ] Depois da autorização, empacotar e verificar o runtime integrado para Windows/Linux.
- [ ] Com uma ROM local compatível, validar extração, tela de título, controles, áudio, salvamento e retomada. A CI sem ROM não comprova gameplay.

## Referências

- [Plano técnico](POKEMON_BLACK_PORT.md)
- [Guia de build local](POKEMON_BLACK_LOCAL_BUILD.md)
- [Aviso legal do Aletheia](https://github.com/Project-Holon/aletheia/blob/6c2aae879f123bcbc028cf6a8b7f8df614402ac8/LEGAL.md)
- [Build e avisos do Eidos](https://github.com/Project-Holon/eidos/blob/b79123f967980d1bb758161891205c03d606dec7/LEGAL.md)
