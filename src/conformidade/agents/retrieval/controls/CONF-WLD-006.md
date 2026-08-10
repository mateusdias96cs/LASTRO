## Afirmação normativa

Todo container deve descartar explicitamente o conjunto de capabilities padrão
(`cap_drop: [ALL]` no Compose, `capabilities.drop: ["ALL"]` no Kubernetes) e
readicionar apenas o que a aplicação comprovadamente usa.

## Por que importa

O runtime concede um conjunto padrão de capabilities a todo container mesmo sem
ninguém pedir — entre elas `CHOWN`, `SETUID`, `SETGID`, `NET_RAW` e
`DAC_OVERRIDE`. A esmagadora maioria das aplicações não usa nenhuma delas.

Duas merecem atenção especial:

- **NET_RAW** permite criar sockets raw, o que viabiliza spoofing de ARP e DNS
  a partir de dentro do container — uma ponte para atacar os vizinhos na rede
- **DAC_OVERRIDE** ignora verificações de permissão de arquivo

O ponto é de superfície de ataque: privilégio concedido e não usado é
privilégio disponível para quem comprometer o processo. Descartar tudo e
readicionar sob demanda inverte o padrão de inseguro para seguro.

## Como corrigir

```yaml
# Compose
cap_drop: [ALL]

# Kubernetes
securityContext:
  capabilities:
    drop: ["ALL"]
```

Se algo quebrar, o erro indica qual capability falta — readicione só aquela.
Vale medir: a maioria das aplicações web e de API roda sem nenhuma.

## Quando não se aplica

Não há exceção para o `drop: ALL`. A discussão legítima é sobre **o que
readicionar**, e essa lista deve ser curta e justificada.
