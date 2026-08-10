## Afirmação normativa

O sistema de arquivos raiz do container deve ser montado como somente-leitura
(`read_only: true` no Compose, `readOnlyRootFilesystem: true` no Kubernetes).
Diretórios que realmente precisam de escrita devem receber um `tmpfs` ou volume
dedicado.

## Por que importa

Container é artefato imutável: o que roda deveria ser exatamente o que foi
construído e auditado. Raiz gravável quebra essa premissa e dá a um atacante o
que ele mais precisa depois de conseguir execução — **persistência e
ferramentas**.

Com raiz gravável, um processo comprometido baixa binários, grava um webshell,
altera configuração da aplicação ou substitui um script que será executado
depois. Com raiz somente-leitura, cada uma dessas ações falha, e a falha
costuma aparecer no log — o ataque fica mais difícil e mais barulhento.

É também um controle de detecção: aplicação legítima que tenta escrever na raiz
revela uma dependência não declarada.

## Como corrigir

Ative a flag e mapeie os caminhos graváveis:

```yaml
# Compose
read_only: true
tmpfs:
  - /tmp

# Kubernetes
securityContext:
  readOnlyRootFilesystem: true
volumeMounts:
  - name: tmp
    mountPath: /tmp
volumes:
  - name: tmp
    emptyDir: {}
```

Caminhos que costumam precisar de escrita: `/tmp`, cache de bibliotecas e
diretório de sessão de servidores de aplicação.

## Quando não se aplica

**Atenção a uma confusão frequente:** este controle é sobre a *raiz* do
container, não sobre montar um volume como somente-leitura. São coisas
diferentes — um volume `:ro` não torna a raiz imutável, e a raiz somente-leitura
não impede escrita em volumes montados com permissão.
