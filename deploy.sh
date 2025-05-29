#!/bin/bash

# AI Voice Assistant Deployment Script for Google Cloud
# This script deploys the Twilio + OpenAI Realtime API voice application

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
PROJECT_ID="${GOOGLE_CLOUD_PROJECT:-$(gcloud config get-value project)}"
REGION="${REGION:-us-central1}"
SERVICE_NAME="${SERVICE_NAME:-ai-voice-assistant}"
DATABASE_INSTANCE="${DATABASE_INSTANCE:-voice-assistant-db}"

echo -e "${GREEN}🚀 Deploying AI Voice Assistant to Google Cloud${NC}"
echo "=" * 60

# Check prerequisites
echo -e "${YELLOW}🔍 Checking prerequisites...${NC}"

if ! command -v gcloud &> /dev/null; then
    echo -e "${RED}❌ Google Cloud CLI is not installed${NC}"
    exit 1
fi

if [ -z "$PROJECT_ID" ]; then
    echo -e "${RED}❌ Google Cloud project not set${NC}"
    exit 1
fi

if [ ! -f ".env" ]; then
    echo -e "${RED}❌ .env file not found. Please copy env.example to .env and configure it${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Prerequisites check passed${NC}"

# Load environment variables
source .env

# Check if database setup is needed
echo -e "${YELLOW}🗄️  Checking database setup...${NC}"
if [ -z "$GOOGLE_CLOUD_SQL_CONNECTION_NAME" ]; then
    echo -e "${YELLOW}⚠️  Database not configured. Setting up Cloud SQL...${NC}"
    ./setup-database.sh
    echo -e "${GREEN}✅ Database setup complete. Please update your .env file with the database configuration${NC}"
    echo -e "${BLUE}ℹ️  Database configuration has been saved to .env.database${NC}"
    exit 0
fi

# Enable required APIs
echo -e "${YELLOW}🔌 Enabling required APIs...${NC}"
gcloud services enable run.googleapis.com cloudbuild.googleapis.com sqladmin.googleapis.com --project=$PROJECT_ID

# Choose deployment method
echo -e "${YELLOW}🎯 Choose deployment method:${NC}"
echo "1) Google Cloud Run (Recommended)"
echo "2) Google App Engine"
read -p "Enter your choice (1 or 2): " DEPLOY_METHOD

case $DEPLOY_METHOD in
    1)
        echo -e "${BLUE}📦 Deploying to Google Cloud Run...${NC}"
        
        # Build and deploy with Cloud Build
        gcloud builds submit --tag gcr.io/$PROJECT_ID/$SERVICE_NAME --project=$PROJECT_ID
        
        # Deploy to Cloud Run with database configuration
        gcloud run deploy $SERVICE_NAME \
            --image gcr.io/$PROJECT_ID/$SERVICE_NAME \
            --platform managed \
            --region $REGION \
            --port 8080 \
            --allow-unauthenticated \
            --timeout 300 \
            --set-env-vars "OPENAI_API_KEY=$OPENAI_API_KEY" \
            --set-env-vars "TWILIO_ACCOUNT_SID=$TWILIO_ACCOUNT_SID" \
            --set-env-vars "TWILIO_AUTH_TOKEN=$TWILIO_AUTH_TOKEN" \
            --set-env-vars "PHONE_NUMBER_FROM=$PHONE_NUMBER_FROM" \
            --set-env-vars "GOOGLE_CLOUD_SQL_CONNECTION_NAME=$GOOGLE_CLOUD_SQL_CONNECTION_NAME" \
            --set-env-vars "DB_USER=$DB_USER" \
            --set-env-vars "DB_PASSWORD=$DB_PASSWORD" \
            --set-env-vars "DB_NAME=$DB_NAME" \
            --set-env-vars "MAX_CONCURRENT_CALLS=${MAX_CONCURRENT_CALLS:-10}" \
            --set-env-vars "MAX_OPENAI_CONNECTIONS=${MAX_OPENAI_CONNECTIONS:-20}" \
            --set-cloudsql-instances $GOOGLE_CLOUD_SQL_CONNECTION_NAME \
            --memory 1Gi \
            --cpu 1 \
            --concurrency 10 \
            --max-instances 10 \
            --project=$PROJECT_ID
        
        # Get the service URL
        SERVICE_URL=$(gcloud run services describe $SERVICE_NAME --platform managed --region $REGION --format 'value(status.url)' --project=$PROJECT_ID)
        DOMAIN=$(echo $SERVICE_URL | sed 's|https://||')
        
        # Update the service with the DOMAIN environment variable
        gcloud run services update $SERVICE_NAME \
            --platform managed \
            --region $REGION \
            --set-env-vars "DOMAIN=$DOMAIN" \
            --project=$PROJECT_ID
        
        echo -e "${GREEN}✅ Cloud Run deployment complete!${NC}"
        ;;
        
    2)
        echo -e "${BLUE}📦 Deploying to Google App Engine...${NC}"
        
        # Update app.yaml with current environment variables
        sed -i.bak "s/your_openai_api_key_here/$OPENAI_API_KEY/g" app.yaml
        sed -i.bak "s/your_twilio_account_sid_here/$TWILIO_ACCOUNT_SID/g" app.yaml
        sed -i.bak "s/your_twilio_auth_token_here/$TWILIO_AUTH_TOKEN/g" app.yaml
        sed -i.bak "s/your_twilio_phone_number_here/$PHONE_NUMBER_FROM/g" app.yaml
        sed -i.bak "s/your-project:region:instance-name/$GOOGLE_CLOUD_SQL_CONNECTION_NAME/g" app.yaml
        sed -i.bak "s/your_database_password/$DB_PASSWORD/g" app.yaml
        
        # Deploy to App Engine
        gcloud app deploy app.yaml --project=$PROJECT_ID --quiet
        
        # Get App Engine URL
        SERVICE_URL="https://$PROJECT_ID.appspot.com"
        DOMAIN="$PROJECT_ID.appspot.com"
        
        # Restore original app.yaml
        mv app.yaml.bak app.yaml
        
        echo -e "${GREEN}✅ App Engine deployment complete!${NC}"
        ;;
        
    *)
        echo -e "${RED}❌ Invalid choice. Please run the script again.${NC}"
        exit 1
        ;;
