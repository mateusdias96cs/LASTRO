## Afirmação normativa

Containers não devem executar como root (UID 0). O usuário deve ser declarado
explicitamente como um UID numérico não-zero — `user:` no Compose,
`runAsUser` combinado com `runAsNonRoot: true` no Kubernetes, `USER` no
Dockerfile.

## Por que importa

Root dentro do container não é root no host, graças aos user namespaces — mas
essa proteção só vale enquanto todas as outras camadas seguram. Root amplifica
qualquer outra falha:

- em volume montado do host, root escreve onde o usuário da aplicação não
  escreveria
- se houver uma capability perigosa ou uma fuga de container, o ponto de
  partida já é privilegiado
- dentro do container, root pode instalar pacotes, alterar binários e
  desabilitar controles da própria aplicação

Detalhe importante para Kubernetes: **`runAsNonRoot: true` sozinho não define
qual usuário usar** — ele apenas rejeita o pod se a imagem tentar rodar como
UID 0. Se a imagem não declara `USER`, o pod nem inicia. Os dois campos se
complementam.

## Como corrigir

Prefira UID numérico. O PodSecurityStandard `restricted` valida o **UID**, não
o nome do usuário — um `USER appuser` no Dockerfile não é suficiente para o
Kubernetes saber que não é root.

```dockerfile
RUN useradd --uid 10001 --no-create-home app
USER 10001
```

```yaml
securityContext:
  runAsNonRoot: true
  runAsUser: 10001
```

## Quando não se aplica

Estágios intermediários de build podem precisar de root para instalar pacotes —
o que importa é o usuário do **último** estágio, que é o que vai executar.
