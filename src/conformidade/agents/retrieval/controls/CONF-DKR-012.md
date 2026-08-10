## Afirmação normativa

A imagem não deve expor a porta 22 nem incluir servidor SSH.

## Por que importa

Container não é máquina virtual. Rodar SSH dentro dele quebra duas premissas do
modelo:

- **imutabilidade**: SSH existe para alguém entrar e mudar coisas. Alteração
  feita por essa via desaparece no próximo deploy e não está em lugar nenhum do
  repositório — o container em produção deixa de corresponder ao que foi
  auditado
- **auditoria**: acesso por SSH é um canal de administração paralelo, fora do
  registro do orquestrador. `kubectl exec` e `docker exec` passam pelo controle
  de acesso e ficam no log de auditoria da API; SSH não

Há ainda o custo de segurança direto: um daemon SSH é mais um serviço em
execução, com sua própria superfície de vulnerabilidade, e exige gestão de
chaves ou senhas dentro da imagem — que é justamente o tipo de segredo que não
deveria estar lá.

Também obriga a rodar um supervisor de processos para manter dois serviços
vivos, o que complica o encerramento gracioso e o repasse de sinais.

## Como corrigir

Remova o `EXPOSE 22`, o pacote do servidor SSH e as chaves. Para acesso
interativo, use o mecanismo do orquestrador:

```bash
docker exec -it <container> sh
kubectl exec -it <pod> -- sh
```

Para diagnóstico em cluster sem shell na imagem (o que é desejável), use
containers efêmeros: `kubectl debug`.

## Quando não se aplica

Imagem cujo propósito **é** ser um servidor SSH — um bastion host, por exemplo.
Nesse caso a porta é a função, não um efeito colateral.
