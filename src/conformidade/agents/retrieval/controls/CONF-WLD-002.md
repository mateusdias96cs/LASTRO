## Afirmação normativa

O socket do runtime de container (`/var/run/docker.sock`, o socket do
containerd ou do CRI-O) não deve ser montado dentro de nenhum container.

## Por que importa

Quem tem acesso ao socket controla o daemon, e o daemon roda como root no host.
Com uma única chamada de API é possível criar um novo container privilegiado
montando `/` do host — o que dá leitura e escrita em qualquer arquivo da
máquina, incluindo chaves SSH, credenciais e binários do sistema.

O detalhe que costuma escapar: **não adianta montar o socket como
somente-leitura**. A operação perigosa é uma requisição HTTP pelo socket, não
uma escrita no arquivo. `:ro` não protege nada aqui.

Montar o socket equivale, para todos os efeitos, a dar root no host ao
processo dentro do container.

## Como corrigir

Remova a montagem:

```yaml
# Compose — remova a linha
services:
  app:
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock   # ← apague

# Kubernetes — remova o volume e o volumeMount
volumes:
  - name: docker-sock
    hostPath:
      path: /var/run/docker.sock                    # ← apague
```

Para os casos que costumam motivar a montagem:

- **build de imagem dentro do cluster**: use uma ferramenta que constrói sem
  daemon privilegiado, em vez de expor o socket
- **descoberta de containers para monitoramento**: prefira a API do
  orquestrador com uma service account de leitura restrita
- **testes de integração que sobem containers**: isole em ambiente descartável,
  nunca em cluster compartilhado

## Quando não se aplica

Praticamente nunca em produção. Se for inevitável, trate o container como parte
do plano de controle do host: nó dedicado, sem tráfego de usuário, e com o
mesmo rigor de acesso que o próprio host.
