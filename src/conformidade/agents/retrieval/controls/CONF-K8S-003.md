## Afirmação normativa

Pods que não interagem com a API do Kubernetes devem declarar
`automountServiceAccountToken: false`, no pod ou na service account.

## Por que importa

Por padrão, o Kubernetes monta um token de service account em
`/var/run/secrets/kubernetes.io/serviceaccount/token` dentro de **todo** pod,
mesmo os que nunca falam com a API. A esmagadora maioria das aplicações — API
web, worker, banco — está nesse caso.

Se o container for comprometido, esse token é a primeira coisa que um atacante
procura. Ele dá acesso autenticado à API do cluster com as permissões daquela
service account, o que transforma "invadiram um container" em "estão dentro do
plano de controle". Mesmo a service account `default`, sem RBAC extra, costuma
permitir enumerar recursos do namespace — informação suficiente para planejar o
próximo passo.

É o exemplo mais direto de privilégio concedido por omissão: ninguém pediu o
token, ele veio sozinho.

## Como corrigir

```yaml
# no pod
spec:
  automountServiceAccountToken: false

# ou, melhor, na service account — vale para todos os pods que a usam
apiVersion: v1
kind: ServiceAccount
metadata:
  name: app-sa
automountServiceAccountToken: false
```

Para os pods que realmente precisam da API, mantenha a montagem e restrinja o
RBAC ao mínimo — Role no namespace, nunca ClusterRole ampla.

## Quando não se aplica

Controladores, operadores e qualquer carga que legitimamente chame a API.

**Não confunda com Secret comum:** o token de service account é armazenado como
Secret por baixo, mas o controle aqui é sobre a montagem automática de uma
credencial de acesso ao cluster, não sobre segredos da aplicação (ver
`CONF-SEC-001`).
