// ============================================================
// Main Bicep — Orchestrates all modules for APIM AI Gateway demo
// Deploy: az deployment group create -g <rg> -f infra/main.bicep -p infra/main.bicepparam
// ============================================================

@description('Primary Azure region for APIM and AI Hub')
param primaryLocation string = 'eastus2'

@description('Secondary Azure region')
param secondaryLocation string = 'westus2'

@description('Unique suffix appended to all resource names')
param nameSuffix string

@description('APIM publisher email')
param publisherEmail string

@description('APIM publisher name')
param publisherName string = 'AI Gateway Demo'

// ============================================================
// 1. Storage Account (for AI Hub)
// ============================================================
module storage 'modules/storage.bicep' = {
  name: 'storage-deploy'
  params: {
    location: primaryLocation
    nameSuffix: nameSuffix
  }
}

// ============================================================
// 2. Azure OpenAI — East US 2
// ============================================================
module openaiEast 'modules/openai.bicep' = {
  name: 'openai-eastus2-deploy'
  params: {
    location: 'eastus2'
    nameSuffix: '${nameSuffix}-eastus2'
  }
}

// ============================================================
// 3. Azure OpenAI — West US 2
// ============================================================
module openaiWest 'modules/openai.bicep' = {
  name: 'openai-westus2-deploy'
  params: {
    location: 'westus2'
    nameSuffix: '${nameSuffix}-westus2'
  }
}

// ============================================================
// 4. Azure API Management (AI Gateway)
// ============================================================
module apim 'modules/apim.bicep' = {
  name: 'apim-deploy'
  params: {
    location: primaryLocation
    nameSuffix: nameSuffix
    publisherEmail: publisherEmail
    publisherName: publisherName
    openaiEndpoint1: openaiEast.outputs.endpoint
    openaiKey1: openaiEast.outputs.primaryKey
    openaiEndpoint2: openaiWest.outputs.endpoint
    openaiKey2: openaiWest.outputs.primaryKey
  }
}

// ============================================================
// 5. Azure AI Foundry Hub + Project
// ============================================================
module aiHub 'modules/ai-hub.bicep' = {
  name: 'aihub-deploy'
  params: {
    location: primaryLocation
    nameSuffix: nameSuffix
    storageAccountId: storage.outputs.storageId
    apimGatewayUrl: apim.outputs.gatewayUrl
    apimSubscriptionKey: '' // Set post-deployment via script
  }
}

// ============================================================
// Outputs
// ============================================================
output apimGatewayUrl string = apim.outputs.gatewayUrl
output apimName string = apim.outputs.apimName
output openaiEastEndpoint string = openaiEast.outputs.endpoint
output openaiWestEndpoint string = openaiWest.outputs.endpoint
output aiProjectName string = aiHub.outputs.projectName
output storageAccountName string = storage.outputs.storageName
