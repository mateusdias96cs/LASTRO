// Recursos da aplicação, no escopo do resource group.
//
// Princípio que orienta o arquivo: **nenhuma chave estática em lugar nenhum.**
// A aplicação acessa o ACR, o Key Vault e o Azure OpenAI por identidade
// gerenciada. O ACR fica com `adminUserEnabled: false` e o Key Vault em modo
// RBAC — as duas configurações que evitam o par usuário/senha de circular.
//
// É o mesmo argumento do controle CONF-SEC-001 que o próprio sistema audita:
// segredo que não existe não vaza.

param location string
param environmentName string
param sufixo string
param tags object
param azureOpenAiEndpoint string
param azureOpenAiDeployment string
param imageTag string

var prefixo = 'conf${sufixo}'

// ─────────────────────────────────────────────── identidade

resource identidade 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: 'id-${prefixo}'
  location: location
  tags: tags
}

// ─────────────────────────────────────────────── observabilidade

resource logs 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: 'log-${prefixo}'
  location: location
  tags: tags
  properties: {
    sku: { name: 'PerGB2018' }
    // Retenção mínima: em assinatura de estudante, log é o que consome crédito
    // sem ninguém perceber.
    retentionInDays: 30
  }
}

resource insights 'Microsoft.Insights/components@2020-02-02' = {
  name: 'appi-${prefixo}'
  location: location
  tags: tags
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logs.id
  }
}

// ─────────────────────────────────────────────── registry

resource registry 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: 'acr${prefixo}'
  location: location
  tags: tags
  sku: { name: 'Basic' }
  properties: {
    // Sem usuário admin: o acesso é por identidade gerenciada, e usuário admin
    // é justamente o par de credenciais estáticas que se quer evitar.
    adminUserEnabled: false
  }
}

// ID do papel embutido `AcrPull`.
var papelAcrPull = '7f951dda-4ed3-4680-a7ca-43fe172d538d'

resource acrPull 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(registry.id, identidade.id, papelAcrPull)
  scope: registry
  properties: {
    principalId: identidade.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', papelAcrPull)
  }
}

// ─────────────────────────────────────────────── key vault

resource cofre 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: 'kv-${prefixo}'
  location: location
  tags: tags
  properties: {
    sku: { family: 'A', name: 'standard' }
    tenantId: subscription().tenantId
    // RBAC em vez de access policies: o modelo antigo é difícil de auditar e
    // não integra com o resto do controle de acesso da assinatura.
    enableRbacAuthorization: true
    enableSoftDelete: true
    softDeleteRetentionInDays: 7
    publicNetworkAccess: 'Enabled'
  }
}

// ID do papel embutido `Key Vault Secrets User`.
var papelSegredosUser = '4633458b-17de-408a-b874-0445c86b69e6'

resource cofreLeitura 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(cofre.id, identidade.id, papelSegredosUser)
  scope: cofre
  properties: {
    principalId: identidade.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      papelSegredosUser
    )
  }
}

// ─────────────────────────────────────────────── container apps

resource ambiente 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: 'cae-${prefixo}'
  location: location
  tags: tags
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logs.properties.customerId
        sharedKey: logs.listKeys().primarySharedKey
      }
    }
  }
}

var imagem = '${registry.properties.loginServer}/conformidade/api:${imageTag}'

var variaveisComuns = [
  { name: 'CONFORMIDADE_ENVIRONMENT', value: environmentName == 'prod' ? 'prod' : 'dev' }
  { name: 'CONFORMIDADE_LOG_LEVEL', value: 'INFO' }
  { name: 'CONFORMIDADE_AZURE_CLIENT_ID', value: identidade.properties.clientId }
  { name: 'CONFORMIDADE_KEY_VAULT_URI', value: cofre.properties.vaultUri }
  { name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', value: insights.properties.ConnectionString }
  { name: 'AZURE_OPENAI_ENDPOINT', value: azureOpenAiEndpoint }
  { name: 'AZURE_OPENAI_DEPLOYMENT', value: azureOpenAiDeployment }
]

resource api 'Microsoft.App/containerApps@2024-03-01' = {
  name: 'ca-api-${prefixo}'
  location: location
  // azd usa esta tag para saber qual serviço do azure.yaml implantar aqui.
  tags: union(tags, { 'azd-service-name': 'api' })
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: { '${identidade.id}': {} }
  }
  properties: {
    managedEnvironmentId: ambiente.id
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        targetPort: 8000
        transport: 'auto'
        allowInsecure: false
      }
      registries: [
        {
          server: registry.properties.loginServer
          identity: identidade.id
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'api'
          image: imagem
          env: variaveisComuns
          resources: { cpu: json('0.5'), memory: '1Gi' }
          probes: [
            {
              type: 'Liveness'
              httpGet: { path: '/health/live', port: 8000 }
              periodSeconds: 30
            }
            {
              type: 'Readiness'
              httpGet: { path: '/health/ready', port: 8000 }
              periodSeconds: 10
            }
            {
              type: 'Startup'
              httpGet: { path: '/health/startup', port: 8000 }
              failureThreshold: 10
              periodSeconds: 5
            }
          ]
        }
      ]
      scale: {
        // Escala a zero: sem tráfego, não consome crédito. O custo é a
        // partida a frio na primeira requisição depois de ocioso — aceitável
        // aqui, e é o que faz o crédito de estudante durar.
        minReplicas: 0
        maxReplicas: 3
        rules: [
          {
            name: 'http'
            http: { metadata: { concurrentRequests: '20' } }
          }
        ]
      }
    }
  }
  dependsOn: [acrPull]
}

// Jobs em lote: rodam sob demanda, não como serviço. A imagem é a mesma —
// muda só o `command`, que o entrypoint usa para escolher o role.
resource jobIngestao 'Microsoft.App/jobs@2024-03-01' = {
  name: 'cj-ingest-${prefixo}'
  location: location
  tags: tags
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: { '${identidade.id}': {} }
  }
  properties: {
    environmentId: ambiente.id
    configuration: {
      triggerType: 'Manual'
      replicaTimeout: 3600
      replicaRetryLimit: 1
      manualTriggerConfig: { parallelism: 1, replicaCompletionCount: 1 }
      registries: [
        {
          server: registry.properties.loginServer
          identity: identidade.id
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'ingest'
          image: imagem
          command: ['/usr/local/bin/entrypoint.sh']
          args: ['ingest', '--baixar']
          env: variaveisComuns
          resources: { cpu: json('1.0'), memory: '2Gi' }
        }
      ]
    }
  }
  dependsOn: [acrPull]
}

output identidadePrincipalId string = identidade.properties.principalId
output identidadeClientId string = identidade.properties.clientId
output registryLoginServer string = registry.properties.loginServer
output registryName string = registry.name
output keyVaultName string = cofre.name
output apiUri string = 'https://${api.properties.configuration.ingress.fqdn}'
