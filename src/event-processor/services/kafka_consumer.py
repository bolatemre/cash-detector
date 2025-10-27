import json
import logging
from kafka import KafkaConsumer
from kafka.errors import KafkaError
from typing import Callable
from config.settings import settings

logger = logging.getLogger(__name__)


class EventConsumer:
    """Kafka consumer for receiving security events"""
    
    def __init__(self):
        self.consumer = None
        self.running = False
        
    def connect(self):
        """Establish connection to Kafka"""
        try:
            self.consumer = KafkaConsumer(
                settings.kafka_topic,
                bootstrap_servers=settings.kafka_bootstrap_servers.split(','),
                group_id=settings.kafka_group_id,
                auto_offset_reset='earliest',
                enable_auto_commit=True,
                value_deserializer=lambda m: json.loads(m.decode('utf-8')),
                max_poll_records=10,
                session_timeout_ms=30000,
                heartbeat_interval_ms=10000
            )
            logger.info(f"Connected to Kafka topic: {settings.kafka_topic}")
            return True
        except KafkaError as e:
            logger.error(f"Failed to connect to Kafka: {e}")
            return False
    
    def consume_events(self, callback: Callable):
        """
        Consume events from Kafka and process them using callback
        
        Args:
            callback: Function to process each event message
        """
        if not self.consumer:
            if not self.connect():
                logger.error("Cannot start consuming - connection failed")
                return
        
        self.running = True
        logger.info("Starting to consume events...")
        
        try:
            for message in self.consumer:
                if not self.running:
                    break
                
                try:
                    event_data = message.value
                    logger.info(f"Received event: {event_data.get('event_type', 'unknown')} "
                              f"from camera {event_data.get('camera_id', 'unknown')}")
                    
                    # Process the event using callback
                    callback(event_data)
                    
                except Exception as e:
                    logger.error(f"Error processing message: {e}", exc_info=True)
                    # Continue processing other messages
                    
        except KeyboardInterrupt:
            logger.info("Received interrupt signal")
        except Exception as e:
            logger.error(f"Error in consumer loop: {e}", exc_info=True)
        finally:
            self.close()
    
    def close(self):
        """Close Kafka consumer connection"""
        self.running = False
        if self.consumer:
            logger.info("Closing Kafka consumer...")
            self.consumer.close()
            self.consumer = None
    
    def stop(self):
        """Stop consuming events"""
        self.running = False

