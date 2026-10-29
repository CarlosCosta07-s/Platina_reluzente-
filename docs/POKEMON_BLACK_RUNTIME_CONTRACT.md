# Pokémon Black — contrato de integração com o launcher

**Estado:** especificação de desenvolvimento; ainda não há integração executável no launcher. Este documento define como ligar um build local do Eidos ao launcher sem reutilizar o runtime, a ROM, os dados ou os saves de Pokémon Platinum.

## Decisões obrigatórias

1. **Runtime fornecido localmente pelo desenvolvedor/usuário.** Não incluir `eidos`, `eidos.exe`, SDL3.dll ou código derivado de Aletheia nos pacotes públicos do Platina Reluzente enquanto a situação de licença não autorizar essa distribuição. A tela deve explicar por que um runtime local é necessário.
2. **Identidade própria do jogo.** O identificador interno é `pokemon-black`; não reutilizar `ORIGINAL_ROM_SHA1`, os caminhos `roms/current.nds`, `runtime/` ou qualquer estado de Platinum.
3. **Validar a ROM antes de executar.** O alvo documentado no par de commits fixados é Pokémon Black USA/Europe NDSi Enhanced, SHA-1 `26ad0b9967aa279c4a266ee69f52b9b2332399a5`, tamanho `268435456` bytes. A validação deve comparar o hash SHA-1 integral da imagem importada, além de checar extensão, tamanho e leitura. O runtime Eidos também valida a imagem durante `--rom`; a verificação do launcher não substitui essa validação.
4. **Não abrir dois seletores.** Depois de o launcher importar e validar a ROM, passe o caminho privado da cópia importada por `--rom`. O Eidos tem seu próprio fluxo de primeira execução, mas `--rom` permite que o runtime faça a extração sem pedir que o usuário selecione o mesmo arquivo de novo.
5. **Dados e saves isolados.** Passe explicitamente `--data-root` para uma pasta de extração dedicada ao Black e defina `EIDOS_HOME` para a configuração do Eidos. Isso, sozinho, não isola os saves: a revisão fixada usa `APPDATA\eidos\saves` no Windows e `XDG_DATA_HOME/eidos/saves` no Linux. Ao iniciar o processo filho, defina `APPDATA` (Windows) ou `XDG_DATA_HOME` (Linux) para uma raiz privada do Black.
6. **Não confundir `spawn` com prontidão.** Criar o processo só confirma que o sistema operacional conseguiu iniciá-lo. O estado “jogo iniciado” não deve afirmar que a tela de título apareceu sem um sinal de prontidão ou validação visual.
7. **Logs sem dados protegidos.** Guardar stdout/stderr num log específico do Black. Logs de erro podem mostrar caminhos locais; revisar/redigir esses caminhos antes de compartilhar. Nunca anexar ROM, saves ou recursos extraídos ao relatório.

## Localização dos arquivos por sistema

| Dado | Windows x64 | Linux x86-64 |
|---|---|---|
| ROM privada importada | `%LOCALAPPDATA%\Platina-Reluzente\PokemonBlack\roms\current.nds` | `$XDG_DATA_HOME/platina-reluzente/pokemon-black/roms/current.nds` (ou `~/.local/share/platina-reluzente/pokemon-black/roms/current.nds`) |
| Dados extraídos | `%LOCALAPPDATA%\Platina-Reluzente\PokemonBlack\extract` | `$XDG_DATA_HOME/platina-reluzente/pokemon-black/extract` (ou `~/.local/share/platina-reluzente/pokemon-black/extract`) |
| Home/config Eidos | `%LOCALAPPDATA%\Platina-Reluzente\PokemonBlack\eidos-home` | `$HOME/.local/share/platina-reluzente/pokemon-black/eidos-home` |
| Saves Eidos (diretório privado do processo) | `%LOCALAPPDATA%\Platina-Reluzente\PokemonBlack\process-appdata\eidos\saves` | `$HOME/.local/share/platina-reluzente/pokemon-black/process-data/eidos/saves` |
| Log do launcher | `%LOCALAPPDATA%\Platina-Reluzente\PokemonBlack\logs\native-startup.log` | `$XDG_STATE_HOME/platina-reluzente/pokemon-black/native-startup.log` ou pasta de logs dos dados locais |

Os caminhos acima são o contrato proposto para a integração futura, não uma afirmação de que o launcher já os cria. Resolver e normalizar os caminhos uma vez, validar permissões e diretórios antes de importar, e não escrever nada na raiz do repositório.

## Descoberta do runtime local

