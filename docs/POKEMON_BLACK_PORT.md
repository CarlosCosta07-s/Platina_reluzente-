# Pokémon Black Version — porte nativo para PC

**Estado em 29/10/2026:** projeto paralelo anunciado e em fase inicial de auditoria técnica. Ainda não existe um runtime de Pokémon Black integrado a este launcher. A entrada da biblioteca é apenas informativa e não permite importar nem iniciar Black.

## Objetivo

Desenvolver, em paralelo ao porte de Pokémon Platinum, um porte nativo de Pokémon Black Version para **Windows x64 e Linux x86-64**. A meta é compilar a lógica C reconstruída para a arquitetura do computador, substituindo os serviços do Nintendo DS por uma camada de plataforma — sem usar um emulador de DS nem interpretar instruções ARM durante a partida.

A ROM local é necessária somente para verificar a versão e fornecer os dados originais exigidos pelo runtime. Ela, os dados extraídos, os saves e quaisquer outros materiais protegidos permanecerão fora do GitHub e dos artefatos públicos.

## Bases técnicas para auditoria

- [Project-Holon/aletheia](https://github.com/Project-Holon/aletheia) — projeto público de decompilação matching de Pokémon Black. Sua documentação descreve a reconstrução de funções de modo que possam ser recompiladas e comparadas byte a byte com a referência.
- [Project-Holon/eidos](https://github.com/Project-Holon/eidos) — porte nativo para PC construído sobre aletheia. O README do upstream declara que compila o código C reconstruído e não emula o Nintendo DS. O upstream descreve progresso até as primeiras horas do jogo; isso **não** é evidência de que este repositório tenha compilado ou validado aquele código.
- [squiddonaut/pokeblack](https://github.com/squiddonaut/pokeblack) — outra referência pública para identificar a versão-base e ferramentas do processo de decompilação.

Esses projetos são **candidatos para revisão**, não dependências já adotadas. Há um bloqueio jurídico a resolver antes de incorporar a base: a licença do aletheia declara expressamente que o MIT cobre ferramentas e documentação, mas **não** concede licença para o código reconstruído do jogo em `src/`; o `LEGAL.md` do eidos também diferencia seu próprio código original do código de jogo compilado a partir do aletheia. Portanto, as licenças MIT dos repositórios não devem ser interpretadas como autorização para redistribuir o código ou a obra do jogo. Antes de copiar, vincular, empacotar ou publicar componentes derivados desse código, será necessária uma revisão jurídica da situação e das alternativas disponíveis. A finalidade de preservação e a ausência de lucro não resolvem, por si só, essa questão.

O upstream aletheia declara a variante USA/Europa NDSi Enhanced com o SHA-1 listado abaixo e relata 100% de correspondência byte a byte; isso é evidência técnica do projeto upstream, não validação realizada por este repositório. A documentação atual do eidos/aletheia indica trabalho de preparação para 64 bits, mas o repositório apresenta diferentes configurações e toolchains de build. Antes de aprovar a base técnica, devemos fixar commits exatos e reproduzir builds limpos Windows x64 e Linux x86-64, incluindo todos os requisitos de extração e compilação. Nenhum desses builds foi executado por este repositório ainda.

## Variante de ROM e importação

A versão-alvo inicial para investigação é **Pokémon Black USA/Europe (NDSi Enhanced)**, associada nas referências públicas ao SHA-1:

`26ad0b9967aa279c4a266ee69f52b9b2332399a5`

Esse hash serve como candidato de identificação, não como autorização para distribuir uma ROM. Um importador futuro deve validar a imagem integral, não apenas o título ou o código de jogo do cabeçalho. Se a referência selecionada mudar, o hash, a ferramenta de extração e os testes de compatibilidade deverão mudar juntos e ficar documentados.

## Plano de execução

1. **Auditar a base:** revisar código, commits, licenças, ferramentas, dependências e o status real dos testes upstream.
2. **Fixar a versão-alvo:** confirmar a ROM USA/Europe NDSi Enhanced por hash e documentar o contrato dos dados que o runtime necessita. A ROM será usada localmente, nunca enviada à CI.
3. **Compilar o código nativo:** preparar builds reproduzíveis para Windows x64 e Linux x86-64. Resolver os requisitos de 32/64 bits antes de escolher definitivamente a base.
4. **Separar o runtime:** manter código, executáveis, dados extraídos, configurações e saves de Black isolados dos equivalentes de Platinum.
5. **Integrar a biblioteca do launcher:** usar um identificador próprio, como `pokemon-black`, um validador de ROM independente e uma localização de dados própria. A implementação Black não pode reutilizar acidentalmente o hash ou o processo de inicialização de Platinum.
6. **Criar testes e pacotes:** verificar que o staging contém apenas o runtime autorizado, nunca ROMs, patches, saves, firmware ou arquivos extraídos.
7. **Validar funcionamento real:** confirmar inicialização, tela de título, nova partida, controles, áudio, batalhas e salvamento antes de anunciar cada etapa como concluída.

## Estado da integração com o launcher

Atualmente o backend de importação/inicialização em `launcher-app/electron/main.cjs` é específico de Pokémon Platinum: ele valida o SHA-1 de Platinum USA Rev. 1 e encontra o runtime Platinum incluído no pacote. A entrada de Black no HTML não altera esse backend, não passa uma ROM de Black pelo validador de Platinum e não finge que existe um executável Black.

A entrada só deverá ser habilitada depois que houver um runtime próprio, importação versionada, caminhos separados para dados e saves, testes de regressão e pacotes Windows/Linux confirmados. A integração não pode quebrar o fluxo já existente de Platinum.

## Critérios para declarar progresso

Uma página de biblioteca, compilação de stubs ou criação de uma janela vazia não demonstra que o jogo é jogável. Cada marco será registrado com a revisão do código, comandos de build, resultado dos testes e limitações ainda conhecidas. A CI não recebe nem publica uma ROM comercial.
