import asyncio
import aiohttp
import datetime
import logging
import sqlite3
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# Корректный импорт планировщика
try:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
except ImportError:
    AsyncIOScheduler = None

# Импортируем функции из database.py
from database import init_db, add_player, get_players, delete_player

# --- КОНФИГУРАЦИЯ ---
TELEGRAM_TOKEN = "PUT UR BOT TOKEN HERE"
BRAWL_API_TOKEN = "BSAPI TOKEN"
DB_NAME = "brawl_data.db"

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()
scheduler = AsyncIOScheduler() if AsyncIOScheduler else None


class Form(StatesGroup):
    waiting_for_tag = State()


# --- РАБОТА С БД ДЛЯ НАСТРОЕК (ИСПРАВЛЕНО) ---

def init_settings_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_settings (
            user_id INTEGER PRIMARY KEY, 
            notify_enabled INTEGER DEFAULT 1
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS last_battles (
            tag TEXT PRIMARY KEY, 
            last_battle_time TEXT
        )
    """)
    conn.commit()
    conn.close()


def toggle_notifs(user_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    # Проверяем текущий статус конкретного юзера
    cursor.execute("SELECT notify_enabled FROM user_settings WHERE user_id = ?", (user_id,))
    res = cursor.fetchone()

    if res is None:
        # Если юзера нет, создаем запись (по умолчанию было 1, значит ставим 0)
        new_status = 0
        cursor.execute("INSERT INTO user_settings (user_id, notify_enabled) VALUES (?, ?)", (user_id, new_status))
    else:
        # Инвертируем текущий статус юзера
        new_status = 1 - res[0]
        cursor.execute("UPDATE user_settings SET notify_enabled = ? WHERE user_id = ?", (new_status, user_id))

    conn.commit()
    conn.close()
    return new_status


def get_notif_status(user_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT notify_enabled FROM user_settings WHERE user_id = ?", (user_id,))
    res = cursor.fetchone()
    conn.close()
    # Если записи нет, считаем, что уведомления включены по умолчанию
    return res[0] if res is not None else 1


def set_last_battle_time(tag, time_str):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO last_battles (tag, last_battle_time) VALUES (?, ?)", (tag, time_str))
    conn.commit()
    conn.close()


def get_last_battle_time(tag):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT last_battle_time FROM last_battles WHERE tag = ?", (tag,))
    res = cursor.fetchone()
    conn.close()
    return res[0] if res else None


# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---

def get_time_ago(time_str):
    try:
        past = datetime.datetime.strptime(time_str[:15], "%Y%m%dT%H%M%S").replace(tzinfo=datetime.timezone.utc)
        now = datetime.datetime.now(datetime.timezone.utc)
        diff = now - past
        seconds = int(diff.total_seconds())
        if seconds < 60: return "только что"
        if seconds < 3600: return f"{seconds // 60} мин. назад"
        if seconds < 86400: return f"{seconds // 3600} ч. назад"
        return f"{seconds // 86400} дн. назад"
    except:
        return "неизвестно"


async def fetch_brawl(url):
    headers = {"Authorization": f"Bearer {BRAWL_API_TOKEN}"}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=10) as resp:
                return await resp.json() if resp.status == 200 else None
    except:
        return None


def get_main_menu_kb(user_id):
    status = get_notif_status(user_id)
    notif_btn = "🔔 Уведомления: ВКЛ" if status == 1 else "🔕 Уведомления: ВЫКЛ"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔍 Добавить по тегу", callback_data="add_tag")],
        [InlineKeyboardButton(text="📜 Мой список", callback_data="show_list")],
        [InlineKeyboardButton(text=notif_btn, callback_data="toggle_notifications")]
    ])


# --- ФОНОВАЯ ПРОВЕРКА ---

async def check_new_battles():
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        # Фильтруем только те связки тег+юзер, где у юзера включены уведомления
        cursor.execute("""
            SELECT p.user_id, p.player_tag FROM tracked_players p 
            JOIN user_settings s ON p.user_id = s.user_id 
            WHERE s.notify_enabled = 1
        """)
        tasks = cursor.fetchall()
        conn.close()

        for user_id, tag in tasks:
            player_tag_notifications = 0
            MAX_NOTIFS_PER_TAG = 2

            log_data = await fetch_brawl(f"https://api.brawlstars.com/v1/players/%23{tag}/battlelog")
            if not log_data or 'items' not in log_data or not log_data['items']:
                continue

            saved_time = get_last_battle_time(tag)
            if saved_time is None:
                set_last_battle_time(tag, log_data['items'][0]['battleTime'])
                continue

            new_battles = []
            for i in range(min(MAX_NOTIFS_PER_TAG, len(log_data['items']))):
                battle = log_data['items'][i]
                if battle['battleTime'] == saved_time:
                    break
                new_battles.append(battle)

            for battle in reversed(new_battles):
                if player_tag_notifications >= MAX_NOTIFS_PER_TAG:
                    break

                mode = battle['event'].get('mode', 'Unknown').capitalize()
                battle_info = battle.get('battle', {})
                res = battle_info.get('result', f"Место: {battle_info.get('rank', '?')}").upper()

                brawler_name = "Unknown"
                entities = []
                if 'teams' in battle_info:
                    for team in battle_info['teams']: entities.extend(team)
                elif 'players' in battle_info:
                    entities.extend(battle_info['players'])

                for p in entities:
                    if p.get('tag', '').replace("#", "") == tag:
                        brawler_name = p.get('brawler', {}).get('name', '???').upper()

                try:
                    await bot.send_message(
                        user_id,
                        f"🔔 **#{tag} сыграл новый матч!**\n"
                        f"🛡 Боец: **{brawler_name}**\n"
                        f"📝 Режим: {mode}\n"
                        f"📊 Результат: {res}"
                    )
                    set_last_battle_time(tag, battle['battleTime'])
                    player_tag_notifications += 1
                    await asyncio.sleep(0.1)
                except Exception as e:
                    logging.error(f"Ошибка отправки пользователю {user_id}: {e}")

    except Exception as e:
        logging.error(f"Ошибка в цикле проверки: {e}")


# --- ОБРАБОТЧИКИ ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    init_db()
    init_settings_db()
    await message.answer("🚀 **Brawl Stats Tracker**\nГлавное меню:",
                         reply_markup=get_main_menu_kb(message.from_user.id))


@dp.callback_query(F.data == "toggle_notifications")
async def handle_toggle(callback: types.CallbackQuery):
    # Теперь меняет статус только для callback.from_user.id
    new_status = toggle_notifs(callback.from_user.id)
    await callback.answer(f"Уведомления {'включены' if new_status == 1 else 'выключены'}!")
    await callback.message.edit_reply_markup(reply_markup=get_main_menu_kb(callback.from_user.id))


@dp.callback_query(F.data == "back_to_main")
async def back_to_main(callback: types.CallbackQuery):
    await callback.message.edit_text("🚀 **Главное меню:**", reply_markup=get_main_menu_kb(callback.from_user.id))


@dp.callback_query(F.data == "add_tag")
async def start_adding(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(Form.waiting_for_tag)
    await callback.message.edit_text("📝 **Введи тег игрока (без #):**")


@dp.message(Form.waiting_for_tag)
async def process_tag(message: types.Message, state: FSMContext):
    tag = message.text.strip().upper().replace("#", "")
    profile = await fetch_brawl(f"https://api.brawlstars.com/v1/players/%23{tag}")

    if not profile:
        kb = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад в меню", callback_data="back_to_main")]])
        await message.answer(f"❌ Профиль `#{tag}` не найден!", reply_markup=kb)
    elif add_player(message.from_user.id, tag):
        log = await fetch_brawl(f"https://api.brawlstars.com/v1/players/%23{tag}/battlelog")
        if log and 'items' in log:
            set_last_battle_time(tag, log['items'][0]['battleTime'])
        await message.answer(f"✅ **{profile.get('name')}** добавлен!",
                             reply_markup=get_main_menu_kb(message.from_user.id))
    else:
        await message.answer("⚠️ Игрок уже в списке.", reply_markup=get_main_menu_kb(message.from_user.id))
    await state.clear()


@dp.callback_query(F.data == "show_list")
async def show_list(callback: types.CallbackQuery):
    tags = get_players(callback.from_user.id)
    if not tags:
        await callback.message.edit_text("❌ Список пуст!", reply_markup=get_main_menu_kb(callback.from_user.id))
        return
    btns = [[InlineKeyboardButton(text=f"👤 #{t}", callback_data=f"stats_{t}")] for t in tags]
    btns.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_main")])
    await callback.message.edit_text("📋 **Выберите профиль:**", reply_markup=InlineKeyboardMarkup(inline_keyboard=btns))


@dp.callback_query(F.data.startswith("stats_"))
async def show_stats(callback: types.CallbackQuery):
    tag = callback.data.split("_")[1]
    player = await fetch_brawl(f"https://api.brawlstars.com/v1/players/%23{tag}")
    log = await fetch_brawl(f"https://api.brawlstars.com/v1/players/%23{tag}/battlelog")
    if not player: return

    battles = log.get('items', []) if log else []
    wins = sum(1 for b in battles if
               b.get('battle', {}).get('result') == 'victory' or (b.get('battle', {}).get('rank', 10) <= 3))
    wr = round((wins / len(battles) * 100), 1) if battles else 0

    res_msg = (
        f"👤 **{player.get('name')}** (`#{tag}`)\n"
        f"━━━━━━━━━━━━\n"
        f"🏆 **Кубки:** `{player.get('trophies', 0)}` (Max: `{player.get('highestTrophies', 0)}`)\n"
        f"📈 **Win Rate (25 игр):** `{wr}%` {'🔥' if wr > 60 else '📊'}\n"
        f"━━━━━━━━━━━━\n"
        f"🎖 **Победы:**\n"
        f"├ 👤 Соло: `{player.get('soloVictories', 0)}`\n"
        f"├ 👥 Дуо: `{player.get('duoVictories', 0)}`\n"
        f"└ ⚔️ 3v3: `{player.get('3vs3Victories', 0)}`\n"
        f"━━━━━━━━━━━━\n"
        f"🕒 **Последний матч:**\n"
        f"└ {battles[0]['event'].get('mode', '???').capitalize() if battles else 'Нет'} ({get_time_ago(battles[0]['battleTime']) if battles else '-'})\n"
        f"━━━━━━━━━━━━\n"
        f"🛡 **Клуб:** {player.get('club', {}).get('name', 'Нет')}"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📜 Посмотреть лог боев", callback_data=f"log_{tag}")],
        [InlineKeyboardButton(text="🔄 Обновить", callback_data=f"stats_{tag}")],
        [InlineKeyboardButton(text="🗑 Удалить", callback_data=f"del_{tag}")],
        [InlineKeyboardButton(text="⬅️ К списку", callback_data="show_list")]
    ])
    await callback.message.edit_text(res_msg, parse_mode="Markdown", reply_markup=kb)


@dp.callback_query(F.data.startswith("log_"))
async def show_log(callback: types.CallbackQuery):
    tag = callback.data.split("_")[1]
    log_data = await fetch_brawl(f"https://api.brawlstars.com/v1/players/%23{tag}/battlelog")
    if not log_data or 'items' not in log_data: return

    log_text = f"📝 **Последние бои (#{tag}):**\n\n"
    btns = []

    for i, m in enumerate(log_data['items'][:10]):
        battle = m.get('battle', {})
        res = "✅" if battle.get('result') == 'victory' or (battle.get('rank', 10) <= 3) else "❌"
        mode = m['event'].get('mode', '???').capitalize()

        b_name = "???"
        all_players = []
        if 'teams' in battle:
            for team in battle['teams']: all_players.extend(team)
        elif 'players' in battle:
            all_players.extend(battle['players'])

        for p in all_players:
            if p.get('tag', '').replace("#", "") == tag:
                b_name = p.get('brawler', {}).get('name', '???').upper()

        log_text += f"{i + 1}. {res} **{mode}** | {b_name}\n└ 🕒 _{get_time_ago(m['battleTime'])}_\n\n"
        btns.append([InlineKeyboardButton(text=f"🔍 Детали матча №{i + 1}", callback_data=f"match_{tag}_{i}")])

    btns.append([InlineKeyboardButton(text="⬅️ Назад к статистике", callback_data=f"stats_{tag}")])
    await callback.message.edit_text(log_text, parse_mode="Markdown",
                                     reply_markup=InlineKeyboardMarkup(inline_keyboard=btns))


@dp.callback_query(F.data.startswith("match_"))
async def show_match_details(callback: types.CallbackQuery):
    _, tag, idx = callback.data.split("_")
    idx = int(idx)
    log_data = await fetch_brawl(f"https://api.brawlstars.com/v1/players/%23{tag}/battlelog")
    if not log_data or idx >= len(log_data['items']): return

    match = log_data['items'][idx]
    battle = match.get('battle', {})
    detail_text = f"⚔️ **ДЕТАЛИ МАТЧА: {match['event'].get('mode', '???').upper()}**\n"
    detail_text += f"🕒 {get_time_ago(match['battleTime'])}\n"
    detail_text += f"━━━━━━━━━━━━\n\n"

    if 'teams' in battle:
        for t_idx, team in enumerate(battle['teams']):
            detail_text += f"{'🟦 ВАША КОМАНДА' if t_idx == 0 else '🟥 ПРОТИВНИКИ'}:\n"
            for p in team:
                p_brawler = p.get('brawler', {}).get('name', '???').upper()
                line = f"└ `{p_brawler}` — **{p.get('name', '???')}**"
                if p.get('tag', '').replace("#", "") == tag: line = "🌟 " + line
                detail_text += line + "\n"
            detail_text += "\n"
    elif 'players' in battle:
        detail_text += "🏆 **РЕЙТИНГ ИГРОКОВ:**\n"
        for p in battle['players']:
            p_brawler = p.get('brawler', {}).get('name', '???').upper()
            line = f"└ {p.get('rank', '?')}. `{p_brawler}` — {p.get('name', '???')}"
            if p.get('tag', '').replace("#", "") == tag: line = "🌟 " + line
            detail_text += line + "\n"

    kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад к логу", callback_data=f"log_{tag}")]])
    await callback.message.edit_text(detail_text, parse_mode="Markdown", reply_markup=kb)


@dp.callback_query(F.data.startswith("del_"))
async def del_tag(callback: types.CallbackQuery):
    tag = callback.data.split("_")[1]
    delete_player(callback.from_user.id, tag)
    await show_list(callback)


async def main():
    init_db()
    init_settings_db()
    if scheduler:
        scheduler.add_job(check_new_battles, "interval", minutes=1)
        scheduler.start()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())