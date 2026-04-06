import requests
import json
import os
import threading
import asyncio
import aiosqlite
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from flask import Flask

# ========== НАСТРОЙКИ ==========
TELEGRAM_TOKEN = "8778233587:AAF2Xvfs2Zoh0UGAO7y573LNCiX9m5xGnQg"
DEEPSEEK_API_KEY = "sk-b985c50489844eadae6e8e0c471506a3"
REMINDERS_FILE = "reminders.json"
DATABASE_PATH = "whitelist.db"
ADMIN_USER_ID = None  # Будет установлен при первом запуске через команду /init_admin
# ================================

DEEPSEEK_URL = "https://api.deepseek.com/v1/chat/completions"

# --- Flask для health check ---
flask_app = Flask(__name__)

@flask_app.route('/')
def health():
    return "OK", 200

def run_flask():
    flask_app.run(host='0.0.0.0', port=8080)

threading.Thread(target=run_flask, daemon=True).start()

# ========== БАЗА ДАННЫХ (белый список) ==========
async def init_db():
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("CREATE TABLE IF NOT EXISTS whitelist (user_id INTEGER PRIMARY KEY)")
        await db.commit()

async def add_user_to_whitelist(user_id: int):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        try:
            await db.execute("INSERT INTO whitelist (user_id) VALUES (?)", (user_id,))
            await db.commit()
            return True
        except aiosqlite.IntegrityError:
            return False

async def remove_user_from_whitelist(user_id: int):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute("DELETE FROM whitelist WHERE user_id = ?", (user_id,))
        await db.commit()
        return cursor.rowcount > 0

async def get_whitelist():
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute("SELECT user_id FROM whitelist")
        rows = await cursor.fetchall()
        return [row[0] for row in rows]

async def is_user_authorized(user_id: int) -> bool:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute("SELECT 1 FROM whitelist WHERE user_id = ?", (user_id,))
        row = await cursor.fetchone()
        return row is not None

# --- Администратор (первый пользователь, который выполнит /init_admin) ---
async def init_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global ADMIN_USER_ID
    whitelist = await get_whitelist()
    if whitelist:
        await update.message.reply_text("❌ Белый список уже не пуст. Администратор уже назначен.")
        return
    user_id = update.effective_chat.id
    await add_user_to_whitelist(user_id)
    ADMIN_USER_ID = user_id
    await update.message.reply_text(f"✅ Вы назначены администратором бота. Ваш ID: {user_id}")

async def add_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ADMIN_USER_ID:
        await update.message.reply_text("❌ Нет прав.")
        return
    reply = update.message.reply_to_message
    if not reply:
        await update.message.reply_text("❌ Ответьте на сообщение пользователя, которого хотите добавить.")
        return
    user_id = reply.from_user.id
    username = reply.from_user.username or "без username"
    if await add_user_to_whitelist(user_id):
        await update.message.reply_text(f"✅ Пользователь @{username} добавлен.")
    else:
        await update.message.reply_text(f"⚠️ Пользователь @{username} уже в списке.")

async def remove_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ADMIN_USER_ID:
        await update.message.reply_text("❌ Нет прав.")
        return
    reply = update.message.reply_to_message
    if not reply:
        await update.message.reply_text("❌ Ответьте на сообщение пользователя, которого хотите удалить.")
        return
    user_id = reply.from_user.id
    username = reply.from_user.username or "без username"
    if await remove_user_from_whitelist(user_id):
        await update.message.reply_text(f"✅ Пользователь @{username} удалён.")
    else:
        await update.message.reply_text(f"⚠️ Пользователь @{username} не найден.")

async def list_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ADMIN_USER_ID:
        await update.message.reply_text("❌ Нет прав.")
        return
    whitelist = await get_whitelist()
    if not whitelist:
        await update.message.reply_text("📋 Белый список пуст.")
        return
    msg = "📋 *Белый список:*\n"
    for uid in whitelist:
        try:
            chat = await context.bot.get_chat(uid)
            username = chat.username or "без username"
            msg += f"• `{uid}` (@{username})\n"
        except:
            msg += f"• `{uid}` (неизвестен)\n"
    await update.message.reply_text(msg, parse_mode="Markdown")

# ========== НАПОМИНАНИЯ ==========
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
    pending = []
    for r in reminders:
        if r["time"] <= now:
            try:
                await context.bot.send_message(chat_id=r["chat_id"], text=f"🔔 НАПОМИНАНИЕ: {r['text']}")
            except:
                pass
        else:
            pending.append(r)
    if len(pending) != len(reminders):
        save_reminders(pending)

# ========== КОМАНДЫ ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 Привет! Я личный помощник.\n"
        "Команды:\n"
        "/remind [текст] at [ЧЧ:ММ] – добавить напоминание\n"
        "/mytasks – список напоминаний\n"
        "/delremind [номер] – удалить\n"
        "/sendto @username [текст] – отправить сообщение (только админ)\n"
        "/sendto_id [ID] [текст] – отправить по ID\n"
        "/getid – узнать свой ID\n"
        "/init_admin – стать администратором (если список пуст)\n"
        "/add_user – ответом на сообщение (админ)\n"
        "/remove_user – ответом на сообщение (админ)\n"
        "/list_users – показать белый список (админ)\n\n"
        "Просто пиши – отвечаю через DeepSeek."
    )

