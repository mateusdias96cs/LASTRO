## Afirmação normativa

Imagens devem ser fixadas por digest (`imagem:tag@sha256:...`). Só o digest
identifica o conteúdo de forma imutável.

## Por que importa

Mesmo uma tag de versão aparentemente estável pode ser reapontada no registry.
Nada impede tecnicamente que `1.27.3` seja republicada com outro conteúdo, e
isso já aconteceu — por engano em pipelines de release e por comprometimento de
conta de publicador.

O digest é o hash SHA-256 do manifesto da imagem. Ele não é atribuído: é
derivado do conteúdo. Se o conteúdo muda, o digest muda, e o pull falha em vez
de trazer algo diferente. É o que transforma "confio em quem publicou" em
"verifico o que recebi".

É também o que torna a auditoria verificável de ponta a ponta: o digest no
manifesto é o mesmo que aparece no registry e o mesmo que o runtime reporta
para o container em execução.

## Como corrigir

```yaml
image: nginx:1.27.3@sha256:0c86dddac19f2ce4fd716ac58c0fd87bf03d0..."
```

Obtenha o digest com `docker buildx imagetools inspect <imagem>:<tag>` ou pelo
próprio registry. Mantenha a tag junto do digest: ela não tem efeito na
resolução, mas diz a quem lê qual versão está fixada.

No Azure Container Registry, habilite o bloqueio de sobrescrita de tag para
impedir republicação acidental na origem.

## Quando não se aplica

Quando a atualização automática de patch é um requisito explícito e o risco foi
aceito. Nesse caso, compense com verificação de assinatura da imagem e scan
obrigatório antes do deploy.
