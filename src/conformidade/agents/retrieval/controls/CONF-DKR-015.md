## Afirmação normativa

A instrução `MAINTAINER` está descontinuada e deve ser substituída por `LABEL`
com as anotações padronizadas da OCI.

## Por que importa

Este é um controle de higiene e rastreabilidade, não de segurança direta —
severidade informativa.

`MAINTAINER` foi descontinuada porque era um campo isolado, com formato livre e
sem equivalente no padrão de imagem da OCI. `LABEL` grava metadado consultável
de forma estruturada, e as chaves `org.opencontainers.image.*` são reconhecidas
por registries, scanners e ferramentas de inventário.

Na prática isso importa em resposta a incidente: quando é preciso descobrir de
onde veio uma imagem em produção, quem mantém e qual commit a originou, o
metadado padronizado responde sem depender de convenção interna. Com
`MAINTAINER`, a informação existe mas nenhuma ferramenta a lê.

## Como corrigir

```dockerfile
LABEL org.opencontainers.image.authors="equipe-plataforma@exemplo.com" \
      org.opencontainers.image.title="conformidade" \
      org.opencontainers.image.description="Auditoria de configuração de containers" \
      org.opencontainers.image.source="https://github.com/org/repo" \
      org.opencontainers.image.licenses="Proprietary"
```

No pipeline, vale preencher também `revision` e `version` com o commit e a tag
do build — é o que fecha o rastro entre a imagem em execução e o código.

## Quando não se aplica

Não há caso em que `MAINTAINER` seja preferível. A correção é mecânica e sem
risco.
