# Pokémon Black Version — porte nativo para PC

**Estado em 29/10/2026:** os builds host Windows x64 e Linux x86-64 e os testes upstream sem ROM passaram na CI. O cartão de Black está integrado à biblioteca unificada e tem importação local de ROM; o runtime ainda não é distribuído nem integrado ao pacote, e não existe pacote Black jogável para baixar.

## Objetivo e regra de arquitetura

Desenvolver o porte de Pokémon Black Version para Windows x64 e Linux x86-64 em paralelo ao porte de Platinum, usando o código C reconstruído e uma camada nativa de plataforma. Não usaremos um emulador de Nintendo DS nem um interpretador de instruções ARM durante a partida. A biblioteca de Black terá um identificador, importador, runtime, diretório de dados e saves independentes de Platinum.

O alvo inicial é **Pokémon Black USA/Europe NDSi Enhanced**, identificado na documentação upstream por SHA-1 `26ad0b9967aa279c4a266ee69f52b9b2332399a5` e tamanho de 268.435.456 bytes. Esse hash é uma referência de identificação, não autorização para redistribuir ROMs. A ROM e os arquivos extraídos permanecem locais e nunca são enviados aos runners.

## Auditoria das bases e revisões fixadas

| Componente | Revisão fixada | Função |
|---|---|---|
| [Project-Holon/aletheia](https://github.com/Project-Holon/aletheia) | `6c2aae879f123bcbc028cf6a8b7f8df614402ac8` | Decompilação e ferramenta de extração; o upstream relata código 100% byte-matched. |
| [Project-Holon/eidos](https://github.com/Project-Holon/eidos) | `b79123f967980d1bb758161891205c03d606dec7` | Porte nativo para PC, camada de plataforma, shims de hardware do DS e testes. |

A revisão eidos fixada registra a revisão aletheia `6c2aae879f123bcbc028cf6a8b7f8df614402ac8`, portanto os dois repositórios são um par compatível. Não usaremos `main` sem fixar um commit: o código e os manifests da decompilação mudam independentemente do porte.

A última correção de aletheia, de 29/10/2026, ajustou a leitura da sequência de animação do cursor de golpes no ramo PC: o código anterior lia aproximadamente 0x20 bytes além do slot correto e podia quebrar o menu da segunda ação em algumas batalhas de treinador no build de 32 bits. O eidos fixou exatamente essa revisão e registrou que as três batalhas de reprodução passaram nos testes upstream. Esse é um bom exemplo de por que precisamos fixar a revisão dos dois projetos juntos.

### Modelo de build

Eidos utiliza CMake/Ninja e C99 para a camada nativa. O build oficial descrito pelo upstream gera o módulo de jogo em WebAssembly, converte-o de WebAssembly para C com a ferramenta wasm2c como etapa de build e compila a saída para o binário nativo de 64 bits. Isso não executa uma CPU de Nintendo DS emulada nem interpreta instruções ARM durante a partida. O WAMR opcional para mods WebAssembly é uma função separada do código do jogo.

Para o primeiro marco, vamos seguir a cadeia de ferramentas e as flags utilizadas pelo próprio upstream, em vez de criar uma engine genérica ou misturar as bibliotecas de Platinum. As compilações precisam demonstrar um executável de host x86-64 para cada sistema-alvo.

## Requisitos e primeiro marco

A documentação upstream exige Python 3.11+, CMake 3.16+, Ninja e um compilador C compatível. O SDL3 fornece janela, áudio e entrada na configuração de distribuição. Eidos também mantém uma suíte de testes sem dados de jogo; os testes que exigem a ROM local são ignorados quando `BW_ROM` não está definido.

1. Fixar as revisões de eidos e aletheia e confirmar que o CMake de eidos declara o mesmo pin da decompilação.
2. Compilar e executar os testes de regressão do motor sem ROM nem assets.
3. Compilar o executável nativo x86-64 no Linux e no Windows, sem distribuir o resultado da compilação.
4. Em ambiente local, usar uma cópia legal da ROM para validar a extração, a tela de título, o início de uma nova partida, controles, áudio, salvamento e retomada.
5. Conectar Black à mesma biblioteca, validar o importador por SHA-1 integral e separar diretórios — etapa de interface e importação já concluída. O próximo bloqueio é integrar um runtime interno legalmente distribuível; o usuário não deve selecionar um executável local separado.

O novo workflow `[Pokémon Black native source validation (no game data)](../.github/workflows/pokemon-black-native-check.yml)` está configurado para Linux x86-64 e Windows x64. Ele fixa os dois commits upstream, executa testes e tenta compilar o porte sem dados do jogo. Ele **não** publica executáveis, ROMs, firmware, saves ou arquivos extraídos. O primeiro resultado da CI será usado para corrigir as instruções, não tratado como prova de que a tela de título funciona.

## Limite jurídico que afeta distribuição

As licenças e avisos foram inspecionados diretamente nos repositórios upstream:

- A licença MIT de **eidos** cobre o código original do porte.
- Em **aletheia**, a licença MIT cobre ferramentas, manifests/layout e documentação; o diretório `src/` com o código reconstruído do jogo é explicitamente distribuído **sem concessão de licença** em `LICENSE` e `LEGAL.md`.

Logo, o fato de as ferramentas serem MIT, o uso de ROM própria ou a finalidade de preservação sem lucro não significa que temos permissão de redistribuir a fonte reconstruída ou binários derivados dela. Por isso, a CI inicial só verifica o build em runners temporários e não envia executáveis Black para releases ou artefatos. Antes de publicar binários para terceiros, precisamos de uma análise jurídica adequada da situação e das alternativas permitidas. Não vamos mascarar esse bloqueio no README nem confundir a licença do launcher com a do código do jogo.

## Limites de progresso

A CI produziu builds de verificação de Windows x64 e Linux x86-64, sem ROM nem recursos do jogo. A tela de título, controles, áudio, salvamento e gameplay com uma ROM local ainda não foram validados. A importação de ROM está disponível no cartão de Black, mas Iniciar permanece bloqueado porque o runtime não está no pacote. Não marcaremos o marco jogável como concluído até resolver a distribuição, integrar o runtime internamente e executar os testes reproduzíveis, mantendo a ROM e os dados extraídos fora do GitHub.

## Referências

- [aletheia — README](https://github.com/Project-Holon/aletheia/blob/6c2aae879f123bcbc028cf6a8b7f8df614402ac8/README.md)
- [aletheia — LICENSE](https://github.com/Project-Holon/aletheia/blob/6c2aae879f123bcbc028cf6a8b7f8df614402ac8/LICENSE)
- [aletheia — LEGAL.md](https://github.com/Project-Holon/aletheia/blob/6c2aae879f123bcbc028cf6a8b7f8df614402ac8/LEGAL.md)
- [eidos — README](https://github.com/Project-Holon/eidos/blob/b79123f967980d1bb758161891205c03d606dec7/README.md)
- [eidos — pinned aletheia revision](https://github.com/Project-Holon/eidos/blob/b79123f967980d1bb758161891205c03d606dec7/docs/aletheia-pin.md)
- [eidos — build guide](https://github.com/Project-Holon/eidos/blob/b79123f967980d1bb758161891205c03d606dec7/docs/building.md)
- [eidos — legal notice](https://github.com/Project-Holon/eidos/blob/b79123f967980d1bb758161891205c03d606dec7/LEGAL.md)
- [eidos — release build workflow](https://github.com/Project-Holon/eidos/blob/b79123f967980d1bb758161891205c03d606dec7/.github/workflows/release.yml)
