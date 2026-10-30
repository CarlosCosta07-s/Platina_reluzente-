# Auditoria da base nativa com REA

## Estado desta integração

Este documento define o procedimento de investigação. **Nenhuma sessão REA foi executada nesta revisão**, porque não há um servidor/provedor REA conectado ao ambiente de edição atual. Os achados preliminares abaixo vêm de leitura estática dos arquivos-fonte no GitHub e precisam ser confrontados com o executável local usando REA antes de serem classificados como defeitos confirmados.

## Proveniência da base

O runtime desktop é compilado a partir de `cybervisi0n/pokeplatinum`, fixado atualmente em:

- Repositório: https://github.com/cybervisi0n/pokeplatinum
- Commit: `35067868f64f23d25d17ac3e536cfdd9a7f40523`
- Origem da lógica: https://github.com/pret/pokeplatinum
- Dependência gráfica/SDK desktop: https://github.com/cybervisi0n/libntr

O próprio `pret/pokeplatinum` descreve o trabalho como uma decompilação em andamento. Portanto, esta base é uma reconstrução em C que busca reproduzir o comportamento do jogo; não é o código-fonte original fornecido pela Game Freak. Os nomes de funções e estruturas também devem ser tratados como nomes de engenharia reversa, não como nomenclatura oficial.

A revisão do repositório upstream não encontrou uma licença geral na raiz de `pret/pokeplatinum` nem da cópia desktop consultada. Existem licenças próprias em algumas ferramentas e dependências. A GPL-3.0 deste projeto não substitui nem concede direitos sobre esses componentes. Antes de disponibilizar código derivado ou binários publicamente, cada componente e a autorização de distribuição precisam ser revisados.

## O papel do REA

O REA será usado para inspecionar os executáveis nativos de Windows/Linux, localizar funções, obter pseudocódigo e assembly, seguir chamadores/referências e conferir constantes. Ele complementa a leitura do C existente; não substitui os testes, compiladores, sanitizadores nem a revisão de licença.

A análise nativa do REA precisa de um provedor como Ghidra, Hopper ou IDA. Para começar com custo de licença zero, a rota preferida é um host Linux x86-64 com Ghidra e JDK 21 ou mais recente, seguindo os requisitos atuais do REA. O suporte de Ghidra no Windows é indicado pelo projeto REA como experimental.

Configuração no computador que executa o agente:

```sh
npx rea-agents@latest setup
```

Revise o plano de instalação, aprove somente as alterações esperadas, reinicie o agente e confirme que o provedor nativo está pronto. Requisitos e compatibilidade podem mudar; consulte https://rea.tools/pt-BR/get-started/ e https://rea.tools/pt-BR/guides/native/.

O REA analisa o binário localmente, mas os resultados da análise são entregues ao agente de codificação. Não envie ROM, arquivos NARC, firmware, saves, dados extraídos ou logs que contenham conteúdo pessoal para o agente ou para qualquer serviço.

## Alvos prioritários da primeira auditoria

A investigação deve usar o executável compilado localmente a partir do commit fixado, sem depender de ROM ou dados extraídos. Os símbolos abaixo são funções do código-fonte; confirme se os símbolos de depuração foram preservados no executável antes de consultar por nome.

| Prioridade | Fonte / função | O que rastrear |
|---|---|---|
| P0 | `src/main.c::NitroMain` | Ordem de inicialização, loop principal, espera por VBlank/IRQ, tarefas e encerramento/reset |
| P0 | `src/system.c::InitSystem` e leitura de arquivos | Inicialização do sistema, interrupções, tamanho/alocação/leitura de recursos e tratamento de falhas |
| P0 | `src/savedata.c::SaveData_Init`, `SaveData_Save` e máquina de estados | Escrita atômica, bloqueios, falhas de I/O, corrupção e recuperação de saves |
| P0 | shim de filesystem e chamadas `FS_OpenFile` | Resolução de caminhos, limites, arquivos ausentes, symlinks e travessia de diretórios |
| P1 | `src/rtc.c::InitRTC`, `UpdateRTC` e callback | Concorrência do callback assíncrono e atualização do relógio |
| P1 | `src/sound_system.c::SoundSystem_Tick` | Ciclo de áudio, tarefas e dependências de temporização |
| P1 | `src/port/sim_config_prj.c::IniHandler` e `SIM_Config_prj_SaveConfigFile` | Contrato do parser INI, validação de valores e gravação de configuração |

Exemplo de consulta CLI documentada pelo REA para uma função nativa:

```sh
npx -y rea-agents@latest function "/caminho/absoluto/para/pokeplatinum" NitroMain --provider ghidra --json
```

Use o caminho do executável host produzido pelo build local. Não use o ZIP de uma ROM como alvo de análise.

## Achado preliminar para validação

No commit upstream fixado, `src/port/sim_config_prj.c` declara `IniHandler` com retorno `int`, mas o corpo termina sem um `return` explícito. O cabeçalho do parser INI em `libntr` define que o callback deve retornar valor não zero em caso de sucesso e zero em caso de erro. O comportamento atual do callback, portanto, não é definido pelo contrato C e precisa ser corrigido/testado.

No mesmo arquivo, `SIM_Config_prj_SaveConfigFile` usa o resultado de `fopen` sem verificar se é nulo antes de chamar `fprintf`. Um diretório de trabalho sem permissão de escrita pode fazer a rotina falhar de forma abrupta.

Esses pontos são **achados de revisão estática preliminar**, não bugs confirmados por execução ou pelo REA. Antes de corrigir, a investigação deve:
1. confirmar no binário a função e a chamada ao parser;
2. verificar o fluxo de retorno do parser quando o handler retorna zero/não zero;
3. reproduzir a configuração ausente, inválida e o diretório sem permissão;
4. implementar a correção no preparador de runtime, sem editar silenciosamente o checkout externo;
5. acrescentar teste de regressão e compilar Windows x64 e Linux x86-64.

## Critério para aceitar uma conclusão do REA

Nenhuma alteração deve se basear apenas no pseudocódigo. Para cada achado, guardar localmente:

- hash SHA-256 do executável analisado;
- commit exato do código-fonte e das dependências;
- versão do REA, provedor e versão do Ghidra/Hopper/IDA;
- nome/endereço da função, instruções relevantes, referências e chamadores;
- trecho correspondente no C e qualquer diferença causada por macros/otimização;
- reprodução independente, teste de regressão e resultado de compilação.

Pseudocódigo incompleto, endereço sem contexto ou uma inferência sem referências não são evidência suficiente para mudar código de produção.

## Limites de segurança e dados

- Nunca adicionar ROM, firmware, arquivos extraídos, NARC, saves ou dados proprietários ao repositório, aos relatórios do REA ou à CI.
- Não tratar uma cópia importada como confiável: validar tamanho, cabeçalho, hash, caminhos relativos, symlinks e limites de leitura antes da extração.
- Manter saves isolados por jogo e por perfil; validar gravações, falhas parciais, bloqueios e recuperação antes de otimizações.
- Não terminar o processo do jogo automaticamente durante um travamento de renderização; proteger o save e preservar diagnósticos.
- Não aplicar correções de sincronização, concorrência ou renderização sem uma trilha de chamadas e um teste reproduzível.
- Manter artefatos de análise fora do Git. Publicar somente conclusões revisadas e não sensíveis.

O REA é uma ferramenta de engenharia reversa e inspeção. Ele não certifica a segurança do aplicativo nem substitui análise estática dedicada, testes com AddressSanitizer/UndefinedBehaviorSanitizer quando compatíveis, fuzzing dos parsers e revisão manual.
