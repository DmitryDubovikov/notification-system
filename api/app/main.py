from fastapi import FastAPI, BackgroundTasks, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field, EmailStr
import uuid
from typing import Optional, List
from datetime import datetime
import logging
from .rabbit import RabbitMQClient

# Настройка логирования
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="Notification Service API")

# Настройка CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Модели данных
class NotificationBase(BaseModel):
    subject: str
    message: str
    recipients: List[EmailStr]
    priority: str = Field(default="normal", description="Priority: low, normal, high")


class NotificationCreate(NotificationBase):
    pass


class Notification(NotificationBase):
    id: str
    created_at: datetime
    status: str = "pending"


# Зависимость для RabbitMQ клиента
def get_rabbitmq():
    client = RabbitMQClient()
    try:
        yield client
    finally:
        client.close()


@app.post("/notifications/", response_model=Notification, status_code=202)
async def create_notification(
    notification: NotificationCreate,
    background_tasks: BackgroundTasks,
    rabbitmq: RabbitMQClient = Depends(get_rabbitmq),
):
    """
    Создать новое уведомление и отправить его в очередь RabbitMQ
    """
    # Создаем ID для уведомления
    notification_id = str(uuid.uuid4())

    # Создаем полное уведомление с метаданными
    full_notification = Notification(id=notification_id, created_at=datetime.now(), **notification.dict())

    # Преобразуем уведомление в JSON-совместимый формат
    notification_dict = jsonable_encoder(full_notification)

    try:
        # Отправляем уведомление в RabbitMQ
        rabbitmq.send_notification(notification_dict)
        logger.info(f"Notification {notification_id} sent to queue")
        return full_notification
    except Exception as e:
        logger.error(f"Failed to send notification to queue: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to process notification")



@app.get("/health")
def health_check():
    """
    Проверка работоспособности API
    """
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
