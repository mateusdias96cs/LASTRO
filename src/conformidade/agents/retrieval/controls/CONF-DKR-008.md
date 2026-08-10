## Afirmação normativa

Arquivos e diretórios na imagem não devem receber permissão de escrita para
todos. `chmod 777`, `chmod 666`, `chmod a+w` e equivalentes não devem aparecer
no Dockerfile.

## Por que importa

`chmod 777` costuma ser usado para "resolver" um erro de permissão sem
investigar a causa. O efeito é que qualquer processo dentro do container passa a
poder sobrescrever aquele arquivo.

O impacto depende do que ficou gravável, e os casos comuns são ruins:

- **binário ou script executado depois**: um atacante substitui o conteúdo e
  ganha execução na próxima chamada
- **arquivo de configuração**: permite desativar controles da própria aplicação,
  redirecionar conexão ou apontar log para outro lugar
- **diretório de biblioteca**: abre espaço para injetar código que será
  carregado pelo runtime

Quando a raiz do container é somente-leitura (ver `CONF-WLD-008`), boa parte
desse risco desaparece — mas o `chmod` continua sendo sinal de que a
propriedade dos arquivos está errada.

## Como corrigir

Ajuste o **dono** em vez da permissão. É quase sempre o que se queria:

```dockerfile
# em vez de
RUN chmod -R 777 /opt/app
# defina o dono na própria cópia
COPY --chown=10001:10001 . /opt/app
```

Para o caso específico de diretório que a aplicação precisa escrever, dê
permissão ao usuário dela, não a todos:

```dockerfile
RUN mkdir -p /var/cache/app && chown 10001:10001 /var/cache/app && \
    chmod 750 /var/cache/app
```

## Quando não se aplica

Diretórios que precisam ser graváveis por múltiplos usuários com sticky bit
(como `/tmp`, que usa `1777`) já vêm configurados na imagem base e não precisam
ser recriados.
