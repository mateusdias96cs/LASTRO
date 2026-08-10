## Afirmação normativa

Scripts remotos não devem ser executados diretamente em um interpretador
durante o build. O padrão `curl ... | sh` é proibido.

## Por que importa

`curl -fsSL https://exemplo.com/install.sh | sh` executa código arbitrário de
um terceiro, no momento do build, sem que ninguém tenha visto o que está sendo
executado. Não há checksum, não há revisão, não há registro do que foi rodado.

Se o servidor de origem for comprometido, ou se o script mudar, o
comprometimento entra na sua imagem e vai para produção. E como o conteúdo nunca
foi gravado em disco antes de executar, não sobra nem artefato para investigar
depois.

Há um agravante conhecido: como o script é consumido em streaming, um servidor
malicioso pode servir conteúdo diferente dependendo de como a requisição é
feita — entregando algo inofensivo para quem inspeciona com o navegador e outra
coisa para o `curl` do pipeline.

Note que o build normalmente roda como root, então esse código executa com
privilégio total sobre a imagem.

## Como corrigir

Baixe, verifique, execute:

```dockerfile
RUN curl -fsSL -o /tmp/install.sh https://exemplo.com/install.sh && \
    echo "a1b2c3...  /tmp/install.sh" | sha256sum -c - && \
    sh /tmp/install.sh && rm /tmp/install.sh
```

Melhor: use o gerenciador de pacotes da distribuição ou da linguagem, com
versão fixada e lockfile. Ele já resolve verificação de integridade.

## Quando não se aplica

Não há caso legítimo em build de imagem de produção. Em script de
desenvolvimento local o risco é seu, mas o padrão não deve migrar para o
Dockerfile.
