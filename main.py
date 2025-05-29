import asyncio
import base64
import json
import os
import argparse
from typing import Optional, Dict
from datetime import datetime
import websockets
import uvicorn
from fastapi import FastAPI, WebSocket, Request, HTTPException
from fastapi.responses import PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, validator
from twilio.rest import Client
from dotenv import load_dotenv
import weakref
from contextlib import asynccontextmanager

# Import database components
from database import db_manager, CallLogger, AnalyticsService

# Load environment variables
load_dotenv()

# Configuration
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN')
PHONE_NUMBER_FROM = os.getenv('PHONE_NUMBER_FROM')
DOMAIN = os.getenv('DOMAIN')
PORT = int(os.getenv('PORT', 8080))

# Concurrency settings
MAX_CONCURRENT_CALLS = int(os.getenv('MAX_CONCURRENT_CALLS', '10'))
MAX_OPENAI_CONNECTIONS = int(os.getenv('MAX_OPENAI_CONNECTIONS', '20'))

# Voice settings
# TODO: Add more specifics w.r.t. the accent and delivery; can add phrases commonly used to make it more natural as a VC
# TODO: Deep downstream shift to elevenlabs proprietary server and train it to do everything automatically

VOICE = 'sage'
SYSTEM_MESSAGE = (
    "You are an AI Agent who handles the introductory call for onboarding users onto the platform Alpha.me "
    "Users on Alpha.me (alpha dot me) are incredibly high agency and high intellect, and they are founders or builders that are working on projects that can change the world. "
    "Every person that you talk to is incredibly special, but also incredibly busy. You aim to ask pointed, sharp questions, much in the way a top venture capitalist would, and understand what makes them tick, what they have achieved, and what they are looking to do next."
    "Don't ask too many questions in one response. Even though you are incredibly focused, speak in a relaxed way–it's fine to add a few umms and hmms to pause, and phrases like ahh ok gotcha or makes sense are good ways to stay conversational."
    "The user should feel as if they are meeting with a top venture capitalist for dinner–they introduce themselves, you press for important details and deeply understand the multitude of different things that they do, and then you dont dril them too much and waste both of yalls time."
    "Push for understanding but dont hyperfixate "
)

# Initialize Twilio client
twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

# Initialize FastAPI app
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    try:
        logger.info("Starting application initialization...")
        logger.info(f"Environment variables check:")
        logger.info(f"  - OPENAI_API_KEY: {'✓' if OPENAI_API_KEY else '✗'}")
        logger.info(f"  - TWILIO_ACCOUNT_SID: {'✓' if TWILIO_ACCOUNT_SID else '✗'}")
        logger.info(f"  - TWILIO_AUTH_TOKEN: {'✓' if TWILIO_AUTH_TOKEN else '✗'}")
        logger.info(f"  - PHONE_NUMBER_FROM: {'✓' if PHONE_NUMBER_FROM else '✗'}")
        logger.info(f"  - DOMAIN: {'✓' if DOMAIN else '✗'}")
        logger.info(f"  - PORT: {PORT}")
        
        await db_manager.initialize()
        logger.info("Application initialization completed successfully")
    except Exception as e:
        logger.error(f"Failed to initialize application: {e}")
        raise
    
    yield
    
    # Shutdown
    try:
        logger.info("Shutting down application...")
        await db_manager.close()
        logger.info("Application shutdown completed")
    except Exception as e:
        logger.error(f"Error during shutdown: {e}")

app = FastAPI(
    title="AI Voice Assistant API", 
    description="Backend API for Twilio + OpenAI Realtime Voice Application",
    version="1.0.0",
    lifespan=lifespan
)

