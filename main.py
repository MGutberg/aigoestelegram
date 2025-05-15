import os
import asyncio
from fastapi import FastAPI, Request
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters
from dotenv import load_dotenv
import uvicorn
import openai
from collections import defaultdict

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
WHISPER_LANGUAGE = os.getenv("WHISPER_LANGUAGE", "de")

openai.api_key = OPENAI_API_KEY

app = FastAPI()
telegram_app = Application.builder().token(BOT_TOKEN).build()
user_contexts = defaultdict(list)

async def show_menu(update: Update, context):
    keyboard = [
        [InlineKeyboardButton("🤖 GPT-Modus", callback_data="gpt_general")],
        [InlineKeyboardButton("🎤 Sprachnachricht senden", callback_data="voice_mode")],
        [InlineKeyboardButton("🧠 Verlauf löschen", callback_data="clear")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Willkommen! Wähle eine Aktion:", reply_markup=reply_markup)

async def button_handler(update: Update, context):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    context.user_data["mode"] = query.data

    if query.data == "gpt_general":
        await query.edit_message_text("🤖 GPT-Modus aktiviert. Bitte sende deine Nachricht.", reply_markup=query.message.reply_markup)
    elif query.data == "voice_mode":
        await query.edit_message_text("🎤 Bitte sende mir jetzt eine Sprachnachricht.", reply_markup=query.message.reply_markup)
    elif query.data == "clear":
        user_contexts[user_id].clear()
        await query.edit_message_text("🧠 Dein Gesprächsverlauf wurde gelöscht.", reply_markup=query.message.reply_markup)

async def gpt_reply(update: Update, context):
    import re
    from gtts import gTTS
    try:
        user_id = update.effective_user.id
        message = update.message.text
        context.user_data.setdefault("mode", "gpt_general")
        print(f"📥 GPT-Text von {user_id}: {message}")

        user_contexts[user_id].append({"role": "user", "content": message})

        messages = [
            {"role": "system", "content": "Auch wenn du keinen Zugriff auf aktuelle Daten hast, gib bitte eine sinnvolle, freundliche und plausible Antwort. Wenn nach dem Wetter gefragt wird, liefere eine hypothetische Beschreibung auf Basis typischer Bedingungen für Ort und Jahreszeit."}
        ] + user_contexts[user_id][-10:]

        retry_attempts = 3
        for attempt in range(retry_attempts):
            try:
                response = openai.ChatCompletion.create(
                    model="gpt-3.5-turbo",
                    messages=messages,
                    temperature=0.7
                )
                break  # bei Erfolg abbrechen
            except openai.error.OpenAIError as e:
                print(f"⚠️ GPT-Fehler bei Versuch {attempt + 1}: {e}")
                if attempt < retry_attempts - 1:
                    time.sleep(3)
                else:
                    raise
        reply = response.choices[0].message.content.strip()
        user_contexts[user_id].append({"role": "assistant", "content": reply})

        # Stadt erkennen
        ort_match = re.search(r'in\s+([A-ZÄÖÜa-zäöüß\-\s]+)', message)
        if ort_match:
            ort = ort_match.group(1).strip().rstrip("?.,!")
            print(f"📍 Stadt erkannt: {ort}")
            reply = f"In {ort} ist es typischerweise so: {reply}"

        await update.message.reply_text(reply)

        # Text-to-Speech erzeugen
        tts = gTTS(reply, lang='de')
        tts_path = f"/tmp/{user_id}_reply.mp3"
        tts.save(tts_path)
        await context.bot.send_voice(chat_id=update.effective_user.id, voice=open(tts_path, "rb"))

    except Exception as e:
        print("❌ Fehler bei GPT/TTS:", e)
        import traceback
        traceback.print_exc()
        await update.message.reply_text("Es ist ein Fehler aufgetreten.")
    user_id = update.effective_user.id
    message = update.message.text
    context.user_data.setdefault("mode", "gpt_general")
    print(f"📥 GPT-Text von {user_id}: {message}")

    user_contexts[user_id].append({"role": "user", "content": message})

    try:
        messages = [
            {"role": "system", "content": "Auch wenn du keinen Zugriff auf aktuelle Daten hast, gib bitte eine sinnvolle, freundliche und plausible Antwort. Wenn nach dem Wetter gefragt wird, liefere eine hypothetische Beschreibung auf Basis typischer Bedingungen für Ort und Jahreszeit."}
        ] + user_contexts[user_id][-10:]
        retry_attempts = 3
        for attempt in range(retry_attempts):
            try:
                response = openai.ChatCompletion.create(
                    model="gpt-3.5-turbo",
                    messages=messages,
                    temperature=0.7
                )
                break  # bei Erfolg abbrechen
            except openai.error.OpenAIError as e:
                print(f"⚠️ GPT-Fehler bei Versuch {attempt + 1}: {e}")
                if attempt < retry_attempts - 1:
                    time.sleep(3)
                else:
                    raise
        reply = response.choices[0].message.content.strip()
        user_contexts[user_id].append({"role": "assistant", "content": reply})
        await update.message.reply_text(reply)
    except Exception as e:
        print("❌ Fehler bei GPT:", e)
        await update.message.reply_text("GPT ist nicht erreichbar.")

async def voice_handler(update: Update, context):
    print("🎧 Sprachnachricht empfangen")
    user_id = update.effective_user.id
    voice = update.message.voice or update.message.audio

    if not voice:
        print("⚠️ Kein Voice-Objekt erkannt.")
        await update.message.reply_text("Bitte sende mir eine Sprachnachricht im OGG-Format.")
        return

    file = await context.bot.get_file(voice.file_id)
    input_path = f"/tmp/{user_id}_voice.ogg"
    output_path = f"/tmp/{user_id}_voice.wav"

    print("⬇️ Lade Datei herunter...")
    await file.download_to_drive(input_path)

    import subprocess
    try:
        print("🔁 Konvertiere mit ffmpeg...")
        subprocess.run(["ffmpeg", "-y", "-i", input_path, output_path], check=True)
    except Exception as ffmpeg_err:
        print("❌ Fehler bei ffmpeg:", ffmpeg_err)
        await update.message.reply_text("Fehler beim Umwandeln der Sprachnachricht.")
        return

    try:
        print("📡 Sende an Whisper...")
        with open(output_path, "rb") as audio_file:
            transcript = openai.Audio.transcribe("whisper-1", audio_file, language=WHISPER_LANGUAGE)
        print("📝 Transkript erhalten:", transcript["text"])
        print("➡️ Übergabe an GPT...")
        await gpt_reply(
            type("FakeUpdate", (), {
                "effective_user": update.effective_user,
                "message": type("FakeMessage", (), {
                    "text": transcript["text"],
                    "reply_text": update.message.reply_text
                })()
            })(), context
        )
    except Exception as e:
        print("❌ Whisper-Fehler:", e)
        import traceback
        traceback.print_exc()
        await update.message.reply_text("Fehler bei Spracherkennung.")

@app.post(WEBHOOK_PATH)
async def process_update(request: Request):
    json_data = await request.json()
    update = Update.de_json(json_data, telegram_app.bot)
    asyncio.create_task(telegram_app.process_update(update))
    return {"status": "ok"}

@app.on_event("startup")
async def on_startup():
    await telegram_app.initialize()
    await telegram_app.bot.set_webhook(WEBHOOK_URL)
    print(f"✅ Webhook gesetzt: {WEBHOOK_URL}")

@app.on_event("shutdown")
async def on_shutdown():
    await telegram_app.shutdown()
    await telegram_app.stop()

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", 10000)))

telegram_app.add_handler(CommandHandler("menu", show_menu))
telegram_app.add_handler(CallbackQueryHandler(button_handler))
telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, gpt_reply))
telegram_app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, voice_handler))



