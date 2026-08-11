# infra/

Infraestrutura como código, em Bicep, para **Azure Container Apps**.

## Por que Container Apps e não AKS

O produto analisa YAML de Kubernetes **estaticamente** — não precisa executar
em Kubernetes para auditá-lo. Container Apps escala a zero e custa perto de
nada em uso de estudo; dois nós de AKS consumiriam crédito continuamente, mesmo
sem tráfego.

Se um dia for preciso demonstrar o produto rodando dentro de um cluster, a
mesma imagem serve: os manifestos vão para `deploy/k8s/`.

## O que é criado

| Recurso | Papel |
|---|---|
| Managed Identity (user-assigned) | Identidade única para ACR, Key Vault e Azure OpenAI |
| Container Registry (Basic) | `adminUserEnabled: false` — acesso só por identidade |
| Key Vault | Modo RBAC, não access policies |
| Log Analytics + Application Insights | Retenção de 30 dias |
| Container Apps Environment | |
| Container App `api` | Escala 0→3, probes ligadas a `/health/*` |
| Container App Job `ingest` | Sob demanda, mesma imagem, role diferente |

**Nenhuma chave estática.** O ACR sem usuário admin e o Key Vault em RBAC são
as duas configurações que impedem par usuário/senha de circular. É o mesmo
argumento do controle `CONF-SEC-001` que o sistema audita: segredo que não
existe não vaza.

## Azure OpenAI

O recurso **não é criado aqui** — ele já existe, feito no Foundry. O Bicep
apenas concede à identidade gerenciada o papel `Cognitive Services OpenAI User`
sobre ele, que permite invocar os modelos e nada mais.

Passe o ID completo do recurso em `AZURE_OPENAI_RESOURCE_ID` e a atribuição é
feita no resource group correto, que normalmente é diferente do da aplicação.

## Subir

```bash
azd auth login
azd env new conformidade-dev
azd env set AZURE_OPENAI_ENDPOINT   https://SEU-RECURSO.openai.azure.com/
azd env set AZURE_OPENAI_DEPLOYMENT gpt-4o-mini
azd env set AZURE_OPENAI_RESOURCE_ID /subscriptions/.../resourceGroups/.../providers/Microsoft.CognitiveServices/accounts/SEU-RECURSO
azd up
```

O hook `predeploy` roda o portão de qualidade antes de implantar — impede subir
com o índice defasado do corpus.

## Ainda não validado

Estes arquivos **não foram compilados**: o ambiente onde foram escritos não tem
`az`, `azd` nem `bicep`. Rode `az bicep build --file infra/main.bicep` antes do
primeiro `azd up` para pegar erro de sintaxe ou de versão de API sem gastar um
ciclo de provisionamento.
