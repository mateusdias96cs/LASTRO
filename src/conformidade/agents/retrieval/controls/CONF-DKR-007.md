## Afirmação normativa

`sudo` não deve ser usado nas instruções do Dockerfile nem permanecer
instalado na imagem final do container.

## Por que importa

Dois problemas distintos.

**No build, é desnecessário.** As instruções `RUN` já executam como root por
padrão. Um `sudo` ali só adiciona uma dependência e uma camada de indireção que
pode falhar de formas surpreendentes — `sudo` espera TTY em algumas
configurações e requer resolução de hostname, o que gera erros difíceis de
diagnosticar em build.

**Na imagem final, é um caminho de escalada.** O binário do `sudo` tem bit
setuid. Se ele ficar na imagem e a aplicação rodar como usuário não-root — que
é o correto —, um atacante que consiga execução de comando tenta usá-lo para
virar root dentro do container. Isso derruba justamente a proteção que o
`USER` não-root deveria oferecer.

A combinação "roda como não-root, mas tem sudo instalado" é pior que a soma das
partes: dá a impressão de container endurecido e mantém a porta aberta.

## Como corrigir

Remova o `sudo` das instruções e da lista de pacotes instalados. Se precisar
alternar de usuário durante o build, use a própria instrução `USER`:

```dockerfile
USER root
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates && \
    rm -rf /var/lib/apt/lists/*
USER 10001
```

Se o processo precisa de um privilégio específico em runtime, conceda a
capability correspondente em vez de manter um caminho para root inteiro.

## Quando não se aplica

Imagens de ambiente de desenvolvimento interativo, em que a pessoa
deliberadamente precisa alternar privilégio. Essas imagens não devem executar
carga de produção.
