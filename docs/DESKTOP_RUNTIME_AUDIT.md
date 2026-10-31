# Auditoria do runtime Desktop — ciclo de vida e diagnóstico gráfico

**Escopo:** Windows x64 e Linux x86-64. Esta auditoria é source-level; não afirma validação manual de gameplay nem de encerramento em aparelho/PC físico.

## Revisão upstream examinada

Base nativa: `cybervisi0n/pokeplatinum` no commit `35067868f64f23d25d17ac3e536cfdd9a7f40523`. A dependência `libntr` usada pela preparação atual está fixada em `1555d911ac80c0190ac1c321f99f1323de8b3c09`.

Fontes examinadas:
- [libntr/sim_main.cpp na revisão fixada](https://github.com/cybervisi0n/libntr/blob/1555d911ac80c0190ac1c321f99f1323de8b3c09/libraries/sim/src/sim_main.cpp)
- [libntr/os_irqHandler.c na revisão fixada](https://github.com/cybervisi0n/libntr/blob/1555d911ac80c0190ac1c321f99f1323de8b3c09/libraries/os/src/os_irqHandler.c)
- [pokeplatinum/src/main.c na revisão nativa fixada](https://github.com/cybervisi0n/pokeplatinum/blob/35067868f64f23d25d17ac3e536cfdd9a7f40523/src/main.c)

## 1. Encerramento: risco real, correção ainda não aplicada

O fluxo observado é:

1. `OSi_InterruptDispatcher` chama `SIM_PreRenderVBlank()`, `SIM_Render(NULL)` e `SIM_PostRenderVBlank()` quando processa o VBlank.
2. `SIM_Render` processa eventos SDL. No evento `SDL_WINDOWEVENT_CLOSE`, a implementação upstream chama `exit(0)` diretamente.
3. O `NitroMain` de Platinum executa um `while (TRUE)` e não expõe, nesta revisão, um sinal de término normal do loop.
4. A inicialização cria subsistemas SDL (vídeo, áudio, timer, joystick), contexto OpenGL, threads PXI e thread de rede.

**Não trocar `exit(0)` por `return` ou por um simples `break`.** `SIM_Render` é chamada pelo caminho de VBlank; sair apenas dessa função não encerra `NitroMain` e pode deixar o runtime em estado parcialmente ativo. Também não devemos encerrar abruptamente enquanto uma gravação de save ou operação de backup estiver em andamento.

### Contrato para uma futura implementação

A implementação de encerramento seguro deve, antes do código:

- mapear o ciclo inteiro de gravação de save, incluindo operações assíncronas e confirmação de flush;
- definir como a solicitação de saída é comunicada do evento SDL ao loop principal sem executar operações de filesystem/SDL pesadas no caminho de VBlank;
- escolher um ponto seguro no loop de jogo para interromper a execução, sem duplicar ou interromper uma atualização de estado;
- interromper e aguardar threads PXI e rede antes de destruir recursos que elas usam;
- liberar joystick, áudio, recursos gráficos, contexto, janela e SDL em ordem definida e no thread proprietário adequado;
- garantir que uma falha em uma etapa não apresente um encerramento limpo falso; registrar a etapa e o erro.

### Testes obrigatórios

- fechar a janela antes do primeiro frame e durante gameplay;
- fechar enquanto o jogo está ocioso e imediatamente após uma operação de save;
- confirmar que saves antigos permanecem íntegros em caso de encerramento forçado;
- verificar que threads auxiliares terminaram antes da liberação dos recursos;
- testar fechamento repetido, perda de foco e falha em cada etapa de teardown;
- confirmar exit code e log de diagnóstico coerentes.

**Estado:** risco identificado; implementação bloqueada até o mapeamento completo do ciclo de save e do ciclo de vida das threads. A prioridade é não corromper progresso do usuário.

## 2. Diagnóstico de GPU e renderer OpenGL

A versão Desktop usa OpenGL 4.2 Core. Antes de escolher automaticamente um futuro backend Vulkan, o log persistente deve informar no início do renderer:

- backend realmente ativo;
- `GL_VENDOR`;
- `GL_RENDERER`;
- `GL_VERSION` e versão OpenGL numérica;
- `GL_SHADING_LANGUAGE_VERSION`.

Cada string precisa ser tratada como opcional (drivers podem retornar `NULL`). O registro deve ser enviado ao `native-startup.log` antes do primeiro handoff de frame, com flush explícito. Isso permite identificar drivers de software e reunir evidência de GPU sem inferir a compatibilidade pelo nome da marca.

Não usar a identificação para forçar uma escolha por fabricante. Perfis e seleção automática só virão após medições reproduzíveis no mesmo workload. Vulkan continuará sendo um segundo backend real, com fallback para OpenGL somente após teardown completo do backend que falhou.

## 3. Como as referências orientam esta auditoria

- **Gen1Recomp:** preservar dados locais, tornar as operações transacionais e separar preparação, execução e encerramento. Não tratar a existência do processo como prova de operação concluída.
- **Black Xbox:** respeitar dependências e sincronização entre runtime, IO, renderização e threads; não desmontar/encerrar recursos enquanto ainda podem estar em uso. Não copiar XISO/XBE nem sua forma de boot para NDS.
- **BT3 Decomp:** identificar GPU/driver/backend, permitir escolha explícita quando houver mais de uma implementação e só criar perfis automáticos usando benchmarks reais. O resultado de aparelhos Android do BT3 não é transportado como benchmark de PC.

## 4. Próxima sequência segura

1. Adicionar os metadados OpenGL ao log e compilar Windows/Linux.
2. Mapear APIs de save/backup e threads do runtime.
3. Desenhar e testar um protocolo de shutdown sem tocar no save ativo.
4. Só então substituir o `exit(0)` por solicitação cooperativa de término.
5. Depois da baseline OpenGL estável e do gameplay validado, iniciar o backend Vulkan Desktop.

Nenhuma ROM, firmware, recurso extraído ou save é necessário para estes testes ROM-free; a validação final de gameplay continua dependendo de uma cópia compatível mantida localmente pelo usuário.
