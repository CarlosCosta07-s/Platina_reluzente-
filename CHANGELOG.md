# Registro de mudanças

Formato livre, mais recente primeiro. Só entram mudanças que existem no `main`. Nada aqui comprova tela de título ou jogabilidade; isso exige teste com uma ROM local.

## Não lançado

### Platinum
- Preparo dos dados em fase separada (`--platina-prepare`), com progresso no launcher, extração em staging e cache verificado por CRC-32 ligado ao SHA-256 da ROM.
- Diagnósticos de falha na preparação, marcadores de etapa e heartbeat de frames no log.
- Correções no extrator da ROM e no log de compilação de shaders.
- Seletor de idioma e pacote PT-BR isolado e verificado, sem alterar a ROM original.
- Runner de testes ROM-free (`scripts/test.py`).

### Launcher
- Visual de console de mesa, sempre em tela cheia (F11 alterna), relógio sincronizado com o sistema e indicador de bateria.
- Verificação assíncrona do manifesto do runtime.

### Projeto
- Modelos de issue e de pull request, `CONTRIBUTING.md`, `docs/TROUBLESHOOTING.md`, `.editorconfig` e `.gitattributes`.
- Android encerrado em 29/10/2026; ver `docs/MOBILE_PORT.md` para a análise de viabilidade de um futuro porte móvel.
