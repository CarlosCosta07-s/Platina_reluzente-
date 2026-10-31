# Estratégia de renderização — OpenGL e Vulkan

**Estado:** decisão arquitetural aprovada; implementação Vulkan ainda não iniciada. O backend OpenGL atual permanece preservado. Esta documentação não autoriza builds Android/iOS e não altera o gate de paridade 1:1 com Desktop.

## 1. Objetivo

O Platina Reluzente manterá **dois backends gráficos independentes**:

- **OpenGL:** preservar o renderer existente. Desktop usa OpenGL 4.2 Core; a trilha móvel atual prepara OpenGL ES 3.0 / GLSL ES 3.00.
- **Vulkan:** adicionar um renderer Vulkan próprio, compartilhando o contrato lógico de renderização, mas não fingindo que as chamadas OpenGL são Vulkan.

O jogador poderá escolher o backend. O modo automático poderá escolher a melhor opção suportada pela máquina, e haverá fallback quando um backend falhar na inicialização.

A implementação de Vulkan é uma segunda rota; não é uma substituição do renderer que já passou pelos testes sintéticos.

## 2. Seleção visível ao jogador

A configuração persistida será conceitualmente:

| Opção | Comportamento |
|---|---|
| **Automático** | detecta os backends válidos, consulta perfil conhecido do GPU/driver e escolhe o mais adequado; se a inicialização falhar, tenta a alternativa |
| **OpenGL** | tenta o backend OpenGL disponível naquela plataforma |
| **Vulkan** | tenta o backend Vulkan disponível naquela plataforma |

A interface também mostrará:
- backend preferido pelo jogador;
- backend realmente ativo;
- GPU, driver e versão da API;
- recursos opcionais detectados;
- motivo de fallback, se ocorreu.

A preferência escolhida e o backend ativo são dados diferentes. Uma falha temporária de Vulkan não deve sobrescrever silenciosamente a preferência salva pelo usuário.

A troca de backend será aplicada no próximo início do runtime. Não vamos prometer hot-switch no meio de uma sessão, porque a troca exige destruir recursos e recriar a superfície/contexto com segurança.

## 3. Compatibilidade por plataforma

| Plataforma | OpenGL | Vulkan |
|---|---|---|
| Windows | OpenGL 4.2 Core | Vulkan nativo |
| Linux | OpenGL 4.2 Core | Vulkan nativo |
| Android | OpenGL ES 3.0 | Vulkan nativo |
| iOS | ANGLE com backend Metal, se validado | MoltenVK sobre Metal, se validado e após revisão do risco de manutenção |

No iOS, OpenGL desktop não existe e OpenGL ES é legado/depreciado no ecossistema Apple. Por isso, a opção OpenGL exige uma implementação compatível como ANGLE com backend Metal. A opção Vulkan pode usar MoltenVK para traduzir Vulkan para Metal. Há um risco de manutenção: o README atual do MoltenVK informa que a Khronos o depreciou e que o projeto passou a ser mantido pela comunidade em regime de melhor esforço; o próprio projeto ainda o recomenda para iOS. Antes de adotá-lo, precisamos avaliar manutenção, licença, atualizações, compatibilidade e suporte aos recursos que o renderer exige. Se o risco for inaceitável, uma implementação Metal nativa é a alternativa, mas não será chamada de Vulkan. As integrações só serão expostas ao jogador após testes reais.

Não vamos incluir automaticamente Vulkan no iOS apenas porque Android/PC o suportam. A matriz por plataforma será baseada no que o runtime realmente compila, inicializa e valida.

## 4. Contrato compartilhado entre backends

O jogo e a camada de simulação não devem conhecer detalhes de OpenGL ou Vulkan. O núcleo deve enviar comandos por uma interface comum de renderer que descreve:
- criação e destruição de recursos;
- texturas, formatos, regiões e filtros;
- buffers de vértices/índices e uniformes/constantes;
- passes de renderização e attachments;
- estado de blending, depth/stencil e prioridade;
- submit, sincronização, leitura de resultados e apresentação;
- perda/recriação da superfície e shutdown.

Cada backend converte esse contrato para sua API. Os detalhes de sincronização ficam no backend, sem vazar fences, semaphores ou handles nativos para a lógica do jogo.

## 5. Regras de fallback e recuperação

1. A seleção ocorre antes de criar a janela/surface com flags incompatíveis com o backend escolhido.
2. O inicializador valida dispositivo físico, fila de apresentação, formatos, extensões obrigatórias, recursos e shaders.
3. Se Vulkan falhar em qualquer etapa, o backend deve destruir tudo que criou parcialmente: device, surface/swapchain, views, semaphores, command pools, buffers e referências de janela.
4. Só depois dessa limpeza o host tenta criar a janela/contexto OpenGL.
5. A tentativa secundária também precisa poder falhar de maneira limpa, com erro legível e log.
6. A falha e o fallback devem ser visíveis ao jogador e gravados no diagnóstico. O valor preferido pelo usuário não é alterado automaticamente.
7. A perda de surface/context por suspensão ou rotação deve seguir um caminho explícito de teardown/recreate, sem assumir que os recursos gráficos continuam válidos.

Este requisito é importante porque o projeto BT3 documentou uma falha de fallback em que uma janela Vulkan parcialmente aberta impedia a criação do contexto OpenGL e deixava a tela preta. A prevenção será parte dos nossos testes.

## 6. Vulkan: recursos opcionais e compatibilidade

A base do backend será definida após a prova de conceito, com um mínimo de API e recursos obrigatório documentado. Não exigiremos recursos opcionais sem necessidade.