# Add CORS middleware for frontend integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure this properly for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Logging setup
import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Connection management
class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, dict] = {}
        self.openai_connection_count = 0
        self.connection_semaphore = asyncio.Semaphore(MAX_OPENAI_CONNECTIONS)
    
    async def add_connection(self, call_sid: str, websocket: WebSocket, openai_ws):
        """Add a new connection to tracking."""
        self.active_connections[call_sid] = {
            "websocket": websocket,
            "openai_ws": openai_ws,
            "created_at": datetime.utcnow(),
            "status": "active"
        }
        logger.info(f"Added connection for call {call_sid}. Total active: {len(self.active_connections)}")
    
    async def remove_connection(self, call_sid: str):
        """Remove connection from tracking."""
        if call_sid in self.active_connections:
            connection = self.active_connections.pop(call_sid)
            if connection.get("openai_ws"):
                try:
                    await connection["openai_ws"].close()
                except:
                    pass
            logger.info(f"Removed connection for call {call_sid}. Total active: {len(self.active_connections)}")
    
    def get_connection_count(self) -> int:
        """Get current active connection count."""
        return len(self.active_connections)
    
    async def cleanup_stale_connections(self):
        """Clean up connections that might have been orphaned."""
        from datetime import timedelta
        cutoff_time = datetime.utcnow() - timedelta(minutes=30)  # 30 minute timeout
        
        stale_connections = [
            call_sid for call_sid, conn in self.active_connections.items()
            if conn["created_at"] < cutoff_time
        ]
        
        for call_sid in stale_connections:
            logger.warning(f"Cleaning up stale connection: {call_sid}")
            await self.remove_connection(call_sid)

# Global connection manager
connection_manager = ConnectionManager()

# Pydantic models for API
class CallRequest(BaseModel):
    phone_number: str
    name: Optional[str] = None
    
    @validator('phone_number')
    def validate_phone_number(cls, v):
        # Remove any formatting and validate
        cleaned = ''.join(filter(str.isdigit, v.replace('+', '', 1)))
        if not v.startswith('+'):
            raise ValueError('Phone number must include country code (e.g., +1)')
        if len(cleaned) < 10 or len(cleaned) > 15:
            raise ValueError('Invalid phone number length')
        return v

