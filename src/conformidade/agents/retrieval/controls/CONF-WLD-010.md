## Afirmação normativa

Todo container de serviço de longa duração deve declarar verificação de saúde:
`healthcheck` no Compose, `livenessProbe` e `readinessProbe` no Kubernetes.

## Por que importa

Sem probe, o orquestrador só sabe se o **processo** está vivo — não se a
aplicação está atendendo. Um processo travado, com deadlock ou com o pool de
conexões esgotado continua no ar do ponto de vista do runtime, e continua
recebendo tráfego.

As duas probes do Kubernetes respondem a perguntas diferentes, e trocá-las causa
problema:

- **readiness** — "posso receber tráfego agora?" Falhou, o pod sai do balanceamento
  mas continua rodando. É a que evita enviar requisição para instância que ainda
  está subindo ou temporariamente sobrecarregada.
- **liveness** — "preciso ser reiniciado?" Falhou, o container é morto. Por isso
  ela deve verificar apenas o processo local, nunca dependência externa: uma
  liveness que consulta o banco reinicia toda a frota quando o banco oscila,
  transformando uma degradação em uma queda.

## Como corrigir

```yaml
# Kubernetes
livenessProbe:
  httpGet: { path: /health/live, port: 8080 }
readinessProbe:
  httpGet: { path: /health/ready, port: 8080 }

# Compose
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:8080/health/live"]
  interval: 30s
```

O endpoint de liveness não deve tocar em dependência externa. O de readiness
deve — é justamente o que ele existe para reportar.

## Quando não se aplica

Containers de inicialização (`initContainers`) e jobs em lote: rodam, terminam
e não recebem tráfego.