Padrões a avaliar:
- timeline semaphores com fallback para fences;
- dynamic rendering com fallback para render passes;
- formatos de depth/stencil alternativos;
- suporte a compressão de textura detectado por formato;
- limites de descritores e memória do dispositivo;
- swapchain e modos de apresentação suportados;
- cache de pipeline identificado por GPU, driver, versão de shader e versão do app.

Não presumir que todo driver exponha os mesmos recursos, nem que extensão reportada funcione corretamente. Recursos opcionais passam por teste funcional e visual antes de serem habilitados.

## 7. Provas obrigatórias de equivalência

### Já aprovado no backend OpenGL

A auditoria existente registra:
- Desktop GL 4.2 Core × OpenGL ES 3.0 em Mesa/EGL;
- 10 cenas G3 e 14 cenas G2;
- todas com `max_delta=0` e zero pixels divergentes;
- shaders ES 3.00 compilados e comparadores host-only.

Isso não prova ainda a composição completa das duas telas, integração ao runtime completo ou execução em drivers físicos.

### Novo gate Vulkan

O backend Vulkan só será considerado pronto quando:
1. a mesma suíte sintética puder renderizar pelo OpenGL e Vulkan;
2. as imagens comparadas respeitarem a tolerância documentada (idealmente igualdade exata em fixtures determinísticas);
3. todos os casos de duas telas, transparência, prioridades, brilho, fog, texturas e layouts forem cobertos;
4. testes de perda/recriação de surface, suspensão, shutdown e falha de inicialização passarem;
5. fallback Vulkan → OpenGL for testado em caso de falha em cada etapa relevante;
6. o backend não provocar vazamento de recursos, tela preta ou estado gráfico residual;
7. os resultados de performance forem medidos com workload e resolução equivalentes.

A comparação de imagem e a comparação de desempenho são gates separados: uma melhoria de FPS não aceita imagem incorreta.

## 8. Perfil e benchmark

Não vamos codificar uma regra simples como “Adreno sempre Vulkan” ou “Mali sempre OpenGL”. O projeto BT3 documentou casos em que:
- Vulkan foi a melhor opção em uma resolução/perfil;
- OpenGL teve resultado competitivo ou melhor em outra;
- buffers persistentes mudaram completamente o desempenho OpenGL em um Adreno;
- uma extensão de framebuffer fetch causou imagem incorreta e travamento em certos Mali.

Para cada GPU/driver medido, guardar:
- backend ativo e versão da API;
- GPU/driver/SO;
- resolução interna e opções;
- FPS médio e frame-time p50/p95/p99;
- custo CPU/GPU, memória e cache;
- temperatura/throttling e consumo quando possível;
- erros, falhas de shader e fallback.

Perfis automáticos serão sugestões conservadoras e atualizáveis. O jogador poderá alterar renderer e qualidade manualmente.

## 9. Ordem de implementação

1. Preservar a rota OpenGL e concluir a integração GLES já preparada.
2. Fechar a comparação visual das duas telas e dos layouts no OpenGL.
3. Definir a interface neutra de renderer no código compartilhado, sem mover a lógica do jogo para um backend.
4. Criar uma prova Vulkan host-only que renderize as mesmas cenas sintéticas.
5. Integrar o Vulkan ao Desktop e comparar equivalência/performance contra OpenGL.
6. Preparar Vulkan Android e executar somente depois do gate de paridade 1:1 permitir builds móveis.
7. Avaliar MoltenVK e ANGLE/Metal no iOS; expor cada opção apenas depois da validação correspondente.
8. Implementar Auto / OpenGL / Vulkan na UI, persistência, diagnóstico e fallback testado.
9. Revisar e documentar perfis de GPU com evidência reproduzível.
10. Fazer uma decisão específica de iOS entre MoltenVK (com risco de manutenção documentado) e um backend Metal nativo; OpenGL será ANGLE/Metal, não OpenGL ES direto.

**Regra permanente:** OpenGL não será removido quando Vulkan entrar. O jogador escolhe entre os backends realmente disponíveis, e Automático seleciona a opção compatível com melhor perfil conhecido.



## 10. Notas atuais das dependências iOS

- [ANGLE](https://github.com/google/angle) implementa OpenGL ES e pode direcioná-lo ao backend Metal no iOS. Isso permite preservar o contrato OpenGL do nosso renderer sem usar OpenGL ES legado diretamente.
- [MoltenVK](https://github.com/KhronosGroup/MoltenVK) mapeia Vulkan para Metal e ainda é apontado pelo seu README como a opção recomendada para iOS. Entretanto, o mesmo README informa que a Khronos depreciou MoltenVK e que a manutenção passou a ser comunitária/em regime de melhor esforço. Esta condição muda o custo de manutenção e precisa entrar na decisão de dependência.
- Uma alternativa Vulkan-on-Metal mais nova não será presumida como pronta para iOS: qualquer substituto precisa ser verificado em suporte de sistema, toolchain, API, licença e dispositivos antes de entrar na matriz.

Fontes externas atualizadas em 30/10/2026:
- [ANGLE — README e matriz de backends](https://github.com/google/angle/blob/main/README.md)
- [MoltenVK — README e aviso de depreciação](https://github.com/KhronosGroup/MoltenVK/blob/main/README.md)
- [Vulkan Docs — considerações de iOS](https://docs.vulkan.org/tutorial/latest/Building_a_Simple_Engine/Mobile_Development/02_platform_considerations.html)
