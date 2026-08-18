"""
Обработчик нажатий на кнопки экрана выбора качества (YouTube/VK) —
handlers/youtube_handler.py и handlers/other_sources_handler.py показывают
клавиатуру quality_pick_kb, а сюда прилетает сам выбор:
yq:<req_id>:v<height> — скачать в конкретном качестве
yq:<req_id>:audio     — скачать только звук
yq:<req_id>:cancel    — отмена
"""
import contextlib

from aiogram import F
from aiogram.types import CallbackQuery

from globals_state import dp
from gates import gate_callback
from quality_state import quality_pending, cleanup_quality_pending
from external_send import download_and_send_with_quality


@dp.callback_query(F.data.startswith("yq:"))
async def quality_pick_callback(call: CallbackQuery):
    uid = call.from_user.id
    label = call.from_user.full_name or str(uid)
    if not await gate_callback(call, label):
        return

    parts = (call.data or "").split(":", 2)
    if len(parts) != 3:
        await call.answer()
        return
    _, req_id, choice = parts

    cleanup_quality_pending()
    st = quality_pending.get(req_id)
    if not st:
        with contextlib.suppress(Exception):
            await call.message.edit_text("⌛ Эта ссылка уже неактуальна, пришли её заново.")
        await call.answer()
        return

    # Выбирать качество может только тот, кто прислал ссылку.
    if st.get("uid") != uid:
        await call.answer("Это не твой запрос", show_alert=True)
        return

    quality_pending.pop(req_id, None)

    if choice == "cancel":
        with contextlib.suppress(Exception):
            await call.message.edit_text("❌ Отменено.")
        await call.answer()
        return

    await call.answer("Качаю…")

    audio_only = choice == "audio"
    max_height = None
    if choice.startswith("v"):
        with contextlib.suppress(ValueError):
            max_height = int(choice[1:])

    await download_and_send_with_quality(
        call.message,
        call.message,
        st["uid"],
        st["label"],
        st["url"],
        st["info"],
        st["platform"],
        st["emoji"],
        max_height=max_height,
        audio_only=audio_only,
    )