@app.get("/")
async def root():
    """Root endpoint providing API information."""
    return {
        "message": "AI Voice Assistant API",
        "description": "Backend service for Twilio + OpenAI Realtime voice calls",
        "version": "1.0.0",
        "concurrent_calls": {
            "current_active": connection_manager.get_connection_count(),
            "max_allowed": MAX_CONCURRENT_CALLS
        },
        "database": {
            "status": "connected" if db_manager.engine else "disconnected"
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

@app.get("/health")
async def health():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "concurrent_calls": {
            "active_connections": connection_manager.get_connection_count(),
            "max_concurrent": MAX_CONCURRENT_CALLS,
            "can_accept_calls": connection_manager.get_connection_count() < MAX_CONCURRENT_CALLS
        },
        "services": {
            "twilio": "connected" if TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN else "not configured",
            "openai": "configured" if OPENAI_API_KEY else "not configured",
            "database": "connected" if db_manager.engine else "disconnected"
        }
    }

@app.get("/startup")
async def startup_health():
    """Simple startup health check that doesn't require database."""
    return {
        "status": "starting",
        "timestamp": datetime.utcnow().isoformat(),
        "port": PORT,
        "environment": "cloud_run" if os.getenv('K_SERVICE') else "local"
    }

@app.post("/api/request-call")
async def request_call(call_request: CallRequest):
    """API endpoint to request an AI call."""
    try:
        phone_number = call_request.phone_number
        name = call_request.name
        
        logger.info(f"Call request received for {phone_number} (name: {name or 'Anonymous'})")
        
        # Check concurrent call limit
        if connection_manager.get_connection_count() >= MAX_CONCURRENT_CALLS:
            raise HTTPException(
                status_code=503,
                detail=f"Service temporarily unavailable. Maximum concurrent calls ({MAX_CONCURRENT_CALLS}) reached. Please try again in a few minutes."
            )
        
        # Enhanced authorization check - DISABLED FOR TESTING
        # if not is_authorized_phone_number(phone_number):
        #     logger.warning(f"Unauthorized call request to {phone_number}")
        #     raise HTTPException(
        #         status_code=403, 
        #         detail="This phone number is not authorized for calls. Please contact support to add your number to the allowlist."
        #     )
        
        # Check for recent calls to prevent spam
        if await has_recent_call(phone_number):
            raise HTTPException(
                status_code=429,
                detail="Please wait before requesting another call. You can only request one call every 1 minute."
            )
        
        # Initiate the call
        call_sid = await make_call_async(phone_number, name)
        
        if call_sid:
            logger.info(f"Call initiated successfully: {call_sid}")
            return {
                "success": True,
                "message": f"Call initiated successfully! You should receive a call within 30 seconds.",
                "call_sid": call_sid,
                "estimated_time": "30 seconds",
                "queue_position": connection_manager.get_connection_count() + 1
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to initiate call. Please try again.")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing call request: {e}")
        raise HTTPException(status_code=500, detail="Internal server error. Please try again later.")

def is_authorized_phone_number(phone_number: str) -> bool:
    """
    Enhanced phone number authorization with multiple validation methods.
    """
    # Allow Twilio numbers (for testing)
    if phone_number.startswith('+1555'):
        return True
    
    # Allow verified caller IDs from environment
    verified_numbers = os.getenv('VERIFIED_PHONE_NUMBERS', '').split(',')
    if phone_number in [num.strip() for num in verified_numbers if num.strip()]:
        return True
    
    # Add your authorized numbers here
    authorized_numbers = [
        # Add your verified caller IDs here
        # '+1234567890',
    ]
    
    if phone_number in authorized_numbers:
        return True
    
    # For development/demo: allow any US/Canada number (remove in production)
    if os.getenv('ALLOW_ALL_US_CANADA', 'false').lower() == 'true':
        cleaned = phone_number.replace('+', '').replace('-', '').replace('(', '').replace(')', '').replace(' ', '')
        if cleaned.startswith('1') and len(cleaned) == 11:
            return True
    
    return False

async def has_recent_call(phone_number: str, cooldown_minutes: int = 1) -> bool:
    """Check if phone number has received a call recently using database."""
    try:
        from datetime import timedelta
        from database import db_manager
        
        async with db_manager.get_session() as session:
            from sqlalchemy import select
            from database import CallLog
            
            cutoff_time = datetime.utcnow() - timedelta(minutes=cooldown_minutes)
            
            stmt = select(CallLog).where(
                CallLog.phone_number == phone_number,
                CallLog.initiated_at >= cutoff_time
            ).limit(1)
            
            result = await session.execute(stmt)
            recent_call = result.scalar_one_or_none()
            
            return recent_call is not None
            
    except Exception as e:
        logger.error(f"Error checking recent calls: {e}")
        return False  # Allow call if we can't check

async def make_call_async(phone_number_to_call: str, name: Optional[str] = None):
    """Make an outbound call using Twilio (async version)."""
    try:
        # Customize system message if name is provided
        custom_message = SYSTEM_MESSAGE
        if name:
            custom_message = f"You are calling {name}. " + SYSTEM_MESSAGE
        
        # TwiML for outbound call - connects to our WebSocket
        outbound_twiml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            f'<Response><Connect><Stream url="wss://{DOMAIN}/media-stream" /></Connect></Response>'
        )
        
        call = twilio_client.calls.create(
            from_=PHONE_NUMBER_FROM,
            to=phone_number_to_call,
            twiml=outbound_twiml
        )
        
        # Create database log entry
        await CallLogger.create_call_log(
            call_sid=call.sid,
            phone_number=phone_number_to_call,
            caller_name=name,
            direction="outbound",
            ai_voice=VOICE,
            system_message=custom_message
        )
        
        await log_call_sid(call.sid, name)
        logger.info(f"Call initiated successfully to {phone_number_to_call} (SID: {call.sid})")
        return call.sid
        
    except Exception as e:
        logger.error(f"Failed to initiate call to {phone_number_to_call}: {e}")
        return None

async def make_call(phone_number_to_call: str):
    """Legacy function for command line usage."""
    # Authorization check disabled for testing
    # if not is_authorized_phone_number(phone_number_to_call):
    #     logger.error(f"Unauthorized phone number: {phone_number_to_call}")
    #     return
    
    call_sid = await make_call_async(phone_number_to_call)
    return call_sid

async def log_call_sid(call_sid: str, name: Optional[str] = None):
    """Log the call SID with additional context."""
    logger.info(f"Call started with SID: {call_sid}" + (f" for {name}" if name else ""))

@asynccontextmanager
async def get_openai_connection():
    """Context manager for OpenAI connections with semaphore control."""
    async with connection_manager.connection_semaphore:
        try:
            connection_manager.openai_connection_count += 1
            logger.info(f"Opening OpenAI connection. Total: {connection_manager.openai_connection_count}")
            
            openai_ws = await websockets.connect(
                'wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview-2024-10-01',
                extra_headers={
                    "Authorization": f"Bearer {OPENAI_API_KEY}",
                    "OpenAI-Beta": "realtime=v1"
                }
            )
            yield openai_ws
        finally:
            connection_manager.openai_connection_count -= 1
            logger.info(f"Closed OpenAI connection. Total: {connection_manager.openai_connection_count}")
            if 'openai_ws' in locals():
                await openai_ws.close()

