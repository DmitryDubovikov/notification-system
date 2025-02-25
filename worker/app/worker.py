import json
import logging
import os
import time
import pika
from pika.exceptions import AMQPConnectionError
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

# Настройка логирования
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class NotificationWorker:
    """
    Обработчик уведомлений из очереди RabbitMQ
    """

    def __init__(self):
        self.connection = None
        self.channel = None
        self.queue_name = os.getenv("RABBITMQ_QUEUE", "notifications")

        # Email настройки
        self.smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        self.smtp_user = os.getenv("SMTP_USER", "")
        self.smtp_password = os.getenv("SMTP_PASSWORD", "")
        self.email_sender = os.getenv("EMAIL_SENDER", "notifications@example.com")

        # Подключение к RabbitMQ
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

                # Устанавливаем prefetch_count=1, чтобы не перегружать worker
                self.channel.basic_qos(prefetch_count=1)

                logger.info("Successfully connected to RabbitMQ")
                return

            except AMQPConnectionError as e:
                retry_count += 1
                wait_time = 2**retry_count  # Экспоненциальная задержка
                logger.warning(f"Failed to connect to RabbitMQ (attempt {retry_count}/{max_retries}): {str(e)}")
                logger.info(f"Retrying in {wait_time} seconds...")
                time.sleep(wait_time)

        raise Exception("Failed to connect to RabbitMQ after multiple attempts")

    def start_consuming(self):
        """
        Начать прослушивание очереди
        """
        logger.info(f"Starting to consume messages from queue: {self.queue_name}")

        try:
            # Регистрируем функцию обратного вызова
            self.channel.basic_consume(
                queue=self.queue_name,
                on_message_callback=self.process_notification,
                auto_ack=False,  # Не отправляем автоматическое подтверждение
            )

            # Начинаем слушать очередь
            logger.info("Waiting for notifications. To exit press CTRL+C")
            self.channel.start_consuming()

        except KeyboardInterrupt:
            logger.info("Interrupted by user, shutting down...")
            self.stop_consuming()
        except Exception as e:
            logger.error(f"Error consuming messages: {str(e)}")
            self.stop_consuming()
            raise

    def process_notification(self, ch, method, properties, body):
        """
        Обработка полученного уведомления
        """
        try:
            # Парсим JSON сообщение
            notification = json.loads(body)
            notification_id = notification.get("id", "unknown")

            logger.info(f"Processing notification: {notification_id}")

            # Логируем детали уведомления
            self.log_notification(notification)

            # Обрабатываем в зависимости от приоритета
            priority = notification.get("priority", "normal")
            if priority == "high":
                # Высокий приоритет - отправляем по электронной почте
                self.send_email_notification(notification)
            elif priority == "normal":
                # Нормальный приоритет - записываем в журнал и возможно отправляем по email
                logger.info(f"Normal priority notification: {notification_id}")
                # Можно добавить дополнительную логику здесь
            else:
                # Низкий приоритет - только запись в журнал
                logger.info(f"Low priority notification logged: {notification_id}")

            # Подтверждаем обработку сообщения
            ch.basic_ack(delivery_tag=method.delivery_tag)
            logger.info(f"Notification {notification_id} processed successfully")

        except json.JSONDecodeError:
            logger.error(f"Failed to parse notification: {body}")
            # Отклоняем сообщение, оно вернется в очередь
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
        except Exception as e:
            logger.error(f"Error processing notification: {str(e)}")
            # В случае ошибки, возвращаем сообщение в очередь
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)

    def log_notification(self, notification):
        """
        Логирование уведомления
        """
        logger.info(f"Notification {notification.get('id')}: {notification.get('subject')}")
        logger.debug(f"Full notification data: {notification}")

    def send_email_notification(self, notification):
        """
        Отправка уведомления по электронной почте
        """
        # Если SMTP не настроен, просто логируем
        if not self.smtp_user or not self.smtp_password:
            logger.warning("SMTP not configured, skipping email notification")
            return

        try:
            # Создаем сообщение
            msg = MIMEMultipart()
            msg["From"] = self.email_sender
            msg["To"] = ", ".join(notification.get("recipients", []))
            msg["Subject"] = notification.get("subject", "Notification")

            # Добавляем тело сообщения
            body = notification.get("message", "No message content")
            msg.attach(MIMEText(body, "plain"))

            # Отправляем email
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_user, self.smtp_password)
                server.send_message(msg)

            logger.info(f"Email notification sent to {len(notification.get('recipients', []))} recipients")

        except Exception as e:
            logger.error(f"Failed to send email notification: {str(e)}")
            raise

    def stop_consuming(self):
        """
        Остановка прослушивания очереди и закрытие соединений
        """
        if self.channel:
            self.channel.stop_consuming()

        if self.connection and self.connection.is_open:
            self.connection.close()

        logger.info("Worker stopped")


if __name__ == "__main__":
    worker = NotificationWorker()
    worker.start_consuming()
