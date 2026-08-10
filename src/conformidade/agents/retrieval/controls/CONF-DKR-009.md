## Afirmação normativa

O cache do gerenciador de pacotes deve ser removido no **mesmo** `RUN` que fez
a instalação.

## Por que importa

Cada instrução do Dockerfile cria uma camada, e camadas são imutáveis. Se a
instalação acontece em um `RUN` e a limpeza em outro, o cache continua presente
na camada anterior — a imagem final carrega o peso e o conteúdo mesmo que o
diretório apareça vazio no sistema de arquivos combinado.

O efeito prático é dobrado:

- **tamanho**: o cache do apt costuma somar dezenas de megabytes, que são
  transferidos a cada pull, em cada nó, a cada deploy
- **superfície analisada**: scanners de vulnerabilidade inspecionam o conteúdo
  das camadas, e listas de pacotes obsoletas geram achados sobre coisas que a
  aplicação não usa — ruído que consome tempo de triagem

## Como corrigir

Encadeie tudo em uma instrução só:

```dockerfile
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl ca-certificates && \
    rm -rf /var/lib/apt/lists/*
```

Equivalentes: `apk add --no-cache` no Alpine, `dnf clean all` no Fedora/RHEL,
`pip install --no-cache-dir` para Python.

Alternativa mais moderna, que mantém o cache fora da imagem e ainda acelera
rebuilds:

```dockerfile
RUN --mount=type=cache,target=/var/cache/apt \
    apt-get update && apt-get install -y --no-install-recommends curl
```

## Quando não se aplica

Estágios intermediários de um build multi-stage cujo conteúdo não é copiado
para a imagem final — ali o cache não chega ao artefato publicado.