@app.websocket("/media-stream")
async def handle_media_stream(websocket: WebSocket):
    """Handle WebSocket connections from Twilio and manage OpenAI Realtime API."""
    await websocket.accept()
    
    call_sid = None
    stream_sid = None
    
    try:
        logger.info("Client connected to media stream")
        
        # Use connection manager for OpenAI connection
        async with get_openai_connection() as openai_ws:
            # Configure OpenAI session
            session_update = {
                "type": "session.update",
                "session": {
                    "turn_detection": {"type": "server_vad"},
                    "input_audio_format": "g711_ulaw",
                    "output_audio_format": "g711_ulaw",
                    "voice": VOICE,
                    "instructions": SYSTEM_MESSAGE,
                    "modalities": ["text", "audio"],
                    "temperature": 0.8,
                    "input_audio_transcription": {
                        "model": "whisper-1"
                    }
                }
            }
            
            await openai_ws.send(json.dumps(session_update))
            logger.info("Sent session update to OpenAI")
            
            # Start OpenAI response listener
            async def openai_listener():
                try:
                    while not openai_ws.closed:
                        try:
                            openai_message = await openai_ws.recv()
                            response = json.loads(openai_message)
                            await handle_openai_response(response, websocket, stream_sid, call_sid)
                        except websockets.exceptions.ConnectionClosed:
                            logger.info(f"OpenAI WebSocket connection closed for call {call_sid}")
                            break
                        except Exception as e:
                            logger.error(f"Error processing OpenAI message for call {call_sid}: {e}")
                except Exception as e:
                    logger.error(f"Error in OpenAI listener for call {call_sid}: {e}")
            
            # Start the OpenAI listener task
            openai_task = asyncio.create_task(openai_listener())
            
            # Handle Twilio messages
            while True:
                try:
                    message = await websocket.receive_text()
                    data = json.loads(message)
                    await handle_twilio_message(data, openai_ws, websocket, call_sid)
                    
                    # Store stream_sid and call_sid for tracking
                    if data.get('event') == 'start':
                        stream_sid = data.get('start', {}).get('streamSid')
                        call_sid = data.get('start', {}).get('callSid')
                        logger.info(f"Stream started with SID: {stream_sid}, Call SID: {call_sid}")
                        
                        # Add to connection manager
                        await connection_manager.add_connection(call_sid, websocket, openai_ws)
                        
                        # Update database call status
                        await CallLogger.update_call_status(
                            call_sid=call_sid,
                            status="connected",
                            stream_sid=stream_sid
                        )
                        
                    elif data.get('event') == 'stop':
                        logger.info(f"Stream stopped for call {call_sid}")
                        # Log conversation end event
                        if call_sid:
                            await CallLogger.log_conversation(
                                call_sid=call_sid,
                                speaker="system",
                                message_type="event",
                                text_content="Call ended",
                                message_metadata={"event": "stream_stop"}
                            )
                        break
                            
                except json.JSONDecodeError:
                    logger.error("Received invalid JSON from Twilio")
                except Exception as e:
                    logger.error(f"Error handling Twilio message for call {call_sid}: {e}")
                    break
                    
    except Exception as e:
        logger.error(f"Error in media stream handler for call {call_sid}: {e}")
        if call_sid:
            await CallLogger.update_call_status(
                call_sid=call_sid,
                status="failed",
                error_message=str(e)
            )
    finally:
        # Clean up connection
        if call_sid:
            await connection_manager.remove_connection(call_sid)
            
            # Finalize call in database
            await CallLogger.finalize_call(call_sid)
                
        logger.info(f"Media stream connection closed for call {call_sid}")

async def handle_twilio_message(data: dict, openai_ws, twilio_ws: WebSocket, call_sid: Optional[str]):
    """Handle messages from Twilio and forward to OpenAI."""
    event_type = data.get('event')
    
    if event_type == 'media':
        # Forward audio to OpenAI
        if openai_ws and not openai_ws.closed:
            audio_append = {
                "type": "input_audio_buffer.append",
                "audio": data['media']['payload']
            }
            await openai_ws.send(json.dumps(audio_append))
            
            # Log user audio input (without storing the actual audio data)
            if call_sid:
                await CallLogger.log_conversation(
                    call_sid=call_sid,
                    speaker="user",
                    message_type="audio",
                    message_metadata={
                        "twilio_timestamp": data.get('media', {}).get('timestamp'),
                        "sequence_number": data.get('sequenceNumber')
                    }
                )
    
    elif event_type == 'start':
        logger.info("Twilio stream started")
        if call_sid:
            await CallLogger.log_conversation(
                call_sid=call_sid,
                speaker="system",
                message_type="event",
                text_content="Call connected",
                message_metadata={"event": "stream_start", "start_data": data.get('start', {})}
            )
        
    elif event_type == 'stop':
        logger.info("Twilio stream stopped")

