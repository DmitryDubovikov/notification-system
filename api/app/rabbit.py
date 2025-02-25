import json
import logging
import pika
from pika.exceptions import AMQPConnectionError
import os
import time
from typing import Dict, Any

logger = logging.getLogger(__name__)


class RabbitMQClient:
    """
    Клиент для работы с RabbitMQ
    """

    def __init__(self):
        self.connection = None
        self.channel = None
        self.queue_name = os.getenv("RABBITMQ_QUEUE", "notifications")
        self.connect()

    def connect(self):
        """
        Установка соединения с RabbitMQ с повторными попытками
        """
        rabbitmq_host = os.getenv("RABBITMQ_HOST", "rabbitmq")
        rabbitmq_user = os.getenv("RABBITMQ_USER", "guest")
        rabbitmq_password = os.getenv("RABBITMQ_PASSWORD", "guest")

        max_retries = 5
        retry_count = 0

        while retry_count < max_retries:
            try:
                credentials = pika.PlainCredentials(rabbitmq_user, rabbitmq_password)
                parameters = pika.ConnectionParameters(
                    host=rabbitmq_host, credentials=credentials, heartbeat=600, blocked_connection_timeout=300
                )

                self.connection = pika.BlockingConnection(parameters)
                self.channel = self.connection.channel()

                # Объявляем очередь (создаем, если не существует)
                self.channel.queue_declare(
                    queue=self.queue_name, durable=True  # Очередь сохраняется при перезапуске RabbitMQ
                )

                logger.info("Successfully connected to RabbitMQ")
                return

            except AMQPConnectionError as e:
                retry_count += 1
                wait_time = 2**retry_count  # Экспоненциальная задержка
                logger.warning(f"Failed to connect to RabbitMQ (attempt {retry_count}/{max_retries}): {str(e)}")
                logger.info(f"Retrying in {wait_time} seconds...")
                time.sleep(wait_time)

        raise Exception("Failed to connect to RabbitMQ after multiple attempts")

    def send_notification(self, notification: Dict[str, Any]):
        """
        Отправка уведомления в очередь RabbitMQ
        """
        try:
            if not self.connection or self.connection.is_closed:
                self.connect()

            # Конвертируем словарь в JSON строку
            message_body = json.dumps(notification)

            # Отправляем сообщение в очередь
            self.channel.basic_publish(
                exchange="",
                routing_key=self.queue_name,
                body=message_body,
                properties=pika.BasicProperties(
                    delivery_mode=2, content_type="application/json"  # Делаем сообщение persistent
                ),
            )

            logger.info(f"Sent notification {notification.get('id')} to RabbitMQ queue")
            return True

        except Exception as e:
            logger.error(f"Error sending message to RabbitMQ: {str(e)}")
            raise

    def close(self):
        """
        Закрытие соединения с RabbitMQ
        """
        if self.connection and self.connection.is_open:
            self.connection.close()
            logger.info("RabbitMQ connection closed")
