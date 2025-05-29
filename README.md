# AI Voice Assistant - Twilio + OpenAI Realtime API

A production-ready backend service that enables AI-powered voice conversations using Twilio and OpenAI's Realtime API, designed for Google Cloud deployment with comprehensive call logging and analytics.

## 🌟 Features

### Core Functionality
- **Real-time voice conversations** using OpenAI's Realtime API
- **Twilio integration** for outbound and inbound calls
- **WebSocket streaming** for low-latency audio processing
- **Multiple concurrent calls** with connection pooling
- **RESTful API** for call management and monitoring

### Database & Logging
- **PostgreSQL database** with Google Cloud SQL integration
- **Comprehensive call logging** with conversation transcripts
- **Real-time analytics** and reporting
- **Call history** with detailed metrics
- **Automatic conversation transcription**
- **Data export** and backup capabilities

### Production Features
- **Auto-scaling** on Google Cloud Run/App Engine
- **Health monitoring** with built-in health checks
- **Rate limiting** and spam protection
- **Phone number authorization** system
- **Error handling** and recovery
- **CORS support** for frontend integration

## 🏗️ Architecture

```
┌─────────────────┐    ┌──────────────┐    ┌─────────────────┐
│    Frontend     │───▶│   FastAPI    │───▶│   OpenAI API    │
│   (External)    │    │   Backend    │    │ (Realtime API)  │
└─────────────────┘    └──────┬───────┘    └─────────────────┘
                              │
                              ▼
                       ┌─────────────┐     ┌─────────────────┐
                       │   Twilio    │────▶│  Google Cloud   │
                       │    API      │     │      SQL        │
                       └─────────────┘     └─────────────────┘
```

## 🚀 Quick Start

### Prerequisites

- Python 3.11+
- Google Cloud CLI
- Twilio account with phone number
- OpenAI API key
- PostgreSQL (local development) or Google Cloud SQL

### 1. Clone and Setup

```bash
git clone <your-repo>
cd alpha-call

# Install dependencies
pip install -r requirements.txt

# Copy environment configuration
cp env.example .env
```

### 2. Configure Environment Variables

Edit `.env` with your credentials:

```bash
# Core API keys
OPENAI_API_KEY=your_openai_api_key_here
TWILIO_ACCOUNT_SID=your_twilio_account_sid_here
TWILIO_AUTH_TOKEN=your_twilio_auth_token_here
PHONE_NUMBER_FROM=your_twilio_phone_number_here
DOMAIN=your_domain_here

# Database (will be configured automatically)
GOOGLE_CLOUD_SQL_CONNECTION_NAME=your-project:region:instance-name
DB_USER=postgres
DB_PASSWORD=your_database_password
DB_NAME=voice_assistant
```

### 3. Database Setup

#### Option A: Automatic Setup (Recommended)
```bash
# Run the database setup script
./setup-database.sh

# Copy the generated database config to your .env file
cat .env.database >> .env
```

#### Option B: Manual Setup
```bash
# Create Cloud SQL instance manually, then run migrations
python manage-db.py migrate
```

### 4. Deploy to Google Cloud

```bash
# Automated deployment script
./deploy.sh

# Follow the prompts to choose Cloud Run or App Engine
```

## 📊 Database Schema

### Call Logs Table
Stores comprehensive call metadata:
- Call identifiers (SID, stream SID)
- Phone number and caller information
- Timestamps (initiated, connected, ended)
- Duration and status tracking
- AI configuration (voice, system message)
- Error tracking and analytics counters

### Conversation Logs Table
Stores detailed conversation data:
- Message-by-message logging
- Speaker identification (user/ai/system)
- Text transcriptions and audio metadata
- OpenAI response tracking
- Timestamps and metadata

## 🛠️ Database Management

### Migration Commands
```bash
# Run migrations
python manage-db.py migrate

# Create new migration
python manage-db.py create-migration --message "Add new feature"

# Test database connection
python manage-db.py test
```

### Analytics and Monitoring
```bash
# View call analytics
python manage-db.py analytics

# Create backup
python manage-db.py backup

# Export conversation transcripts
python manage-db.py export-transcripts --days 7
```

### Data Management
```bash
# Add test data for development
python manage-db.py seed

# Clean up old data (30+ days)
python manage-db.py cleanup --days 30
```

## 📡 API Endpoints

