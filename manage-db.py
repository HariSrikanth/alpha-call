#!/usr/bin/env python3
"""
Database Management Script for AI Voice Assistant
Handles migrations, backups, data import/export, and analytics
"""

import asyncio
import os
import argparse
import json
from datetime import datetime, timedelta
from typing import List, Dict, Any

from dotenv import load_dotenv
from database import db_manager, AnalyticsService, CallLogger
from sqlalchemy import text

# Load environment variables
load_dotenv()


async def run_migrations():
    """Run database migrations"""
    print("🗄️  Running database migrations...")
    
    # Import alembic programmatically
    from alembic.config import Config
    from alembic import command
    
    alembic_cfg = Config("alembic.ini")
    command.upgrade(alembic_cfg, "head")
    
    print("✅ Database migrations completed")


async def create_migration(message: str):
    """Create a new migration"""
    print(f"📝 Creating migration: {message}")
    
    from alembic.config import Config
    from alembic import command
    
    alembic_cfg = Config("alembic.ini")
    command.revision(alembic_cfg, message=message, autogenerate=True)
    
    print("✅ Migration created")


async def backup_database():
    """Export call data to JSON backup"""
    print("💾 Creating database backup...")
    
    await db_manager.initialize()
    
    try:
        # Get all call history
        call_history = await AnalyticsService.get_call_history(limit=10000)
        
        # Get analytics
        analytics = await AnalyticsService.get_call_analytics()
        
        backup_data = {
            "created_at": datetime.utcnow().isoformat(),
            "version": "1.0",
            "analytics": analytics,
            "call_history": call_history,
            "total_records": len(call_history)
        }
        
        # Create backup filename with timestamp
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        backup_file = f"backup_voice_assistant_{timestamp}.json"
        
        with open(backup_file, 'w') as f:
            json.dump(backup_data, f, indent=2, default=str)
        
        print(f"✅ Backup created: {backup_file}")
        print(f"   Records: {len(call_history)}")
        print(f"   Size: {os.path.getsize(backup_file)} bytes")
        
    finally:
        await db_manager.close()


async def get_analytics():
    """Display database analytics"""
    print("📊 Fetching database analytics...")
    
    await db_manager.initialize()
    
    try:
        analytics = await AnalyticsService.get_call_analytics()
        recent_calls = await AnalyticsService.get_call_history(limit=10)
        
        print("\n" + "="*50)
        print("📈 CALL ANALYTICS")
        print("="*50)
        print(f"Total Calls: {analytics.get('total_calls', 0)}")
        print(f"Average Duration: {analytics.get('average_duration_seconds', 0):.1f} seconds")
        print(f"Recent Calls (24h): {analytics.get('recent_calls_24h', 0)}")
        
        print(f"\n📋 CALLS BY STATUS:")
        for status, count in analytics.get('calls_by_status', {}).items():
            print(f"  {status.capitalize()}: {count}")
        
        print(f"\n🕒 RECENT CALLS:")
        for call in recent_calls[:5]:
            duration = call.get('duration_seconds', 0)
            duration_str = f"{duration}s" if duration else "N/A"
            print(f"  {call['call_sid'][:10]}... | {call['phone_number']} | {duration_str} | {call['status']}")
        
        print("="*50)
        
    finally:
        await db_manager.close()


async def cleanup_old_data(days: int = 30):
    """Clean up old call data"""
    print(f"🧹 Cleaning up data older than {days} days...")
    
    await db_manager.initialize()
    
    try:
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        
        async with db_manager.get_session() as session:
            # Count records to be deleted
            count_query = text("""
                SELECT COUNT(*) 
                FROM call_logs 
                WHERE initiated_at < :cutoff_date
            """)
            result = await session.execute(count_query, {"cutoff_date": cutoff_date})
            count = result.scalar()
            
            if count == 0:
                print("✅ No old records found")
                return
            
            print(f"Found {count} records older than {cutoff_date.date()}")
            
            # Ask for confirmation
            confirm = input(f"Delete {count} records? (y/N): ")
            if confirm.lower() != 'y':
                print("❌ Cleanup cancelled")
                return
            
            # Delete conversation logs first (foreign key constraint)
            delete_conversations = text("""
                DELETE FROM conversation_logs 
                WHERE call_id IN (
                    SELECT id FROM call_logs 
                    WHERE initiated_at < :cutoff_date
                )
            """)
            await session.execute(delete_conversations, {"cutoff_date": cutoff_date})
            
            # Delete call logs
            delete_calls = text("""
                DELETE FROM call_logs 
                WHERE initiated_at < :cutoff_date
            """)
            await session.execute(delete_calls, {"cutoff_date": cutoff_date})
            
            await session.commit()
            
            print(f"✅ Deleted {count} old records")
            
    finally:
        await db_manager.close()


