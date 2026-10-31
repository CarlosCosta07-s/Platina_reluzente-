# Contrato de integração — launcher e os dois jogos

**Escopo:** aplicativo Desktop unificado Platina Reluzente, Windows x64 e Linux x86-64.

## O launcher é o aplicativo

A pasta launcher-app contém a aplicação principal. A biblioteca, seleção do título, importação dos dados, configurações, progresso, diagnósticos e gerenciamento das sessões fazem parte do mesmo produto. Os runtimes nativos são componentes internos iniciados e supervisionados pelo launcher; não são aplicativos independentes que o jogador deve localizar no disco.

A biblioteca reúne dois jogos, cada um com identidade e ciclo de dados próprios:

1. **Pokémon Platinum** — runtime nativo baseado no código C/C++ reconstruído; a versão original USA Rev. 1 é a base atualmente suportada. English usa os recursos da ROM; PT-BR é uma localização verificada aplicada a esse título, não um terceiro jogo.
2. **Pokémon Black Version** — runtime nativo Eidos/Aletheia, com identidade, importação, extração, configuração, saves e logs isolados de Platinum. Não confundir com o jogo Xbox Black usado como referência histórica.

A identidade visual e a navegação permanecem em uma só janela Electron. O launcher permite escolher o título e inicia a sessão correspondente sem abrir um segundo launcher nem pedir ao jogador para escolher um executável.

## Responsabilidades compartilhadas

O launcher fornece serviços comuns:

- biblioteca e seleção de título;
- controle de instância única e limite de uma sessão nativa ativa por aplicativo;
- validação e importação transacional de arquivos fornecidos pelo usuário;
- estado de preparação, progresso, mensagens de erro e diagnósticos;
- primeiro-frame, watchdog de heartbeat, detecção de travamento, recuperação da janela e encerramento;
- configurações globais do aplicativo e preferências específicas por jogo;
- ciclo de vida coerente no Windows e Linux.

Os dados específicos permanecem separados:

| Dado | Platinum | Pokémon Black |
|---|---|---|
| ROM e metadados | diretório privado Platinum | diretório privado Black |
| Extração/cache | vinculado à identidade ROM + build do runtime | raiz de dados Eidos isolada |
| Saves e configurações | perfil Platinum | perfil Black |
| Logs | log Platinum | log Black |
| Idioma | English / pacote PT-BR validado | idioma conforme suporte do jogo |

Nenhuma ROM, save, firmware, arquivo extraído ou dado protegido é empacotado, enviado ao Git ou colocado em artefatos de CI.

## Contrato de primeiro frame e vida da sessão

O launcher só considera a janela do jogo pronta depois de receber o marcador [Platina-Progress] window-ready.

O evento deve ocorrer **depois** que o presenter nativo retornar da apresentação do primeiro frame (SDL renderer ou swap de OpenGL). Não basta criar uma janela, criar um contexto gráfico ou declarar que o renderer inicializou.

Após a confirmação, o launcher pode minimizar sua janela. Enquanto a sessão existir, o runtime envia heartbeat com o número do frame: [Platina-Progress] heartbeat frame=N.

A ausência de heartbeat aciona diagnóstico e restaura a interface do launcher, mas não mata automaticamente uma sessão que ainda possa estar salvando ou recuperando dados. Quando o processo termina, a janela do launcher é restaurada e a guarda de sessão é liberada.

O protocolo é comum aos dois jogos, com mensagens de progresso direcionadas ao painel do jogo selecionado. O runtime Platinum e o runtime Eidos precisam cumprir o mesmo contrato. Um processo que não implementa o protocolo não pode ser anunciado como integrado e pronto para uso.

### Estado da implementação

- Platinum já utiliza o protocolo por meio do preparador de runtime e do gerenciador native-process.
- A revisão Eidos fixada não emitia os marcadores esperados. O novo preparador injeta o sinal após render(p) e heartbeats periódicos, com teste de idempotência e falha segura.
- O launcher aplica os mesmos callbacks de primeiro frame, travamento, recuperação e encerramento a Platinum e Black, direcionando as mensagens ao painel correto.
- O runtime de Black não está no pacote público. A restrição de licença do código reconstruído Aletheia continua bloqueando a redistribuição até revisão jurídica adequada. A integração de runtime e o protocolo técnico não anulam essa restrição.

## Condições de aceite

1. Os dois títulos aparecem na mesma biblioteca e compartilham a mesma janela e aplicação.
2. Cada jogo importa e valida apenas sua ROM compatível, sem misturar caches, saves, configurações ou logs.
3. O launcher executa somente o runtime correspondente ao título selecionado.
4. Ambos sinalizam o primeiro frame somente depois da apresentação real.
5. Ambos enviam heartbeat, informam travamentos e permitem recuperar a interface sem encerrar o jogo de forma insegura.
6. O término da sessão restaura o launcher e libera a guarda para iniciar outro título.
7. Erros de importação, preparação, inicialização ou renderer permanecem visíveis no painel do título correto.
8. A integração é verificada com testes ROM-free e testes de contrato antes da compilação final integrada.
9. Nenhum executável Black é publicado enquanto a situação de licença de Aletheia não permitir a redistribuição.

## Sequência de entrega

A ordem é: implementar os contratos e as funcionalidades dos dois runtimes → validar as integrações e os testes de fonte/fixtures → fechar os testes de gameplay, saves, áudio, entrada, renderer e shutdown com dados locais → compilar uma única entrega integrada Windows/Linux → testar os pacotes finais.

Os workflows de desenvolvimento não devem produzir builds completos em pushes normais. Os jobs de compilação e empacotamento só podem executar por despacho manual com o respectivo sinalizador de autorização final explicitamente definido como verdadeiro. O padrão é falso.
