"""
Скачивание видео с YouTube через yt-dlp.

В отличие от TikTok-провайдеров (providers.py), тут нет отдельного "получить
ссылки" + "скачать по ссылке" — yt-dlp сам качает файл на диск за один вызов,
и делает это синхронно, поэтому каждый вызов заворачиваем в отдельный поток
(asyncio.to_thread), чтобы не блокировать event loop бота.
"""
import asyncio
import os
import shutil
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import yt_dlp

from config import YOUTUBE_MAX_HEIGHT


class YoutubeTooLargeError(Exception):
    """Итоговый файл больше допустимого лимита."""


def _find_ffmpeg() -> Optional[str]:
    """
    Ищет ffmpeg: сначала системный (если вдруг есть), потом — портативный
    бинарник из пакета imageio-ffmpeg (ставится через pip, ничего вручную
    в систему устанавливать не нужно — именно так чинили отсутствие ffmpeg
    на этом сервере).
    """
    system_path = shutil.which("ffmpeg")
    if system_path:
        return system_path
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


_FFMPEG_PATH: Optional[str] = _find_ffmpeg()

# С начала 2026 YouTube резко усилил анти-бот защиту: без явного указания
# "клиента" плеера yt-dlp то ловит 403 на скачивании, то отдаёт кривой/
# неполный список форматов (отсюда качества, которых на видео на самом деле
# нет). android/tv/web в таком порядке — по опыту сообщества yt-dlp сейчас
# самые стабильные комбинации, mweb — доп. фолбэк.
_PLAYER_CLIENTS = [c.strip() for c in os.getenv(
    "YT_DLP_PLAYER_CLIENTS", "android,tv,web,mweb"
).split(",") if c.strip()]

# Необязательный путь к файлу с cookies (формат Netscape, как экспортирует
# расширение "Get cookies.txt") — если задан, сильно снижает шанс 403 на
# возрастных/залогиненных видео. Указывается через .env: YT_DLP_COOKIES_FILE.
_COOKIES_FILE = os.getenv("YT_DLP_COOKIES_FILE", "").strip()


def _common_opts() -> Dict[str, Any]:
    opts: Dict[str, Any] = {
        "extractor_args": {"youtube": {"player_client": _PLAYER_CLIENTS}},
    }
    if _COOKIES_FILE and Path(_COOKIES_FILE).exists():
        opts["cookiefile"] = _COOKIES_FILE
    return opts


def _probe_sync(url: str) -> Dict[str, Any]:
    opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "skip_download": True,
        "socket_timeout": 20,
        **_common_opts(),
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
        if info is None:
            raise RuntimeError("yt-dlp: пустой ответ при получении информации о видео")
        return info


async def probe_youtube(url: str) -> Dict[str, Any]:
    """Узнаёт длительность/название и т.п. БЕЗ скачивания — чтобы отсечь слишком длинные видео заранее."""
    return await asyncio.to_thread(_probe_sync, url)


async def download_youtube(
    url: str, out_dir: Path, max_height: int = YOUTUBE_MAX_HEIGHT
) -> Tuple[Path, Dict[str, Any]]:
    """Качает видео на диск, возвращает путь к файлу и распарсенный info-dict yt-dlp."""
    info_holder: Dict[str, Any] = {}

    def _run() -> Path:
        out_template = str(out_dir / "%(id)s.%(ext)s")

        if _FFMPEG_PATH:
            # ffmpeg есть (системный или портативный из imageio-ffmpeg) —
            # можно склеивать отдельные видео/аудио-потоки, это даёт заметно
            # лучшее качество (особенно для вертикальных Shorts, где хорошие
            # потоки почти всегда раздельные, а не в одном файле).
            fmt = (
                f"bestvideo[height<={max_height}]+bestaudio/"
                f"best[height<={max_height}]/best"
            )
        else:
            # ffmpeg не нашёлся вообще нигде — склейка невозможна, берём
            # только уже готовые (video+audio в одном файле) форматы.
            fmt = f"best[ext=mp4][height<={max_height}]/best[height<={max_height}]/best"

        opts = {
            "format": fmt,
            "outtmpl": out_template,
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "nocheckcertificate": True,
            "socket_timeout": 20,
            "retries": 3,
            **_common_opts(),
            # ===== Ускорение скачивания =====
            # YouTube (и большинство других площадок через yt-dlp) отдают
            # видео фрагментами (DASH/HLS) — по умолчанию yt-dlp качает их
            # строго по одному. concurrent_fragment_downloads тянет сразу
            # несколько фрагментов параллельно, что на нормальном канале
            # даёт кратный прирост скорости, особенно на HD/FHD видео.
            #
            # ВАЖНО: http_chunk_size сюда специально НЕ добавляем — вместе с
            # concurrent_fragment_downloads это ломает скачивание с ошибкой
            # "Conflicting range" на форматах, которые отдаются одним URL
            # через псевдо-фрагментацию по Range-заголовкам (именно так и
            # было: несколько параллельных потоков путались в расчёте
            # диапазонов при ретраях). concurrent_fragment_downloads сам по
            # себе безопасен и работает для настоящих multi-URL фрагментов
            # (DASH/HLS) — именно на них и даёт прирост скорости.
            "concurrent_fragment_downloads": 4,
            "fragment_retries": 5,
            "retry_sleep_functions": {"http": lambda n: min(1 + n, 5)},
        }
        if _FFMPEG_PATH:
            opts["merge_output_format"] = "mp4"
            opts["ffmpeg_location"] = _FFMPEG_PATH

        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            info_holder.update(info or {})
            filename = ydl.prepare_filename(info)
            p = Path(filename)
            if not p.exists():
                candidate = p.with_suffix(".mp4")
                if candidate.exists():
                    p = candidate
            if not p.exists():
                raise RuntimeError(f"yt-dlp: итоговый файл не найден ({filename})")
            return p

    path = await asyncio.to_thread(_run)
    return path, info_holder


