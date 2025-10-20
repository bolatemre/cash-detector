#!/usr/bin/env python3
"""
Security System - Event Processing Service

This service consumes events from Kafka, stores them in PostgreSQL,
and sends email notifications for suspicious activities.
"""

import logging
import signal
import sys
from database import SessionLocal
from services.kafka_consumer import EventConsumer
from services.notifications import NotificationService
from services.event_processor import EventProcessor
from services.minio_service import MinioService
from config.settings import settings
from alembic.config import Config
from alembic import command

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('event_processor.log')
    ]
)

logger = logging.getLogger(__name__)

# Global consumer instance for signal handling
consumer_instance = None


def signal_handler(signum, frame):
    """Handle shutdown signals gracefully"""
    logger.info(f"Received signal {signum}, shutting down...")
    if consumer_instance:
        consumer_instance.stop()
    sys.exit(0)


def main():
    """Main entry point for the event processing service"""
    global consumer_instance
    
    logger.info("Starting Security System - Event Processing Service")
    logger.info(f"Kafka Topic: {settings.kafka_topic}")
    logger.info(f"Database: {settings.database_url.split('@')[1] if '@' in settings.database_url else 'configured'}")
    
    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        # Run database migrations
        logger.info("Running database migrations...")
        logger.info("Creating Alembic config...")
        alembic_cfg = Config("alembic.ini")
        logger.info("Alembic config created, running upgrade...")
        command.upgrade(alembic_cfg, "head")
        logger.info("Database migrations completed successfully")
        
        # Initialize services
        notification_service = NotificationService()
        minio_service = MinioService()
        consumer_instance = EventConsumer()
        
        logger.info("MinIO service initialized successfully")
        
        logger.info(f"Notification channels available: {notification_service.get_available_channels()}")
        logger.info(f"Notification channels enabled: {notification_service.get_enabled_channels()}")
        
        # Create event processor callback
        def process_event_callback(event_data: dict):
            """Callback function to process each event"""
            db_session = SessionLocal()
            try:
                processor = EventProcessor(db_session, notification_service, minio_service)
                processor.process_event(event_data)
            finally:
                db_session.close()
        
        # Start consuming events
        logger.info("Starting to consume events from Kafka...")
        consumer_instance.consume_events(process_event_callback)
        
    except Exception as e:
        logger.error(f"Fatal error in main: {e}", exc_info=True)
        sys.exit(1)
    finally:
        if consumer_instance:
            consumer_instance.close()
        logger.info("Event Processing Service stopped")


if __name__ == "__main__":
    main()