async def handle_openai_response(response: dict, twilio_ws: WebSocket, stream_sid: Optional[str], call_sid: Optional[str]):
    """Handle responses from OpenAI and forward audio to Twilio."""
    response_type = response.get('type')
    
    if response_type == 'response.audio.delta':
        # Forward audio to Twilio
        if stream_sid:
            audio_payload = {
                "event": "media",
                "streamSid": stream_sid,
                "media": {
                    "payload": response['delta']
                }
            }
            await twilio_ws.send_text(json.dumps(audio_payload))
    
    elif response_type == 'response.audio.done':
        logger.info("OpenAI audio response completed")
        if call_sid:
            await CallLogger.log_conversation(
                call_sid=call_sid,
                speaker="ai",
                message_type="audio",
                openai_response_type=response_type,
                openai_response_id=response.get('response_id'),
                message_metadata=response
            )
    
    elif response_type == 'error':
        logger.error(f"OpenAI error: {response}")
        if call_sid:
            await CallLogger.log_conversation(
                call_sid=call_sid,
                speaker="system",
                message_type="error",
                text_content=f"OpenAI error: {response.get('error', {}).get('message', 'Unknown error')}",
                message_metadata=response
            )
    
    elif response_type == 'session.created':
        logger.info("OpenAI session created successfully")
    
    elif response_type == 'response.text.delta':
        # Log text responses for debugging and transcription
        text_delta = response.get('delta', '')
        if text_delta and call_sid:
            logger.info(f"OpenAI text delta: {text_delta}")
            await CallLogger.log_conversation(
                call_sid=call_sid,
                speaker="ai",
                message_type="text",
                text_content=text_delta,
                openai_response_type=response_type,
                openai_response_id=response.get('response_id'),
                message_metadata=response
            )
    
    elif response_type == 'conversation.item.input_audio_transcription.completed':
        # Log user speech transcription
        transcription = response.get('transcript', '')
        if transcription and call_sid:
            logger.info(f"User said: {transcription}")
            await CallLogger.log_conversation(
                call_sid=call_sid,
                speaker="user",
                message_type="text",
                text_content=transcription,
                openai_response_type=response_type,
                message_metadata=response
            )

@app.post("/incoming-call")
async def handle_incoming_call(request: Request):
    """Handle incoming calls with TwiML response."""
    # Extract phone number from Twilio request for logging
    form_data = await request.form()
    from_number = form_data.get('From', 'Unknown')
    call_sid = form_data.get('CallSid', 'Unknown')
    
    # Create database log for incoming call
    try:
        await CallLogger.create_call_log(
            call_sid=call_sid,
            phone_number=from_number,
            direction="inbound",
            ai_voice=VOICE,
            system_message=SYSTEM_MESSAGE
        )
    except Exception as e:
        logger.error(f"Failed to log incoming call {call_sid}: {e}")
    
    twiml_response = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<Response><Connect><Stream url="wss://{DOMAIN}/media-stream" /></Connect></Response>'
    )
    return PlainTextResponse(content=twiml_response, media_type="application/xml")

@app.get("/api/call-history")
async def get_call_history(limit: int = 50, offset: int = 0):
    """Get recent call history from database."""
    try:
        call_history = await AnalyticsService.get_call_history(limit=limit, offset=offset)
        return {
            "success": True,
            "call_history": call_history,
            "pagination": {
                "limit": limit,
                "offset": offset,
                "returned_count": len(call_history)
            },
            "concurrent_connections": connection_manager.get_connection_count()
        }
    except Exception as e:
        logger.error(f"Error getting call history: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve call history")

