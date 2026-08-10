## Afirmação normativa

Toda instrução `apt-get install` no Dockerfile deve usar a flag
`--no-install-recommends`, para não instalar pacotes que ninguém pediu.

## Por que importa

O apt instala, por padrão, os pacotes marcados como "recomendados" pela
dependência — não apenas os obrigatórios. Ninguém pediu por eles e quase sempre
não são usados.

O custo aparece em três lugares:

- **superfície de ataque**: cada pacote extra é código dentro do container que
  pode conter vulnerabilidade. Recomendados costumam puxar utilitários de rede,
  interpretadores e documentação — exatamente o ferramental que um atacante
  aproveita depois de conseguir execução
- **ruído no scan**: CVEs em pacotes que a aplicação nunca chama consomem tempo
  de triagem e diluem os achados que importam
- **tamanho**: um `install` inocente pode trazer centenas de megabytes

O caso clássico: instalar um cliente de banco de dados e receber junto o
servidor completo, com serviço e usuário criados.

## Como corrigir

```dockerfile
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        curl ca-certificates && \
    rm -rf /var/lib/apt/lists/*
```

Se algo quebrar, o pacote faltante é identificável no erro e pode ser
adicionado explicitamente — o que é melhor, porque a dependência fica
declarada.

Vale também revisar a imagem base: variantes `-slim` já vêm sem boa parte do
que não é essencial.

## Quando não se aplica

Imagens de desenvolvimento onde a conveniência importa mais que o tamanho.
Imagem de produção, não.
