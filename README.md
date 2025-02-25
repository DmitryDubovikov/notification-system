# notification-system

# Notification System

Простая масштабируемая система уведомлений с использованием FastAPI, RabbitMQ и асинхронного воркера.

## Архитектура

Система состоит из следующих компонентов:

- **FastAPI** - API для приема HTTP-запросов с уведомлениями
- **RabbitMQ** - Очередь сообщений для хранения и передачи уведомлений
- **Worker** - Обработчик уведомлений из очереди

## Функционал

- Создание уведомлений через API
- Асинхронная обработка уведомлений
- Отправка уведомлений по email (для высокоприоритетных)
- Логирование всех уведомлений
- Различные уровни приоритета уведомлений (low, normal, high)

## Запуск

### Через Docker Compose

```bash
docker-compose up -d
```

Это запустит все необходимые сервисы.

### Настройка переменных окружения

Перед запуском отредактируйте файл `docker-compose.yml` и укажите:

- SMTP настройки для отправки email уведомлений
- Учетные данные RabbitMQ (по умолчанию используются guest/guest)

## API Endpoints

### Создание уведомления

```
POST /notifications/
```

Пример запроса:

```json
{
  "subject": "New Update Available",
  "message": "A new version of the app is available. Please update to the latest version.",
  "recipients": [
    "user1@example.com",
    "user2@example.com"
  ],
  "priority": "high"
}

```

### Проверка работоспособности API

```
GET /health
```

## Мониторинг RabbitMQ

RabbitMQ Management UI доступен по адресу `http://localhost:15672`

- Логин: guest
- Пароль: guest

## Расширение функционала

