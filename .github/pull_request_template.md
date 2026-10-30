## O que muda

<!-- Explique o problema e a solução em poucas linhas. -->

## Checklist

- [ ] Não inclui ROMs, firmware, arquivos NARC/extraídos, saves nem patches binários.
- [ ] Testes ROM-free passam: `python3 scripts/test.py --quick` e `cd launcher-app && npm test`.
- [ ] Mudanças em `scripts/prepare_native_runtime.py` foram aplicadas e compiladas contra o commit fixado do upstream.
- [ ] A documentação não afirma jogabilidade ou tela de título sem evidência reproduzível.
- [ ] Se o comportamento visível ao usuário mudou, `CHANGELOG.md` foi atualizado.
