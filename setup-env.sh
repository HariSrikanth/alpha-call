#!/bin/bash

# Environment Setup Script for Twilio + OpenAI Voice Application
# This script helps configure environment variables in Google Cloud

echo "🔧 Environment Variable Setup for Google Cloud"
echo "=============================================="

# Check if .env file exists
if [ ! -f ".env" ]; then
    echo "❌ Error: .env file not found. Please create one first:"
    echo "   cp env.example .env"
    echo "   # Then edit .env with your values"
    exit 1
fi

# Source the .env file
set -a
source .env
set +a

# Validate required variables
required_vars=("OPENAI_API_KEY" "TWILIO_ACCOUNT_SID" "TWILIO_AUTH_TOKEN" "PHONE_NUMBER_FROM" "DOMAIN")
missing_vars=()

for var in "${required_vars[@]}"; do
    if [ -z "${!var}" ]; then
        missing_vars+=("$var")
    fi
done

if [ ${#missing_vars[@]} -ne 0 ]; then
    echo "❌ Error: Missing required environment variables:"
    printf '   %s\n' "${missing_vars[@]}"
    echo "   Please update your .env file"
    exit 1
fi

echo "✅ All required environment variables found"

# Function to setup Cloud Run environment
setup_cloud_run() {
    echo ""
    echo "🚢 Setting up Cloud Run environment variables..."
    
    # Check if service exists
    if ! gcloud run services describe twilio-openai-voice --region us-central1 &> /dev/null; then
        echo "❌ Error: Cloud Run service 'twilio-openai-voice' not found"
        echo "   Please deploy the service first using ./deploy.sh"
        exit 1
    fi
    
    echo "🔄 Updating environment variables..."
    gcloud run services update twilio-openai-voice \
        --region us-central1 \
        --set-env-vars="OPENAI_API_KEY=${OPENAI_API_KEY},TWILIO_ACCOUNT_SID=${TWILIO_ACCOUNT_SID},TWILIO_AUTH_TOKEN=${TWILIO_AUTH_TOKEN},PHONE_NUMBER_FROM=${PHONE_NUMBER_FROM},DOMAIN=${DOMAIN},PORT=${PORT}"
    
    if [ $? -eq 0 ]; then
        echo "✅ Cloud Run environment variables updated successfully!"
        
        # Get service URL
        SERVICE_URL=$(gcloud run services describe twilio-openai-voice --region us-central1 --format 'value(status.url)')
        DOMAIN_ONLY=${SERVICE_URL#https://}
        
        echo ""
        echo "📝 Important reminders:"
        echo "   1. Your service URL: $SERVICE_URL"
        echo "   2. Update DOMAIN in .env to: $DOMAIN_ONLY"
        echo "   3. Configure Twilio webhook: $SERVICE_URL/incoming-call"
        
        # Check if DOMAIN needs updating
        if [ "$DOMAIN" != "$DOMAIN_ONLY" ]; then
            echo ""
            echo "⚠️  DOMAIN mismatch detected!"
            echo "   Current DOMAIN in .env: $DOMAIN"
            echo "   Actual service domain: $DOMAIN_ONLY"
            echo ""
            read -p "Update DOMAIN automatically? (y/n): " update_domain
            if [ "$update_domain" = "y" ] || [ "$update_domain" = "Y" ]; then
                # Update .env file
                if command -v sed &> /dev/null; then
                    sed -i.bak "s|DOMAIN=.*|DOMAIN=$DOMAIN_ONLY|" .env
                    echo "✅ Updated DOMAIN in .env file"
                    echo "🔄 Re-updating Cloud Run with correct domain..."
                    gcloud run services update twilio-openai-voice \
                        --region us-central1 \
                        --set-env-vars="DOMAIN=${DOMAIN_ONLY}"
                else
                    echo "📝 Please manually update DOMAIN in .env to: $DOMAIN_ONLY"
                fi
            fi
        fi
    else
        echo "❌ Failed to update Cloud Run environment variables"
        exit 1
    fi
}

# Function to setup App Engine environment
setup_app_engine() {
    echo ""
    echo "🚢 Setting up App Engine environment variables..."
    
    # Check if App Engine app exists
    if ! gcloud app describe &> /dev/null; then
        echo "❌ Error: App Engine application not found"
        echo "   Please deploy the app first using ./deploy.sh"
        exit 1
    fi
    
    echo "📝 Updating app.yaml with environment variables..."
    
    # Create a backup of app.yaml
    cp app.yaml app.yaml.bak
    
    # Update app.yaml with actual values
    cat > app.yaml << EOF
runtime: python39

env_variables:
  OPENAI_API_KEY: "${OPENAI_API_KEY}"
  TWILIO_ACCOUNT_SID: "${TWILIO_ACCOUNT_SID}"
  TWILIO_AUTH_TOKEN: "${TWILIO_AUTH_TOKEN}"
  PHONE_NUMBER_FROM: "${PHONE_NUMBER_FROM}"
  DOMAIN: "${DOMAIN}"
  PORT: "${PORT}"

automatic_scaling:
  min_instances: 1
  max_instances: 10

resources:
  cpu: 1
  memory_gb: 0.5
  disk_size_gb: 10
EOF
    
    echo "✅ Updated app.yaml with environment variables"
    echo "🚀 Redeploying to App Engine..."
    
    gcloud app deploy app.yaml --quiet
    
    if [ $? -eq 0 ]; then
        echo "✅ App Engine redeployed successfully!"
        
        # Get service URL
        SERVICE_URL=$(gcloud app describe --format="value(defaultHostname)")
        
        echo ""
        echo "📝 Important reminders:"
        echo "   1. Your service URL: https://$SERVICE_URL"
        echo "   2. Configure Twilio webhook: https://$SERVICE_URL/incoming-call"
        echo "   3. Backup created: app.yaml.bak"
    else
        echo "❌ Failed to redeploy App Engine"
        echo "🔄 Restoring app.yaml backup..."
        mv app.yaml.bak app.yaml
        exit 1
    fi
}

# Main menu
echo ""
echo "Choose your deployment target:"
echo "1) Cloud Run"
echo "2) App Engine"
echo "3) Exit"

read -p "Enter your choice (1-3): " choice

case $choice in
    1)
        setup_cloud_run
        ;;
    2)
        setup_app_engine
        ;;
    3)
        echo "👋 Goodbye!"
        exit 0
        ;;
    *)
        echo "❌ Invalid choice. Please run the script again."
        exit 1
        ;;
esac

echo ""
echo "🎉 Setup complete! Your application should now be configured with the correct environment variables." 