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
ADMIN_BOT_TOKEN = "9126496920:AAH3R7wayQ6cUE0JWLt3SVDSuOSq34gD0NA"
ADMIN_ID = 8808258682 # Твой ID
# ======================

bot = Bot(token=ADMIN_BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

data_dir = Path(os.environ.get("DATA_DIR", "/app/data"))
data_dir.mkdir(parents=True, exist_ok=True)
db_path = data_dir / "shop.db"

def get_db():
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def is_admin(user_id):
    return user_id == ADMIN_ID

def main_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 Список юзеров", callback_data="users_list")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="stats")]
    ])

@dp.message(Command("start"))
async def start(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Доступ запрещен.")
        return
    await message.answer("👑 <b>Админ-панель</b>\n\nВыберите действие:", reply_markup=main_menu())

@dp.callback_query(F.data == "main_menu")
async def to_main(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id): return
    await callback.message.edit_text("👑 <b>Админ-панель</b>\n\nВыберите действие:", reply_markup=main_menu())

@dp.callback_query(F.data == "users_list")
async def users_list(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id): return
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT user_id, username, full_name, sub_until FROM users ORDER BY sub_until DESC LIMIT 20")
    users = cur.fetchall()
    conn.close()

    if not users:
        await callback.message.edit_text("❌ Пользователей пока нет.", reply_markup=main_menu())
        return

    text = "👥 <b>Последние 20 юзеров:</b>\n\n"
    kb = []
    today = datetime.datetime.now().strftime("%Y-%m-%d")

    for u in users:
        sub = u['sub_until']
        status = "✅" if sub and sub >= today else "❌"
        text += f"{status} {u['full_name']} (@{u['username']})\n"
        kb.append([InlineKeyboardButton(text=f"{status} {u['full_name']} (@{u['username']})", callback_data=f"user_{u['user_id']}")])

    kb.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="main_menu")])
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data.startswith("user_"))
async def user_info(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id): return
    user_id = int(callback.data.split("_")[1])
    
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user = cur.fetchone()
    conn.close()

    if not user:
        await callback.answer("Пользователь не найден.")
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
    if not is_admin(callback.from_user.id): return
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
    msg = f"👑 <b>Администратор продлил вашу подписку!</b>\n\nТеперь она активна до: <b>{new_date_str}</b>"
    cur.execute("UPDATE users SET notify_msg = ? WHERE user_id = ?", (msg, user_id))
    conn.commit()
    conn.close()

    await callback.answer(f"Продлено до {new_date_str}")
    await user_info(callback)

@dp.callback_query(F.data.startswith("revoke_"))
async def revoke(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id): return
    user_id = int(callback.data.split("_")[1])

    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE users SET sub_until = NULL WHERE user_id = ?", (user_id,))
    msg = "❌ <b>Ваша подписка была отменена администратором.</b>"
    cur.execute("UPDATE users SET notify_msg = ? WHERE user_id = ?", (msg, user_id))
    conn.commit()
    conn.close()

    await callback.answer("Подписка забрана.")
    await user_info(callback)

@dp.callback_query(F.data == "stats")
async def stats(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id): return
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

async def main():
    print("Админ-бот запущен.")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
