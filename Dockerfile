# syntax=docker/dockerfile:1

FROM python:3.12-slim

ENV DEBIAN_FRONTEND=noninteractive

# ============================================================================
# Системные зависимости
# ============================================================================

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    ca-certificates \
    git \
    cmake \
    g++ \
    make \
    pkg-config \
    libssl-dev \
    zlib1g-dev \
    gperf \
    file \
    && rm -rf /var/lib/apt/lists/*

# ============================================================================
# Telegram Bot API
# ============================================================================

WORKDIR /tmp

RUN git clone --recursive --depth 1 \
    https://github.com/tdlib/telegram-bot-api.git

WORKDIR /tmp/telegram-bot-api

RUN mkdir build && \
    cd build && \
    cmake -DCMAKE_BUILD_TYPE=Release .. && \
    cmake --build . --target telegram-bot-api -j2 && \
    cp telegram-bot-api /usr/local/bin/telegram-bot-api

RUN chmod +x /usr/local/bin/telegram-bot-api && \
    file /usr/local/bin/telegram-bot-api && \
    /usr/local/bin/telegram-bot-api --version

# ============================================================================
# Python-бот
# ============================================================================

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# ============================================================================
# Local Telegram Bot API
# ============================================================================

ENV LOCAL_BOT_API_DATA_PATH=/var/lib/telegram-bot-api
ENV LOCAL_BOT_API_URL=http://127.0.0.1:8081

RUN mkdir -p /var/lib/telegram-bot-api && \
    chmod +x /app/entrypoint.sh

# ============================================================================
# Запуск
# ============================================================================

ENTRYPOINT ["/app/entrypoint.sh"]
