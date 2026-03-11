# TCDD Ticket Bot

A Docker-containerized bot that monitors TCDD (Turkish State Railways) train ticket availability and sends Telegram notifications when economy seats become available.

## Features

- Monitors multiple dates via environment variable
- Telegram notifications for available seats
- Automatic retry with exponential backoff
- Sustained failure alerts and recovery notifications
- Structured logging with configurable log level

## Prerequisites

- Docker
- Docker Compose (optional)

## Quick Start

1. Copy the example environment file:
   ```bash
   cp .env.example .env
   ```

2. Edit `.env` with your credentials:
   - Telegram bot token and chat ID
   - TCDD API authorization tokens
   - Routes to monitor (e.g., ISTANBUL-KONYA,ANKARA-ISTANBUL)
   - Dates to monitor

3. Build and run:
   ```bash
   docker-compose up -d
   ```

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `ROUTES` | Yes | - | Comma-separated routes (e.g., ISTANBUL-KONYA,ANKARA-ISTANBUL) |
| `CHECK_DATES` | Yes | - | Comma-separated dates in DD-MM-YYYY format |
| `CHECK_INTERVAL` | No | 300 | Seconds between availability checks |
| `LOG_LEVEL` | No | INFO | Logging level (DEBUG, INFO, WARNING, ERROR) |
| `TELEGRAM_BOT_TOKEN` | Yes | - | Telegram bot token |
| `TELEGRAM_CHAT_ID` | Yes | - | Telegram chat ID for notifications |
| `USER_AUTHORIZATION` | Yes | - | TCDD API user authorization token |
| `AUTHORIZATION` | Yes | - | TCDD API authorization token |

## Available Routes

| Route | From | To |
|-------|------|------|
| ISTANBUL-KONYA | İstanbul (Pendik) | Konya (Selçuklu YHT) |
| ISTANBUL-ANKARA | Istanbul (Pendik) | Ankara (Gar) |
| ANKARA-ISTANBUL | Ankara (Gar) | Istanbul (Pendik) |
| ANKARA-KONYA | Ankara (Gar) | Konya (Selçuklu YHT) |
| KONYA-ISTANBUL | Konya (Selçuklu YHT) | Istanbul (Pendik) |
| KONYA-ANKARA | Konya (Selçuklu YHT) | Ankara (Gar) |

**Note:** This bot only monitors **YHT** (High Speed Train) routes.

## Docker Compose Deployment

```bash
# Build and start
docker-compose up -d

# View logs
docker-compose logs -f

# Stop
docker-compose down
```

## Standalone Docker Run

```bash
# Build
docker build -t tcdd-bot .

# Run
docker run -d \
  --name tcdd-bot \
  -e ROUTES="ISTANBUL-KONYA,ANKARA-ISTANBUL" \
  -e CHECK_DATES="21-03-2026,22-03-2026" \
  -e TELEGRAM_BOT_TOKEN="your_token" \
  -e TELEGRAM_CHAT_ID="your_chat_id" \
  -e USER_AUTHORIZATION="your_auth" \
  -e AUTHORIZATION="your_auth" \
  tcdd-bot

# View logs
docker logs -f tcdd-bot

# Stop
docker stop tcdd-bot
```

## Troubleshooting

### Bot exits immediately
- Check that `CHECK_DATES` is set and contains valid dates
- Ensure dates are not in the past
- Verify Telegram credentials are correct

### No notifications received
- Verify `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` are correct
- Check logs for Telegram API errors

### API connection failures
- Check network connectivity
- Verify TCDD API tokens are not expired
- Check logs for specific error messages
