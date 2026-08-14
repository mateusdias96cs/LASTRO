// Recursos da aplicação, no escopo do resource group.
//
// Princípio que orienta o arquivo: **nenhuma chave estática em lugar nenhum.**
// A aplicação acessa o ACR, o Key Vault e o Azure OpenAI por identidade
// gerenciada. O ACR fica com `adminUserEnabled: false` e o Key Vault em modo
// RBAC — as duas configurações que evitam o par usuário/senha de circular.
//
// É o mesmo argumento do controle CONF-SEC-001 que o próprio sistema audita:
// segredo que não existe não vaza.
//
// ── Domínio próprio num ambiente novo ────────────────────────────────────────
//
// Este template assume que `lastro.engineer` já está ligado ao app `web`. Num
// ambiente do zero ele falha na criação do certificado, com:
//
//     Creating managed certificate requires hostname '...' added as a custom
//     hostname to a container app in environment
//
// Não é defeito do template: é a dependência circular do issue #796. O
// certificado exige o hostname registrado; o hostname, aqui, exige o
// certificado. Duas saídas, nessa ordem de preferência:
//
// 1. Provisionar uma vez com o bloco `customDomains` do `web` comentado, rodar
//    `az containerapp hostname bind --hostname lastro.engineer -n ca-web-<sufixo>
//    -g <rg> --environment cae-<sufixo> --validation-method HTTP`, ajustar o
//    nome do certificado abaixo para o que a CLI criou e reprovisionar.
//
// 2. Subir o `web` para a API 2025-07-01 e trocar o `customDomains` por
//    `{ name: dominioWeb, bindingType: 'Auto' }`, sem `certificateId`, movendo
//    o `dependsOn: [web]` para o certificado. `Auto` existe exatamente para
//    quebrar esse ciclo e resolve em uma passagem. Não é o que está aqui
//    porque, no ambiente atual, trocaria o `bindingType` de um binding vivo e
//    em produção sem necessidade: o ciclo só existe na primeira vez.

param location string
param environmentName string
param sufixo string
param tags object
param azureOpenAiEndpoint string
param azureOpenAiDeployment string
param apiImageName string
param webImageName string

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

var imagem = apiImageName

var variaveisComuns = [
  { name: 'CONFORMIDADE_ENVIRONMENT', value: environmentName == 'prod' ? 'prod' : 'dev' }
  { name: 'CONFORMIDADE_LOG_LEVEL', value: 'INFO' }
  { name: 'CONFORMIDADE_AZURE_CLIENT_ID', value: identidade.properties.clientId }
  { name: 'CONFORMIDADE_KEY_VAULT_URI', value: cofre.properties.vaultUri }
  { name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', value: insights.properties.ConnectionString }
  { name: 'AZURE_OPENAI_ENDPOINT', value: azureOpenAiEndpoint }
  { name: 'AZURE_OPENAI_DEPLOYMENT', value: azureOpenAiDeployment }
  { name: 'CONFORMIDADE_CORS_ORIGINS', value: 'https://${web.properties.configuration.ingress.fqdn},https://lastro.engineer,http://localhost:3000' }
  // O cache da camada 3 precisa de um caminho gravável pelo usuário 10001.
  //
  // `/app` pertence a root: o `WORKDIR` do Dockerfile o cria assim, e os
  // `COPY --chown` só mudam o dono dos caminhos copiados. O padrão relativo
  // do código resolvia para `/app/.cache-analise` e estourava com
  // `PermissionError` em toda auditoria — gastando a cota do modelo para
  // descartar a resposta logo em seguida.
  //
  // `/tmp` some a cada reinício, e com `minReplicas: 0` isso é frequente. É
  // aceitável: o cache é otimização, e o código já trata a ausência dele.
  { name: 'CONFORMIDADE_ANALISE_CACHE_DIR', value: '/tmp/conformidade-cache' }
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

// ─────────────────────────────────────────────── frontend

var imagemWeb = webImageName

// Domínio próprio do frontend.
//
// O DNS fica fora do Azure: registro A no apex apontando para o IP estático do
// ambiente, e TXT em `asuid` provando a posse. Aqui declaramos só o lado Azure.
var dominioWeb = 'lastro.engineer'

resource web 'Microsoft.App/containerApps@2024-03-01' = {
  name: 'ca-web-${prefixo}'
  location: location
  tags: union(tags, { 'azd-service-name': 'web' })
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
        targetPort: 3000
        transport: 'auto'
        allowInsecure: false
        // **Este bloco é o motivo de o domínio ter sumido.**
        //
        // O ARM não faz merge de `ingress`: cada PUT substitui o objeto
        // inteiro. Enquanto o domínio existia só por `az containerapp hostname
        // bind`, ele morava num campo que o template não declarava, e todo
        // `azd provision` reescrevia o ingress sem ele. O site caía com
        // ERR_CONNECTION_RESET até alguém refazer o bind à mão. Declarado
        // aqui, o provision passa a reafirmá-lo em vez de apagá-lo.
        customDomains: [
          { name: dominioWeb, bindingType: 'SniEnabled', certificateId: certificadoWeb.id }
        ]
      }
      registries: [
        { server: registry.properties.loginServer, identity: identidade.id }
      ]
    }
    template: {
      containers: [
        {
          name: 'web'
          image: imagemWeb
          resources: { cpu: json('0.25'), memory: '0.5Gi' }
        }
      ]
      scale: {
        minReplicas: 0
        maxReplicas: 3
        rules: [
          { name: 'http', http: { metadata: { concurrentRequests: '50' } } }
        ]
      }
    }
  }
  dependsOn: [acrPull]
}

// Certificado gerenciado gratuito para o domínio próprio.
//
// **`domainControlValidation: 'HTTP'` não é escolha, é a regra do apex.** A
// documentação da Microsoft tabela assim: domínio apex usa registro A e
// validação HTTP; subdomínio usa CNAME e validação CNAME. `lastro.engineer` é
// apex, então HTTP. CNAME aqui falha, e é o erro que já custou uma
// configuração antes.
//
// **O nome é literal de propósito.** É o certificado que já existe e está
// válido, criado por `az containerapp hostname bind`. Declarar com o mesmo
// nome faz o ARM adotar o recurso em vez de emitir um segundo: nenhuma
// validação HTTP nova, nenhuma janela sem certificado. O sufixo numérico veio
// da CLI e não é derivável do `sufixo` do ambiente, por isso está cravado.
//
// **A ordem: certificado antes do app.** O `certificateId` acima cria a
// dependência, então o ARM resolve este recurso primeiro. Funciona porque o
// certificado já existe. Num ambiente novo, do zero, isso trava: emitir um
// certificado gerenciado exige que o hostname já esteja registrado em algum
// app do ambiente, e o app espera o certificado. É o issue #796
// (microsoft/azure-container-apps), e a saída documentada está no cabeçalho
// deste arquivo, em "Domínio próprio num ambiente novo".
resource certificadoWeb 'Microsoft.App/managedEnvironments/managedCertificates@2025-07-01' = {
  parent: ambiente
  name: 'mc-cae-conflwqwpg-lastro-engineer-5216'
  location: location
  tags: tags
  properties: {
    subjectName: dominioWeb
    domainControlValidation: 'HTTP'
  }
}

output webUri string = 'https://${web.properties.configuration.ingress.fqdn}'
output webDominio string = 'https://${dominioWeb}'
output webCertificadoId string = certificadoWeb.id
