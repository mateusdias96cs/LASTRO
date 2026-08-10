## Afirmação normativa

Nenhum container deve executar em modo privilegiado. `privileged: true` no
Compose e `securityContext.privileged: true` no Kubernetes desligam
praticamente todo o isolamento fornecido pelo runtime.

## Por que importa

Um container privilegiado recebe **todas** as capabilities do Linux, acesso aos
devices do host em `/dev` e perde as restrições de seccomp e AppArmor aplicadas
por padrão. Nessas condições, sair do container para o host deixa de ser um
exploit e vira uma sequência de comandos comuns: montar o disco do host,
carregar um módulo de kernel ou escrever no `cgroup` de release_agent.

Na prática, privilegiado significa que o container e o host têm a mesma
fronteira de segurança — ou seja, nenhuma.

## Como corrigir

Remova a flag. Se algo específico for necessário, conceda apenas aquilo:

- precisa de um device? use `devices:` (Compose) ou um device plugin (Kubernetes)
- precisa de uma capability? conceda só ela em `cap_add` / `capabilities.add`
- precisa montar sistema de arquivos? avalie se um volume nomeado resolve

No Kubernetes, o PodSecurityStandard `baseline` já rejeita pods privilegiados —
aplicar o admission controller impede a reintrodução.

## Quando não se aplica

Cargas de infraestrutura que genuinamente operam o nó — agentes de CNI,
drivers de storage, coletores que leem `/proc` do host. Nesses casos o
privilégio deve ser acompanhado de namespace dedicado, RBAC restrito e
justificativa registrada. Aplicação de negócio nunca se enquadra aqui.
