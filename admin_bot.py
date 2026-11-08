import asyncio
import sqlite3
import datetime
import os
from pathlib import Path
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.filters import Command
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

# ===== НАСТРОЙКИ =====
ADMIN_BOT_TOKEN = "9126496920:AAH3R7wayQ6cUE0JWLt3SVDSuOSq34gD0NA"  # Админка
ADMIN_ID = 8808258682                     # Твой ID
MAIN_BOT_TOKEN = "9232358495:AAHAAXXqACqM4-RIDuS1Yxkb2PHOmVH9ZN0"  # Магазин (для уведомлений)
# ======================

# Бот админки
admin_bot = Bot(token=ADMIN_BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
# Бот магазина (нужен только для отправки сообщений)
main_bot = Bot(token=MAIN_BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))

dp = Dispatcher()

data_dir = Path(os.environ.get("DATA_DIR", "/app/data"))
data_dir.mkdir(parents=True, exist_ok=True)
db_path = data_dir / "shop.db"

def get_db():
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def main_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 Список юзеров", callback_data="users_list")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="stats")]
    ])

@dp.message(Command("start"))
async def start(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ Доступ запрещен.")
        return
    await message.answer("👑 <b>Админ-панель</b>\n\nВыберите действие:", reply_markup=main_menu())

@dp.callback_query(F.data == "main_menu")
async def to_main(callback: types.CallbackQuery):
    await callback.answer()
    if callback.from_user.id != ADMIN_ID: return
    await callback.message.edit_text("👑 <b>Админ-панель</b>\n\nВыберите действие:", reply_markup=main_menu())

@dp.callback_query(F.data == "users_list")
async def users_list(callback: types.CallbackQuery):
    await callback.answer()
    if callback.from_user.id != ADMIN_ID: return
    
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT user_id, username, full_name, sub_until FROM users ORDER BY sub_until DESC")
    users = cur.fetchall()
    conn.close()

    if not users:
        await callback.message.edit_text("❌ Пользователей пока нет.", reply_markup=main_menu())
        return

    text = "👥 <b>Все пользователи:</b>\n\n"
    kb = []
    today = datetime.datetime.now().strftime("%Y-%m-%d")

    # Выводим всех, разбивая на страницы по 10 (для удобства)
    for u in users:
        sub = u['sub_until']
        status = "✅" if sub and sub >= today else "❌"
        text += f"{status} {u['full_name']} (@{u['username']})\n"
        
        # В кнопку пихаем ID и имя
        kb.append([InlineKeyboardButton(
            text=f"{status} {u['full_name']}", 
            callback_data=f"user_{u['user_id']}"
        )])

    kb.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="main_menu")])
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data.startswith("user_"))
async def user_info(callback: types.CallbackQuery):
    await callback.answer()
    if callback.from_user.id != ADMIN_ID: return
    user_id = int(callback.data.split("_")[1])
    
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user = cur.fetchone()
    conn.close()

    if not user:
        await callback.message.edit_text("❌ Пользователь не найден.", reply_markup=main_menu())
        return

    today = datetime.datetime.now().strftime("%Y-%m-%d")
    sub = user['sub_until']
    status = "✅ Активна" if sub and sub >= today else "❌ Истекла"
    sub_text = sub if sub else "Нет"

    text = (
        f"👤 <b>Инфо о юзере</b>\n\n"
        f"Имя: {user['full_name']}\n"
        f"Юзер: @{user['username']}\n"
        f"ID: <code>{user['user_id']}</code>\n"
        f"Подписка: {sub_text} ({status})"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Продлить (30 дней)", callback_data=f"extend_{user_id}")],
        [InlineKeyboardButton(text="❌ Забрать подписку", callback_data=f"revoke_{user_id}")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="users_list")]
    ])

    await callback.message.edit_text(text, reply_markup=kb)

@dp.callback_query(F.data.startswith("extend_"))
async def extend(callback: types.CallbackQuery):
    await callback.answer("Продлеваю...")
    if callback.from_user.id != ADMIN_ID: return
    user_id = int(callback.data.split("_")[1])
    days = 30

    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT sub_until FROM users WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    today = datetime.datetime.now()

    if row and row['sub_until'] and row['sub_until'] > today.strftime("%Y-%m-%d"):
        base = datetime.datetime.strptime(row['sub_until'], "%Y-%m-%d")
        new_date = base + datetime.timedelta(days=days)
    else:
        new_date = today + datetime.timedelta(days=days)
    
    new_date_str = new_date.strftime("%Y-%m-%d")
    
    cur.execute("UPDATE users SET sub_until = ? WHERE user_id = ?", (new_date_str, user_id))
    conn.commit()
    conn.close()

    # Уведомляем юзера через ОСНОВНОГО бота
    try:
        msg = f"👑 <b>Администратор продлил вашу подписку!</b>\n\nТеперь она активна до: <b>{new_date_str}</b>"
        await main_bot.send_message(user_id, msg)
    except Exception as e:
        print(f"Не удалось отправить уведомление: {e}")

    await user_info(callback)

@dp.callback_query(F.data.startswith("revoke_"))
async def revoke(callback: types.CallbackQuery):
    await callback.answer("Забираю...")
    if callback.from_user.id != ADMIN_ID: return
    user_id = int(callback.data.split("_")[1])

    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE users SET sub_until = NULL WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

    # Уведомляем юзера
    try:
        msg = "❌ <b>Ваша подписка была отменена администратором.</b>"
        await main_bot.send_message(user_id, msg)
    except Exception as e:
        print(f"Не удалось отправить уведомление: {e}")

    await user_info(callback)

@dp.callback_query(F.data == "stats")
async def stats(callback: types.CallbackQuery):
    await callback.answer()
    if callback.from_user.id != ADMIN_ID: return
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) as cnt FROM users")
    total = cur.fetchone()['cnt']
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    cur.execute("SELECT COUNT(*) as cnt FROM users WHERE sub_until >= ?", (today,))
    active = cur.fetchone()['cnt']
    conn.close()

    text = (
        f"📊 <b>Статистика:</b>\n\n"
        f"Всего юзеров: {total}\n"
        f"С активной подпиской: {active}\n"
        f"Без подписки: {total - active}"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="main_menu")]])
    await callback.message.edit_text(text, reply_markup=kb)

# ===== НОВЫЙ ХЕНДЛЕР: УВЕДОМЛЕНИЕ О НОВОМ START =====
@dp.message(Command("start"))
async def catch_start(message: types.Message):
    # Если это не админ, просто выходим (админка уже обработала выше)
    if message.from_user.id == ADMIN_ID:
        return
    
    # Отправляем тебе уведомление о новом юзере
    user = message.from_user
    text = (
        f"🔔 <b>Новый пользователь в магазине!</b>\n\n"
        f"Имя: {user.full_name}\n"
        f"Юзер: @{user.username}\n"
        f"ID: <code>{user.id}</code>"
    )
    try:
        await admin_bot.send_message(ADMIN_ID, text)
    except Exception as e:
        print(f"Не удалось отправить уведомление админу: {e}")

async def main():
    print("Админ-бот запущен.")
    await dp.start_polling(admin_bot, allowed_updates=["message", "callback_query"])

if __name__ == "__main__":
    asyncio.run(main())