async def getid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"🆔 Твой chat_id: {update.effective_chat.id}")

async def remind_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    parts = text.split(" at ")
    if len(parts) != 2:
        await update.message.reply_text("❌ Формат: /remind что сделать at 15:30")
        return
    reminder_text = parts[0].replace("/remind", "").strip()
    time_str = parts[1].strip()
    try:
        datetime.strptime(time_str, "%H:%M")
    except:
        await update.message.reply_text("❌ Время должно быть ЧЧ:ММ, например 15:30")
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
    await update.message.reply_text(f"✅ Напоминание «{reminder_text}» в {time_str}")

async def mytasks_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reminders = load_reminders()
    user_reminders = [r for r in reminders if r["chat_id"] == update.effective_chat.id]
    if not user_reminders:
        await update.message.reply_text("Нет активных напоминаний.")
        return
    msg = "📋 Твои напоминания:\n"
    for r in user_reminders:
        msg += f"{r['id']}. {r['text']} — в {r['time'][5:16]}\n"
    await update.message.reply_text(msg)

async def delremind_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        rem_id = int(context.args[0])
    except:
        await update.message.reply_text("❌ Укажи номер: /delremind 2")
        return
    reminders = load_reminders()
    new_list = [r for r in reminders if not (r["chat_id"] == update.effective_chat.id and r["id"] == rem_id)]
    if len(new_list) == len(reminders):
        await update.message.reply_text("Напоминание не найдено.")
        return
    save_reminders(new_list)
    await update.message.reply_text(f"✅ Напоминание {rem_id} удалено.")

async def sendto_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ADMIN_USER_ID:
        await update.message.reply_text("❌ Нет прав.")
        return
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("❌ /sendto @username текст")
        return
    username = args[0].lstrip('@')
    message_text = ' '.join(args[1:])
    try:
        chat = await context.bot.get_chat(f"@{username}")
        await context.bot.send_message(chat_id=chat.id, text=f"📨 Сообщение от админа:\n{message_text}")
        await update.message.reply_text(f"✅ Отправлено @{username}")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

async def sendto_id_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ADMIN_USER_ID:
        await update.message.reply_text("❌ Нет прав.")
        return
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("❌ /sendto_id 123456789 текст")
        return
    try:
        target_id = int(args[0])
        message_text = ' '.join(args[1:])
        await context.bot.send_message(chat_id=target_id, text=f"📨 Сообщение от админа:\n{message_text}")
        await update.message.reply_text(f"✅ Отправлено ID {target_id}")
    except ValueError:
        await update.message.reply_text("❌ ID должен быть числом.")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

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
        reply = f"Ошибка: {e}"
    await update.message.reply_text(reply)

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print(f"Ошибка: {context.error}")

# ========== MAIN ==========
def main():
    # Инициализируем БД
    asyncio.run(init_db())
    # Глобальный ADMIN_USER_ID будем загружать из базы? Упростим: при запуске ищем первого пользователя
    # Но оставим команду /init_admin для назначения админа. Для удобства: если база пуста, первый написавший /init_admin станет админом.
    # Для этого обновим переменную ADMIN_USER_ID в памяти.
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    # Загрузим существующего админа (первый в белом списке)
    whitelist = loop.run_until_complete(get_whitelist())
    if whitelist:
        global ADMIN_USER_ID
        ADMIN_USER_ID = whitelist[0]
        print(f"Администратор загружен: {ADMIN_USER_ID}")
    else:
        print("Белый список пуст. Назначьте администратора командой /init_admin")

    app = Application.builder().token(TELEGRAM_TOKEN).connect_timeout(30).read_timeout(30).write_timeout(30).build()

    # Регистрация хендлеров
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("getid", getid))
    app.add_handler(CommandHandler("remind", remind_command))
    app.add_handler(CommandHandler("mytasks", mytasks_command))
    app.add_handler(CommandHandler("delremind", delremind_command))
    app.add_handler(CommandHandler("sendto", sendto_command))
    app.add_handler(CommandHandler("sendto_id", sendto_id_command))
    app.add_handler(CommandHandler("init_admin", init_admin))
    app.add_handler(CommandHandler("add_user", add_user))
    app.add_handler(CommandHandler("remove_user", remove_user))
    app.add_handler(CommandHandler("list_users", list_users))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_error_handler(error_handler)

    if app.job_queue:
        app.job_queue.run_repeating(remind_job, interval=60, first=10)
        print("JobQueue включён.")
    else:
        print("JobQueue не доступен")

    print("Бот запущен")
    import time
    time.sleep(2)
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

if __name__ == "__main__":
    main()