esac

# Run database migrations
echo -e "${YELLOW}🗄️  Running database migrations...${NC}"
if [ "$DEPLOY_METHOD" = "1" ]; then
    # For Cloud Run, migrations are run automatically in the container
    echo -e "${BLUE}ℹ️  Database migrations will run automatically when the service starts${NC}"
else
    # For App Engine, we can run migrations manually if needed
    echo -e "${BLUE}ℹ️  Database migrations will run automatically when the service starts${NC}"
fi

# Update webhook URL in Twilio (if configured)
if [ ! -z "$TWILIO_ACCOUNT_SID" ] && [ ! -z "$TWILIO_AUTH_TOKEN" ]; then
    echo -e "${YELLOW}📞 Twilio webhook configuration${NC}"
    echo -e "${BLUE}ℹ️  Please update your Twilio phone number webhook URL to:${NC}"
    echo "   $SERVICE_URL/incoming-call"
    echo
    echo -e "${BLUE}ℹ️  You can do this in the Twilio Console or using the Twilio CLI:${NC}"
    echo "   twilio phone-numbers:update $PHONE_NUMBER_FROM --voice-url=$SERVICE_URL/incoming-call"
fi

# Display deployment information
echo
echo -e "${GREEN}🎉 Deployment Summary${NC}"
echo "=" * 40
echo -e "${GREEN}Service URL:${NC} $SERVICE_URL"
echo -e "${GREEN}Domain:${NC} $DOMAIN"
echo -e "${GREEN}Health Check:${NC} $SERVICE_URL/health"
echo -e "${GREEN}API Documentation:${NC} $SERVICE_URL/docs"
echo -e "${GREEN}Call History:${NC} $SERVICE_URL/api/call-history"
echo -e "${GREEN}Analytics:${NC} $SERVICE_URL/api/analytics"
echo
echo -e "${GREEN}Database:${NC} $GOOGLE_CLOUD_SQL_CONNECTION_NAME"
echo
echo -e "${YELLOW}🔗 Important URLs:${NC}"
echo "   • Request Call: POST $SERVICE_URL/api/request-call"
echo "   • Incoming Call Webhook: $SERVICE_URL/incoming-call"
echo "   • WebSocket Stream: wss://$DOMAIN/media-stream"
echo
echo -e "${YELLOW}🔒 Security Reminders:${NC}"
echo "   • Update VERIFIED_PHONE_NUMBERS in your environment"
echo "   • Configure CORS origins for production"
echo "   • Review phone number authorization settings"
echo "   • Monitor call logs and analytics regularly"
echo
echo -e "${GREEN}✅ Deployment completed successfully!${NC}" 