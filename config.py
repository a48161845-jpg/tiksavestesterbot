"""
Конфигурация бота: переменные окружения, константы, логгер.
"""
import os
import re
import logging
from pathlib import Path
from datetime import timezone
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

# ================== CONFIG ==================
ENV_PATH = Path(__file__).with_name(".env")
load_dotenv(dotenv_path=ENV_PATH, override=True)

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
if not BOT_TOKEN:
    raise RuntimeError("❌ BOT_TOKEN не найден. Добавь BOT_TOKEN в .env рядом с bot.py")
if not re.match(r"^\d+:[A-Za-z0-9_-]{30,}$", BOT_TOKEN):
    raise RuntimeError("❌ BOT_TOKEN имеет неверный формат. Проверь токен в .env")

# База данных (PostgreSQL на Render)
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
# Render даёт postgres://, asyncpg требует postgresql://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = "postgresql://" + DATABASE_URL[len("postgres://"):]

# Путь к JSON для первичной миграции данных (если файл существует — мигрируем)
DATA_FILE = Path("data.json")

API_URL = "https://tikwm.com/api/"
ADMINS = {7233257134}  # <-- твой Telegram ID

ADMIN_LOG_FILE = Path("admin.log")

SUPPORT_USERNAME = "@tiksavesbotsupport"
try:
    MSK_TZ = ZoneInfo("Europe/Moscow")
except Exception:
    MSK_TZ = timezone.utc

# Канал для логов (бот должен быть админом канала)
LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID", "-1003763229922"))

# Технический канал ТОЛЬКО для получения file_id при кэшировании inline-режима
# (см. handlers/inline_handler.py). ОБЯЗАТЕЛЬНО отдельный от LOG_CHANNEL_ID —
# туда не должны попадать все скачанные через инлайн видео/фото, это не
# журнал действий, просто техническое хранилище для повторного использования
# уже скачанного файла без повторного скачивания. Если не задан (0) —
# инлайн-режим просто не кэширует и не будет мгновенно отвечать на повторные
# запросы (каждый раз качает заново).
INLINE_CACHE_CHANNEL_ID = int(os.getenv("INLINE_CACHE_CHANNEL_ID", "0"))

# ========= ЛОКАЛЬНЫЙ TELEGRAM BOT API SERVER (для файлов >50 МБ) =========
# Обычный облачный Bot API (api.telegram.org) ограничивает отправку файлов
# 50 МБ и скачивание входящих файлов — 20 МБ, независимо от кода бота, это
# ограничение самого облачного API. Единственный способ поднять лимит —
# поднять собственный локальный Bot API сервер (Telegram сам его
# предоставляет как open source), который позволяет файлы до 2000 МБ
# (2 ГБ — это уже жёсткий потолок самого Telegram, выше в принципе нельзя
# никаким способом). Сервер поднимается в том же контейнере, см. Dockerfile
# и entrypoint.sh. Если LOCAL_BOT_API_URL не задан — бот работает как раньше
# через облачный API с лимитом 50 МБ.
LOCAL_BOT_API_URL = os.getenv("LOCAL_BOT_API_URL", "").strip().rstrip("/")
# Локальный сервер, помимо прочего, умеет отдавать файлы боту напрямую с
# диска (local mode) — загрузка тогда идёт не через HTTP, а как чтение
# файла с той же файловой системы, это на порядок быстрее обычной отправки.
LOCAL_BOT_API_DATA_PATH = os.getenv("LOCAL_BOT_API_DATA_PATH", "/var/lib/telegram-bot-api").strip()

# Дефолтный лимит файла зависит от того, поднят ли локальный Bot API сервер:
# с ним лимит поднимается почти до потолка самого Telegram (2000 МБ / 2 ГБ),
# без него — стандартные 50 МБ облачного Bot API.
_DEFAULT_MAX_VIDEO_MB = "2000" if LOCAL_BOT_API_URL else "49"

TIKTOK_RE = re.compile(r"(https?://)?(www\.)?(tiktok\.com|vm\.tiktok\.com|vt\.tiktok\.com)/", re.I)

# ========= YOUTUBE =========
YOUTUBE_RE = re.compile(
    r"(https?://)?(www\.|m\.)?(youtube\.com/(watch\?|shorts/|live/)|youtu\.be/)", re.I
)

