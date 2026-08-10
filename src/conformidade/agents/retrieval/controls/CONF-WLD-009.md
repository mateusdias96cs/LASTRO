## Afirmação normativa

Todo container deve declarar limites de CPU e de memória. No Compose, via
`deploy.resources.limits` (ou `mem_limit`/`cpus` no formato antigo); no
Kubernetes, via `resources.limits`, acompanhados de `resources.requests`.

## Por que importa

Sem limite, um container consome todo o recurso disponível no nó. Isso derruba
os vizinhos, e não é preciso atacante nenhum: basta um vazamento de memória,
uma consulta pesada ou um pico de tráfego.

No Kubernetes o efeito é pior do que parece. Sem `requests`, o escalonador não
sabe quanto o pod precisa e empilha carga em nós que não a suportam. Quando a
memória do nó acaba, o kubelet mata pods para liberar espaço — e pods sem
`requests` são os primeiros da fila, inclusive os que não causaram o problema.

Também é um controle de contenção de incidente: com limite, um container
comprometido que passe a minerar criptomoeda ou varrer a rede tem o estrago
limitado ao seu quinhão.

## Como corrigir

```yaml
# Kubernetes
resources:
  requests: { cpu: "100m", memory: "128Mi" }
  limits:   { cpu: "500m", memory: "512Mi" }

# Compose
deploy:
  resources:
    limits: { cpus: "0.5", memory: 512M }
```

Defina `requests` a partir do consumo observado em regime normal, e `limits`
com folga para o pico. Limite de memória muito apertado causa OOM kill em
produção; muito folgado não protege ninguém.

## Quando não se aplica

Cargas de processamento em lote em nó dedicado, onde o objetivo é justamente
usar o nó inteiro. Ainda assim, declare `requests` para o escalonador.
