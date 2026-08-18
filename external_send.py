"""
Общая логика отправки видео из "внешних" источников — YouTube, Instagram,
VK, Pinterest. Все они идут через yt-dlp (youtube_provider.py) и после
скачивания ведут себя так же, как TikTok: видео с нейтральной подписью
(без имени/названия из исходного поста) + кнопки "🎵 Музыка" / "📝 Описание"
(по требованию, через video_extras/req_id), плюс Донат/Поделиться из той же
клавиатуры under_video_kb.
"""
import time
import random
import contextlib
from pathlib import Path
from typing import Any, Dict, Optional

from aiogram.types import Message, FSInputFile

from config import (
    CAPTION_VIDEO,
    CAPTION_AUDIO,
    LARGE_VIDEO_NO_AUDIO_BYTES,
    YOUTUBE_MAX_VIDEO_BYTES,
    YOUTUBE_MAX_VIDEO_MB,
    DOWNLOADING_MESSAGES,
    SENDING_MESSAGES,
)
from helpers import normalize_description, html_escape, code, clamp_reason, exc_type_name
from storage import store
from picker_state import video_extras, new_req_id, cleanup_video_extras
from keyboards import under_video_kb
from youtube_provider import has_audio_track, download_youtube, download_audio_only
from logging_channel import log_event, format_user_for_log
from referral import after_download_hooks


async def send_external_video(
    message: Message,
    uid: int,
    label: str,
    tmp_path: Path,
    info: Dict[str, Any],
    dl_info: Dict[str, Any],
    emoji: str,
    source: str = "youtube",
) -> None:
    """Отправляет скачанное видео с кнопками Музыка/Описание/Донат и учитывает статистику/рефералку."""
    description = normalize_description(dl_info.get("description") or info.get("description"))
    has_music = has_audio_track(dl_info) or has_audio_track(info)

    # Для очень больших видео не предлагаем отдельно вытащить звук — см.
    # комментарий у LARGE_VIDEO_NO_AUDIO_BYTES в config.py.
    try:
        file_size = tmp_path.stat().st_size
    except Exception:
        file_size = 0
    if file_size > LARGE_VIDEO_NO_AUDIO_BYTES:
        has_music = False

    src = dl_info.get("webpage_url") or info.get("webpage_url") or ""

    req_id = new_req_id()
    cleanup_video_extras()
    if has_music or description:
        video_extras[req_id] = {
            # Для внешних источников звук не берём прямой CDN-ссылкой (у многих
            # площадок, особенно VK, она требует спец-заголовков, без которых
            # скачивание падает или приходит битым) — вместо этого при нажатии
            # кнопки качаем звук заново через yt-dlp (см. music_mode).
            "music": src if has_music else None,
            "music_mode": "ytdlp_external",
            "description": description,
            "src": src,
            "uid": uid,
            "ts": time.time(),
        }

    # Без имени/названия исходного поста — единый вид подписи, как у TikTok.
    caption = CAPTION_VIDEO
    kb = under_video_kb(has_music=has_music, has_description=bool(description), req_id=req_id)

    try:
        await message.answer_video(FSInputFile(tmp_path), caption=caption, parse_mode="HTML", reply_markup=kb)
    except Exception:
        # Иногда попадается кодек/контейнер, который Telegram не принимает
        # как "видео" — на такой случай шлём документом, чтобы человек
        # всё равно получил файл (кнопки при этом сохраняются).
        await message.answer_document(FSInputFile(tmp_path), caption=caption, parse_mode="HTML", reply_markup=kb)

    store.inc_download(uid, "video", items=1, source=source)
    await after_download_hooks(message.bot, uid, label)


async def _log_ext_err(bot, platform: str, stage: str, uid: int, label: str, url: str, e: Exception) -> None:
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


async def download_and_send_with_quality(
    message: Message,
    status: Message,
    uid: int,
    label: str,
    url: str,
    info: Dict[str, Any],
    platform: str,
    emoji: str,
    *,
    max_height: Optional[int] = None,
    audio_only: bool = False,
) -> None:
    """Качает видео (в выбранном качестве) или только звук и отправляет —
    общий хвост для пикера качества (handlers/quality_callbacks.py) и для
    обычного потока без выбора (если у видео вообще нет доступных высот)."""
    out_dir = Path(".")
    tmp_path: Optional[Path] = None

    with contextlib.suppress(Exception):
        await status.edit_text(random.choice(DOWNLOADING_MESSAGES))

    try:
        if audio_only:
            tmp_path = await download_audio_only(url, out_dir)
        elif max_height is not None:
            tmp_path, dl_info = await download_youtube(url, out_dir, max_height=max_height)
        else:
            tmp_path, dl_info = await download_youtube(url, out_dir)
    except Exception as e:
        await _log_ext_err(message.bot, platform, "download", uid, label, url, e)
        with contextlib.suppress(Exception):
            await status.edit_text("❌ Не получилось скачать это видео. Попробуй другую ссылку/качество.")
        return

    try:
        size = tmp_path.stat().st_size if tmp_path.exists() else 0
        if size <= 0:
            with contextlib.suppress(Exception):
                await status.edit_text("❌ Скачанный файл пустой. Попробуй ещё раз.")
            return
        if size > YOUTUBE_MAX_VIDEO_BYTES:
            with contextlib.suppress(Exception):
                await status.edit_text(f"❌ Файл больше лимита ({YOUTUBE_MAX_VIDEO_MB} МБ). Попробуй качество пониже.")
            return

        with contextlib.suppress(Exception):
            await status.edit_text(random.choice(SENDING_MESSAGES))

        try:
            if audio_only:
                await message.answer_audio(FSInputFile(tmp_path), caption=CAPTION_AUDIO, parse_mode="HTML")
                store.inc_audio(uid, 1)
                await after_download_hooks(message.bot, uid, label)
            else:
                await send_external_video(message, uid, label, tmp_path, info, dl_info, emoji=emoji, source=platform)
        except Exception as e:
            await _log_ext_err(message.bot, platform, "send", uid, label, url, e)
            with contextlib.suppress(Exception):
                await status.edit_text(
                    "❌ Telegram отклонил файл — скорее всего, он слишком большой "
                    "для отправки ботом (обычный лимит Telegram — 50 МБ на файл)."
                )
            return

        with contextlib.suppress(Exception):
            await status.delete()
    finally:
        if tmp_path:
            with contextlib.suppress(Exception):
                tmp_path.unlink(missing_ok=True)
