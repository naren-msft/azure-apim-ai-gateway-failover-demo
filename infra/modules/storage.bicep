// ============================================================
// Storage Account — required by AI Foundry Hub
// ============================================================

@description('Azure region')
param location string

@description('Unique suffix')
param nameSuffix string

var storageNameClean = replace('st${nameSuffix}', '-', '')
var storageName = length(storageNameClean) > 24 ? substring(storageNameClean, 0, 24) : storageNameClean

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: storageName
  location: location
  sku: {
    name: 'Standard_LRS'
  }
  kind: 'StorageV2'
  properties: {
    accessTier: 'Hot'
    minimumTlsVersion: 'TLS1_2'
    supportsHttpsTrafficOnly: true
  }
}

output storageId string = storage.id
output storageName string = storage.name
