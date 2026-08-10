# infra/

Infraestrutura como código em **Bicep** — ainda vazio (próximas etapas).

Este caminho não é arbitrário: `infra/` na raiz, junto de um `azure.yaml`, é a
convenção do **Azure Developer CLI (`azd`)**. Mantendo o layout, a migração vira
`azd init` + `azd up`, sem reorganizar o repositório.

Layout previsto:

```
infra/
├── main.bicep              # escopo de subscription: cria o resource group
├── main.parameters.json    # parâmetros por ambiente (lidos do azd)
└── modules/
    ├── acr.bicep           # Azure Container Registry (destino do push)
    ├── identity.bicep      # user-assigned managed identity + role assignments
    ├── keyvault.bicep      # segredos
    ├── monitoring.bicep    # Log Analytics + Application Insights
    └── aks.bicep           # ou containerapps.bicep, conforme o destino
```

Decisão de destino (Container Apps vs. AKS) fica para a etapa de Kubernetes.
A imagem produzida pelo `Dockerfile` da raiz serve aos dois sem alteração.