# ========= ДРУГИЕ ИСТОЧНИКИ (через тот же движок yt-dlp, что и YouTube) =========
# Работают только с ПУБЛИЧНЫМ контентом без логина — это ограничение самих
# площадок (закрытые профили/приватные посты без авторизации не скачать),
# а не бота.
INSTAGRAM_RE = re.compile(r"(https?://)?(www\.)?instagram\.com/(reel|reels|p|tv)/", re.I)
VK_RE = re.compile(r"(https?://)?(www\.|m\.)?(vk\.com|vk\.ru|vkvideo\.ru)/(video|clip)", re.I)
PINTEREST_RE = re.compile(r"(https?://)?(www\.)?(pinterest\.[a-z.]+/pin/|pin\.it/)", re.I)

# Ограничение по длительности видео (в секундах). Раньше стояло 1800 (30 мин)
# как искусственный потолок бота, никак не связанный с самим Telegram —
# убрано по просьбе: 0 = лимита нет (проверка ниже просто пропускается).
YOUTUBE_MAX_DURATION_SEC = int(os.getenv("YOUTUBE_MAX_DURATION_SEC", "0"))  # 0 = без лимита
# Для вертикальных Shorts yt-dlp репортит "height" как реальную высоту в
# пикселях (у "1080p"-шортса это 1920, а не 1080!) — если тут стоит 720,
# такие шортсы срезаются до огрызка качества. Ставим с запасом, чтобы
# доставало и обычным горизонтальным видео (720/1080p), и вертикальным Shorts.
YOUTUBE_MAX_HEIGHT = int(os.getenv("YOUTUBE_MAX_HEIGHT", "1920"))

# Обычный облачный Bot API не даёт боту отправлять файлы больше 50 МБ.
# С локальным Bot API сервером лимит поднимается до 2000 МБ (см. MAX_VIDEO_MB
# и комментарий там же).
YOUTUBE_MAX_VIDEO_MB = int(os.getenv("YOUTUBE_MAX_VIDEO_MB", _DEFAULT_MAX_VIDEO_MB))
YOUTUBE_MAX_VIDEO_BYTES = YOUTUBE_MAX_VIDEO_MB * 1024 * 1024

MEDIA_GROUP_LIMIT = 10
PAGE_SIZE = 10
PENDING_TTL_SEC = 300

# ========= DONATE =========
CRYPTO_DONATE_URL = os.getenv("CRYPTO_DONATE_URL", "").strip() or "https://t.me/send?start=IVba6SXTH9iy"
DONATIONALERTS_URL = os.getenv("DONATIONALERTS_URL", "").strip() or "https://dalink.to/tiksavesbot"
BOT_SHARE_URL = os.getenv("BOT_SHARE_URL", "").strip() or "https://t.me/tiksavesbot"
STARS_MIN = int(os.getenv("STARS_MIN", "1"))
STARS_MAX = int(os.getenv("STARS_MAX", "1000"))
WAITING_STARS_TTL_SEC = 120

# ========= GLOBAL LIMITS =========
# Сколько скачиваний могут обрабатываться параллельно (а не одно за другим).
# Раньше было = 1 (строгая очередь "один за раз, ~раз в минуту").
GLOBAL_CONCURRENCY = int(os.getenv("GLOBAL_CONCURRENCY", "8"))

# ========= SPAM LIMIT (тихий cooldown, без страйков) =========
EVENT_WINDOW_SEC = 15
EVENT_MAX = 8
SPAM_COOLDOWN_SEC = 60

# ========= DOWNLOAD LIMIT =========
DL_WINDOW_SEC = 60
DL_MAX_ACTIONS = 6

# ========= PHOTO VOLUME LIMIT =========
PHOTO_WINDOW_SEC = 60
PHOTO_LIMIT_PER_MIN = 120

# ========= AUTOSAVE =========
AUTO_SAVE_INTERVAL_SEC = 5  # автосинхронизация раз в N сек

# ========= DESCRIPTION (CAPTION TEXT) =========
# Если описание видео влезает в это ограничение — шлём сообщением,
# иначе — файлом (.txt), чтобы не обрезать текст.
DESCRIPTION_TG_LIMIT = 3500

