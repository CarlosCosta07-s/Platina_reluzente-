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

O arquivo `tools/import_localization.py`:

- valida o cabeçalho da ROM e as tabelas FNT/FAT;
- exige correspondência SHA-256 dos sete NARC com `tools/localization_manifest.py` antes de escrever qualquer arquivo, impedindo que uma ROM USA ou outra tradução seja importada por engano;
- só aceita CPUE e extrai caminhos de uma allowlist explícita;
- valida cabeçalho, tamanho e blocos essenciais dos arquivos NARC;
- evita sobrescrever os arquivos existentes sem a opção explícita --force;
- recusa intervalos sobrepostos a outro arquivo FAT;
- permite recuperar o tamanho declarado pelo NARC quando o FAT termina antes, apenas quando o intervalo cabe na ROM e não se sobrepõe a outro arquivo FAT;
- nunca modifica a ROM de origem nem faz upload de dados.

## Fluxo provisório atual de desenvolvimento (não é a UX final do launcher)

O procedimento abaixo documenta o importador atual para análise e testes internos. Ele ainda exige uma ROM PT-BR como fonte e substitui os arquivos allowlisted do destino com a opção --force. Deve ser refatorado para gerar/aplicar uma camada separada antes de ser considerado a implementação final do seletor de idioma.

## Como importar os recursos PT-BR no diretório local

Faça um build e inicie o jogo uma vez usando os dados locais da versão original para preparar o diretório de recursos. Encerre o jogo antes de importar para que nenhum arquivo esteja aberto.

Linux:

    python3 tools/import_localization.py \
      --rom "/caminho/local/PK Plat [PT-BR].nds" \
      --destination "vendor/pokeplatinum-native/build_linux/pokeplatinum" \
      --force

Windows: use o diretório de trabalho do executável em build_win64/pokeplatinum. O extrator upstream grava os arquivos no diretório de trabalho atual, então inicie o executável a partir de build_linux/pokeplatinum ou build_win64/pokeplatinum antes de importar os arquivos.

A opção --force é necessária porque os recursos originais normalmente já existem no diretório de destino. Depois da importação, verifique o diretório com `python3 tools/check_runtime_data.py --runtime-dir vendor/pokeplatinum-native/build_linux/pokeplatinum --require-localized-resources` (em Windows, substitua pelo caminho vendor/pokeplatinum-native/build_win64/pokeplatinum). O verificador compara os sete hashes SHA-256 com a variante PT-BR exata que foi usada como referência durante o desenvolvimento; não basta que um arquivo tenha um cabeçalho NARC válido. Se a ferramenta recusar uma ROM, caminho ou estrutura, não ignore o erro; investigue a diferença antes de tentar outra extração.

## O que ainda precisa ser validado

A extração segura comprova somente que os sete arquivos NARC podem ser copiados. O verificador local compara seus hashes com a variante PT-BR de referência para detectar arquivos incorretos ou versões diferentes. Isso não comprova que a versão PT-BR executa corretamente. Testes necessários:

1. inicialização e jogo com a ROM USA Rev. 1 original;
2. substituição local dos sete arquivos NARC allowlisted;
3. inspeção de fontes, acentos, nomes, menus, tela de título e diálogos;
4. teste de batalhas, transições, progressão de história e salvamento/carregamento;
5. análise separada de qualquer diferença fora da allowlist, sem copiar executáveis/binários desconhecidos.

## Testes automatizados

Os testes sintéticos não precisam de ROM:

    python3 -m unittest discover -s tools/tests -v

## Política de dados

Não faça commit, release, upload de CI ou espelhamento de ROMs, patches binários, NARC extraídos, saves ou demais recursos proprietários. Os testes do jogo usam arquivos locais do próprio usuário e a CI não publica conteúdo do jogo.
