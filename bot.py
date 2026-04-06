import requests
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import threading
from flask import Flask

TELEGRAM_TOKEN = "8778233587:AAF2Xvfs2Zoh0UGAO7y573LNCiX9m5xGnQg"
DEEPSEEK_API_KEY = "sk-b985c50489844eadae6e8e0c471506a3"

DEEPSEEK_URL = "https://api.deepseek.com/v1/chat/completions"

# Flask app for health check
flask_app = Flask(__name__)

@flask_app.route('/')
def health():
    return "OK", 200

def run_flask():
    flask_app.run(host='0.0.0.0', port=8080)

# Запускаем Flask в отдельном потоке
threading.Thread(target=run_flask, daemon=True).start()

# --- Telegram bot handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привет, бро! Я твой помощник на базе DeepSeek. Пиши любые вопросы, задачи - я отвечу.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text

    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": "Ты - личный помощник руководителя. Отвечай кратко, по делу, дружелюбно. Используй обращение 'бро'."},
            {"role": "user", "content": user_text}
        ],
        "stream": False
    }

    try:
        response = requests.post(DEEPSEEK_URL, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        reply = response.json()["choices"][0]["message"]["content"]
    except Exception as e:
        reply = f"Ошибка, бро: {str(e)}. Проверь интернет или API ключ."

    await update.message.reply_text(reply)

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print(f"Ошибка: {context.error}")

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_error_handler(error_handler)
    print("Бот запущен...")
    app.run_polling()

if __name__ == "__main__":
    main()
