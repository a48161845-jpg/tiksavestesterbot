#!/usr/bin/env bash
# Поднимает локальный Telegram Bot API сервер (для файлов до 2 ГБ) в фоне,
# ждёт пока он реально начнёт отвечать, и только потом запускает самого бота.
#
# TELEGRAM_API_ID / TELEGRAM_API_HASH обязательны для локального сервера —
# получить их можно на https://my.telegram.org/apps (это НЕ токен бота,
# а данные для доступа к Telegram API как приложение, выдаются бесплатно).
set -euo pipefail

if [[ -n "${TELEGRAM_API_ID:-}" && -n "${TELEGRAM_API_HASH:-}" ]]; then
    echo "[entrypoint] Запускаю локальный Telegram Bot API сервер…"

    # command -v только проверяет, что файл есть в PATH — а не то, что он
    # реально запускается (именно так сломалось в прошлый раз: бинарник был
    # на месте, но не мог исполниться из-за несовместимой libc). Поэтому
    # реально пробуем его запустить и смотрим код возврата: 126/127 —
    # классические коды "не могу исполнить" в bash.
    set +e
    telegram-bot-api --help >/dev/null 2>&1
    tgapi_check_rc=$?
    set -e

    if [[ $tgapi_check_rc -eq 126 || $tgapi_check_rc -eq 127 ]]; then
        echo "[entrypoint] ОШИБКА: бинарник telegram-bot-api не запускается (код $tgapi_check_rc)."
        echo "[entrypoint] Работаю через облачный Bot API (лимит файлов 50 МБ), чтобы бот хотя бы стартовал."
        unset LOCAL_BOT_API_URL
        echo "[entrypoint] Запускаю бота…"
        exec python3 bot.py
    fi

    telegram-bot-api \
        --api-id="${TELEGRAM_API_ID}" \
        --api-hash="${TELEGRAM_API_HASH}" \
        --local \
        --dir="${LOCAL_BOT_API_DATA_PATH:-/var/lib/telegram-bot-api}" \
        --http-port=8081 \
        &

    TGAPI_PID=$!

    # Ждём, пока сервер реально поднимется (до 30 сек), прежде чем стартовать
    # бота — иначе первое подключение бота упадёт с connection refused.
    for i in $(seq 1 30); do
        if curl -fsS "http://127.0.0.1:8081/" -o /dev/null 2>/dev/null; then
            echo "[entrypoint] Локальный Bot API сервер готов."
            break
        fi
        sleep 1
    done

    # Если сервер вдруг умрёт — роняем весь контейнер, чтобы платформа
    # (Render/Docker) перезапустила его, а не осталась молча без Bot API.
    ( wait "$TGAPI_PID"; echo "[entrypoint] telegram-bot-api неожиданно завершился!"; exit 1 ) &
else
    echo "[entrypoint] TELEGRAM_API_ID/TELEGRAM_API_HASH не заданы — работаю через облачный Bot API (лимит файлов 50 МБ)."
    unset LOCAL_BOT_API_URL
fi

echo "[entrypoint] Запускаю бота…"
exec python3 bot.py
