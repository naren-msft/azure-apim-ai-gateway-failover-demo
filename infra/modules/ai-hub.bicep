// ============================================================
// Azure AI Foundry — Hub + Project
// The project is configured to use APIM as its OpenAI connection
// ============================================================

@description('Azure region for the AI Hub')
param location string

@description('Unique suffix')
param nameSuffix string

@description('Storage account resource ID (required by Hub)')
param storageAccountId string

@description('APIM gateway URL (used as OpenAI endpoint connection)')
param apimGatewayUrl string

@description('APIM subscription key for the OpenAI API')
@secure()
param apimSubscriptionKey string

var hubName = 'aihub-${nameSuffix}'
var projectName = 'aiproj-${nameSuffix}'

// ----- AI Hub -----
resource hub 'Microsoft.MachineLearningServices/workspaces@2024-10-01' = {
  name: hubName
  location: location
  kind: 'Hub'
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    friendlyName: 'AI Gateway Demo Hub'
    storageAccount: storageAccountId
    publicNetworkAccess: 'Enabled'
  }
}

// ----- AI Project -----
resource project 'Microsoft.MachineLearningServices/workspaces@2024-10-01' = {
  name: projectName
  location: location
  kind: 'Project'
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    friendlyName: 'AI Gateway Demo Project'
    hubResourceId: hub.id
    publicNetworkAccess: 'Enabled'
  }
}

// ----- Connection to APIM (acts as our OpenAI endpoint) -----
resource apimConnection 'Microsoft.MachineLearningServices/workspaces/connections@2024-10-01' = {
  parent: hub
  name: 'apim-openai-connection'
  properties: {
    category: 'AzureOpenAI'
    target: '${apimGatewayUrl}/openai'
    authType: 'ApiKey'
    credentials: {
      key: apimSubscriptionKey
    }
    metadata: {
      ApiType: 'Azure'
      ResourceId: ''
    }
  }
}

@description('AI Hub resource ID')
output hubId string = hub.id

@description('AI Project resource ID')
output projectId string = project.id

@description('AI Project name')
output projectName string = project.name

@description('Connection name for APIM')
output connectionName string = apimConnection.name
