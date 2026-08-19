# TikSaves Bot

Telegram-бот для скачивания видео/фото/музыки из TikTok (aiogram 3.29+).

## Запуск

```bash
pip install -r requirements.txt
cp .env.example .env   # заполни BOT_TOKEN
python bot.py
```

## Структура

```
tiksaves_bot/
├── bot.py                 # точка входа (main, polling)
├── config.py               # переменные окружения, константы
├── helpers.py                # HTML/даты/URL утилиты, парсинг длительности бана
├── storage.py                  # класс Storage (data.json) — пользователи, баны, страйки, статистика
├── admin_log_file.py             # текстовый лог-файл (admin.log)
├── logging_channel.py              # буферизованные логи в Telegram-канал + автосейв
├── user_label.py                     # resolve_user_label (имя/юзернейм для логов)
├── limiters.py                         # анти-флуд, лимит скачиваний/фото
├── strikes.py                            # страйки и авто-баны
├── gates.py                                # проверка бана + анти-флуд перед хендлерами
├── providers.py                              # TikWMClient / ApifyProvider / ProviderSwitcher
├── globals_state.py                            # общий Dispatcher (dp) и текущий provider
├── send_helpers.py                               # отправка фото-альбомов/видео/музыки
├── picker_state.py                                 # состояние фото-пикера
├── keyboards.py                                      # инлайн-клавиатуры и тексты UI
├── donate.py                                           # логика донатов / Stars-инвойсов
├── broadcast.py                                          # ручная и плановая рассылка
├── stats.py                                                # тексты статистики/топов
└── handlers/
    ├── __init__.py            # регистрирует все хендлеры на dp
    ├── commands.py              # /start /help /support /donate /admin /stats /top
    ├── admin_commands.py          # /ban /unban /banlist /baninfo /info /broadcast ...
    ├── strikes_commands.py          # /strikes /strikeadd /strikedel
    ├── admin_callbacks.py             # кнопки админ-панели (ad:*)
    ├── donate_callbacks.py              # кнопки донатов/Stars (dl:*, donate:*, stars:*)
    ├── help_callbacks.py                  # кнопки раздела помощи (help:*)
    ├── picker_callbacks.py                  # кнопки фото-пикера (pk:*)
    ├── video_choice_callbacks.py               # задел на выбор перед видео (vd:*, сейчас не используется)
    └── main_handler.py                           # основной catch-all обработчик ссылок
```

## Заметки

- `video_choice_callbacks.py` / `picker_state.pending_video` сохранены как есть из
  оригинала, но сейчас не используются: `main_handler` отправляет видео сразу,
  без промежуточного экрана выбора. Это не баг, просто незавершённая ветка функционала.
- Данные хранятся в `data.json` рядом с `bot.py` (создаётся автоматически).
- Для резервного провайдера скачивания установи `ALT_PROVIDER=apify` и `APIFY_TOKEN`
  в `.env` — но `ApifyProvider.get_media` потребует доработки (маппинг полей актора).

## Деплой через Dockerfile (файлы > 50 МБ, до 2 ГБ)

В репозитории есть `Dockerfile` — если хостинг (например Render) поддерживает
деплой через "Use own Dockerfile" / "Использовать собственный Dockerfile",
он используется вместо автоматически сгенерированного образа.

Контейнер поднимает **два** процесса: локальный Telegram Bot API сервер
(снимает лимит облачного API 50 МБ на отправку и 20 МБ на приём файлов,
поднимает его до 2000 МБ — это уже потолок самого Telegram, выше нельзя
никаким способом) и самого бота, который подключается к нему вместо
`api.telegram.org`.

Бинарник локального сервера собирается из исходников (TDLib) прямо в
Dockerfile — это гарантирует совместимость с базовым образом (раньше
пробовали брать готовый бинарник из community-образа, но он был собран под
другую libc и не запускался). Сборка C++ занимает время — рассчитывай на
30-60+ минут на первый деплой (кешируется при последующих, если хостинг
кеширует Docker-слои и `requirements.txt`/код бота не менялись).

Чтобы это заработало, нужно дополнительно задать в переменных окружения:

- `TELEGRAM_API_ID` и `TELEGRAM_API_HASH` — бесплатно на
  https://my.telegram.org/apps ("API development tools"). Это данные
  приложения для доступа к Telegram API, НЕ токен бота.

Если эти две переменные не заданы — бот сам определяет это и тихо
откатывается на обычный облачный Bot API с лимитом 50 МБ, ничего не падает.

`LOCAL_BOT_API_URL` уже прописан в `Dockerfile` (указывает на сервер внутри
того же контейнера) — трогать его не нужно.

