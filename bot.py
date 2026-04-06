import requests
import json
import os
import threading
import asyncio
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from flask import Flask

# ========== НАСТРОЙКИ ==========
TELEGRAM_TOKEN = "8778233587:AAF2Xvfs2Zoh0UGAO7y573LNCiX9m5xGnQg"
DEEPSEEK_API_KEY = "sk-b985c50489844eadae6e8e0c471506a3"
REMINDERS_FILE = "reminders.json"
AUTHORIZED_CHAT_ID = 987654321   # замени на свой реальный ID после /getid
# ================================

DEEPSEEK_URL = "https://api.deepseek.com/v1/chat/completions"

# Flask для health check
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
    reminders = load_reminders()
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    still_pending = []
    for r in reminders:
        if r["time"] <= now:
            try:
                await context.bot.send_message(chat_id=r["chat_id"], text=f"🔔 НАПОМИНАНИЕ: {r['text']}")
            except:
                pass
        else:
            still_pending.append(r)
    if len(still_pending) != len(reminders):
        save_reminders(still_pending)

# ---------- Команды Telegram ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет, бро! Я твой помощник с напоминаниями и пересылкой сообщений.\n\n"
        "Команды:\n"
        "/remind [что] at [время] — добавить напоминание (пример: /remind Позвонить at 15:30)\n"
        "/mytasks — показать список напоминаний\n"
        "/delremind [номер] — удалить напоминание\n"
        "/sendto @username текст — отправить сообщение другому пользователю\n"
        "/sendto_id [числовой_айди] текст — отправить по ID\n"
        "/getid — узнать свой chat_id (для владельца)\n\n"
        "Просто пиши вопросы — я отвечу через DeepSeek."
    )

async def getid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id == AUTHORIZED_CHAT_ID:
        await update.message.reply_text(f"Твой chat_id: {update.effective_chat.id}")
    else:
        await update.message.reply_text("Нет прав.")

async def remind_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    parts = text.split(" at ")
    if len(parts) != 2:
        await update.message.reply_text("❌ Неправильный формат. Пиши: /remind что сделать at 15:30")
        return
    reminder_text = parts[0].replace("/remind", "").strip()
    time_str = parts[1].strip()
    try:
        datetime.strptime(time_str, "%H:%M")
    except:
        await update.message.reply_text("❌ Время должно быть в формате ЧЧ:ММ, например 15:30")
        return
    today = datetime.now().strftime("%Y-%m-%d")
    full_time_str = f"{today} {time_str}"
    if datetime.now() > datetime.strptime(full_time_str, "%Y-%m-%d %H:%M"):
        tomorrow = datetime.now().replace(day=datetime.now().day+1).strftime("%Y-%m-%d")
        full_time_str = f"{tomorrow} {time_str}"
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

async def sendto_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != AUTHORIZED_CHAT_ID:
        await update.message.reply_text("❌ Нет прав.")
        return
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("❌ Использование: /sendto @username текст сообщения")
        return
    username = args[0]
    if username.startswith('@'):
        username = username[1:]
    message_text = ' '.join(args[1:])
    try:
        chat = await context.bot.get_chat(f"@{username}")
        chat_id = chat.id
        await context.bot.send_message(chat_id=chat_id, text=f"📨 Сообщение от {update.effective_user.first_name}:\n{message_text}")
        await update.message.reply_text(f"✅ Отправлено @{username}")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