# ========= VIDEO/AUDIO FALLBACK DOWNLOAD =========
# Обычный облачный Bot API не даёт боту отправлять файлы больше 50 МБ — это
# ограничение платформы, не бота. Если поднят локальный Bot API сервер
# (LOCAL_BOT_API_URL), лимит поднимается почти до потолка самого Telegram —
# 2000 МБ (2 ГБ), поэтому дефолт зависит от того, включён локальный сервер.
MAX_VIDEO_MB = int(os.getenv("MAX_VIDEO_MB", _DEFAULT_MAX_VIDEO_MB))
MAX_VIDEO_BYTES = MAX_VIDEO_MB * 1024 * 1024
MAX_AUDIO_MB = int(os.getenv("MAX_AUDIO_MB", "25"))
MAX_AUDIO_BYTES = MAX_AUDIO_MB * 1024 * 1024

# ========= API FALLBACK / HEALTH =========
API_ERROR_WINDOW_SEC = 120
API_ERROR_THRESHOLD = 6

# Варианты fallback: "none" | "apify"
ALT_PROVIDER = os.getenv("ALT_PROVIDER", "none").strip().lower()
APIFY_TOKEN = os.getenv("APIFY_TOKEN", "").strip()
APIFY_ACTOR = os.getenv("APIFY_ACTOR", "apilabs/tiktok-downloader").strip()

# Небольшая задержка между запросами к бесплатному tikwm API — чтобы не
# словить рейт-лимит/бан на их стороне при частых запросах.
TIKWM_COOLDOWN_SEC = float(os.getenv("TIKWM_COOLDOWN_SEC", "1.2"))

BAN_DURATION_SEC = int(os.getenv("BAN_DURATION_SEC", str(24 * 3600)))  # 24 часа по умолчанию
BAN_REASON_SPAM = "Авто-бан: спам/флуд"

# Подпись с указанием бота
CAPTION_PHOTO = (
    "✨ <b>Готово!</b> 🖼️\n"
    "Забирай — и приятного просмотра 😎\n\n"
    "📥 <i>Скачано в</i> @tiksavesbot"
)
CAPTION_VIDEO = (
    "✨ <b>Готово!</b> 🎬\n"
    "Без водяных знаков, как и должно быть 😉\n\n"
    "📥 <i>Скачано в</i> @tiksavesbot"
)
CAPTION_AUDIO = (
    "🎵 <b>Твой звук готов!</b>\n"
    "Сохраняй и слушай 🎧\n\n"
    "📥 <i>Скачано в</i> @tiksavesbot"
)

ALBUM_PAUSE_MIN = 0.4
ALBUM_PAUSE_MAX = 0.8

BROADCAST_DELAY_SEC = 0.35
BROADCAST_MAX_USERS = 5000
# Рассылка раньше слала сообщения строго по одному с паузой BROADCAST_DELAY_SEC
# между каждым — при 5000 получателей это ~30 минут. Telegram разрешает боту
# слать сообщения РАЗНЫМ пользователям с частотой около 30 в секунду, так что
# отправка пачками параллельно (с паузой между пачками) на порядок быстрее
# и всё ещё укладывается в этот лимит: 20 сообщений / 0.7 сек ≈ 28.5 msg/s.
BROADCAST_CONCURRENCY = int(os.getenv("BROADCAST_CONCURRENCY", "20"))
BROADCAST_CHUNK_DELAY_SEC = float(os.getenv("BROADCAST_CHUNK_DELAY_SEC", "0.7"))

PHOTO_WARNING_TEXT = (
    "⚠️ <b>Прежде чем скачать</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n\n"
    "Скачивай только свой контент или тот, на который у тебя есть разрешение автора.\n"
    "Уважай чужой труд 🙏"
)

MSG_SPAM = "🛡 <b>Слишком быстро!</b>\nПереведи дух ~{n} сек. и пробуй снова."
MSG_DL = "⏳ <b>Лимит скачиваний</b>\nПодожди ~{n} сек. — и продолжим."

# Видео тяжелее этого порога считаем "очень большим": отдельную кнопку
# "🎵 Музыка" (вытащить только звук) под ним не показываем — распаковка
# аудио-дорожки из многосотмегабайтного файла заново качает/перекодирует
# его ради результата, который почти никогда не нужен при таком размере
# исходника, и просто зря грузит бота.
LARGE_VIDEO_NO_AUDIO_MB = int(os.getenv("LARGE_VIDEO_NO_AUDIO_MB", "300"))
LARGE_VIDEO_NO_AUDIO_BYTES = LARGE_VIDEO_NO_AUDIO_MB * 1024 * 1024