# Качества, которые предлагаем выбрать пользователю (кнопками) — сверяем
# с реально доступными у видео высотами и показываем только то, что есть.
QUALITY_CANDIDATES = [2160, 1440, 1080, 720, 480, 360, 240]


def list_available_heights(info: Dict[str, Any]) -> list:
    """Какие качества видео реально доступны (высоты в px), по данным пробы.
    Возвращает отсортированный по убыванию список из QUALITY_CANDIDATES,
    пересечённый с тем, что реально есть у видео."""
    heights = set()
    for f in info.get("formats") or []:
        h = f.get("height")
        vcodec = f.get("vcodec")
        # has_drm/помечен "Premium" — формат в списке ЕСТЬ, но реально
        # скачать его нельзя (нужна подписка/логин), из-за чего пикер
        # предлагал качество, которого "на самом деле нет". Пропускаем такие.
        if f.get("has_drm"):
            continue
        if h and vcodec and vcodec != "none":
            heights.add(int(h))
    if not heights:
        return []
    available = [q for q in QUALITY_CANDIDATES if any(h >= q - 5 for h in heights)]
    # Если ни один "круглый" вариант не подошёл (редкие площадки с нестандартными
    # высотами) — хотя бы предложим максимальное реально доступное качество.
    if not available:
        available = [max(heights)]
    return available


def has_audio_track(info: Dict[str, Any]) -> bool:
    """Есть ли у видео вообще звук — проверяем по данным пробы/скачивания разными способами."""
    acodec = info.get("acodec")
    if acodec and acodec != "none":
        return True
    for f in info.get("requested_formats") or []:
        if f.get("acodec") and f.get("acodec") != "none":
            return True
    for f in info.get("formats") or []:
        if f.get("acodec") and f.get("acodec") != "none":
            return True
    return False


async def download_audio_only(url: str, out_dir: Path) -> Path:
    """
    Качает только звук через yt-dlp (bestaudio) — так же, как видео, а не
    попыткой переиспользовать сырую CDN-ссылку напрямую. У многих площадок
    (особенно VK) прямые ссылки на медиа требуют специфичных заголовков
    (Referer и т.п.), которых у нашего простого HTTP-скачивателя нет — из-за
    этого звук иногда не скачивался/приходил битым. yt-dlp сам знает, что
    нужно каждой площадке, поэтому эта дорожка надёжнее.
    """
    def _run() -> Path:
        out_template = str(out_dir / "%(id)s.audio.%(ext)s")
        opts = {
            "format": "bestaudio/best",
            "outtmpl": out_template,
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "nocheckcertificate": True,
            "socket_timeout": 20,
            "retries": 3,
            "concurrent_fragment_downloads": 4,
            **_common_opts(),
        }
        if _FFMPEG_PATH:
            opts["ffmpeg_location"] = _FFMPEG_PATH
            opts["postprocessors"] = [
                {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}
            ]

        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            p = Path(filename)
            # После FFmpegExtractAudio (если ffmpeg найден) расширение меняется на .mp3
            for ext in (".mp3", ".m4a", ".webm", ".opus", ".ogg"):
                candidate = p.with_suffix(ext)
                if candidate.exists():
                    return candidate
            if p.exists():
                return p
            raise RuntimeError(f"yt-dlp: аудиофайл не найден ({filename})")

    return await asyncio.to_thread(_run)


# Эти функции на самом деле не привязаны к YouTube — просто вызывают
# yt-dlp.extract_info(url), который сам определяет площадку. Алиасы с
# нейтральными именами — для использования с Instagram/VK/Pinterest и т.п.
probe_media = probe_youtube
download_media = download_youtube
