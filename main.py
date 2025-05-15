import os
import asyncio
from fastapi import FastAPI, Request
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters
from dotenv import load_dotenv
import uvicorn
import openai

# .env laden
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

openai.api_key = OPENAI_API_KEY

app = FastAPI()
telegram_app = Application.builder().token(BOT_TOKEN).build()

# /start-Befehl
async def start(update: Update, context):
    print("✅ /start empfangen von:", update.effective_user.username)
    await update.message.reply_text("Hallo! Ich bin dein GPT-gestützter Telegram-Bot 🤖")

telegram_app.add_handler(CommandHandler("start", start))

# GPT-Handler für freie Texteingabe
async def gpt_reply(update: Update, context):
    user_input = update.message.text
    print(f"🤖 GPT-Anfrage von {update.effective_user.username}: {user_input}")
    
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": user_input}],
            temperature=0.7
        )
        answer = response.choices[0].message.content.strip()
        await update.message.reply_text(answer)
    except Exception as e:
        print(f"❌ Fehler bei OpenAI: {e}")
        await update.message.reply_text("Ups! GPT ist gerade nicht erreichbar.")

telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, gpt_reply))

# Webhook-Endpoint
@app.post(WEBHOOK_PATH)
async def process_update(request: Request):
    json_data = await request.json()
    print("📩 Telegram-Update empfangen")
    update = Update.de_json(json_data, telegram_app.bot)
    asyncio.create_task(telegram_app.process_update(update))
    return {"status": "ok"}

# Startup → Telegram-App initialisieren + Webhook setzen
@app.on_event("startup")
async def on_startup():
    print("🚀 Initialisiere Telegram-Bot...")
    await telegram_app.initialize()
    try:
        await telegram_app.bot.set_webhook(WEBHOOK_URL)
        print(f"✅ Webhook gesetzt: {WEBHOOK_URL}")
    except Exception as e:
        print(f"❌ Fehler beim Webhook-Setzen: {e}")

@app.on_event("shutdown")
async def on_shutdown():
    await telegram_app.shutdown()
    await telegram_app.stop()

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", 10000)))