# Статусные сообщения, которые видит пользователь во время скачивания —
# несколько вариантов на каждую стадию, чтобы бот не выглядел как робот,
# повторяющий одну и ту же фразу при каждом скачивании.
DOWNLOADING_MESSAGES = [
    "⬇️ Скачиваю видео…",
    "⏬ Тяну видео с сервера…",
    "📥 Загружаю файл…",
    "🎬 Забираю видео, секунду…",
    "⚙️ Обрабатываю ссылку и качаю видео…",
]
SENDING_MESSAGES = [
    "📤 Отправляю…",
    "🚀 Почти готово, отправляю файл…",
    "📨 Загружаю тебе в чат…",
    "✅ Готово, отправляю…",
    "📦 Упаковываю и отправляю…",
]
MSG_PHOTO = "📸 <b>Лимит по фото</b>\nПодожди ~{n} сек. — и продолжим."

# ========= РЕФЕРАЛЬНАЯ СИСТЕМА / МАГАЗИН ПОДАРКОВ =========
BOT_USERNAME = os.getenv("BOT_USERNAME", "tiksavesbot").strip().lstrip("@")
REF_POINTS_PER_REFERRAL = int(os.getenv("REF_POINTS_PER_REFERRAL", "10"))
REF_TOP_LIMIT = int(os.getenv("REF_TOP_LIMIT", "10"))

# Каталог подарков: ключ, эмодзи, название, цена в баллах.
# Выдаются вручную администрацией — тут только учёт заявок/баланса.
GIFTS = [
    {"key": "bear_santa",      "emoji": "🎅", "name": "Мишка-Санта",         "price": 60, "tg_id": "5956217000635139069"},
    {"key": "tree",            "emoji": "🎄", "name": "Новогодняя ёлка",      "price": 60, "tg_id": "5922558454332916696"},
    {"key": "bear_heart",      "emoji": "💕", "name": "Мишка с сердечком",    "price": 60, "tg_id": "5800655655995968830"},
    {"key": "heart_love",      "emoji": "💌", "name": "Сердце I LOVE U",      "price": 60, "tg_id": "5801108895304779062"},
    {"key": "bear_flowers",    "emoji": "🌹", "name": "Мишка с цветами",      "price": 60, "tg_id": "5866352046986232958"},
    {"key": "bear_leprechaun", "emoji": "🍀", "name": "Мишка-Лепрекон",       "price": 60, "tg_id": "5893356958802511476"},
    {"key": "bear_clown",      "emoji": "🤡", "name": "Мишка-Клоун",          "price": 60, "tg_id": "5935895822435615975"},
    {"key": "bear_rabbit",     "emoji": "🐰", "name": "Мишка-Заяц",           "price": 60, "tg_id": "5969796561943660080"},
    {"key": "bear_hammer",     "emoji": "🔨", "name": "Мишка с молотком",     "price": 60, "tg_id": "6026193266406327981"},
    {"key": "bear_ball",       "emoji": "⚽", "name": "Мишка с мячом",        "price": 60, "tg_id": "5974210632977745012"},
    {"key": "bear_gun",        "emoji": "🔫", "name": "Мишка с пистолетиком", "price": 60, "tg_id": "6046178578163303744"},
]
GIFTS_BY_KEY = {g["key"]: g for g in GIFTS}

# Цена подарка билетиками зафиксирована отдельно от цены звёздами (не
# gift['price'] * 10) — при повышении цены в звёздах билетики трогать не
# нужно.
GIFT_TICKET_PRICE = int(os.getenv("GIFT_TICKET_PRICE", "500"))

# Себестоимость подарка в звёздах (сколько реально стоит сам Telegram-подарок,
# который админ вручную отправляет пользователю). Разница между тем, что
# платит пользователь (gift['price']) и себестоимостью — уходит в бота как
# донат и учитывается в статистике донатов.
GIFT_COST_STARS = int(os.getenv("GIFT_COST_STARS", "50"))

# Канал для заявок на подарки / выдачи призов реферальной системы
# Сюда идят все запросы на покупку подарков (звёзды/билеты) на одобрение админу
REFERRAL_LOG_CHANNEL_ID = int(os.getenv("REFERRAL_LOG_CHANNEL_ID", "-1004333103786"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
log = logging.getLogger("tiktok_bot")
