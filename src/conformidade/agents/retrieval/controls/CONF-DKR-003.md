## Afirmação normativa

Use `COPY` em vez de `ADD` quando a origem for um arquivo ou diretório local
comum.

## Por que importa

`COPY` faz exatamente uma coisa: copia. `ADD` tem comportamentos implícitos que
dependem do que a origem parece ser:

- se a origem for um arquivo tar reconhecido, `ADD` **extrai** o conteúdo no
  destino em vez de copiar o arquivo
- se a origem for uma URL, `ADD` **baixa** da rede durante o build

O problema é que esse comportamento é decidido pelo conteúdo, não pela
instrução. Um arquivo que passa a ser um tarball muda o resultado do build sem
que o Dockerfile mude. E a extração automática pode escrever fora do caminho
esperado se o tar for construído para isso.

É uma questão de tornar explícito o que está acontecendo — em auditoria, uma
instrução que faz coisas diferentes conforme a entrada é difícil de avaliar.

## Como corrigir

```dockerfile
# em vez de
ADD ./config.json /etc/app/config.json
# use
COPY ./config.json /etc/app/config.json
```

Quando precisar extrair um arquivo, faça de forma explícita:

```dockerfile
COPY ./pacote.tar.gz /tmp/
RUN tar -xzf /tmp/pacote.tar.gz -C /opt && rm /tmp/pacote.tar.gz
```

## Quando não se aplica

`ADD` é a escolha certa quando a extração automática de tarball local é
justamente o comportamento desejado e está documentado. Para origem remota, ver
`CONF-DKR-004`.
