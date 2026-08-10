## Afirmação normativa

Imagens não devem ser referenciadas por tag mutável. `latest`, `stable`,
`main`, `edge`, `dev` e `nightly` apontam para conteúdo que muda sem aviso.

## Por que importa

Tag em registry é um rótulo reatribuível, não um identificador de conteúdo. O
mantenedor publica uma nova imagem com a mesma tag e todo mundo que fizer pull
depois recebe algo diferente — sem que nenhuma linha do seu repositório mude.

As consequências práticas:

- **deploy não reprodutível**: o rollback para o commit anterior não devolve a
  imagem anterior, porque a tag já se moveu
- **réplicas divergentes**: pods criados em momentos diferentes podem estar
  rodando builds diferentes do mesmo Deployment
- **auditoria impossível**: não há como afirmar o que estava executando na data
  de um incidente
- **superfície de cadeia de suprimentos**: se a conta do publicador for
  comprometida, o conteúdo malicioso entra no próximo pull, sem alteração
  visível em lugar nenhum

## Como corrigir

Use tag de versão imutável e fixe o digest:

```yaml
image: nginx:1.27.3@sha256:...
```

A tag legível continua útil para quem lê o manifesto; o digest é o que garante
o conteúdo. Automatize a atualização com uma ferramenta que abra pull request,
para que a mudança passe por revisão.

## Quando não se aplica

Ambiente de desenvolvimento local descartável. Em qualquer ambiente
compartilhado — inclusive homologação — a tag móvel já causa o problema de
"funciona na minha máquina" na sua forma mais cara de diagnosticar.
