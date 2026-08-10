## Afirmação normativa

Caminhos sensíveis do host — `/`, `/etc`, `/proc`, `/sys`, `/dev`, `/var/run`,
`/root`, diretórios de binários do sistema — não devem ser montados dentro de
containers. Quando a montagem de um caminho do host for indispensável, ela deve
apontar para o subdiretório mais específico possível e ser somente-leitura.

## Por que importa

O isolamento de um container é, em boa parte, isolamento de sistema de
arquivos. Montar um caminho do host abre um buraco exatamente nessa fronteira.

O impacto varia com o caminho, e todos os casos comuns são graves: `/etc` expõe
configuração e usuários do sistema; `/proc` e `/sys` permitem ler estado de
outros processos e, com escrita, alterar parâmetros do kernel; `/var/run`
costuma conter sockets de serviços privilegiados; a raiz expõe tudo de uma vez.

Montagem com escrita é pior: um processo comprometido passa a modificar
configuração ou binários que o host vai executar depois.

## Como corrigir

Reduza o escopo e o modo de acesso:

```yaml
# em vez de
- /etc:/host-etc
# monte só o necessário, somente-leitura
- /etc/ssl/certs:/etc/ssl/certs:ro
```

No Kubernetes, prefira `configMap`, `secret` ou `emptyDir` a `hostPath`. Se
`hostPath` for necessário, combine com `readOnly: true` no `volumeMount`.

## Quando não se aplica

Agentes de observabilidade e segurança que precisam inspecionar o nó. Mesmo
nesses casos, monte somente-leitura e apenas o subcaminho usado.
