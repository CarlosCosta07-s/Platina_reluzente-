# Solução de problemas

Esta página usa só o que o launcher e o runtime já registram. Nenhum passo exige enviar a ROM.

## Onde ficam os arquivos

| O quê | Windows | Linux |
|---|---|---|
| Dados do launcher | `%APPDATA%\platina-reluzente-launcher` | `~/.config/platina-reluzente-launcher` |
| Log de inicialização | `...\logs\native-startup.log` | `.../logs/native-startup.log` |
| Cópia gravável do runtime e dados extraídos | `...\runtime` | `.../runtime` |
| ROM importada (cópia privada) | `...\roms\current.nds` | `.../roms/current.nds` |

O botão **Abrir log de inicialização** do launcher abre o log direto. Para reportar um problema, copie só as últimas linhas dele.

## Como ler o log

Cada tentativa começa com `--- Native launch request ---`. As etapas aparecem como marcadores:

`verifying` → `extracting` → `ready` (preparo dos dados) → `native-boot-start` → `window-ready` → `renderer-ready` → `heartbeat` (jogo desenhando).

O último marcador que apareceu mostra até onde o jogo chegou.

| Você vê | Provável significado | O que fazer |
|---|---|---|
| Para em `verifying` ou `extracting` | Preparo em andamento ou travado | A primeira vez leva minutos. Se passar de 20 min, envie o log. |
| `Cache validation failed` em toda abertura | O cache de extração nunca é aceito | Envie o log; veja a linha logo antes (`Overlay validation failed`, `Cannot open ... locked or missing`). |
| `Cannot open ... (locked or missing)` | Antivírus ou indexador segurando o arquivo | Exclua a pasta `runtime` das verificações em tempo real e tente de novo. |
| `process exit: code=2` | ROM ou ambiente inválido (ROM sem SHA-256, caminho inseguro) | Importe a ROM de novo pelo launcher. |
| `process exit: code=4` | Dados extraídos ausentes ou corrompidos | Apague a pasta `runtime` (copie `save.bin` antes, se existir) e inicie de novo. |
| `SDL ... failed` ou `OpenGL ...` | GPU/driver sem OpenGL 4.2 | Atualize o driver. Em máquina virtual, ative aceleração 3D. |
| Janela preta e "não está respondendo" sem erro | O jogo travou antes do primeiro frame | Envie o log: o último marcador mostra onde parou. |

Os códigos de saída podem mudar entre versões; vale o texto da mensagem no log.

## Limpar e recomeçar

1. Feche o jogo e o launcher.
2. Copie `save.bin` (dentro de `runtime`) para um lugar seguro, se existir.
3. Apague a pasta `runtime`. A ROM importada não é afetada.
4. Abra o launcher e inicie o jogo: o runtime e os dados são preparados de novo.
5. Para restaurar o save, copie `save.bin` de volta **depois** do primeiro preparo e com o jogo fechado.

## O que enviar ao reportar

- O texto do trecho final do `native-startup.log`.
- Sistema operacional, placa de vídeo e versão do driver.
- De qual execução do GitHub Actions você baixou o launcher.

**Nunca envie:** a ROM, a pasta `runtime`, `save.bin`, `firmware.bin` ou arquivos `.narc`.
