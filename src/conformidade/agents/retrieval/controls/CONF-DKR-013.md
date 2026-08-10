## Afirmação normativa

`ENTRYPOINT` e `CMD` devem usar a forma exec — array JSON —, não a forma shell.

## Por que importa

Na forma shell (`ENTRYPOINT /app/start.sh`), o Docker executa
`/bin/sh -c "/app/start.sh"`. O shell vira **PID 1** e a aplicação vira processo
filho. Isso quebra o encerramento gracioso.

Quando o orquestrador quer parar o container, ele envia `SIGTERM` ao PID 1. O
`sh` do BusyBox e do Debian não repassa o sinal para os filhos — então a
aplicação não recebe nada, continua atendendo, e depois do
`terminationGracePeriodSeconds` (30s por padrão no Kubernetes) leva `SIGKILL`.

O efeito visível em produção: durante cada deploy, cada rolling update e cada
scale-down, as requisições em andamento nos pods que estão saindo são cortadas
no meio. Conexões abertas caem, transações ficam incompletas, e o erro aparece
para o usuário sem nada nos logs da aplicação — porque ela nunca soube que ia
morrer.

Na forma exec, o processo da aplicação **é** o PID 1 e recebe o `SIGTERM`
diretamente, podendo drenar conexões e encerrar limpo.

## Como corrigir

```dockerfile
# em vez de
ENTRYPOINT /app/start.sh
CMD python -m app

# use
ENTRYPOINT ["/app/start.sh"]
CMD ["python", "-m", "app"]
```

Se o entrypoint for um script shell, use `exec` na última linha dele, para que
o processo final substitua o shell:

```sh
exec python -m app "$@"
```

## Quando não se aplica

Quando a expansão de variável de ambiente pelo shell é necessária no comando.
Mesmo aí, prefira um script com `exec` no final a depender da forma shell.