- O desenvolvedor seleciona a pasta que contém o executável host que ele compilou a partir das revisões fixadas. O executável esperado é `eidos.exe` no Windows e `eidos` no Linux, no diretório `build64/host` do build descrito em [POKEMON_BLACK_LOCAL_BUILD.md](POKEMON_BLACK_LOCAL_BUILD.md).
- No Windows, verificar a presença de `SDL3.dll` junto ao executável, conforme a configuração host upstream. Não presumir que uma DLL ausente possa ser suprida pelo runtime de Platinum.
- No Linux, verificar que o binário é executável e documentar as dependências dinâmicas requeridas pelo build local; não reutilizar AppImage, bibliotecas nem executáveis do porte de Platinum como substitutos.
- Recusar um caminho que esteja ausente, seja diretório, seja link simbólico inesperado ou não contenha o executável correto da plataforma. Não adivinhar executáveis diferentes.
- Persistir apenas o caminho selecionado e a identidade/versão do build local em metadados privados do launcher. Nunca copiar o binário Eidos automaticamente para dentro do pacote público.

## Contrato de inicialização

A chamada do processo segue este formato, após a validação da ROM e a criação dos diretórios privados:

Windows (PowerShell):
```powershell
$env:EIDOS_HOME = Join-Path $env:LOCALAPPDATA "Platina-Reluzente\PokemonBlack\eidos-home"
$env:APPDATA = Join-Path $env:LOCALAPPDATA "Platina-Reluzente\PokemonBlack\process-appdata"
$eidosArgs = @(
  "--rom", (Join-Path $env:LOCALAPPDATA "Platina-Reluzente\PokemonBlack\roms\current.nds"),
  "--data-root", (Join-Path $env:LOCALAPPDATA "Platina-Reluzente\PokemonBlack\extract")
)
& "C:\caminho\do\build64\host\eidos.exe" @eidosArgs
```

Linux:
```sh
export EIDOS_HOME="$HOME/.local/share/platina-reluzente/pokemon-black/eidos-home"
export XDG_DATA_HOME="$HOME/.local/share/platina-reluzente/pokemon-black/process-data"
./build64/host/eidos \
  --rom "$HOME/.local/share/platina-reluzente/pokemon-black/roms/current.nds" \
  --data-root "$HOME/.local/share/platina-reluzente/pokemon-black/extract"
```

Na revisão Eidos fixada, `EIDOS_HOME` controla a configuração e a instalação padrão, mas o código de saves usa variáveis separadas (`sdk/plat_save.c`). No launcher Electron, crie e valide também as raízes `APPDATA`/`XDG_DATA_HOME` antes de `spawn(executable, args, { cwd, env, shell: false, stdio })`. Passe argumentos como array, defina `cwd` para uma pasta adequada ao runtime local e mantenha o log de Black separado. Um caminho de ROM com espaços deve funcionar sem aspas manuais dentro dos argumentos.

## Critérios antes de habilitar o cartão Black

- [ ] A CI conclui com sucesso testes upstream sem ROM e builds host Windows x64/Linux x86-64.
- [ ] Um build local selecionado é detectado e sua versão/caminho são exibidos sem instalar nem redistribuir executáveis.
- [ ] O importador Black valida o SHA-1 e instala a ROM de maneira transacional, com recuperação em falha, sem afetar os metadados de Platinum.
- [ ] Testes confirmam que ROM, configuração, dados extraídos, saves e logs Black ficam separados de Platinum.
- [ ] O launcher passa `--rom` e `--data-root` e define `EIDOS_HOME`; nenhum segundo seletor de ROM aparece.
- [ ] Uma ROM local compatível chega à tela de título, aceita comandos e confirma salvamento/retomada em teste manual documentado.
- [ ] A distribuição do código e dos binários derivados de Aletheia foi revista juridicamente antes de qualquer artefato público.

## Referências upstream fixadas

- [Eidos — revisão `b79123f967980d1bb758161891205c03d606dec7`](https://github.com/Project-Holon/eidos/tree/b79123f967980d1bb758161891205c03d606dec7)
- [Aletheia — revisão `6c2aae879f123bcbc028cf6a8b7f8df614402ac8`](https://github.com/Project-Holon/aletheia/tree/6c2aae879f123bcbc028cf6a8b7f8df614402ac8)
- [Fluxo de primeira execução e `--rom`/`--data-root`](https://github.com/Project-Holon/eidos/blob/b79123f967980d1bb758161891205c03d606dec7/docs/installer.md)
- [Camada de dados e `BW_DATA_ROOT`](https://github.com/Project-Holon/eidos/blob/b79123f967980d1bb758161891205c03d606dec7/docs/files.md)
- [Guia de compilação local](POKEMON_BLACK_LOCAL_BUILD.md)
- [Auditoria, pins e limite jurídico deste projeto](POKEMON_BLACK_PORT.md)
