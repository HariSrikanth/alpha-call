# 🎯 AI Voice Assistant API Documentation

## 🌐 **Base URL**
```
https://ai-voice-assistant-664531083530.us-central1.run.app
```

## 📋 **Core API Endpoints**

### 1. **Health Check**
```http
GET /health
```
**Purpose**: Check service health and current status
**Response**:
```json
{
  "status": "healthy",
  "timestamp": "2025-05-28T23:59:05.478909",
  "concurrent_calls": {
    "active_connections": 0,
    "max_concurrent": 10,
    "can_accept_calls": true
  },
  "services": {
    "twilio": "connected",
    "openai": "configured", 
    "database": "connected"
  }
}
```

### 2. **Request Call** (Primary Action)
```http
POST /api/request-call
Content-Type: application/json
```
**Purpose**: Schedule/initiate an AI voice call
**Request Body**:
```json
{
  "phone_number": "+1234567890",  // Required: E.164 format
  "name": "John Doe"              // Optional: Caller's name
}
```
**Success Response**:
```json
{
  "success": true,
  "message": "Call initiated successfully! You should receive a call within 30 seconds.",
  "call_sid": "CAb77fc692305528b7f89be7ac9e907b98",
  "estimated_time": "30 seconds",
  "queue_position": 1
}
```
**Error Responses**:
```json
// Rate limited (1 minute cooldown)
{
  "detail": "Please wait before requesting another call. You can only request one call every 1 minute."
}

// Service busy
{
  "detail": "Service temporarily unavailable. Maximum concurrent calls (10) reached. Please try again in a few minutes."
}

// Invalid phone number
{
  "detail": "Phone number must include country code (e.g., +1)"
}
```

### 3. **Call History**
```http
GET /api/call-history?limit=50&offset=0
```
**Purpose**: Get paginated list of recent calls
**Query Parameters**:
- `limit` (optional): Number of records (default: 50)
- `offset` (optional): Pagination offset (default: 0)

**Response**:
```json
{
  "success": true,
  "call_history": [
    {
      "call_sid": "CAf20b6ee841a9bea73a5f4d80535fdc77",
      "phone_number": "+19166930389",
      "caller_name": "Test User",
      "initiated_at": "2025-05-29T00:01:40.552419+00:00",
      "duration_seconds": null,
      "status": "completed",  // "initiated", "connected", "completed", "failed"
      "total_ai_responses": 0,
      "total_user_inputs": 0
    }
  ],
  "pagination": {
    "limit": 50,
    "offset": 0,
    "returned_count": 1
  },
  "concurrent_connections": 0
}
```

### 4. **Analytics Dashboard**
```http
GET /api/analytics
```
**Purpose**: Get system metrics and call statistics
**Response**:
```json
{
  "success": true,
  "analytics": {
    "total_calls": 5,
    "calls_by_status": {
      "completed": 3,
      "initiated": 2
    },
    "average_duration_seconds": 0,
    "recent_calls_24h": 5,
    "current_concurrent_calls": 0,
    "max_concurrent_calls": 10
  }
}
```

### 5. **Conversation Logs** (Detailed Call Data)
```http
GET /api/call/{call_sid}/conversation
```
**Purpose**: Get detailed conversation transcript and logs for a specific call
**Response**:
```json
{
  "success": true,
  "call_info": {
    "call_sid": "CAb77fc692305528b7f89be7ac9e907b98",
    "phone_number": "+19166930389",
    "caller_name": "Test User",
    "initiated_at": "2025-05-28T23:59:34.401695+00:00",
    "duration_seconds": null,
    "status": "completed"
  },
  "conversation": [
    {
      "timestamp": "2025-05-29T00:00:06.958986+00:00",
      "speaker": "user|ai|system",
      "message_type": "text|audio|event|error",
      "text_content": "Hello, how are you?",
      "message_metadata": {
        "openai_response_id": "resp_123",
        "event": "stream_start"
      }
    }
  ]
}
```

### 6. **System Information**
```http
GET /
```
**Purpose**: Get API overview and available endpoints
**Response**:
```json
{
  "message": "AI Voice Assistant API",
  "description": "Backend service for Twilio + OpenAI Realtime voice calls",
  "version": "1.0.0",
  "concurrent_calls": {
    "current_active": 0,
    "max_allowed": 10
  },
  "database": {
    "status": "connected"
  },
  "endpoints": {
    "health": "/health",
    "request_call": "/api/request-call",
    "call_history": "/api/call-history", 
    "analytics": "/api/analytics",
    "incoming_call": "/incoming-call",
    "media_stream": "/media-stream"
  }
}
```

