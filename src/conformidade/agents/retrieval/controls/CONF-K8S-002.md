## Afirmação normativa

Todo pod ou container deve definir um perfil seccomp válido —
`seccompProfile.type: RuntimeDefault` na maioria dos casos, ou `Localhost` com
perfil próprio quando houver necessidade específica.

## Por que importa

Seccomp filtra quais chamadas de sistema o processo pode fazer ao kernel. O
kernel do Linux expõe mais de 300 syscalls, e uma aplicação típica usa algumas
dezenas. As demais são superfície de ataque pura: é por syscall pouco usada que
a maioria dos exploits de escalonamento de privilégio no kernel entra.

`RuntimeDefault` aplica o perfil do runtime, que bloqueia as syscalls
reconhecidamente perigosas e desnecessárias (`kexec_load`, `init_module`,
`ptrace` em certos contextos, entre outras) sem afetar aplicação comum. O custo
prático é próximo de zero e o ganho é fechar a porta de uma classe inteira de
exploits.

Importante: **o Kubernetes não aplica seccomp por padrão** quando o campo está
ausente. Diferente do Docker, que aplica o perfil padrão automaticamente, um pod
sem `seccompProfile` roda sem filtro nenhum. É uma diferença que surpreende quem
vem do Docker.

## Como corrigir

Defina no nível do pod para valer para todos os containers:

```yaml
spec:
  securityContext:
    seccompProfile:
      type: RuntimeDefault
```

Se a aplicação quebrar, o log do runtime indica qual syscall foi bloqueada — aí
sim justifica-se um perfil `Localhost` sob medida, que deve ser mínimo e
revisado.

## Quando não se aplica

**Não confunda com AppArmor.** Seccomp filtra chamadas de sistema; AppArmor
controla acesso a arquivos, rede e capabilities. São camadas complementares, não
alternativas — configurar uma não dispensa a outra.
