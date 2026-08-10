## Afirmação normativa

Toda referência de imagem deve declarar tag explícita. Omitir a tag faz o
runtime assumir `latest`.

## Por que importa

`nginx` e `nginx:latest` são a mesma coisa para o runtime, e nenhuma das duas
identifica conteúdo. O que foi auditado hoje não é necessariamente o que vai
executar amanhã — a tag é um ponteiro móvel que o mantenedor da imagem
reaponta a cada publicação.

Isso quebra três coisas ao mesmo tempo: reprodutibilidade (o mesmo manifesto
gera resultados diferentes), rastreabilidade (não dá para dizer qual versão
está em produção) e resposta a incidente (não dá para responder "estamos
expostos a esta CVE?" sem saber qual build está rodando).

No Kubernetes há um efeito adicional: com a tag `latest`, o `imagePullPolicy`
padrão vira `Always`, então cada recriação de pod pode trazer conteúdo
diferente — inclusive dentro do mesmo Deployment, resultando em réplicas
rodando versões distintas.

## Como corrigir

Declare a versão:

```yaml
image: nginx:1.27.3
```

E, de preferência, fixe também o digest (ver `CONF-IMG-003`). Para automatizar
a atualização sem perder o controle, use uma ferramenta de bump de dependência
que abra pull request com a mudança visível na revisão.

## Quando não se aplica

Nunca em ambiente compartilhado ou produção. Em experimentação local descartável
o impacto é baixo, mas o hábito vaza para os manifestos que vão para o cluster.
