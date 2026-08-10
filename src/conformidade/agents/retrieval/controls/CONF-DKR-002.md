## Afirmação normativa

O último estágio do Dockerfile deve declarar `HEALTHCHECK`, indicando como
verificar se a aplicação está atendendo.

## Por que importa

Sem healthcheck, o runtime só sabe se o processo existe. Um servidor travado,
com deadlock ou com pool de conexões esgotado, continua "rodando" e continua
recebendo tráfego.

O healthcheck no Dockerfile é a definição de saúde que **acompanha a imagem** —
quem for executá-la não precisa saber qual endpoint consultar. Isso vale para
execução direta, para Compose, e como documentação executável do contrato da
aplicação.

## Como corrigir

```dockerfile
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD curl -fsS http://localhost:8080/health/live || exit 1
```

Ajuste `start-period` ao tempo real de inicialização: valor curto demais faz o
container ser marcado como não saudável durante um boot legítimo.

Se a imagem não tiver `curl` (o que é desejável em imagem mínima), use o
runtime da própria aplicação:

```dockerfile
HEALTHCHECK CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8080/health/live')"
```

## Quando não se aplica

Em Kubernetes, as probes do manifesto prevalecem e o `HEALTHCHECK` da imagem é
ignorado — mas ele continua valendo para execução local e Compose, então não é
motivo para omiti-lo.

Imagens de ferramenta de linha de comando e estágios de build não precisam.
