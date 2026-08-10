## Afirmação normativa

Cargas de trabalho devem declarar um namespace dedicado em
`metadata.namespace`. O namespace `default` não deve receber aplicação.

## Por que importa

Namespace é a unidade de isolamento lógico do Kubernetes, e quase todo controle
se apoia nele: RBAC delimita permissão por namespace, NetworkPolicy delimita
tráfego por namespace, ResourceQuota e LimitRange delimitam consumo por
namespace, e o PodSecurityAdmission aplica perfil de segurança por namespace.

O `default` não tem nada disso configurado por convenção, e é onde tudo cai
quando ninguém declara. O resultado é um espaço compartilhado sem política, com
cargas de times diferentes convivendo — onde uma NetworkPolicy que isolasse
seria ampla demais para ser escrita e um RBAC restritivo quebraria alguém.

Há um efeito de gestão também: sem namespace declarado, o destino do manifesto
depende do contexto do `kubectl` de quem aplica. É como um deploy vai para o
cluster errado.

## Como corrigir

```yaml
metadata:
  name: minha-app
  namespace: producao
```

Crie o namespace com política desde o início — PodSecurityAdmission no perfil
`restricted`, NetworkPolicy default-deny e ResourceQuota:

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: producao
  labels:
    pod-security.kubernetes.io/enforce: restricted
```

## Quando não se aplica

Manifestos distribuídos como template, em que o namespace é injetado no momento
da aplicação (por Helm, Kustomize ou pipeline). Nesse caso a ausência é
intencional — mas o valor precisa estar definido em algum lugar do processo de
deploy.
