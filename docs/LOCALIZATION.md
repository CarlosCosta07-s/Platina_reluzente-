# Versões e localização

## Decisão de produto: idioma no launcher

O jogo deverá ser iniciado com a **ROM original Pokémon Platinum USA Rev. 1**. A experiência final não exigirá uma ROM PT-BR modificada nem substituirá os bytes da ROM importada.

Antes de iniciar, o launcher oferecerá:
- **English (original):** usa os recursos originais extraídos da ROM USA Rev. 1.
- **Português (Brasil):** usa um pacote de localização separado, validado e aplicado a um ambiente local isolado do idioma.

A opção escolhida será salva nas configurações privadas do launcher. A base original deverá permanecer intacta; a preparação do ambiente PT-BR não poderá sobrescrever permanentemente os recursos originais. Caso o pacote PT-BR esteja ausente, incompleto ou seja incompatível, o launcher deverá impedir a inicialização nesse idioma e explicar como resolver o problema, sem alternar silenciosamente para inglês.

A estrutura do pacote deve conter somente os recursos aprovados pelo manifesto de localização e informação de compatibilidade/hash. O fluxo atual de importação a partir de uma ROM PT-BR é uma ferramenta provisória de desenvolvimento — não é ainda a experiência final do jogador. A transformação e distribuição do pacote devem passar por revisão legal; ROMs completas e recursos extraídos não serão adicionados ao Git nem publicados como artefatos de CI.

## Objetivo

Permitir a execução da versão original USA Rev. 1 e investigar compatibilidade com a variante em português brasileiro fornecida pelo usuário, mantendo ROMs e recursos derivados fora do Git.

## Base de referência original

O upstream pret/pokeplatinum documenta estas impressões digitais para Pokémon Platinum USA:

- Rev. 1: SHA-1 0862ec35b24de5c7e2dcb88c9eea0873110d755c
- Rev. 0: SHA-1 ce81046eda7d232513069519cb2085349896dec7

A cópia USA fornecida para o desenvolvimento corresponde à Rev. 1 e serve como referência inicial de compatibilidade.

## Verificação adicional da ROM USA enviada em 29/10/2026

O ZIP `Pokemon - Platinum Version (USA).zip` foi inspecionado extraindo apenas o arquivo NDS para cálculo local de identificadores. A imagem tem 134.217.728 bytes, SHA-1 `ce81046eda7d232513069519cb2085349896dec7`, SHA-256 `ede62292aa7f7014ff27d42097e769753380531739889c29b968b67b80f80678`, CRC-32 `9253921D`, código `CPUE` e byte de revisão `0`. O SHA-1 confirma a ROM oficial USA Rev. 0 de referência do projeto pret/pokeplatinum.

Essa imagem **não é compatível com a configuração atual do runtime**, que foi fixada em USA Rev. 1 (SHA-1 `0862ec35b24de5c7e2dcb88c9eea0873110d755c`). A partir da validação do launcher, a seleção da Rev. 0 será recusada explicitamente e a ROM só será copiada para o armazenamento privado se o SHA-1 integral corresponder à Rev. 1 esperada. Não se deve remover essa proteção nem tratar apenas um cabeçalho `CPUE` como prova suficiente.

