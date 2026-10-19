import logging
import signal
import sys

from common.kafka_messages import PipelineStageEnvelope, StageName

from services.kafka_consumer import ConsumerFatalError, VideoConsumer
from services.classification_service import ClassificationService
from services.kafka_producer import ClassificationKafkaProducer
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
    
    kafka_producer = None
    exit_code = 0
    try:
        logger.info("Initializing Kafka consumer...")
        consumer = VideoConsumer()

        logger.info("Initializing Kafka producer...")
        kafka_producer = ClassificationKafkaProducer()

        logger.info("Initializing classification service (loading ML models)...")
        classification_service = ClassificationService(kafka_producer=kafka_producer)
        logger.info("Classification service initialized successfully")

        def process_video_callback(video_data):
            job = PipelineStageEnvelope.model_validate(video_data)
            stage_result = classification_service.classify_video_payload(job.model_dump(mode="json"))
            completion = job.with_completion(StageName.CLASSIFICATION, stage_result)
            if not kafka_producer.send_stage_result(completion):
                raise RuntimeError("Failed to send classification stage result")

        logger.info("Starting video classification service...")
        consumer.consume_videos(process_video_callback)

    except ConsumerFatalError as e:
        logger.error("Consumer failed fatally: %s", e, exc_info=True)
        exit_code = 1
    except RuntimeError as e:
        logger.error("CRITICAL: Service cannot start - %s", e, exc_info=True)
        logger.error("Please ensure all required ML models are available")
        exit_code = 1
    except Exception as e:
        logger.error("Fatal error in classification service: %s", e, exc_info=True)
        exit_code = 1
    finally:
        if kafka_producer:
            kafka_producer.close()
        logger.info("Classification service stopped")

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
