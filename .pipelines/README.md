# .pipelines/

Pipelines do **Azure DevOps** — ainda vazio (próximas etapas).

Layout previsto:

```
.pipelines/
├── ci.yaml                 # lint + testes + build da imagem + scan
├── cd.yaml                 # push no ACR + deploy por ambiente
└── templates/
    ├── build-image.yaml
    └── deploy-env.yaml
```

O `Dockerfile` da raiz já é o artefato de build do CI: uma tag por commit,
mesma imagem promovida entre dev → staging → prod (sem rebuild por ambiente).