### Core Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/request-call` | Initiate AI call to phone number |
| `GET` | `/api/call-history` | Retrieve call history with pagination |
| `GET` | `/api/analytics` | Get call analytics and metrics |
| `GET` | `/api/call/{call_sid}/conversation` | Get conversation transcript |
| `GET` | `/health` | Service health check |
| `POST` | `/incoming-call` | Twilio webhook for incoming calls |
| `WS` | `/media-stream` | WebSocket for audio streaming |

### Example Usage

```bash
# Request a call
curl -X POST "https://your-domain.com/api/request-call" \
  -H "Content-Type: application/json" \
  -d '{"phone_number": "+1234567890", "name": "John Doe"}'

# Get call history
curl "https://your-domain.com/api/call-history?limit=10&offset=0"

# View analytics
curl "https://your-domain.com/api/analytics"
```

## 🔧 Configuration

### Environment Variables

#### Core Configuration
- `OPENAI_API_KEY`: OpenAI API key for Realtime API
- `TWILIO_ACCOUNT_SID`: Twilio account identifier
- `TWILIO_AUTH_TOKEN`: Twilio authentication token
- `PHONE_NUMBER_FROM`: Twilio phone number for outbound calls
- `DOMAIN`: Your deployed domain (without protocol)

#### Database Configuration
- `GOOGLE_CLOUD_SQL_CONNECTION_NAME`: Cloud SQL instance connection name
- `DB_USER`: Database username (default: postgres)
- `DB_PASSWORD`: Database password
- `DB_NAME`: Database name (default: voice_assistant)
- `DATABASE_URL`: Alternative full database URL

#### Phone Authorization
- `VERIFIED_PHONE_NUMBERS`: Comma-separated list of authorized numbers
- `ALLOW_ALL_US_CANADA`: Allow all US/Canada numbers (development only)

#### Concurrency Settings
- `MAX_CONCURRENT_CALLS`: Maximum simultaneous calls (default: 10)
- `MAX_OPENAI_CONNECTIONS`: Maximum OpenAI connections (default: 20)

### Twilio Configuration

1. **Webhook URLs**: Set your Twilio phone number webhooks to:
   - Voice: `https://your-domain.com/incoming-call`

2. **Phone Number Authorization**: Add authorized numbers to `VERIFIED_PHONE_NUMBERS`

## 📈 Monitoring and Analytics

### Built-in Analytics
- Total calls and success rates
- Average call duration
- Calls by status (initiated, connected, completed, failed)
- Recent activity (24-hour window)
- Conversation metrics (AI responses, user inputs)

### Real-time Monitoring
- Active connection count
- Current concurrent calls
- Service health status
- Database connectivity

### Data Export
- JSON backups with full call data
- Conversation transcript exports
- Analytics data in structured format

## 🔒 Security Considerations

### Phone Number Authorization
- Whitelist-based phone number validation
- Environment-configurable authorized numbers
- Rate limiting (5-minute cooldown per number)

### API Security
- CORS configuration for frontend integration
- Input validation with Pydantic models
- Error handling without information disclosure

### Database Security
- Google Cloud SQL with private networking
- Connection pooling with limits
- Automatic cleanup of stale connections

## 🚀 Deployment Options

### Google Cloud Run (Recommended)
- Automatic scaling based on demand
- Pay-per-use pricing model
- Integrated Cloud SQL connectivity
- Container-based deployment

### Google App Engine
- Managed platform with automatic scaling
- Built-in load balancing
- Integrated monitoring and logging

### Local Development
```bash
# Set up local PostgreSQL
# Update .env with local database URL
python main.py
```

## 📋 Troubleshooting

### Common Issues

1. **Database Connection Errors**
   ```bash
   # Test database connectivity
   python manage-db.py test
   
   # Check Cloud SQL instance status
   gcloud sql instances describe your-instance-name
   ```

2. **Migration Issues**
   ```bash
   # Reset migrations (development only)
   python manage-db.py create-migration --message "Initial migration"
   python manage-db.py migrate
   ```

3. **Twilio Webhook Issues**
   - Verify webhook URLs in Twilio Console
   - Check service URL accessibility
   - Review call logs for error details

### Debugging

```bash
# Enable database query logging
DB_ECHO=true python main.py

# View recent call logs
python manage-db.py analytics

# Export call details for investigation
python manage-db.py export-transcripts --call-sid CAxxxxx
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Add database migrations if needed
4. Test with local database
5. Submit a pull request

## 📜 License

This project is licensed under the MIT License.

## ⚖️ Legal Notice

**Important**: Always disclose the use of AI for outbound or inbound calls. All TCPA (Telephone Consumer Protection Act) rules apply even if a call is made by AI. Consult with legal counsel for compliance advice in your jurisdiction. 