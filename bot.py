import requests
import json
import os
import threading
from datetime import datetime
from telegram import Update, ParseMode
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from flask import Flask

# ========== НАСТРОЙКИ ==========
TELEGRAM_TOKEN = "8778233587:AAF2Xvfs2Zoh0UGAO7y573LNCiX9m5xGnQg"
DEEPSEEK_API_KEY = "sk-b985c50489844eadae6e8e0c471506a3"
REMINDERS_FILE = "reminders.json"
# ================================

DEEPSEEK_URL = "https://api.deepseek.com/v1/chat/completions"

# Flask для health check (не трогаем)
flask_app = Flask(__name__)

@flask_app.route('/')
def health():
    return "OK", 200

def run_flask():
    flask_app.run(host='0.0.0.0', port=8080)

threading.Thread(target=run_flask, daemon=True).start()

# ---------- Работа с напоминаниями ----------
def load_reminders():
    if os.path.exists(REMINDERS_FILE):
        with open(REMINDERS_FILE, 'r') as f:
            return json.load(f)
    return []

def save_reminders(reminders):
    with open(REMINDERS_FILE, 'w') as f:
        json.dump(reminders, f, indent=2)

async def remind_job(context: ContextTypes.DEFAULT_TYPE):
    # Задача, выполняемая каждую минуту
    reminders = load_reminders()
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    still_pending = []
    for r in reminders:
        if r["time"] <= now:
            # Отправляем напоминание пользователю (chat_id храним в напоминании)
            try:
                await context.bot.send_message(chat_id=r["chat_id"], text=f"🔔 НАПОМИНАНИЕ: {r['text']}")
            except:
                pass
        else:
            still_pending.append(r)
    if len(still_pending) != len(reminders):
        save_reminders(still_pending)

# ---------- Telegram handlers ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет, бро! Я твой помощник с напоминаниями.\n\n"
        "Команды:\n"
        "/remind [что] at [время] — добавить напоминание\n"
        "   пример: /remind Позвонить клиенту at 15:30\n"
        "/mytasks — показать список напоминаний\n"
        "/delremind [номер] — удалить напоминание\n"
        "Просто пиши вопросы — я отвечу через DeepSeek."
    )

async def remind_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Парсим команду: /remind текст at время
    text = update.message.text
    parts = text.split(" at ")
    if len(parts) != 2:
        await update.message.reply_text("❌ Неправильный формат. Пиши: /remind что сделать at 15:30")
        return
    reminder_text = parts[0].replace("/remind", "").strip()
    time_str = parts[1].strip()
    # Проверяем формат времени (ЧЧ:ММ)
    try:
        datetime.strptime(time_str, "%H:%M")
    except:
        await update.message.reply_text("❌ Время должно быть в формате ЧЧ:ММ, например 15:30")
        return
    # Собираем полную дату-время: сегодня + время
    today = datetime.now().strftime("%Y-%m-%d")
    full_time_str = f"{today} {time_str}"
    # Если время уже прошло сегодня, добавляем на завтра
    if datetime.now() > datetime.strptime(full_time_str, "%Y-%m-%d %H:%M"):
        # переносим на завтра
        tomorrow = datetime.now().replace(day=datetime.now().day+1).strftime("%Y-%m-%d")
        full_time_str = f"{tomorrow} {time_str}"
    # Сохраняем
    reminders = load_reminders()
    new_id = len(reminders) + 1
    reminders.append({
        "id": new_id,
        "chat_id": update.effective_chat.id,
        "text": reminder_text,
        "time": full_time_str
    })
    save_reminders(reminders)
    await update.message.reply_text(f"✅ Напоминание добавлено: «{reminder_text}» в {time_str}")

async def mytasks_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reminders = load_reminders()
    user_reminders = [r for r in reminders if r["chat_id"] == update.effective_chat.id]
    if not user_reminders:
        await update.message.reply_text("У тебя нет активных напоминаний.")
        return
    msg = "📋 Твои напоминания:\n"
    for r in user_reminders:
        msg += f"{r['id']}. {r['text']} — в {r['time'][5:16]}\n"
    await update.message.reply_text(msg)

async def delremind_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        rem_id = int(context.args[0])
    except:
        await update.message.reply_text("❌ Укажи номер напоминания: /delremind 2")
        return
    reminders = load_reminders()
    new_list = [r for r in reminders if not (r["chat_id"] == update.effective_chat.id and r["id"] == rem_id)]
    if len(new_list) == len(reminders):
        await update.message.reply_text("Напоминание с таким номером не найдено.")
        return
    save_reminders(new_list)
    await update.message.reply_text(f"✅ Напоминание {rem_id} удалено.")

# Обычный ответ через DeepSeek (как было)
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

    # Команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("remind", remind_command))
    app.add_handler(CommandHandler("mytasks", mytasks_command))
    app.add_handler(CommandHandler("delremind", delremind_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_error_handler(error_handler)

    # Планировщик: проверять напоминания каждую минуту
    job_queue = app.job_queue
    if job_queue:
        job_queue.run_repeating(remind_job, interval=60, first=10)
    else:
        print("JobQueue не доступен — напоминания не будут работать")

    print("Бот запущен с поддержкой напоминаний...")
    app.run_polling()

if __name__ == "__main__":
    main()import requests
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
