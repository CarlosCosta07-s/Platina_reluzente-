# Política de segurança

## Escopo

Esta política cobre o launcher desktop, o código de integração nativa, os scripts de build/preparação, a importação e validação de arquivos locais, a extração de recursos e o sistema de saves deste repositório.

## Versões

O projeto está em desenvolvimento experimental. A referência de trabalho é a branch `main`; ainda não há uma versão estável com garantia de suporte.

## Como relatar uma vulnerabilidade

Não publique detalhes exploráveis, arquivos de demonstração maliciosos ou provas de conceito em uma issue pública.

1. Verifique se a aba **Security** do GitHub oferece a opção **Report a vulnerability** para este repositório e use o canal privado, caso esteja habilitado.
2. Se o canal privado não estiver disponível, contate o mantenedor por um meio privado indicado no perfil do proprietário do repositório e solicite um canal seguro antes de enviar detalhes técnicos.
3. Inclua o commit afetado, sistema operacional, versão do launcher/runtime, passos mínimos de reprodução e logs sanitizados.

Não existe prazo de resposta ou correção garantido. O relato será avaliado quanto à reprodutibilidade, impacto e versões afetadas.

## O que não enviar

Nunca envie ROMs, firmware, arquivos NARC, recursos extraídos, saves, chaves, credenciais, tokens, dumps de memória ou logs que contenham conteúdo pessoal. Um relato deve usar uma reprodução mínima e dados sintéticos sempre que possível.

## Tratamento

As correções devem ser desenvolvidas na branch `main`, acompanhadas por um teste de regressão e verificadas nos alvos afetados. Não se deve declarar uma vulnerabilidade corrigida apenas porque o código foi alterado: é necessário registrar os testes executados e as limitações que permanecerem.