O patch PT-BR E4T v1.2.0 publicado documenta como base `3541 – Pokémon Platinum Version (US)(XenoPhobia).nds`, CRC-32 `1D8A5220` (fonte: [E4T — informações de Pokémon Platina](https://e4t.com.br/downloads/pokemon-platina/informacoes-pokemon-platina/)). Esse CRC não corresponde nem à ROM Rev. 0 enviada agora (`9253921D`) nem à ROM Rev. 1 suportada (`69D628E8`). Portanto, **o arquivo de patch não deve ser aplicado diretamente à ROM enviada nem à Rev. 1 presumindo compatibilidade**. A fonte PT-BR já examinada continua sendo apenas uma referência local para os sete recursos NARC aprovados; a compatibilidade visual e de jogo desses recursos em execução nativa ainda não foi demonstrada.

## Comparação local dos recursos na ROM Rev. 0 enviada

A inspeção local comparou os sete caminhos permitidos entre a ROM USA Rev. 0 recém-enviada e a ROM PT-BR de referência. Os sete caminhos existem nas duas imagens com os mesmos IDs FAT e cabeçalhos NARC válidos; os hashes de conteúdo são diferentes na versão inglesa e a versão PT-BR corresponde ao manifesto de hashes aprovado:

| Caminho do recurso | ID FAT | Resultado de conteúdo PT-BR |
|---|---:|---|
| `battle/graphic/pl_b_plist_gra.narc` | 157 | Hash PT-BR aprovado; distinto do inglês |
| `data/slot.narc` | 245 | Hash PT-BR aprovado; distinto do inglês |
| `demo/title/op_demo.narc` | 318 | Hash PT-BR aprovado; distinto do inglês |
| `graphic/pl_bag_gra.narc` | 370 | Hash PT-BR aprovado; distinto do inglês |
| `graphic/pl_plist_gra.narc` | 372 | Hash PT-BR aprovado; distinto do inglês |
| `graphic/pl_pst_gra.narc` | 373 | Hash PT-BR aprovado; distinto do inglês |
| `msgdata/pl_msg.narc` | 404 | Hash PT-BR aprovado; distinto do inglês |

O `msgdata/pl_msg.narc` da ROM PT-BR tem tamanho declarado de 4.185.274 bytes no cabeçalho NARC, mas a entrada FAT declara apenas 4.184.402 bytes. O importador já recupera os 872 bytes adicionais somente após validar o cabeçalho e provar que o intervalo não se sobrepõe a outro arquivo FAT. Esse caso precisa continuar coberto pelos testes.

**Conclusão de dados:** existe evidência em nível de arquivo de que os sete recursos traduzidos são identificáveis e compatíveis com a allowlist de importação, inclusive na ROM Rev. 0 recém-enviada. Isso permite preparar uma camada de localização para o runtime Rev. 1 como próximo passo de implementação. Contudo, não prova que o runtime nativo mostre corretamente esses recursos: o teste em jogo permanece pendente, e a ROM Rev. 0 em si continua incompatível com o alvo nativo atual.

## Verificação do patch PT-BR v1.2.0 (29/10/2026)

O arquivo enviado contém `Pokemon Platinum (BR) v1.2.0.xdelta`. O README incluído no pacote e a página da tradução identificam a ROM-base como `3541 – Pokémon Platinum Version (US)(XenoPhobia).nds`, CRC-32 `1D8A5220` ([informações da tradução E4T](https://e4t.com.br/downloads/pokemon-platina/informacoes-pokemon-platina/)).

A base atualmente aceita pelo launcher é Pokémon Platinum USA Rev. 1: SHA-1 `0862ec35b24de5c7e2dcb88c9eea0873110d755c`, CRC-32 `69D628E8` e byte de revisão no offset `0x1E` igual a `1` ([referência pret/pokeplatinum](https://github.com/pret/pokeplatinum)). Portanto, a base documentada pelo patch não corresponde à impressão digital da ROM Rev. 1. Não aplicar esse patch diretamente à Rev. 1 sem prova de compatibilidade.

A ROM PT-BR de referência examinada localmente tem SHA-1 `3d92f853eda6e70e9272809f01277db5fdb870ab`, CRC-32 `A00BE79B` e byte de revisão `0` em `0x1E`. Ela não é a mesma imagem da Rev. 1 esperada pelo launcher. O patch Xdelta em si não foi executado neste teste contra uma ROM-base com CRC `1D8A5220`; por isso, não se afirma que sua aplicação foi testada nem que funcionaria na Rev. 1.

### Verificação local dos recursos de tradução

Os sete arquivos NARC da lista permitida foram comparados com `tools/localization_manifest.py`: todos os sete SHA-256 correspondem exatamente aos valores aprovados e todos têm cabeçalhos NARC válidos, com blocos `BTAF`, `BTNF` e `GMIF`. A comparação por caminho entre a ROM Rev. 1 e a referência PT-BR encontrou nove arquivos nomeados com conteúdo/tamanho diferente: os sete NARC permitidos e `data/utility.bin` e `dwc/utility.bin`. Também existe uma entrada FAT sem caminho FNT conhecido. Os dois `utility.bin` e a entrada sem caminho continuam proibidos para importação.

O `msgdata/pl_msg.narc` traduzido declara 4.185.274 bytes no cabeçalho NARC, enquanto seu intervalo FAT mede 4.184.402 bytes. O importador já contém recuperação condicionada ao tamanho do NARC e à verificação de que o intervalo não sobreponha outro arquivo FAT; esse comportamento precisa continuar coberto por testes.

**Conclusão de compatibilidade:** a tradução pode ser representada pelos sete recursos aprovados no runtime local, mas o patch `.xdelta` enviado não está comprovado como aplicável diretamente à ROM USA Rev. 1. A próxima etapa é preparar um pacote de idioma/overlay isolado e validado — ou demonstrar, com a base correta, como gerar esses sete recursos — sem modificar a ROM original e sem distribuir ROMs ou arquivos extraídos no repositório.

## Diferenças encontradas na variante PT-BR

A cópia PT-BR possui código de jogo CPUE, mas não tem a mesma impressão digital da Rev. 1. A impressão digital SHA-1 da cópia exata usada para estabelecer os hashes de referência é `3d92f853eda6e70e9272809f01277db5fdb870ab`. O verificador aceita somente os sete recursos com hashes correspondentes a essa variante; outra edição PT-BR será recusada até que seja analisada e adicionada deliberadamente. Uma comparação local de 462 entradas da tabela FAT encontrou dez entradas diferentes:

- sete recursos NARC selecionados para importação local;
- data/utility.bin e dwc/utility.bin, que não fazem parte do allowlist;
- uma entrada FAT sem caminho conhecido na tabela FNT.

Os dois arquivos utility.bin e a entrada FAT não mapeada são deliberadamente excluídos. O projeto exige código nativo compilado, sem emular ou interpretar código ARM do DS; nenhum binário desconhecido será transplantado para o runtime sem uma análise técnica separada.

Os recursos allowlisted são:

- battle/graphic/pl_b_plist_gra.narc
- data/slot.narc
- demo/title/op_demo.narc
- graphic/pl_bag_gra.narc
- graphic/pl_plist_gra.narc
- graphic/pl_pst_gra.narc
- msgdata/pl_msg.narc

Os arquivos msgdata/msg.narc e msgdata/scenario/scr_msg.narc são idênticos entre as ROMs fornecidas. Não são substituídos pela ferramenta.

## Segurança do importador

O arquivo tools/import_localization.py:
- valida cabeçalho, FNT/FAT, limites de arquivos e estrutura interna dos sete NARCs;
- aceita somente a variante PT-BR aprovada, identificada pelo SHA-1 3d92f853eda6e70e9272809f01277db5fdb870ab;
- exige correspondência SHA-256 individual dos sete recursos antes da publicação;
- grava os arquivos em uma área temporária, verifica o pacote e só então instala a pasta por renomeação no mesmo volume;
- gera localization-manifest.json com o idioma, a ROM-base compatível, a ROM-fonte e os sete hashes;
- só permite --force para substituir um pacote PT-BR previamente criado por esta ferramenta;
- rejeita links simbólicos, arquivos inesperados, recursos modificados e diretórios fora da allowlist;
- não altera os dados-base do runtime, a ROM-fonte ou saves/configurações.

## Fluxo de pacote PT-BR isolado

O pacote deve ficar em uma pasta privada de dados do usuário, separada da raiz do runtime. O importador não instala os NARCs na pasta de trabalho do jogo.

Linux:
```sh
python3 tools/import_localization.py \
  --rom "/caminho/local/PK Plat [PT-BR].nds" \
  --package "$HOME/.local/share/PlatinaReluzente/localizations/pt-BR"
```

Windows (PowerShell):
```powershell
python tools/import_localization.py `
  --rom "C:\ROMs\PK Plat [PT-BR].nds" `
  --package "$env:APPDATA\PlatinaReluzente\localizations\pt-BR"
```

Para substituir um pacote anterior reconhecido pela ferramenta, acrescente --force. A opção não substitui diretórios arbitrários nem arquivos da instalação original.

O resultado contém os sete recursos nos caminhos relativos originais e localization-manifest.json. A geração e a verificação do pacote são automatizadas, mas a seleção de idioma no launcher e a resolução desses arquivos pelo filesystem nativo ainda não estão integradas. Não copie manualmente o conteúdo do pacote para a raiz do runtime.

## O que ainda precisa ser validado

1. Validar a execução da ROM USA Rev. 1 em inglês, sem camada PT-BR.
2. Integrar o manifesto e os sete arquivos como overlay de leitura, sem alterar os recursos originais.
3. Implementar no launcher a opção English / Português (Brasil), com validação antes de iniciar.
4. Inspecionar fontes, acentos, nomes, menus, tela de título e diálogos.
5. Testar batalhas, transições, progressão e salvamento/carregamento com cada idioma.

A criação do pacote prova apenas a integridade dos arquivos e sua identidade. Ela não prova compatibilidade visual ou de gameplay.

## Testes automatizados

Os testes sintéticos não precisam de ROM:
```sh
python3 -m unittest discover -s tools/tests -v
python3 scripts/test.py --full
```

## Política de dados

Não faça commit, release, upload de CI ou espelhamento de ROMs, patches binários, NARC extraídos, saves ou demais recursos proprietários. Os testes do jogo usam arquivos locais do próprio usuário e a CI não publica conteúdo do jogo.
