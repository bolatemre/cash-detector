import logging
import signal
import sys
from services.kafka_consumer import VideoConsumer
from services.classification_service import ClassificationService
from config.settings import settings

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('/app/logs/classification-service.log')
    ]
)

logger = logging.getLogger(__name__)


def signal_handler(signum, frame):
    """Handle shutdown signals gracefully"""
    logger.info(f"Received signal {signum}, shutting down...")
    sys.exit(0)


def main():
    """Main entry point for classification service"""
    logger.info(f"Starting {settings.service_name} v{settings.service_version}")
    
    # Set up signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        # Initialize services
        logger.info("Initializing Kafka consumer...")
        consumer = VideoConsumer()
        
        logger.info("Initializing classification service (loading ML models)...")
        classification_service = ClassificationService()
        logger.info("Classification service initialized successfully")
        
        # Define callback function for processing videos
        def process_video_callback(video_data):
            classification_service.process_video(video_data)
        
        # Start consuming video upload events
        logger.info("Starting video classification service...")
        consumer.consume_videos(process_video_callback)
        
    except RuntimeError as e:
        logger.error(f"CRITICAL: Service cannot start - {e}", exc_info=True)
        logger.error("Please ensure all required ML models are available")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Fatal error in classification service: {e}", exc_info=True)
        sys.exit(1)
    finally:
        logger.info("Classification service stopped")


if __name__ == "__main__":
    main()
