# Roteiro de desenvolvimento

O foco inicial é compilar e executar a base nativa, sem otimização prematura. Cada marco só muda para concluído com evidência reproduzível.

## Marco 0 — base real e processo de build

- [x] Escolher uma base que reutiliza código C reconstruído do jogo, em vez de uma recriação em engine genérica.
- [x] Fixar a revisão do porte desktop upstream e as revisões conhecidas das dependências Meson durante o build.
- [x] Restaurar referências temporariamente fixadas ao fim da compilação.
- [x] Criar scripts de build desktop e workflow de CI somente para main.
- [x] Documentar o escopo legal, a política de assets e a estratégia de localização.
- [x] Implementar um importador local com allowlist explícita de recursos NARC.
- [x] Adicionar testes sintéticos do importador, do fixador de dependências e da auditoria gráfica.
- [x] Confirmar compilação Linux x86-64 e Windows x64 na CI em 28/10/2026 ([execução 40627263360](https://github.com/CarlosCosta07-s/Platina_reluzente-/actions/runs/40627263360)).
- [x] Adicionar verificador local dos dados extraídos do runtime e dos sete NARC allowlisted.

> O sucesso da compilação Linux prova que o alvo nativo é compilável pelo pipeline; não prova que o jogo inicia nem que seja jogável.

## Marco 1 — inicialização desktop reproduzível

- [x] Build limpo Linux x86-64 na CI, sem artefatos de build preexistentes.
- [x] Build limpo Windows x64 na CI.
- [ ] Reproduzir as instruções numa máquina limpa.
- [ ] Confirmar inicialização com uma cópia local válida da ROM USA Rev. 1.
- [ ] Confirmar que logs e erros de carregamento identificam os problemas.
- [x] Manter ROMs e recursos derivados fora do repositório e dos artefatos de CI.

## Marco 2 — original + PT-BR

- [x] Comparar localmente 462 entradas FAT das ROMs fornecidas.
- [x] Identificar dez diferenças e separar sete recursos NARC localizados de dois utility.bin e uma entrada FAT não mapeada.
- [x] Criar allowlist de sete NARC não executáveis para importação local, sem modificar a ROM.
- [ ] Validar execução com os recursos originais depois de compilar o porte.
- [ ] Importar os sete NARC PT-BR no diretório local do executável.
- [ ] Testar acentos, fontes, menus, diálogos, tela de título, batalhas, eventos e save/load.
- [ ] Investigar separadamente diferenças fora da allowlist sem importar binários desconhecidos.

## Marco 3 — Android nativo

- [x] Fazer auditoria estática inicial do contexto, shaders e APIs OpenGL desktop.
- [x] Selecionar SDL2 + OpenGL ES 3.2 como primeira hipótese a prototipar, não suporte concluído.
- [ ] Compilar um protótipo GLES 3.2 e comprovar shaders, FBO e caminhos de textura num dispositivo Android.
- [ ] Adaptar operações incompatíveis sem stubs que finjam sucesso.
- [ ] Integrar Android NDK, ciclo de vida, toque, controles, áudio e armazenamento.
- [ ] Gerar APK arm64-v8a por CI, sem ROMs ou conteúdo do jogo.
- [ ] Testar inicialização, gameplay, áudio, salvamento, pausa e retomada.

## Marco 4 — fidelidade e estabilidade

- [ ] Comparar telas e comportamento com a versão original.
- [ ] Corrigir renderização, temporização, áudio, entrada, carregamento e salvamento.
- [ ] Criar testes de regressão para correções.
- [ ] Só então avaliar resolução ampliada, escalonamento, melhorias visuais e desempenho.

## Marco 5 — distribuição responsável

- [ ] Auditar licenças do código original reconstruído e das dependências.
- [ ] Garantir que nenhum recurso protegido seja empacotado ou espelhado indevidamente.
- [ ] Preparar instruções que exijam dados locais do próprio usuário.
- [ ] Publicar somente artefatos cuja redistribuição e licenciamento tenham sido revisados.

## O que não conta como conclusão

Uma janela vazia, uma tela de teste isolada, um executável que não carrega os dados, stubs que fingem sucesso, ou um build que só funciona em ambiente preexistente não comprovam o porte. Os marcos exigem evidência concreta e testes registrados.
