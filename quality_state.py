"""
Состояние экрана выбора качества перед скачиванием YouTube/VK видео
(handlers/quality_callbacks.py). Ключ — req_id, не uid, по той же причине,
что и в picker_state.py: один пользователь может прислать несколько ссылок
подряд, и каждая должна открыть свой независимый пикер.
"""
import time
import uuid
from typing import Dict, Any, List

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from config import PENDING_TTL_SEC, LARGE_VIDEO_NO_AUDIO_MB
from youtube_provider import list_available_heights

quality_pending: Dict[str, Dict[str, Any]] = {}


def new_quality_req_id() -> str:
    return uuid.uuid4().hex[:12]


def cleanup_quality_pending() -> None:
    now = time.time()
    dead = [rid for rid, st in quality_pending.items() if now - float(st.get("ts", 0)) > PENDING_TTL_SEC]
    for rid in dead:
        quality_pending.pop(rid, None)


def quality_pick_kb(req_id: str, heights: List[int], *, offer_audio: bool = True, very_large_hint: bool = False) -> InlineKeyboardMarkup:
    rows: List[List[InlineKeyboardButton]] = []
    row: List[InlineKeyboardButton] = []
    for h in heights:
        label = f"{h}p"
        if h >= 2160:
            label = "4K"
        elif h >= 1440:
            label = "2K"
        row.append(InlineKeyboardButton(text=f"🎬 {label}", callback_data=f"yq:{req_id}:v{h}"))
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)

    # Для очень больших видео (по длительности/оценочному весу) кнопку
    # "только аудио" не показываем — см. LARGE_VIDEO_NO_AUDIO_MB в config.py:
    # вытаскивать звук из такого видео почти всегда не нужно и просто зря
    # грузит бота лишним скачиванием.
    if offer_audio and not very_large_hint:
        rows.append([InlineKeyboardButton(text="🎵 Только аудио", callback_data=f"yq:{req_id}:audio")])

    rows.append([InlineKeyboardButton(text="❌ Отмена", callback_data=f"yq:{req_id}:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
