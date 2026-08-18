# syntax=docker/dockerfile:1

# ============================================================================
# Стадия 1: берём готовый бинарник локального Telegram Bot API сервера.
# Он нужен, чтобы снять стандартный лимит облачного Bot API (50 МБ на
# отправку / 20 МБ на приём) и поднять его почти до потолка самого Telegram
# (2000 МБ = 2 ГБ — выше нельзя никаким способом, это ограничение платформы).
# Собирать telegram-bot-api из исходников в этом же Dockerfile долго (это
# C++ проект с зависимостью от OpenSSL и занимает 10+ минут сборки), поэтому
# берём уже собранный бинарник из официально поддерживаемого community-образа.
# ============================================================================
FROM aiogram/telegram-bot-api:latest AS tgapi

# ============================================================================
# Стадия 2: основной образ с ботом.
# ============================================================================
FROM python:3.12-slim

# ffmpeg — нужен для склейки видео/аудио дорожек (yt-dlp) и конвертаций;
# ставим отдельно от pip-пакетов, т.к. это системный бинарник, не питон-пакет.
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        curl \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Бинарник локального Bot API сервера из первой стадии.
COPY --from=tgapi /usr/local/bin/telegram-bot-api /usr/local/bin/telegram-bot-api

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Каталог, куда локальный Bot API сервер складывает файлы (local mode) —
# бот читает/пишет туда напрямую с диска, без лишнего HTTP-хопа, это и есть
# основное ускорение аплоада больших файлов.
ENV LOCAL_BOT_API_DATA_PATH=/var/lib/telegram-bot-api
RUN mkdir -p ${LOCAL_BOT_API_DATA_PATH}

# По умолчанию локальный Bot API сервер слушает 127.0.0.1:8081 внутри этого
# же контейнера — наружу этот порт не пробрасываем, он не нужен снаружи.
ENV LOCAL_BOT_API_URL=http://127.0.0.1:8081

RUN chmod +x entrypoint.sh

ENTRYPOINT ["./entrypoint.sh"]
