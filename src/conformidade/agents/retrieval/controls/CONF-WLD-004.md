## Afirmação normativa

Containers não devem compartilhar os namespaces de rede, de processos ou de IPC
do host. Isso significa não usar `hostNetwork`, `hostPID` e `hostIPC` no
Kubernetes, nem `network_mode: host`, `pid: host` e `ipc: host` no Compose.

## Por que importa

Cada namespace compartilhado remove uma fronteira distinta:

- **rede**: o container passa a enxergar todas as interfaces do host. Ele
  alcança serviços que só escutam em `localhost` (bancos, painéis
  administrativos, o metadata endpoint da nuvem) e pode capturar tráfego. Além
  disso, NetworkPolicy deixa de valer, porque não há IP de pod a filtrar.
- **processos**: o container vê e, com as capabilities certas, manipula
  processos do host. Isso inclui ler a linha de comando de outros processos,
  que frequentemente contém segredo.
- **IPC**: memória compartilhada e filas de mensagens do host ficam acessíveis.

O de rede é o mais comum e o mais subestimado, porque costuma ser adotado
"para simplificar" e leva junto o acesso ao endpoint de metadados da nuvem — a
porta de entrada clássica para roubo de credencial de instância.

## Como corrigir

Remova as flags e exponha o serviço pelo caminho normal: `Service` no
Kubernetes, `ports:` na rede interna do Compose. Se a aplicação precisa de uma
porta específica no nó, avalie `NodePort` ou um LoadBalancer antes de recorrer
a `hostNetwork`.

## Quando não se aplica

Componentes de infraestrutura de rede (CNI, proxy de nó, coletor que precisa da
pilha do host). Aplicação de negócio, não.
