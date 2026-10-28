# Versões e localização

## Objetivo

Manter o comportamento do jogo original e permitir também a variante em português brasileiro fornecida pelo usuário, sem colocar ROMs ou pacotes de recursos derivados no repositório.

## Base de referência original

O upstream `pret/pokeplatinum` documenta duas revisões USA:

- Rev. 1: SHA-1 `0862ec35b24de5c7e2dcb88c9eea0873110d755c`
- Rev. 0: SHA-1 `ce81046eda7d232513069519cb2085349896dec7`

O ZIP USA enviado para o desenvolvimento contém uma ROM cuja SHA-1 corresponde à Rev. 1 listada acima. Esse é o ponto de partida para validar primeiro a extração e a execução desktop.

## Variante PT-BR

O arquivo enviado como PT-BR tem o código de jogo `CPUE`, mas sua impressão digital não corresponde à Rev. 1 original. Isso é consistente com uma ROM modificada/patch, mas não prova por si só que apenas textos foram alterados. Portanto, ainda não é correto prometer compatibilidade integral.

## Estratégia de suporte

1. Validar carregamento e inicialização com a cópia USA Rev. 1 de referência.
2. Inspecionar localmente a variante PT-BR e identificar precisamente o que foi alterado, sem enviar dados da ROM para a CI.
3. Comparar os bancos de texto que a implementação desktop documenta como substituíveis:
   - `msgdata/msg.narc`
   - `msgdata/pl_msg.narc`
   - `msgdata/scenario/scr_msg.narc`
4. Criar ferramenta local reproduzível que extraia ou importe esses arquivos do dump do próprio usuário e verifique integridade, sem commitar os arquivos extraídos.
5. Testar interface, diálogos, nomes, fontes/acentos, eventos de história e salvamento com a versão original e PT-BR.
6. Tratar divergências no código executável ou nos dados não textuais como uma etapa de compatibilidade separada; não mascarar diferenças com detecção frágil de nome de arquivo.

A possibilidade de substituir arquivos de texto descrita pelo porte desktop é um ponto de partida, não uma validação automática da ROM PT-BR específica.

## Política de dados

Não faça commit, release, upload de CI ou espelhamento de ROMs, patches binários, NARC extraídos ou outros arquivos proprietários. O teste de cada versão deve usar caminhos locais fornecidos pelo usuário e registrar somente metadados mínimos necessários para diagnosticar compatibilidade.
