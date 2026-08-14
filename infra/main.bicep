// Infraestrutura do sistema de conformidade — escopo de assinatura.
//
// Cria o resource group e delega o resto para `resources.bicep`. É a convenção
// do Azure Developer CLI (azd): `azd up` executa este arquivo.
//
// Decisão de hospedagem: Container Apps, não AKS. O produto analisa YAML de
// Kubernetes **estaticamente** — não precisa executar em Kubernetes. Container
// Apps escala a zero e custa perto de nada em uso de estudo, enquanto dois nós
// de AKS consumiriam crédito continuamente mesmo parados.

targetScope = 'subscription'

@minLength(1)
@maxLength(20)
@description('Nome do ambiente. Compõe o nome dos recursos e o resource group.')
param environmentName string

@minLength(1)
@description('Região dos recursos. Use a mesma do seu Azure OpenAI para reduzir latência.')
param location string

@description('Endpoint do Azure OpenAI já existente (Foundry). Ex.: https://meu-recurso.openai.azure.com/')
param azureOpenAiEndpoint string = ''

@description('Nome do deployment do modelo no Foundry. Ex.: gpt-4o-mini')
param azureOpenAiDeployment string = ''

@description('Resource id do Azure OpenAI. Vazio pula a atribuição de papel — e a aplicação sobe sem conseguir chamar o modelo.')
param azureOpenAiResourceId string = ''

@description('Nome completo da imagem da API, incluindo registry e tag.')
param apiImageName string = ''

@description('Nome completo da imagem do frontend, incluindo registry e tag.')
param webImageName string = ''

// Sufixo determinístico: dois deploys do mesmo ambiente reusam os mesmos nomes,
// e nomes globalmente únicos (ACR, Key Vault) não colidem entre assinaturas.
var sufixo = uniqueString(subscription().id, environmentName)
var tags = {
  'azd-env-name': environmentName
  aplicacao: 'conformidade'
  ambiente: environmentName
}

resource rg 'Microsoft.Resources/resourceGroups@2021-04-01' = {
  name: 'rg-conformidade-${environmentName}'
  location: location
  tags: tags
}

module recursos 'resources.bicep' = {
  name: 'recursos'
  scope: rg
  params: {
    location: location
    environmentName: environmentName
    sufixo: sufixo
    tags: tags
    azureOpenAiEndpoint: azureOpenAiEndpoint
    azureOpenAiDeployment: azureOpenAiDeployment
    apiImageName: apiImageName
    webImageName: webImageName
  }
}

// O Azure OpenAI já existe (criado no Foundry) e costuma viver em outro
// resource group, então a atribuição de papel precisa ser feita no escopo dele.
module papelOpenAi 'openai-role.bicep' = if (!empty(azureOpenAiResourceId)) {
  name: 'papel-openai'
  scope: resourceGroup(split(azureOpenAiResourceId, '/')[4])
  params: {
    contaOpenAi: last(split(azureOpenAiResourceId, '/'))
    principalId: recursos.outputs.identidadePrincipalId
  }
}

output AZURE_LOCATION string = location
output AZURE_RESOURCE_GROUP string = rg.name
output AZURE_CONTAINER_REGISTRY_ENDPOINT string = recursos.outputs.registryLoginServer
output AZURE_CONTAINER_REGISTRY_NAME string = recursos.outputs.registryName
output AZURE_KEY_VAULT_NAME string = recursos.outputs.keyVaultName
output SERVICE_API_URI string = recursos.outputs.apiUri
output AZURE_CLIENT_ID string = recursos.outputs.identidadeClientId

// Torna visível, no fim do deploy, se a aplicação vai conseguir chamar o
// modelo. A atribuição de papel é condicional a `azureOpenAiResourceId`, e a
// condição some sem erro quando o parâmetro vem vazio — o deploy termina com
// sucesso e a camada 3 falha em runtime, longe da causa.
output PAPEL_OPENAI_ATRIBUIDO bool = !empty(azureOpenAiResourceId)

output SERVICE_WEB_URI string = recursos.outputs.webUri
