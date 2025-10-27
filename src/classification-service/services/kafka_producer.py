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
        'client.id': 'classification-service',
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


def send_classification_event(camera_id: str, event_type: str, video_url: str = None, detected_at: str = None):
    """
    Send classification event to Kafka for event-processor to consume
    
    Args:
        camera_id: Camera identifier
        event_type: Type of event ('suspicious' or 'normal')
        video_url: Full URL to the video clip in MinIO (optional)
        detected_at: ISO timestamp when event was detected (optional, defaults to current time)
        
    Returns:
        bool: True if message was successfully queued, False otherwise
    """
    try:
        producer = get_kafka_producer()
        
        # Prepare message payload according to EventMessage schema
        message = {
            'event_type': event_type,
            'camera_id': camera_id,
            'detected_at': detected_at or __import__('datetime').datetime.utcnow().isoformat() + 'Z',
            'video_url': video_url
        }
        
        # Serialize message to JSON
        message_json = json.dumps(message)
        
        # Send message to Kafka
        topic = settings.kafka_security_events_topic
        logger.info(f"Sending classification event to Kafka topic '{topic}': {message}")
        
        producer.produce(
            topic=topic,
            key=camera_id.encode('utf-8'),  # Use camera_id as key for partitioning
            value=message_json.encode('utf-8'),
            callback=delivery_callback
        )
        
        # Wait for message to be delivered (with timeout)
        producer.flush(timeout=10)
        
        logger.info(f"Classification event sent successfully for camera {camera_id}")
        return True
        
    except Exception as e:
        logger.error(f"Error sending classification event to Kafka: {e}", exc_info=True)
        return False
