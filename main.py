import os
import asyncio
from fastapi import FastAPI, Request
from telegram import Update
from telegram.ext import Application, CommandHandler
from dotenv import load_dotenv
import uvicorn

# .env laden
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

# FastAPI & Telegram-Setup
app = FastAPI()
telegram_app = Application.builder().token(BOT_TOKEN).build()

# /start-Befehl
async def start(update: Update, context):
    print("✅ /start empfangen von:", update.effective_user.username)
    await update.message.reply_text("Hallo! Ich bin jetzt auf Render aktiv! 🤖")

telegram_app.add_handler(CommandHandler("start", start))

# Webhook-Verarbeitung
@app.post(WEBHOOK_PATH)
async def process_update(request: Request):
    json_data = await request.json()
    print("📩 Telegram-Update empfangen")
    update = Update.de_json(json_data, telegram_app.bot)
    asyncio.create_task(telegram_app.process_update(update))
    return {"status": "ok"}

# Initialisierung beim Start
@app.on_event("startup")
async def on_startup():
    print("🚀 Initialisiere Telegram-Bot...")
    await telegram_app.initialize()  # wichtig!
    try:
        await telegram_app.bot.set_webhook(WEBHOOK_URL)
        print(f"✅ Webhook gesetzt: {WEBHOOK_URL}")
    except Exception as e:
        print(f"❌ Fehler beim Webhook-Setzen: {e}")

# Optional: Shutdown sauber beenden
@app.on_event("shutdown")
async def on_shutdown():
    await telegram_app.shutdown()
    await telegram_app.stop()

# Local testing fallback (nicht nötig bei Render)
if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", 10000)))
