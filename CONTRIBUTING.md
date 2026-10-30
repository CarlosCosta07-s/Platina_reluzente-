# Como contribuir

Projeto comunitário, sem fins comerciais. Antes de mexer, leia [docs/LEGAL.md](docs/LEGAL.md).

## Regras que não mudam

- **Nada de dados protegidos:** ROMs, firmware, NARC extraídos, saves e patches binários nunca entram no Git, em issues, em artefatos de CI nem em releases.
- **Sem emulador e sem interpretador ARM:** o jogo roda como código C/C++ nativo.
- **Desenvolvimento direto na `main`:** não crie branches de trabalho (veja o README). Faça commits pequenos.
- **Honestidade de estado:** só marque algo como funcionando com evidência reproduzível. Compilar não prova que o jogo inicia.

## Preparar o ambiente

    git clone https://github.com/CarlosCosta07-s/Platina_reluzente-.git
    cd Platina_reluzente-
    git submodule update --init --recursive

Build nativo: [docs/BUILDING.md](docs/BUILDING.md). Launcher: `cd launcher-app && npm install`.

## Testes (nenhum exige ROM)

    python3 scripts/test.py --quick     # importador, cache, runtime
    python3 scripts/test.py --full      # toda a suíte Python
    cd launcher-app && npm test         # launcher (Node)

## Mexendo no código nativo

O C++ do jogo vem do upstream fixado. Alterações são aplicadas por `scripts/prepare_native_runtime.py` por substituição exata de texto, e falham de propósito se o upstream mudar. Ao editar esse script:

1. Teste contra o commit fixado do upstream, não contra a `main` dele.
2. Atualize `tools/tests/test_prepare_native_runtime.py`.
3. Confirme que a CI compila Linux e Windows antes de dar o trabalho por concluído.

## Reportar problemas

Use o modelo de issue e anexe apenas trechos do `native-startup.log`. Veja [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md). Vulnerabilidades: [SECURITY.md](SECURITY.md).