async def gpt_reply_voice_only(message, update, context):
    import re
    from gtts import gTTS

    try:
        user_id = update.effective_user.id
        context.user_data.setdefault("mode", "gpt_general")
        print(f"🎤 GPT-Sprachmodus für {user_id}: {message}")

        user_contexts[user_id].append({"role": "user", "content": message})

        messages = [
            {"role": "system", "content": "Auch wenn du keinen Zugriff auf aktuelle Daten hast, gib bitte eine sinnvolle, freundliche und plausible Antwort. Wenn nach dem Wetter gefragt wird, liefere eine hypothetische Beschreibung auf Basis typischer Bedingungen für Ort und Jahreszeit."}
        ] + user_contexts[user_id][-10:]

        retry_attempts = 3
        for attempt in range(retry_attempts):
            try:
                response = openai.ChatCompletion.create(
                    model="gpt-3.5-turbo",
                    messages=messages,
                    temperature=0.7
                )
                break
            except openai.error.OpenAIError as e:
                print(f"⚠️ GPT-Fehler bei Versuch {attempt + 1}: {e}")
                if attempt < retry_attempts - 1:
                    time.sleep(3)
                else:
                    raise

        reply = response.choices[0].message.content.strip()
        user_contexts[user_id].append({"role": "assistant", "content": reply})

        ort_match = re.search(r'in\s+([A-ZÄÖÜa-zäöüß\-\s]+)', message)
        if ort_match:
            ort = ort_match.group(1).strip().rstrip("?.,!")
            print(f"📍 Stadt erkannt: {ort}")
            reply = f"In {ort} ist es typischerweise so: {reply}"

        tts = gTTS(reply, lang='de')
        tts_path = f"/tmp/{user_id}_reply.mp3"
        tts.save(tts_path)
        await context.bot.send_voice(chat_id=update.effective_user.id, voice=open(tts_path, "rb"))

    except Exception as e:
        print("❌ Fehler bei GPT/TTS-Sprachantwort:", e)
        import traceback
        traceback.print_exc()
        await update.message.reply_text("Fehler bei Sprachantwort.")
