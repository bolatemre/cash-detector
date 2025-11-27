import json
import logging
from confluent_kafka import Producer
from config.settings import settings

logger = logging.getLogger(__name__)


def get_kafka_producer():
    """
    Create and return a Kafka producer instance
    
    Returns:
        Producer: Kafka producer instance
    """
    conf = {
        'bootstrap.servers': settings.kafka_bootstrap_servers,
        'client.id': 'celery-worker',
        'acks': 'all',  # Wait for all replicas
        'retries': 3,
        'retry.backoff.ms': 100,
    }
    return Producer(conf)


def delivery_callback(err, msg):
    """
    Callback function for message delivery reports
    
    Args:
        err: Error object if delivery failed
        msg: Message object
    """
    if err:
        logger.error(f'Message delivery failed: {err}')
    else:
        logger.info(f'Message delivered to {msg.topic()} [{msg.partition()}] at offset {msg.offset()}')


def send_video_uploaded_event(camera_id: str, video_path: str, bucket_name: str = None, recording_started_at: str = None):
    """
    Send video uploaded event to Kafka
    
    Args:
        camera_id: Camera identifier
        video_path: Path to video in MinIO (object name)
        bucket_name: MinIO bucket name (optional)
        
    Returns:
        bool: True if message was successfully queued, False otherwise
    """
    try:
        producer = get_kafka_producer()
        
        # Prepare message payload
        message = {
            'camera_id': camera_id,
            'video_path': video_path,
            'bucket_name': bucket_name,
            'event_type': 'video_uploaded',
            'recording_started_at': recording_started_at
        }
        
        # Serialize message to JSON
        message_json = json.dumps(message)
        
        # Send message to Kafka
        topic = settings.kafka_uploaded_videos_topic
        logger.info(f"Sending video uploaded event to Kafka topic '{topic}': {message}")
        
        producer.produce(
            topic=topic,
            key=camera_id.encode('utf-8'),  # Use camera_id as key for partitioning
            value=message_json.encode('utf-8'),
            callback=delivery_callback
        )
        
        # Wait for message to be delivered (with timeout)
        producer.flush(timeout=10)
        
        logger.info(f"Video uploaded event sent successfully for camera {camera_id}")
        return True
        
    except Exception as e:
        logger.error(f"Error sending video uploaded event to Kafka: {e}", exc_info=True)
        return False

