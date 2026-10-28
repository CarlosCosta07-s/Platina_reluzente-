# Versões e localização

## Objetivo

Manter o comportamento do jogo original e permitir também a variante em português brasileiro fornecida pelo usuário, sem colocar ROMs ou pacotes de recursos derivados no repositório.

## Base de referência original

O upstream `pret/pokeplatinum` documenta duas revisões USA:

- Rev. 1: SHA-1 `0862ec35b24de5c7e2dcb88c9eea0873110d755c`
- Rev. 0: SHA-1 `ce81046eda7d232513069519cb2085349896dec7`

O ZIP USA fornecido para o desenvolvimento contém uma ROM cuja SHA-1 corresponde à Rev. 1 listada acima. Esse é o ponto de partida para validar a execução desktop.

## Variante PT-BR

O arquivo fornecido como PT-BR tem o código de jogo `CPUE`, mas sua impressão digital não corresponde à Rev. 1 original. Isso é consistente com uma ROM modificada/patch, mas não prova por si só que apenas textos foram alterados.

A ferramenta local `tools/import_localization.py` foi criada para extrair **somente** estes bancos de texto, mantendo a ROM intacta:

- `msgdata/msg.narc`
- `msgdata/pl_msg.narc`
- `msgdata/scenario/scr_msg.narc`

A ferramenta identifica as estruturas FNT/FAT do Nintendo DS, valida o cabeçalho do jogo, valida o cabeçalho e os blocos NARC, evita sobrescrever arquivos existentes sem `--force` e recusa intervalos que se sobreponham a outro arquivo da ROM. Alguns dumps modificados podem ter um final FAT mais curto do que o tamanho declarado pelo próprio NARC; a ferramenta só permite recuperar o tamanho indicado pelo NARC quando o intervalo completo está dentro do arquivo e não sobrepõe nenhum outro arquivo FAT.

## Resultado da comparação local atual

Na comparação dos três bancos selecionados das duas cópias fornecidas, `msg.narc` e `scr_msg.narc` são idênticos; `pl_msg.narc` é diferente. O importador extraiu os três bancos de ambas as cópias em diretórios locais de teste, incluindo a recuperação validada do tamanho de `pl_msg.narc` na variante PT-BR.

Isso confirma a extração dos arquivos selecionados, **não** a execução completa da variante PT-BR. A compatibilidade final depende de testar o jogo e verificar se os dados alterados se limitam a esses bancos. Fontes, acentos, nomes, eventos e quaisquer diferenças fora deles ainda precisam de smoke tests.

## Como importar no diretório local do porte

Após gerar os dados do jogo com sua própria cópia original e encerrar o aplicativo, execute no diretório raiz do repositório:

```bash
python3 tools/import_localization.py \
  --rom "/caminho/local/PK Plat [PT-BR].nds" \
  --destination "vendor/pokeplatinum-native/build_linux/pokeplatinum" \
  --force
```

Em Windows, substitua o destino por `vendor/pokeplatinum-native/build_win64/pokeplatinum`. A opção `--force` é explícita porque o destino normalmente já contém os bancos originais. Se a ferramenta recusar a ROM ou relatar sobreposição/estrutura inválida, não ignore o erro nem tente forçar uma extração manual sem entender a diferença.

Os testes sintéticos podem ser executados sem ROM:

```bash
python3 -m unittest discover -s tools/tests -v
```

## Próximos testes

1. Confirmar a inicialização com a ROM USA Rev. 1 de referência.
2. Importar os bancos PT-BR no diretório local usado pelo executável.
3. Testar tela inicial, menus, diálogos, acentos, eventos de história, batalhas, salvamento e carregamento.
4. Registrar bugs reproduzíveis sem anexar ROMs, NARC ou conteúdo proprietário.
5. Tratar divergências no executável ou nos dados não textuais como uma etapa de compatibilidade separada.

## Política de dados

Não faça commit, release, upload de CI ou espelhamento de ROMs, patches binários, NARC extraídos ou outros arquivos proprietários. O teste deve usar caminhos locais fornecidos pelo usuário e registrar somente metadados mínimos necessários para diagnosticar compatibilidade.
