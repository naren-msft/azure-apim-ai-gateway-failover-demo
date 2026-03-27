# ============================================================
# deploy.ps1 — Deploy Azure infrastructure for the APIM AI Gateway demo
# Usage:  .\scripts\deploy.ps1 -ResourceGroup <rg-name> -Location eastus2
# ============================================================

param(
    [Parameter(Mandatory = $true)]
    [string]$ResourceGroup,

    [string]$Location = "eastus2",

    [string]$NameSuffix = "aigwdemo",

    [string]$PublisherEmail = "admin@contoso.com"
)

$ErrorActionPreference = "Stop"

Write-Host "`n===== Azure APIM AI Gateway Demo — Deployment =====" -ForegroundColor Cyan

# ---- 1. Ensure resource group exists ----
Write-Host "`n[1/4] Creating resource group '$ResourceGroup' in '$Location' ..." -ForegroundColor Yellow
az group create --name $ResourceGroup --location $Location --output none

# ---- 2. Deploy Bicep ----
Write-Host "`n[2/4] Deploying Bicep templates (this may take 15-30 min for APIM) ..." -ForegroundColor Yellow
$deployment = az deployment group create `
    --resource-group $ResourceGroup `
    --template-file infra/main.bicep `
    --parameters infra/main.bicepparam `
    --parameters nameSuffix=$NameSuffix publisherEmail=$PublisherEmail `
    --output json | ConvertFrom-Json

$apimName = $deployment.properties.outputs.apimName.value
$apimGatewayUrl = $deployment.properties.outputs.apimGatewayUrl.value
$projectName = $deployment.properties.outputs.aiProjectName.value

Write-Host "  APIM Name:       $apimName"
Write-Host "  APIM Gateway:    $apimGatewayUrl"
Write-Host "  AI Project:      $projectName"

# ---- 3. Retrieve APIM subscription key ----
Write-Host "`n[3/4] Retrieving APIM subscription key ..." -ForegroundColor Yellow
$subKeys = az apim subscription list-secrets `
    --resource-group $ResourceGroup `
    --service-name $apimName `
    --subscription-id "ai-gateway-sub" `
    --output json | ConvertFrom-Json

$subscriptionKey = $subKeys.primaryKey
Write-Host "  Subscription key retrieved."

# ---- 4. Retrieve AI Foundry project connection string ----
Write-Host "`n[4/4] Retrieving project connection string ..." -ForegroundColor Yellow
$subscriptionId = (az account show --query id -o tsv)
$connectionString = az ml workspace show `
    --name $projectName `
    --resource-group $ResourceGroup `
    --query "{endpoint: discovery_url, sub: '$subscriptionId', rg: '$ResourceGroup', name: '$projectName'}" `
    --output json | ConvertFrom-Json

$projConnStr = "$($connectionString.endpoint);$subscriptionId;$ResourceGroup;$projectName"

# ---- Write .env ----
$envContent = @"
AGENT_ENDPOINT=$projConnStr
AGENT_ID=
APIM_GATEWAY_URL=$apimGatewayUrl/openai
APIM_SUBSCRIPTION_KEY=$subscriptionKey
"@

$envContent | Out-File -FilePath ".env" -Encoding utf8
Write-Host "`n✅ Deployment complete! .env file created." -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "  1. Activate the venv:  .\.venv\Scripts\Activate.ps1"
Write-Host "  2. Create the agent:   python scripts/setup_agent.py"
Write-Host "  3. Run the app:        uvicorn app.main:app --reload"
Write-Host ""
