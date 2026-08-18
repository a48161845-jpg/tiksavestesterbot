"""
Обработчик ссылок на Instagram (Reels/посты), VK (видео/клипы) и Pinterest
(видео-пины) — через тот же движок, что и YouTube (yt-dlp, см.
youtube_provider.py). Регистрируется раньше main_handler.py (см.
handlers/__init__.py), поэтому такие ссылки перехватываются здесь и не
долетают до TikTok-хендлера.

Важная честная оговорка: все три площадки отдают только ПУБЛИЧНЫЙ контент
без входа в аккаунт — закрытые профили, приватные посты и некоторые Reels
могут не скачаться. Это ограничение самих площадок, а не бота. Pinterest
вообще в основном картинки — видео-пины скачаются, обычные фото-пины нет
(это не видео, yt-dlp их не обрабатывает).
"""
import time
import contextlib
from pathlib import Path
from typing import Optional

from aiogram import F
from aiogram.types import Message

from globals_state import dp
from config import (
    MSG_DL,
    YOUTUBE_MAX_DURATION_SEC,
    LARGE_VIDEO_NO_AUDIO_BYTES,
)
from helpers import (
    html_escape,
    code,
    clamp_reason,
    exc_type_name,
    is_instagram,
    is_vk,
    is_pinterest,
    extract_other_source_url,
)
from storage import store
from user_label import resolve_user_label
from gates import gate_message
from limiters import lim, download_sem
from logging_channel import log_event, format_user_for_log
from strikes import add_download_strike
from youtube_provider import probe_media, list_available_heights
from external_send import download_and_send_with_quality
from quality_state import quality_pending, cleanup_quality_pending, new_quality_req_id, quality_pick_kb

PLATFORM_LABELS = {
    "instagram": ("📸", "Instagram"),
    "vk": ("🔵", "VK"),
    "pinterest": ("📌", "Pinterest"),
}


async def _log_err(bot, platform: str, stage: str, uid: int, label: str, url: str, e: Exception) -> None:
    with contextlib.suppress(Exception):
        store.inc_error(f"{platform}_{stage}", e)
    await log_event(
        bot,
        "dlerr",
        [
            f"❌ Категория: <b>Ошибка скачивания ({platform})</b>",
            f"👤 User/id: <b>{format_user_for_log(label, uid)}</b>",
            f"🧩 Стадия: <b>{html_escape(stage)}</b>",
            f"🧬 Тип: <b>{html_escape(exc_type_name(e))}</b>",
            f"🔗 Ссылка: {code(url)}",
            f"🧨 Причина: <b>{html_escape(clamp_reason(e))}</b>",
        ],
    )


def _detect_platform(text: str) -> Optional[str]:
    if is_instagram(text):
        return "instagram"
    if is_vk(text):
        return "vk"
    if is_pinterest(text):
        return "pinterest"
    return None


def _is_other_source_message(message: Message) -> bool:
    text = (message.text or "").strip()
    if not text or text.startswith("/"):
        return False
    return _detect_platform(text) is not None


@dp.message(F.text, _is_other_source_message)
async def other_sources_handler(message: Message):
    uid = message.from_user.id
    text = (message.text or "").strip()
    platform = _detect_platform(text) or "other"
    emoji, platform_name = PLATFORM_LABELS.get(platform, ("📎", "источника"))

    label = await resolve_user_label(message.bot, uid)
    store.set_user_label(uid, label)

    if not await gate_message(message, label):
        return

    store.register(uid)

    url = extract_other_source_url(text) or text

    ok_dl, wait_dl = lim.dl_hit(uid)
    if not ok_dl:
        await message.answer(MSG_DL.format(n=wait_dl))
        await add_download_strike(message.bot, uid, label, "Лимит скачиваний", src=url)
        return

    status = await message.answer(f"⏳ Смотрю {platform_name}…")
    tmp_path: Optional[Path] = None

    try:
        async with lim.user_dl_lock(uid), download_sem:
            try:
                info = await probe_media(url)
            except Exception as e:
                await _log_err(message.bot, platform, "probe", uid, label, url, e)
                with contextlib.suppress(Exception):
                    await status.edit_text(
                        f"❌ Не удалось получить видео с {platform_name}.\n"
                        "Возможно, пост закрытый/приватный или требует входа в аккаунт — "
                        "такое, увы, не скачать."
                    )
                return

            duration = int(info.get("duration") or 0)
            if YOUTUBE_MAX_DURATION_SEC and duration > YOUTUBE_MAX_DURATION_SEC:
                with contextlib.suppress(Exception):
                    await status.edit_text(
                        f"❌ Видео слишком длинное ({duration // 60} мин). "
                        f"Лимит: {YOUTUBE_MAX_DURATION_SEC // 60} мин."
                    )
                return

            # Выбор качества показываем только для VK (по требованию — как и
            # для YouTube). Instagram/Pinterest качаем как раньше, сразу.
            if platform == "vk":
                heights = list_available_heights(info)
                if heights:
                    best_h = heights[0]
                    est_size = 0
                    for f in info.get("formats") or []:
                        if f.get("height") == best_h:
                            est_size = max(est_size, f.get("filesize") or f.get("filesize_approx") or 0)
                    very_large = est_size > LARGE_VIDEO_NO_AUDIO_BYTES

                    cleanup_quality_pending()
                    req_id = new_quality_req_id()
                    quality_pending[req_id] = {
                        "url": url,
                        "uid": uid,
                        "label": label,
                        "info": info,
                        "platform": platform,
                        "emoji": emoji,
                        "ts": time.time(),
                    }
                    with contextlib.suppress(Exception):
                        await status.edit_text(
                            "🎚 <b>Выбери качество видео:</b>",
                            parse_mode="HTML",
                            reply_markup=quality_pick_kb(req_id, heights, very_large_hint=very_large),
                        )
                    return

            await download_and_send_with_quality(message, status, uid, label, url, info, platform, emoji)
            return

    finally:
        if tmp_path:
            with contextlib.suppress(Exception):
                tmp_path.unlink(missing_ok=True)
