## Afirmação normativa

Containers não devem declarar `hostPort`. A exposição de serviços deve ser
feita por `Service`.

## Por que importa

`hostPort` reserva a porta diretamente na interface do nó e encaminha para o
container. Três consequências:

- **contorna o modelo de rede do cluster.** O tráfego chega ao container sem
  passar pelo Service, então NetworkPolicy baseada em seletor de pod não se
  aplica ao caminho de entrada. Um controle que a equipe acredita estar ativo
  simplesmente não é consultado.
- **limita o escalonamento a um pod por nó.** Duas réplicas não podem
  compartilhar a mesma porta no mesmo nó, então réplicas adicionais ficam
  pendentes sem motivo aparente.
- **expõe o serviço no IP do nó.** Se os nós tiverem endereço alcançável, a
  porta fica acessível diretamente, fora de qualquer LoadBalancer, WAF ou
  Ingress que a equipe tenha colocado na frente.

## Como corrigir

Exponha pelo caminho normal:

```yaml
# em vez de hostPort no container
apiVersion: v1
kind: Service
spec:
  type: ClusterIP        # ou LoadBalancer para tráfego externo
  ports:
    - port: 80
      targetPort: 8080
```

Para HTTP externo, prefira Ingress ou Gateway API, que centralizam TLS e
roteamento.

## Quando não se aplica

DaemonSets de infraestrutura que precisam receber tráfego no próprio nó —
proxy de nó, coletor de log, agente de monitoração.

**Não confunda com `hostNetwork`** (ver `CONF-WLD-004`): `hostPort` mapeia
**uma** porta e o container mantém seu próprio namespace de rede;
`hostNetwork` entrega a pilha de rede inteira do nó. O segundo é bem mais
grave.