@app.get("/api/analytics")
async def get_analytics():
    """Get call analytics and metrics."""
    try:
        analytics = await AnalyticsService.get_call_analytics()
        analytics["current_concurrent_calls"] = connection_manager.get_connection_count()
        analytics["max_concurrent_calls"] = MAX_CONCURRENT_CALLS
        
        return {
            "success": True,
            "analytics": analytics
        }
    except Exception as e:
        logger.error(f"Error getting analytics: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve analytics")

@app.get("/api/call/{call_sid}/conversation")
async def get_call_conversation(call_sid: str):
    """Get conversation log for a specific call."""
    try:
        async with db_manager.get_session() as session:
            from sqlalchemy import select
            from database import CallLog, ConversationLog
            
            # Get call log with conversation
            stmt = (
                select(CallLog)
                .where(CallLog.call_sid == call_sid)
            )
            result = await session.execute(stmt)
            call_log = result.scalar_one_or_none()
            
            if not call_log:
                raise HTTPException(status_code=404, detail="Call not found")
            
            # Get conversation logs
            conversation_stmt = (
                select(ConversationLog)
                .where(ConversationLog.call_id == call_log.id)
                .order_by(ConversationLog.timestamp)
            )
            conversation_result = await session.execute(conversation_stmt)
            conversation_logs = conversation_result.scalars().all()
            
            return {
                "success": True,
                "call_info": {
                    "call_sid": call_log.call_sid,
                    "phone_number": call_log.phone_number,
                    "caller_name": call_log.caller_name,
                    "initiated_at": call_log.initiated_at.isoformat(),
                    "duration_seconds": call_log.duration_seconds,
                    "status": call_log.status
                },
                "conversation": [
                    {
                        "timestamp": log.timestamp.isoformat(),
                        "speaker": log.speaker,
                        "message_type": log.message_type,
                        "text_content": log.text_content,
                        "message_metadata": log.message_metadata
                    }
                    for log in conversation_logs
                ]
            }
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting conversation for {call_sid}: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve conversation")

# Background task for cleanup
async def cleanup_task():
    """Background task to clean up stale connections."""
    while True:
        try:
            await connection_manager.cleanup_stale_connections()
            await asyncio.sleep(300)  # Run every 5 minutes
        except Exception as e:
            logger.error(f"Error in cleanup task: {e}")
            await asyncio.sleep(60)  # Retry in 1 minute on error

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the Twilio AI voice assistant server.")
    parser.add_argument('--call', help="The phone number to call, e.g., '--call=+18005551212'")
    parser.add_argument('--server-only', action='store_true', help="Run server only without making a call")
    args = parser.parse_args()

    print("🤖 Twilio + OpenAI Realtime API Voice Assistant")
    print("=" * 50)
    print("🔌 Backend API Server with Database Logging")
    print(f"📞 Max concurrent calls: {MAX_CONCURRENT_CALLS}")
    print(f"🔗 Max OpenAI connections: {MAX_OPENAI_CONNECTIONS}")
    print("🗄️  PostgreSQL database integration")
    print("📞 Call requests accepted via /api/request-call endpoint")
    print("🌐 CORS enabled for frontend integration")
    print("⚖️  Recommendation: Always disclose the use of AI for outbound or inbound calls.")
    print("📋 Reminder: All TCPA rules apply even if a call is made by AI.")
    print("⚖️  Check with your counsel for legal and compliance advice.")
    print("=" * 50)

    # Validate environment variables
    required_vars = ['OPENAI_API_KEY', 'TWILIO_ACCOUNT_SID', 'TWILIO_AUTH_TOKEN', 'PHONE_NUMBER_FROM']
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        print(f"❌ Missing required environment variables: {', '.join(missing_vars)}")
        print("Please check your .env file and ensure all variables are set.")
        exit(1)
    
    # DOMAIN can be set after deployment, so just warn if missing
    if not DOMAIN:
        print("⚠️  DOMAIN environment variable not set. This will be set automatically after deployment.")

    # Legacy command line call support
    if args.call and not args.server_only:
        phone_number = args.call
        async def make_cli_call():
            await db_manager.initialize()
            await make_call(phone_number)
            await db_manager.close()
        
        asyncio.run(make_cli_call())
    
    # Start the server
    print(f"🚀 Starting API server on port {PORT}...")
    print(f"📡 API Documentation: http://localhost:{PORT}/docs")
    uvicorn.run(
        app, 
        host="0.0.0.0", 
        port=PORT,
        timeout_keep_alive=30,
        timeout_graceful_shutdown=30,
        access_log=True,
        log_level="info"
    ) 