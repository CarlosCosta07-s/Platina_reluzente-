# Roteiro de desenvolvimento

O foco inicial é **conseguir compilar e executar a base nativa**, sem otimização prematura. Cada marco só muda para concluído depois de uma prova reproduzível.

## Marco 0 — base real e processo de build

- [x] Escolher uma base que reutiliza código C reconstruído do jogo, em vez de uma recriação em engine genérica.
- [x] Fixar a revisão do porte desktop upstream como dependência de código.
- [x] Criar scripts de build desktop e workflow de CI somente para main.
- [x] Documentar o escopo legal, a política de assets e a estratégia de localização.
- [x] Implementar um importador local que extrai somente os três bancos de texto necessários.
- [x] Adicionar testes sintéticos do importador e executar localmente contra as duas cópias fornecidas.
- [x] Confirmar que a compilação do alvo Linux x86-64 passa na CI em 28/10/2026 ([execução 40625184953](https://github.com/CarlosCosta07-s/Platina_reluzente-/actions/runs/40625184953)).
- [ ] Confirmar que a compilação do alvo Windows x64 passa na CI.

> O sucesso da compilação Linux confirma que o alvo nativo pode ser construído pelo pipeline; não confirma que o jogo inicia nem que seja jogável.

## Marco 1 — inicialização desktop reproduzível

Critérios de aceite:
- [x] build limpo Linux x86-64 na CI, sem arquivos de build pré-existentes;
- [ ] build limpo Windows x64 na CI;
- [ ] reproduzir as instruções numa máquina limpa;
- [ ] confirmar inicialização com uma cópia local válida da ROM USA Rev. 1;
- [ ] confirmar que logs e erros de carregamento identificam claramente os problemas;
- [x] manter ROMs e dados proprietários fora do repositório e dos artefatos da CI.

## Marco 2 — original + PT-BR

- [x] Extrair localmente msgdata/msg.narc, msgdata/pl_msg.narc e msgdata/scenario/scr_msg.narc das duas cópias fornecidas.
- [ ] validar a execução com os textos originais depois de compilar o porte;
- [ ] importar os bancos PT-BR no diretório local usado pelo executável;
- [ ] testar acentos, fontes, menus, diálogos, eventos de história e save/load;
- [ ] testar separadamente qualquer divergência de executável/dados da ROM modificada.

## Marco 3 — Android nativo

- [ ] auditar APIs desktop e shaders usados pela camada gráfica nativa;
- [ ] decidir com base em protótipo técnico entre um backend OpenGL ES e um backend Vulkan;
- [ ] implementar backend de renderização Android sem stubs para operações obrigatórias;
- [ ] integrar Android NDK, ciclo de vida, toque, controles, áudio e armazenamento;
- [ ] gerar APK arm64-v8a por CI, sem ROMs ou conteúdo do jogo;
- [ ] smoke test em dispositivo real e registro de logs;
- [ ] confirmar inicialização, jogo, áudio, salvamento, pausa e retomada.

## Marco 4 — fidelidade e estabilidade

- [ ] comparar telas e comportamento com a versão original;
- [ ] corrigir renderização, temporização, áudio, entrada, carregamento e salvamento;
- [ ] criar testes de regressão para correções;
- [ ] só então avaliar resolução ampliada, escalonamento, melhorias visuais e desempenho.

## Marco 5 — distribuição responsável

- [ ] auditar licenças do código original reconstruído e de todas as dependências;
- [ ] garantir que nenhum recurso protegido seja empacotado ou espelhado indevidamente;
- [ ] preparar instruções que exijam dados locais do próprio usuário;
- [ ] publicar somente artefatos cuja redistribuição e licenciamento tenham sido revisados.

## O que não conta como conclusão

Uma janela vazia, uma tela de teste isolada, um executável que não carrega os dados, stubs que fingem sucesso, ou um build que só funciona em ambiente preexistente não comprovam o porte do jogo. Os marcos exigem evidência concreta e testes registrados.
