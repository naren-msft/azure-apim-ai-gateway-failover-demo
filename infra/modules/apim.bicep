// ============================================================
// Azure API Management — AI Gateway with load-balanced backend pool
// Handles 429 failover between two Azure OpenAI backends
// ============================================================

@description('Azure region for APIM')
param location string

@description('Unique suffix for naming')
param nameSuffix string

@description('APIM publisher email')
param publisherEmail string

@description('APIM publisher name')
param publisherName string = 'AI Gateway Demo'

@description('Endpoint URL of OpenAI backend 1 (East US 2)')
param openaiEndpoint1 string

@description('API key of OpenAI backend 1')
@secure()
param openaiKey1 string

@description('Endpoint URL of OpenAI backend 2 (West US 2)')
param openaiEndpoint2 string

@description('API key of OpenAI backend 2')
@secure()
param openaiKey2 string

@description('APIM SKU')
param skuName string = 'Developer'

var apimName = 'apim-${nameSuffix}'

// ----- APIM Instance -----
resource apim 'Microsoft.ApiManagement/service@2023-09-01-preview' = {
  name: apimName
  location: location
  sku: {
    name: skuName
    capacity: 1
  }
  properties: {
    publisherEmail: publisherEmail
    publisherName: publisherName
  }
}

// ----- Named Values (API keys stored securely) -----
resource nvKey1 'Microsoft.ApiManagement/service/namedValues@2023-09-01-preview' = {
  parent: apim
  name: 'openai-key-eastus2'
  properties: {
    displayName: 'openai-key-eastus2'
    value: openaiKey1
    secret: true
  }
}

resource nvKey2 'Microsoft.ApiManagement/service/namedValues@2023-09-01-preview' = {
  parent: apim
  name: 'openai-key-westus2'
  properties: {
    displayName: 'openai-key-westus2'
    value: openaiKey2
    secret: true
  }
}

// ----- Backends -----
resource backendEastUS2 'Microsoft.ApiManagement/service/backends@2023-09-01-preview' = {
  parent: apim
  name: 'openai-eastus2'
  properties: {
    url: '${openaiEndpoint1}openai'
    protocol: 'http'
    description: 'Azure OpenAI - East US 2'
    circuitBreaker: {
      rules: [
        {
          name: 'breakOnThrottle'
          failureCondition: {
            count: 1
            interval: 'PT10S'
            statusCodeRanges: [
              { min: 429, max: 429 }
            ]
          }
          tripDuration: 'PT10S'
          acceptRetryAfter: true
        }
      ]
    }
  }
}

resource backendWestUS2 'Microsoft.ApiManagement/service/backends@2023-09-01-preview' = {
  parent: apim
  name: 'openai-westus2'
  properties: {
    url: '${openaiEndpoint2}openai'
    protocol: 'http'
    description: 'Azure OpenAI - West US 2'
    circuitBreaker: {
      rules: [
        {
          name: 'breakOnThrottle'
          failureCondition: {
            count: 1
            interval: 'PT10S'
            statusCodeRanges: [
              { min: 429, max: 429 }
            ]
          }
          tripDuration: 'PT10S'
          acceptRetryAfter: true
        }
      ]
    }
  }
}

// ----- Load-balanced Backend Pool -----
resource backendPool 'Microsoft.ApiManagement/service/backends@2023-09-01-preview' = {
  parent: apim
  name: 'openai-pool'
  properties: {
    type: 'Pool'
    description: 'Load-balanced pool across East US 2 & West US 2 OpenAI'
    pool: {
      services: [
        { id: backendEastUS2.id, priority: 1, weight: 50 }
        { id: backendWestUS2.id, priority: 1, weight: 50 }
      ]
    }
  }
}

// ----- OpenAI API definition -----
resource api 'Microsoft.ApiManagement/service/apis@2023-09-01-preview' = {
  parent: apim
  name: 'azure-openai-api'
  properties: {
    displayName: 'Azure OpenAI API'
    path: 'openai'
    protocols: [ 'https' ]
    subscriptionRequired: true
    subscriptionKeyParameterNames: {
      header: 'api-key'
      query: 'api-key'
    }
    serviceUrl: 'https://placeholder.openai.azure.com/openai'
  }
}

// ----- Catch-all operation -----
resource apiOperation 'Microsoft.ApiManagement/service/apis/operations@2023-09-01-preview' = {
  parent: api
  name: 'openai-all'
  properties: {
    displayName: 'All OpenAI Operations'
    method: '*'
    urlTemplate: '/*'
  }
}

// ----- Inbound policy: route to pool, set api-key per backend, add region header -----
resource apiPolicy 'Microsoft.ApiManagement/service/apis/policies@2023-09-01-preview' = {
  parent: api
  name: 'policy'
  properties: {
    format: 'rawxml'
    value: '''
<policies>
  <inbound>
    <base />
    <set-backend-service backend-id="openai-pool" />
    <!-- Set the correct API key based on which backend was selected -->
    <choose>
      <when condition="@(context.Request.Url.Host.Contains("eastus2"))">
        <set-header name="api-key" exists-action="override">
          <value>{{openai-key-eastus2}}</value>
        </set-header>
      </when>
      <when condition="@(context.Request.Url.Host.Contains("westus2"))">
        <set-header name="api-key" exists-action="override">
          <value>{{openai-key-westus2}}</value>
        </set-header>
      </when>
    </choose>
  </inbound>
  <backend>
    <base />
  </backend>
  <outbound>
    <base />
    <!-- Add custom header so the client can see which backend served the request -->
    <set-header name="x-backend-region" exists-action="override">
      <value>@{
        var backendUrl = context.Request.Url.Host;
        if (backendUrl.Contains("eastus2")) return "eastus2";
        if (backendUrl.Contains("westus2")) return "westus2";
        return "unknown";
      }</value>
    </set-header>
  </outbound>
  <on-error>
    <base />
  </on-error>
</policies>
'''
  }
  dependsOn: [
    backendPool
    nvKey1
    nvKey2
  ]
}

// ----- Subscription for the API -----
resource subscription 'Microsoft.ApiManagement/service/subscriptions@2023-09-01-preview' = {
  parent: apim
  name: 'ai-gateway-sub'
  properties: {
    displayName: 'AI Gateway Demo Subscription'
    scope: api.id
    state: 'active'
  }
}

@description('APIM gateway URL')
output gatewayUrl string = apim.properties.gatewayUrl

@description('APIM resource ID')
output resourceId string = apim.id

@description('APIM name')
output apimName string = apim.name
