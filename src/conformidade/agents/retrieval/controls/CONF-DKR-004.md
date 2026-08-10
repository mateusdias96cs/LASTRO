## Afirmação normativa

Conteúdo remoto não deve ser baixado durante o build sem verificação de
integridade. `ADD https://...` sem checksum traz para dentro da imagem o que
quer que esteja na URL no momento do build.

## Por que importa

É um problema de cadeia de suprimentos. O build confia cegamente em um servidor
de terceiro, e três coisas podem dar errado sem que nada no repositório mude:

- o conteúdo da URL é alterado pelo mantenedor, e o build passa a produzir uma
  imagem diferente da que foi auditada
- o servidor de origem é comprometido, e o conteúdo malicioso entra na imagem
  silenciosamente
- o domínio expira ou é sequestrado, e passa a servir outra coisa

Como o build normalmente roda em pipeline automatizado, ninguém inspeciona o
que foi baixado. O artefato vai para o registry e daí para produção.

## Como corrigir

O Dockerfile suporta verificação de checksum diretamente:

```dockerfile
ADD --checksum=sha256:24454f830c... https://exemplo.com/pacote.tar.gz /tmp/
```

Alternativa que funciona em qualquer versão e deixa a verificação explícita:

```dockerfile
RUN curl -fsSL -o /tmp/pacote.tar.gz https://exemplo.com/pacote.tar.gz && \
    echo "24454f830c...  /tmp/pacote.tar.gz" | sha256sum -c - && \
    tar -xzf /tmp/pacote.tar.gz -C /opt && rm /tmp/pacote.tar.gz
```

Melhor ainda: baixe uma vez, publique o artefato no seu próprio registry ou
storage, e consuma de lá.

## Quando não se aplica

Quando há verificação de checksum ou assinatura fixada no próprio Dockerfile —
que é o que este controle pede. Origem remota sem verificação nenhuma não tem
justificativa.
