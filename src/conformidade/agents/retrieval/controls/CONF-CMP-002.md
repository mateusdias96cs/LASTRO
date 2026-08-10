## Afirmação normativa

Portas de serviços de dados e de administração — bancos, filas, caches,
painéis, API do Docker — não devem ser publicadas em todas as interfaces do
host. Quando a publicação for necessária, prefixe com o endereço de loopback.

## Por que importa

`"5432:5432"` **não** publica em localhost: publica em `0.0.0.0`, ou seja, em
toda interface de rede da máquina. Numa máquina com IP alcançável — VPS,
instância em nuvem, notebook em rede corporativa — o banco fica exposto para
quem alcançar aquele IP.

O agravante é específico do Docker e pega muita gente: o daemon insere as
próprias regras no `iptables`, em uma cadeia processada **antes** das regras do
firewall do host. O resultado é que `ufw deny 5432` frequentemente não bloqueia
a porta publicada por um container. O administrador acredita estar protegido,
o firewall reporta a regra ativa, e a porta continua aberta.

Serviços de dados costumam ainda ter autenticação fraca ou padrão em ambiente
de desenvolvimento, o que transforma exposição acidental em acesso direto.

## Como corrigir

```yaml
# expõe só para a própria máquina
ports:
  - "127.0.0.1:5432:5432"
```

Melhor ainda: não publique. Serviços na mesma rede do Compose se enxergam pelo
nome do serviço, sem nenhuma porta publicada no host:

```yaml
# a aplicação conecta em postgres://banco:5432 — sem `ports:`
```

## Quando não se aplica

Quando a exposição é o objetivo (um proxy reverso na 80/443) e há autenticação
e TLS adequados. Porta de banco de dados praticamente nunca se enquadra.
