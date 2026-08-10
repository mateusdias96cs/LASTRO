## Afirmação normativa

O último estágio do Dockerfile deve declarar `USER` com um UID numérico
não-zero. Sem essa instrução, o container executa como root.

## Por que importa

A ausência de `USER` não é neutra: o padrão do Docker é root. Uma imagem sem
`USER` produz um container root em qualquer lugar onde for executada.

Root dentro do container amplifica qualquer outra falha. Em volume montado do
host, escreve onde o usuário da aplicação não escreveria; combinado com uma
capability perigosa ou uma fuga de container, o ponto de partida já é
privilegiado; e dentro do próprio container permite alterar binários e
desabilitar controles da aplicação.

Um detalhe que muda a implementação: **use UID numérico, não nome de usuário.**
O PodSecurityStandard `restricted` do Kubernetes valida `runAsNonRoot` olhando
o UID declarado na imagem. Se o Dockerfile diz `USER appuser`, o Kubernetes não
consegue determinar se é root e **rejeita o pod**. Com `USER 10001`, a
verificação passa.

## Como corrigir

```dockerfile
RUN groupadd --gid 10001 app && \
    useradd --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin app
USER 10001:10001
```

Garanta que os caminhos que a aplicação precisa escrever pertençam a esse UID,
usando `COPY --chown=10001:10001`.

## Quando não se aplica

Estágios intermediários de build legitimamente rodam como root para instalar
pacotes. O que importa é o `USER` do **último** estágio, que é o que vira
imagem final.

Se a imagem base já declara um usuário não-root, o container não roda como
root — mas isso não é verificável a partir do Dockerfile isoladamente, e
declarar explicitamente remove a ambiguidade.