async def sendto_id_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != AUTHORIZED_CHAT_ID:
        await update.message.reply_text("❌ Нет прав.")
        return
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("❌ Использование: /sendto_id 123456789 текст")
        return
    try:
        target_id = int(args[0])
        message_text = ' '.join(args[1:])
        await context.bot.send_message(chat_id=target_id, text=f"📨 Сообщение от {update.effective_user.first_name}:\n{message_text}")
        await update.message.reply_text(f"✅ Отправлено ID {target_id}")
    except ValueError:
        await update.message.reply_text("❌ ID должен быть числом.")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

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
    # Создаём приложение с таймаутами
    app = Application.builder().token(TELEGRAM_TOKEN).connect_timeout(30).read_timeout(30).write_timeout(30).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("getid", getid))
    app.add_handler(CommandHandler("remind", remind_command))
    app.add_handler(CommandHandler("mytasks", mytasks_command))
    app.add_handler(CommandHandler("delremind", delremind_command))
    app.add_handler(CommandHandler("sendto", sendto_command))
    app.add_handler(CommandHandler("sendto_id", sendto_id_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_error_handler(error_handler)

    # JobQueue должен быть доступен
    if app.job_queue:
        app.job_queue.run_repeating(remind_job, interval=60, first=10)
        print("JobQueue включён, напоминания будут работать.")
    else:
        print("JobQueue недоступен. Проверь установку python-telegram-bot.")

    print("Бот запущен...")
    # Небольшая задержка для предотвращения конфликта при перезапуске
    import time
    time.sleep(2)
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

if __name__ == "__main__":
    main()import requests
import json
import os
import threading
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from flask import Flask

# ========== НАСТРОЙКИ ==========
TELEGRAM_TOKEN = "8778233587:AAF2Xvfs2Zoh0UGAO7y573LNCiX9m5xGnQg"
DEEPSEEK_API_KEY = "sk-b985c50489844eadae6e8e0c471506a3"
REMINDERS_FILE = "reminders.json"
AUTHORIZED_CHAT_ID = 8778233587  # замени на свой реальный chat_id (узнай через /getid)
# ================================

DEEPSEEK_URL = "https://api.deepseek.com/v1/chat/completions"

# Flask для health check
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
    reminders = load_reminders()
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    still_pending = []
    for r in reminders:
        if r["time"] <= now:
            try:
                await context.bot.send_message(chat_id=r["chat_id"], text=f"🔔 НАПОМИНАНИЕ: {r['text']}")
            except:
                pass
        else:
            still_pending.append(r)
    if len(still_pending) != len(reminders):
        save_reminders(still_pending)

# ---------- Команды Telegram ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет, бро! Я твой помощник с напоминаниями и пересылкой сообщений.\n\n"
        "Команды:\n"
        "/remind [что] at [время] — добавить напоминание (пример: /remind Позвонить at 15:30)\n"
        "/mytasks — показать список напоминаний\n"
        "/delremind [номер] — удалить напоминание\n"
        "/sendto @username текст — отправить сообщение другому пользователю\n"
        "/sendto_id [числовой_айди] текст — отправить по ID\n"
        "/getid — узнать свой chat_id (для владельца)\n\n"
        "Просто пиши вопросы — я отвечу через DeepSeek."
    )

async def getid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"Твой chat_id: {update.effective_chat.id}")

async def remind_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    parts = text.split(" at ")
    if len(parts) != 2:
        await update.message.reply_text("❌ Неправильный формат. Пиши: /remind что сделать at 15:30")
        return
    reminder_text = parts[0].replace("/remind", "").strip()
    time_str = parts[1].strip()
    try:
        datetime.strptime(time_str, "%H:%M")
    except:
        await update.message.reply_text("❌ Время должно быть в формате ЧЧ:ММ, например 15:30")
        return
    today = datetime.now().strftime("%Y-%m-%d")
    full_time_str = f"{today} {time_str}"
    if datetime.now() > datetime.strptime(full_time_str, "%Y-%m-%d %H:%M"):
        tomorrow = datetime.now().replace(day=datetime.now().day+1).strftime("%Y-%m-%d")
        full_time_str = f"{tomorrow} {time_str}"
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

async def sendto_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != AUTHORIZED_CHAT_ID:
        await update.message.reply_text("❌ Нет прав.")
        return
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("❌ Использование: /sendto @username текст сообщения")
        return
    username = args[0]
    if username.startswith('@'):
        username = username[1:]
    message_text = ' '.join(args[1:])
    try:
        chat = await context.bot.get_chat(f"@{username}")
        chat_id = chat.id
        await context.bot.send_message(chat_id=chat_id, text=f"📨 Сообщение от {update.effective_user.first_name}:\n{message_text}")
        await update.message.reply_text(f"✅ Отправлено @{username}")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

async def sendto_id_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != AUTHORIZED_CHAT_ID:
        await update.message.reply_text("❌ Нет прав.")
        return
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("❌ Использование: /sendto_id 123456789 текст")
        return
    try:
        target_id = int(args[0])
        message_text = ' '.join(args[1:])
        await context.bot.send_message(chat_id=target_id, text=f"📨 Сообщение от {update.effective_user.first_name}:\n{message_text}")
        await update.message.reply_text(f"✅ Отправлено ID {target_id}")
    except ValueError:
        await update.message.reply_text("❌ ID должен быть числом.")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

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
    app.add_handler(CommandHandler("getid", getid))
    app.add_handler(CommandHandler("remind", remind_command))
    app.add_handler(CommandHandler("mytasks", mytasks_command))
    app.add_handler(CommandHandler("delremind", delremind_command))
    app.add_handler(CommandHandler("sendto", sendto_command))
    app.add_handler(CommandHandler("sendto_id", sendto_id_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_error_handler(error_handler)

    job_queue = app.job_queue
    if job_queue:
        job_queue.run_repeating(remind_job, interval=60, first=10)
    else:
        print("JobQueue не доступен — напоминания не будут работать")

    print("Бот запущен с поддержкой напоминаний и пересылки...")
    app.run_polling()

if __name__ == "__main__":
    main()
