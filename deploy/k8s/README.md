# deploy/k8s/

Manifestos Kubernetes (AKS) — ainda vazio (próximas etapas).

Layout previsto, com Kustomize para separar ambientes sem duplicar YAML:

```
deploy/k8s/
├── base/
│   ├── deployment.yaml     # probes apontando para /health/{live,ready,startup}
│   ├── service.yaml
│   ├── serviceaccount.yaml # anotada com a workload identity do AKS
│   ├── configmap.yaml
│   └── kustomization.yaml
└── overlays/
    ├── dev/
    ├── staging/
    └── prod/
```

A imagem já está preparada para o Pod Security Standard `restricted`:
roda como UID numérico 10001, sem root, e o filesystem pode ser montado
read-only (ver `compose.yaml`, que já roda assim localmente).
