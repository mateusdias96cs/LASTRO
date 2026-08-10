## Afirmação normativa

O Dockerfile não deve atualizar pacotes do sistema — `apt-get upgrade`,
`dist-upgrade`, `yum update`, `apk upgrade`. Manter a base atualizada é
responsabilidade da imagem base, não do build da aplicação.

## Por que importa

O problema é de reprodutibilidade. `apt-get upgrade` traz o que estiver
disponível nos repositórios naquele instante, então o mesmo Dockerfile produz
imagens diferentes conforme o dia em que roda. Duas consequências:

- **o build deixa de ser auditável.** Não há como reconstruir a imagem que foi
  para produção na semana passada, nem determinar exatamente o que ela contém
- **quebras aparecem sem alteração de código.** Uma atualização de biblioteca do
  sistema muda comportamento, e o commit que "causou" o problema não tocou em
  nada relacionado

Há também a expectativa errada que isso cria: um upgrade no build dá a sensação
de que a imagem está protegida, quando na verdade a proteção só vale para o
momento do build. A imagem construída hoje e executada por seis meses fica
igualmente desatualizada.

A abordagem correta é tratar a atualização como troca de dependência: fixar a
versão da base, e atualizá-la deliberadamente, com rebuild e novo deploy.

## Como corrigir

Remova o upgrade e atualize a base:

```dockerfile
# de
FROM debian:12
RUN apt-get update && apt-get upgrade -y
# para
FROM debian:12.8-slim@sha256:...
RUN apt-get update && apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*
```

Automatize o bump da base com uma ferramenta que abra pull request, e mantenha
scan de vulnerabilidade no pipeline para saber quando atualizar.

## Quando não se aplica

Quando a imagem base é sua e o upgrade acontece no build **dela**, com versões
fixadas. O que este controle rejeita é o upgrade indeterminado no build da
aplicação.
