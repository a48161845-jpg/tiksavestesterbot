# syntax=docker/dockerfile:1

# ============================================================================
# Telegram Bot API
# ============================================================================
FROM aiogram/telegram-bot-api:latest AS tgapi

# ============================================================================
# Основной образ бота
# ============================================================================
FROM python:3.12-slim

ENV DEBIAN_FRONTEND=noninteractive

# Системные зависимости
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    ca-certificates \
    libstdc++6 \
    libgcc-s1 \
    libc6 \
    openssl \
    && rm -rf /var/lib/apt/lists/*

# ============================================================================
# Telegram Bot API
# ============================================================================

COPY --from=tgapi /usr/local/bin/telegram-bot-api /usr/local/bin/telegram-bot-api

RUN chmod +x /usr/local/bin/telegram-bot-api

# Проверяем бинарник во время сборки
RUN echo "=== Telegram Bot API binary ===" && \
    ls -lah /usr/local/bin/telegram-bot-api && \
    file /usr/local/bin/telegram-bot-api && \
    echo "=== Dynamic libraries ===" && \
    ldd /usr/local/bin/telegram-bot-api || true && \
    echo "=== Architecture ===" && \
    uname -m

# ============================================================================
# Приложение
# ============================================================================

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# ============================================================================
# Local Bot API storage
# ============================================================================

ENV LOCAL_BOT_API_DATA_PATH=/var/lib/telegram-bot-api

RUN mkdir -p /var/lib/telegram-bot-api

# ============================================================================
# Local Bot API URL
# ============================================================================

ENV LOCAL_BOT_API_URL=http://127.0.0.1:8081

# ============================================================================
# Entrypoint
# ============================================================================

RUN chmod +x /app/entrypoint.sh

ENTRYPOINT ["/app/entrypoint.sh"]

# JavaScript runtime required by modern yt-dlp YouTube extraction
RUN curl -fsSL https://deno.land/install.sh | sh \
    && ln -sf /root/.deno/bin/deno /usr/local/bin/deno
