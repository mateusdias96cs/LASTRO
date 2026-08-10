## Afirmação normativa

Capabilities de alto risco não devem ser concedidas a containers. Isso inclui
`ALL`, `SYS_ADMIN`, `SYS_MODULE`, `SYS_PTRACE`, `SYS_RAWIO`, `NET_ADMIN`,
`DAC_READ_SEARCH`, `BPF` e `PERFMON`.

## Por que importa

Capabilities fatiam o poder de root em pedaços. O problema é que alguns pedaços
sozinhos já reconstituem root, ou perto disso:

- **SYS_ADMIN** é a mais ampla de todas — permite montar sistemas de arquivos,
  manipular namespaces e é o caminho de fuga de container mais documentado que
  existe. Conceder SYS_ADMIN é quase equivalente a `privileged`
- **SYS_MODULE** carrega módulos no kernel do host: comprometimento total
- **SYS_PTRACE** permite inspecionar e injetar código em outros processos
- **DAC_READ_SEARCH** ignora a verificação de permissão de leitura
- **NET_ADMIN** reconfigura a rede, o que viabiliza interceptação de tráfego

`cap_add: [ALL]` concede tudo isso de uma vez e não tem justificativa legítima.

## Como corrigir

Descarte tudo e readicione apenas o necessário:

```yaml
# Compose
cap_drop: [ALL]
cap_add: [NET_BIND_SERVICE]   # só se realmente precisar de porta < 1024

# Kubernetes
securityContext:
  capabilities:
    drop: ["ALL"]
    add: ["NET_BIND_SERVICE"]
```

Se a necessidade é escutar em porta baixa, considere apenas mudar a porta da
aplicação para acima de 1024 — resolve sem capability nenhuma.

## Quando não se aplica

Ferramentas de diagnóstico de rede ou de kernel, em execução temporária e
isolada. Nunca em serviço de longa duração exposto a tráfego.
