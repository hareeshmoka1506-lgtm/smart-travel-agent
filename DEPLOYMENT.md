# Azure Free Tier Deployment Guide

## Local Run

```bash
pip install -r requirements.txt
python app.py
```
Open your browser at `http://localhost:8000`.

---

## Deploy to Azure App Service (Free F1 Tier - $0 Cost)

### Prerequisites
- Azure CLI installed (`az`)
- An active Azure subscription (Free tier supported)

### Step 1: Login to Azure
```bash
az login
```

### Step 2: Set Resource Group and Free Service Plan
Using your existing resource group (e.g., `agent-demo-rg`):

```bash
# Create a Free F1 Linux App Service Plan (Free Tier: 0 USD)
az appservice plan create \
  --name travel-agent-plan \
  --resource-group agent-demo-rg \
  --sku F1 \
  --is-linux

# Create the Web App with Python 3.11/3.12
az webapp create \
  --name travel-agent-mcp-demo \
  --resource-group agent-demo-rg \
  --plan travel-agent-plan \
  --runtime "PYTHON:3.11"
```

### Step 3: Configure Startup Command and Environment Variables
```bash
# FastAPI is ASGI. Azure's default Gunicorn worker is WSGI and returns Internal Server Error.
az webapp config set \
  --resource-group agent-demo-rg \
  --name travel-agent-mcp-demo \
  --startup-file "gunicorn --worker-class uvicorn.workers.UvicornWorker --bind=0.0.0.0:8000 --workers 1 --timeout 600 app:app"

# Set App Settings (.env variables)
az webapp config appsettings set \
  --resource-group agent-demo-rg \
  --name travel-agent-mcp-demo \
  --settings \
    AZURE_OPENAI_KEY="<YOUR_AZURE_OPENAI_KEY>" \
    AZURE_OPENAI_ENDPOINT="<YOUR_AZURE_OPENAI_ENDPOINT>" \
    AZURE_OPENAI_DEPLOYMENT="gpt-4o" \
    AZURE_OPENAI_API_VERSION="2024-02-15-preview" \
    SCM_DO_BUILD_DURING_DEPLOYMENT="true"
```

### Step 4: Deploy Code via ZIP or Git
```bash
# Deploy using Azure Webapp UP (Single step)
az webapp up \
  --resource-group agent-demo-rg \
  --name travel-agent-mcp-demo \
  --sku F1 \
  --runtime "PYTHON:3.11"
```

### Step 5: Verify App
Open `https://travel-agent-mcp-demo.azurewebsites.net` in your browser.
