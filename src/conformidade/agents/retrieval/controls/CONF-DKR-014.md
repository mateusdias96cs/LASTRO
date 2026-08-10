## Afirmação normativa

Segredos não devem aparecer em `ENV` nem `ARG` no Dockerfile. Segredo de build
deve usar `RUN --mount=type=secret`; segredo de runtime deve ser injetado pelo
orquestrador ou por um cofre.

## Por que importa

`ENV` e `ARG` ficam gravados nos **metadados da imagem**. Qualquer pessoa com
acesso à imagem lê os valores:

```bash
docker history --no-trunc <imagem>
docker inspect <imagem>
```

Isso vale mesmo que uma instrução posterior sobrescreva ou apague o valor —
camadas são imutáveis e o histórico permanece. Não existe "apagar depois".

O caso mais comum e mais caro: um `ARG GITHUB_TOKEN` usado para clonar um
repositório privado no build. O token fica no histórico da imagem, a imagem vai
para o registry, e todo mundo com acesso de pull ao registry tem o token. Como
esse acesso costuma ser amplo dentro da organização, o segredo se espalha em
silêncio.

`ARG` tem ainda a armadilha de parecer temporário — ele é "só para o build" —
mas o valor usado é persistido no metadado da camada.

## Como corrigir

Para segredo de build, use o mount, que não deixa rastro na imagem:

```dockerfile
RUN --mount=type=secret,id=npm_token \
    NPM_TOKEN=$(cat /run/secrets/npm_token) npm ci
```

```bash
docker build --secret id=npm_token,src=./npm_token .
```

Para runtime, não coloque nada no Dockerfile: injete via secret do orquestrador
ou, no Azure, via `DefaultAzureCredential` com managed identity buscando do Key
Vault — assim não há segredo estático em lugar nenhum.

## Quando não se aplica

`ENV` e `ARG` são apropriados para configuração não sensível: versão de
dependência, nível de log, nome do ambiente.
