## Afirmação normativa

Todo container de um pod Kubernetes deve declarar
`securityContext.allowPrivilegeEscalation: false`, impedindo que o processo
obtenha privilégios além dos concedidos na criação.

## Por que importa

Este campo controla a flag `no_new_privs` do kernel. Com ela ativa, um processo
não consegue ganhar privilégios além dos que tinha ao iniciar — o bit setuid de
binários dentro da imagem passa a ser ignorado.

Sem isso, um atacante que consiga execução de comando como usuário não-root
procura por binários setuid na imagem (`/bin/su`, `/usr/bin/passwd`, `sudo`
instalado por engano) e escala para root dentro do container. A partir daí, as
demais defesas valem menos: ele pode alterar arquivos da aplicação, ler
segredos montados e tentar abusar de capabilities disponíveis.

O campo é omitido com muita frequência, e o padrão do Kubernetes quando ele
está ausente é permitir a escalada. Ausência não é neutra aqui.

O PodSecurityStandard `restricted` **rejeita** o pod que não declare este campo
como `false` — então o manifesto que hoje passa vai parar de subir quando o
admission controller for aplicado.

## Como corrigir

```yaml
containers:
  - name: app
    securityContext:
      allowPrivilegeEscalation: false
```

Note que `privileged: true` força a escalada independentemente deste campo — os
dois precisam estar corretos. É um controle por container, não do pod.

## Quando não se aplica

Container que precisa fazer drop de privilégio no entrypoint com `gosu` ou
similar. A solução preferível é iniciar já como o usuário final, eliminando a
necessidade.
