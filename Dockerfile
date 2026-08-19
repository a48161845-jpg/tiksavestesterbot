# syntax=docker/dockerfile:1

# ============================================================================
# Стадия 1: собираем локальный Telegram Bot API сервер ИЗ ИСХОДНИКОВ.
#
# Раньше здесь брался готовый бинарник из community-образа — но он собран
# под другую libc (Alpine/musl), а этот проект работает на Debian/glibc, из-за
# чего бинарник вообще не запускался ("cannot execute: required file not
# found" — не находится нужный динамический линковщик). Чтобы такого не
# было в принципе, собираем бинарник сами, в ТОЙ ЖЕ базовой image, что и
# рантайм (python:3.12-slim) — гарантированно совместимая glibc.
#
# Сборка C++ занимает ощутимое время (обычно 10-25 минут на обычном CI/VPS) —
# это нормально, зато результат гарантированно запускается.
# ============================================================================
FROM python:3.12-slim AS tgapi-builder

RUN apt-get update && apt-get install -y --no-install-recommends \
        git \
        make \
        cmake \
        g++ \
        gperf \
        zlib1g-dev \
        libssl-dev \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /src
RUN git clone --depth=1 --recursive https://github.com/tdlib/telegram-bot-api.git

# -j2, а не -j$(nproc): сборка TDLib по некоторым единицам компиляции
# (td_api.cpp и т.п.) требует по 1.5-2 ГБ RAM НА КАЖДЫЙ параллельный
# процесс — на хостингах с ограниченной памятью для сборки (типа
# бесплатных/базовых планов Render) -j$(nproc) на многоядерной машине с
# небольшим RAM почти гарантированно падает с OOM. -j2 медленнее (сборка
# может занять 40-60+ минут), зато надёжно не падает по памяти. Если сборка
# идёт на машине с гарантированно большим RAM (8 ГБ+) — можно смело поднять.
RUN mkdir -p /src/telegram-bot-api/build \
    && cd /src/telegram-bot-api/build \
    && cmake -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX:PATH=/tgapi-out .. \
    && cmake --build . --target install -j2

# ============================================================================
# Стадия 2: основной образ с ботом — та же база (python:3.12-slim), поэтому
# бинарник из первой стадии гарантированно совместим по glibc.
# ============================================================================
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        curl \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY --from=tgapi-builder /tgapi-out/bin/telegram-bot-api /usr/local/bin/telegram-bot-api
RUN chmod +x /usr/local/bin/telegram-bot-api

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV LOCAL_BOT_API_DATA_PATH=/var/lib/telegram-bot-api
RUN mkdir -p ${LOCAL_BOT_API_DATA_PATH}

# По умолчанию локальный Bot API сервер слушает 127.0.0.1:8081 внутри этого
# же контейнера — наружу этот порт не пробрасываем, он не нужен снаружи.
ENV LOCAL_BOT_API_URL=http://127.0.0.1:8081

RUN chmod +x entrypoint.sh

ENTRYPOINT ["./entrypoint.sh"]
