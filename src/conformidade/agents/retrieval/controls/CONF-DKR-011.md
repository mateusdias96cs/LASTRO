## Afirmação normativa

O Dockerfile não deve copiar o contexto de build inteiro (`COPY . .`). Copie
caminhos explícitos e mantenha um `.dockerignore` restritivo.

## Por que importa

`COPY . .` leva para dentro da imagem tudo o que o `.dockerignore` não barrar —
e a lista do que costuma estar no diretório é desconfortável:

- `.env` com credenciais de desenvolvimento
- `.git/`, que contém **todo o histórico**, incluindo segredos que foram
  removidos em commits posteriores
- chaves SSH, certificados, arquivos de configuração de nuvem
- `node_modules` ou `.venv` construídos para outro sistema operacional

O agravante é que segredo copiado para uma camada **permanece nela**. Apagar o
arquivo em uma instrução posterior não remove o conteúdo da imagem — qualquer
pessoa com acesso à imagem recupera com `docker history` ou extraindo as
camadas.

Também há o efeito colateral de cache: qualquer alteração em qualquer arquivo
do diretório invalida a camada e força a reconstrução de tudo que vem depois.

## Como corrigir

Copie o que é necessário, na ordem que aproveita o cache:

```dockerfile
# dependências primeiro — só invalida quando o lock muda
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-install-project

# depois o código
COPY src/ ./src/
```

E mantenha um `.dockerignore` que negue por padrão o que não deve entrar:
`.git/`, `.env`, `*.pem`, `*.key`, `.venv/`, `tests/`.

## Quando não se aplica

Contexto de build já minimizado e verificado, com `.dockerignore` rigoroso —
mas mesmo assim a cópia explícita dá melhor uso de cache.
