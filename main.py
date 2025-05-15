import os
import asyncio
from fastapi import FastAPI, Request
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters
from dotenv import load_dotenv
import uvicorn
import openai
from collections import defaultdict

# ENV laden
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
WHISPER_LANGUAGE = os.getenv("WHISPER_LANGUAGE", "de")

openai.api_key = OPENAI_API_KEY

app = FastAPI()
telegram_app = Application.builder().token(BOT_TOKEN).build()

# Per-User-Kontextspeicher
user_contexts = defaultdict(list)

# Menü anzeigen
async def show_menu(update: Update, context):
    keyboard = [
        [InlineKeyboardButton("🤖 GPT-Modus", callback_data="gpt_general")],
        [InlineKeyboardButton("🎤 Sprachnachricht senden", callback_data="voice_mode")],
        [InlineKeyboardButton("🧠 Verlauf löschen", callback_data="clear")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Willkommen! Wähle eine Aktion:", reply_markup=reply_markup)

# Button-Handler
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

# Textnachricht → GPT mit Memory
async def gpt_reply(update: Update, context):
    user_id = update.effective_user.id
    message = update.message.text
    context.user_data.setdefault("mode", "gpt_general")

    # Konversation speichern
    user_contexts[user_id].append({"role": "user", "content": message})

    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=user_contexts[user_id][-10:],  # letzte 10 Nachrichten
            temperature=0.7
        )
        reply = response.choices[0].message.content.strip()
        user_contexts[user_id].append({"role": "assistant", "content": reply})
        await update.message.reply_text(reply)
    except Exception as e:
        print("❌ Fehler bei GPT:", e)
        await update.message.reply_text("GPT ist nicht erreichbar.")

# Sprachnachrichten verarbeiten (nur OGG/Voice)
async def voice_handler(update: Update, context):
    user_id = update.effective_user.id
    voice = update.message.voice or update.message.audio

    if not voice:
        await update.message.reply_text("Bitte sende mir eine Sprachnachricht im OGG-Format.")
        return

    file = await context.bot.get_file(voice.file_id)
    input_path = f"/tmp/{user_id}_voice.ogg"
    output_path = f"/tmp/{user_id}_voice.wav"

    await file.download_to_drive(input_path)

    import subprocess
    subprocess.run(["ffmpeg", "-i", input_path, output_path], check=True)

    with open(output_path, "rb") as audio_file:
        transcript = openai.Audio.transcribe("whisper-1", audio_file, language=WHISPER_LANGUAGE)

    update.message.text = transcript["text"]
    await gpt_reply(update, context)

# Webhook Endpoint
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
