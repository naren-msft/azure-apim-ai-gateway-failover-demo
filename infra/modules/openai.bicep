// ============================================================
// Azure OpenAI — Cognitive Services account + GPT-4o deployment
// Parameterised by region so it can be called twice (East US 2 & West US 2)
// ============================================================

@description('Azure region for this OpenAI resource')
param location string

@description('Unique suffix to avoid naming collisions')
param nameSuffix string

@description('SKU for the Cognitive Services account')
param skuName string = 'S0'

@description('GPT-4o model deployment name')
param deploymentName string = 'gpt-4o'

@description('GPT-4o model version')
param modelVersion string = '2024-11-20'

@description('Tokens-per-minute capacity (in thousands)')
param capacityK int = 30

var accountName = 'oai-${nameSuffix}'

resource openai 'Microsoft.CognitiveServices/accounts@2024-10-01' = {
  name: accountName
  location: location
  kind: 'OpenAI'
  sku: {
    name: skuName
  }
  properties: {
    customSubDomainName: accountName
    publicNetworkAccess: 'Enabled'
  }
}

resource deployment 'Microsoft.CognitiveServices/accounts/deployments@2024-10-01' = {
  parent: openai
  name: deploymentName
  sku: {
    name: 'Standard'
    capacity: capacityK
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: 'gpt-4o'
      version: modelVersion
    }
  }
}

@description('Endpoint URL for this OpenAI resource')
output endpoint string = openai.properties.endpoint

@description('Resource ID')
output resourceId string = openai.id

@description('Account name')
output accountName string = openai.name

@description('Primary key')
output primaryKey string = openai.listKeys().key1