async def test_connection():
    """Test database connection"""
    print("🔌 Testing database connection...")
    
    try:
        await db_manager.initialize()
        
        async with db_manager.get_session() as session:
            result = await session.execute(text("SELECT version()"))
            version = result.scalar()
            print(f"✅ Connected to PostgreSQL: {version}")
            
            # Test tables exist
            tables_query = text("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public'
                ORDER BY table_name
            """)
            result = await session.execute(tables_query)
            tables = [row[0] for row in result.fetchall()]
            
            print(f"📋 Available tables: {', '.join(tables)}")
            
            if 'call_logs' in tables and 'conversation_logs' in tables:
                print("✅ All required tables present")
            else:
                print("⚠️  Some tables missing - run migrations")
                
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        
    finally:
        await db_manager.close()


async def seed_test_data():
    """Add test data for development"""
    print("🌱 Seeding test data...")
    
    await db_manager.initialize()
    
    try:
        # Create a test call log
        call_sid = await CallLogger.create_call_log(
            call_sid="test_call_001",
            phone_number="+15551234567",
            caller_name="Test User",
            direction="outbound",
            ai_voice="alloy",
            system_message="Test system message"
        )
        
        # Update to connected status
        await CallLogger.update_call_status(
            call_sid="test_call_001",
            status="connected",
            stream_sid="test_stream_001"
        )
        
        # Add some conversation logs
        await CallLogger.log_conversation(
            call_sid="test_call_001",
            speaker="user",
            message_type="text",
            text_content="Hello, how are you?"
        )
        
        await CallLogger.log_conversation(
            call_sid="test_call_001",
            speaker="ai",
            message_type="text",
            text_content="Hi! I'm doing great, thank you for asking. How can I help you today?"
        )
        
        # Finalize the call
        await CallLogger.finalize_call("test_call_001")
        
        print("✅ Test data seeded successfully")
        print("   Created test call: test_call_001")
        print("   Added conversation logs")
        
    finally:
        await db_manager.close()


async def export_call_transcripts(call_sid: str = None, days: int = 7):
    """Export call transcripts to text files"""
    print(f"📝 Exporting call transcripts...")
    
    await db_manager.initialize()
    
    try:
        async with db_manager.get_session() as session:
            from sqlalchemy import select
            from database import CallLog, ConversationLog
            
            # Build query
            if call_sid:
                call_query = select(CallLog).where(CallLog.call_sid == call_sid)
            else:
                cutoff_date = datetime.utcnow() - timedelta(days=days)
                call_query = select(CallLog).where(CallLog.initiated_at >= cutoff_date)
            
            result = await session.execute(call_query)
            calls = result.scalars().all()
            
            if not calls:
                print("❌ No calls found matching criteria")
                return
            
            export_dir = f"exports_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
            os.makedirs(export_dir, exist_ok=True)
            
            for call in calls:
                # Get conversation logs
                conv_query = (
                    select(ConversationLog)
                    .where(ConversationLog.call_id == call.id)
                    .order_by(ConversationLog.timestamp)
                )
                conv_result = await session.execute(conv_query)
                conversations = conv_result.scalars().all()
                
                # Create transcript file
                filename = f"{export_dir}/transcript_{call.call_sid}.txt"
                with open(filename, 'w') as f:
                    f.write(f"Call Transcript\n")
                    f.write(f"=" * 50 + "\n")
                    f.write(f"Call SID: {call.call_sid}\n")
                    f.write(f"Phone: {call.phone_number}\n")
                    f.write(f"Name: {call.caller_name or 'N/A'}\n")
                    f.write(f"Date: {call.initiated_at}\n")
                    f.write(f"Duration: {call.duration_seconds or 0} seconds\n")
                    f.write(f"Status: {call.status}\n")
                    f.write(f"\nConversation:\n")
                    f.write(f"-" * 30 + "\n")
                    
                    for conv in conversations:
                        if conv.text_content and conv.message_type == "text":
                            timestamp = conv.timestamp.strftime("%H:%M:%S")
                            speaker = conv.speaker.upper()
                            f.write(f"[{timestamp}] {speaker}: {conv.text_content}\n")
                
                print(f"   Exported: {filename}")
            
            print(f"✅ Exported {len(calls)} call transcripts to {export_dir}/")
            
    finally:
        await db_manager.close()


async def main():
    parser = argparse.ArgumentParser(description="Database Management for AI Voice Assistant")
    parser.add_argument("command", choices=[
        "migrate", "create-migration", "backup", "analytics", 
        "cleanup", "test", "seed", "export-transcripts"
    ], help="Command to run")
    
    parser.add_argument("--message", "-m", help="Migration message")
    parser.add_argument("--days", "-d", type=int, default=30, help="Days for cleanup/export")
    parser.add_argument("--call-sid", help="Specific call SID for export")
    
    args = parser.parse_args()
    
    try:
        if args.command == "migrate":
            await run_migrations()
        elif args.command == "create-migration":
            if not args.message:
                print("❌ Migration message required. Use --message 'description'")
                return
            await create_migration(args.message)
        elif args.command == "backup":
            await backup_database()
        elif args.command == "analytics":
            await get_analytics()
        elif args.command == "cleanup":
            await cleanup_old_data(args.days)
        elif args.command == "test":
            await test_connection()
        elif args.command == "seed":
            await seed_test_data()
        elif args.command == "export-transcripts":
            await export_call_transcripts(args.call_sid, args.days)
            
    except KeyboardInterrupt:
        print("\n❌ Operation cancelled")
    except Exception as e:
        print(f"❌ Error: {e}")


if __name__ == "__main__":
    asyncio.run(main()) 