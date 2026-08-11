// Concede à identidade gerenciada acesso ao Azure OpenAI existente.
//
// Roda no escopo do resource group do recurso de OpenAI, que normalmente é
// diferente do resource group da aplicação — foi criado antes, pelo Foundry.
//
// O papel `Cognitive Services OpenAI User` permite invocar os modelos e nada
// mais: não permite criar, apagar nem reconfigurar deployments. É o mínimo de
// que a aplicação precisa.

param contaOpenAi string
param principalId string

// ID do papel embutido `Cognitive Services OpenAI User`.
var papelUsuarioOpenAi = '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd'

resource openai 'Microsoft.CognitiveServices/accounts@2024-10-01' existing = {
  name: contaOpenAi
}

resource atribuicao 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(openai.id, principalId, papelUsuarioOpenAi)
  scope: openai
  properties: {
    principalId: principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      papelUsuarioOpenAi
    )
  }
}