## 🔧 **Technical Details**

### **CORS Configuration**
- ✅ CORS enabled for all origins (`*`)
- ✅ All HTTP methods allowed
- ✅ Credentials supported

### **Rate Limiting**
- **Cooldown**: 1 minute between calls per phone number
- **Concurrent Calls**: Maximum 10 simultaneous calls
- **Phone Number Format**: Must include country code (E.164 format)

### **Call Status Flow**
1. `initiated` → Call request accepted, Twilio call starting
2. `connected` → Call answered, WebSocket stream active
3. `completed` → Call ended normally
4. `failed` → Call failed due to error

### **Voice Configuration**
- **Current Voice**: `sage` (male, conversational, VC-like)
- **AI Persona**: Venture capitalist interviewer
- **Response Style**: Thoughtful, probing questions with natural conversation flow

### **Database Logging**
- All calls logged with metadata
- Conversation transcripts stored
- Audio events tracked (but audio data not stored)
- Analytics computed in real-time

## 🎨 **Frontend Implementation Suggestions**

### **Call Scheduling Interface**
```javascript
// Example call request
const scheduleCall = async (phoneNumber, name) => {
  const response = await fetch('/api/request-call', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      phone_number: phoneNumber,
      name: name
    })
  });
  return response.json();
};
```

### **Real-time Status Polling**
```javascript
// Poll call status every 5 seconds
const pollCallStatus = (callSid) => {
  setInterval(async () => {
    const response = await fetch(`/api/call/${callSid}/conversation`);
    const data = await response.json();
    updateCallStatus(data.call_info.status);
  }, 5000);
};
```

### **Dashboard Components Needed**
1. **Call Request Form** (phone number + name input)
2. **Call History Table** (with pagination)
3. **Analytics Dashboard** (charts/metrics)
4. **Conversation Viewer** (transcript display)
5. **Real-time Status Indicator** (active calls counter)

### **Error Handling**
- Handle rate limiting with countdown timer
- Show service capacity warnings
- Validate phone number format client-side
- Display connection status indicators

## 🚀 **Testing**
- **Test Phone Number**: +19166930389 (Twilio verified)
- **Health Check**: Always test `/health` before making calls
- **Rate Limit**: Wait 1 minute between test calls

## 📱 **Frontend Requirements**

### **Core Features to Implement**
1. **Call Scheduling**
   - Phone number input with validation
   - Optional name field
   - Submit button with loading states
   - Success/error feedback

2. **Call Status Tracking**
   - Real-time status updates
   - Progress indicators
   - Call duration tracking
   - Queue position display

3. **Call History Management**
   - Paginated table/list view
   - Search/filter capabilities
   - Sort by date, status, duration
   - Export functionality

4. **Analytics Dashboard**
   - Call volume charts
   - Success rate metrics
   - Average duration stats
   - Real-time concurrent calls

5. **Conversation Viewer**
   - Transcript display
   - Speaker identification
   - Timestamp formatting
   - Search within conversations

### **UI/UX Considerations**
- **Responsive Design**: Mobile-first approach
- **Real-time Updates**: WebSocket or polling for live data
- **Error States**: Clear error messages and recovery options
- **Loading States**: Skeleton screens and progress indicators
- **Accessibility**: WCAG compliance for screen readers

### **State Management**
```javascript
// Suggested state structure
const appState = {
  calls: {
    active: [],
    history: [],
    currentCall: null,
    loading: false,
    error: null
  },
  analytics: {
    metrics: {},
    loading: false,
    lastUpdated: null
  },
  ui: {
    selectedCall: null,
    showConversation: false,
    filters: {},
    pagination: { page: 1, limit: 50 }
  }
};
```

## 🔐 **Security & Best Practices**

### **Input Validation**
- Validate phone numbers client-side (E.164 format)
- Sanitize all user inputs
- Implement rate limiting UI feedback

### **Error Handling**
- Graceful degradation for network issues
- Retry mechanisms for failed requests
- User-friendly error messages

### **Performance**
- Implement pagination for large datasets
- Cache frequently accessed data
- Optimize API calls with debouncing

This API is production-ready with full database logging, analytics, and error handling. The frontend can provide a complete call management interface with real-time status updates and detailed conversation logs. 