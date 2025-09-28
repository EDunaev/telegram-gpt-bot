import tempfile
import logging
from collections import defaultdict, deque
from telegram import Update
from telegram.ext import ContextTypes
from pydub import AudioSegment
from config import client, current_model, ADMINS
from helpers import is_allowed, format_exc

user_histories = defaultdict(lambda: deque(maxlen=5))

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update):
        return

    user = update.effective_user
    chat = update.effective_chat
    user_id = user.id

    logging.info(f"[{user.id}] @{user.username or 'no_username'} - VOICE: получено голосовое сообщение")

    try:
        # 1. Скачиваем голосовое
        voice_file = await update.message.voice.get_file()
        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as f:
            await voice_file.download_to_drive(f.name)
            ogg_path = f.name

        # 2. Конвертируем в wav
        wav_path = ogg_path.replace(".ogg", ".wav")
        AudioSegment.from_ogg(ogg_path).export(wav_path, format="wav")

        # 3. Распознаём речь (Whisper)
        with open(wav_path, "rb") as audio_file:
            transcript = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
            )
        text = transcript.text.strip()
        logging.info(f"{user} - VOICE TEXT: {text}")

        # 4. Формируем сообщения для GPT
        messages = []
        if chat.type == "private" and user_id in ADMINS:
            history = user_histories[user_id]
            messages.extend(list(history))
            messages.append({"role": "user", "content": text})
        else:
            messages.append({"role": "user", "content": text})

        # 5. Отвечаем GPT
        resp = client.chat.completions.create(
            model=current_model,
            messages=messages,
        )
        answer_text = resp.choices[0].message.content

        logging.info(f"[BOT -> {user.id}] Ответ: {answer_text}")

        # 6. Отправляем ответ
        await update.message.reply_text(
            f"🗣️ Ты сказал: {text}\n\n🤖 {answer_text}"
        )

        # 7. Сохраняем историю для админов
        if chat.type == "private" and user_id in ADMINS:
            history = user_histories[user_id]
            history.append({"role": "assistant", "content": answer_text})

    except Exception as e:
        logging.error(f"{user} - VOICE ERROR: {str(e)}")
        await update.message.reply_text(f"❌ Ошибка при обработке голосового: {format_exc(e)}")
