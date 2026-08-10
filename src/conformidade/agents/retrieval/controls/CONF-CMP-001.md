## Afirmação normativa

Serviços do Compose devem declarar `security_opt: ["no-new-privileges:true"]`,
que impede que um processo dentro do container obtenha privilégios além dos
concedidos na criação.

## Por que importa

Sem essa flag, um binário com bit setuid dentro da imagem permite que um
processo escale para o dono do binário — tipicamente root. É o caminho clássico
de escalada local, e ele funciona dentro do container do mesmo jeito que
funciona num host.

O cenário concreto: a aplicação roda como usuário não-root (o que está certo),
mas a imagem base traz `/bin/su`, `/usr/bin/passwd` ou `sudo` com setuid. Um
atacante que consiga execução de comando usa esse binário para virar root
dentro do container — e aí todas as outras defesas passam a valer menos.

`no-new-privileges` define a flag `NoNewPrivs` do kernel, que faz o setuid ser
ignorado. É barato, não quebra aplicação bem-comportada e fecha a classe
inteira.

## Como corrigir

```yaml
services:
  api:
    security_opt:
      - no-new-privileges:true
```

Atenção ao separador: o Compose documenta a forma com dois-pontos
(`no-new-privileges:true`) e a CLI do Docker usa igual
(`--security-opt no-new-privileges=true`). As duas circulam na prática.

O equivalente no Kubernetes é `allowPrivilegeEscalation: false` (ver
`CONF-K8S-001`) — mesmo conceito, sintaxe diferente.

## Quando não se aplica

Container que legitimamente precisa trocar de usuário em tempo de execução,
como um entrypoint que faz drop de privilégio com `gosu` ou `su-exec`. Nesse
caso, prefira já iniciar como o usuário final e dispensar a troca.
