# Versões e localização

## Objetivo

Permitir a execução da versão original USA Rev. 1 e investigar compatibilidade com a variante em português brasileiro fornecida pelo usuário, mantendo ROMs e recursos derivados fora do Git.

## Base de referência original

O upstream pret/pokeplatinum documenta estas impressões digitais para Pokémon Platinum USA:

- Rev. 1: SHA-1 0862ec35b24de5c7e2dcb88c9eea0873110d755c
- Rev. 0: SHA-1 ce81046eda7d232513069519cb2085349896dec7

A cópia USA fornecida para o desenvolvimento corresponde à Rev. 1 e serve como referência inicial de compatibilidade.

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
