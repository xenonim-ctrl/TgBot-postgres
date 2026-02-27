import logging
import os
import asyncio
from dotenv import load_dotenv
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
from db_connect import get_connection

load_dotenv()
logging.basicConfig(level=logging.INFO)

TOKEN = os.getenv("BOT_TOKEN")
ALLOWED_USER_ID = int(os.getenv("ALLOWED_USER_ID"))

TABLES = {

    "predictions": ["category", "prediction"]
}

STATE = {}

# --- Хелперы ---

def get_tables():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'public'
            """)
            return [row[0] for row in cur.fetchall()]

def get_table_columns(table_name):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(f"""
                SELECT column_name FROM information_schema.columns
                WHERE table_name = %s
            """, (table_name,))
            return [row[0] for row in cur.fetchall()]

async def check_access(update: Update):
    return update.effective_user.id == ALLOWED_USER_ID

# --- Хендлеры ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_access(update):
        return await update.message.reply_text("Нет доступа.")

    await update.message.reply_text("Выбери, что сделать:",
        reply_markup=ReplyKeyboardMarkup(
            [["Добавить в таблицу", "Просмотреть таблицу"], ["Создать новую таблицу"]],
            resize_keyboard=True))

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_access(update):
        return await update.message.reply_text("Нет доступа.")

    text = update.message.text.strip()

    if text == "Добавить в таблицу":
        tables = get_tables()
        STATE[update.effective_user.id] = {"mode": "insert"}
        await update.message.reply_text("Выбери таблицу:",
            reply_markup=ReplyKeyboardMarkup([[t] for t in tables] + [['Назад']], resize_keyboard=True))
    elif text == "Назад":
        STATE.pop(update.effective_user.id, None)  # очищаем состояние
        await start(update, context)
    elif text == "Просмотреть таблицу":
        tables = get_tables()
        STATE[update.effective_user.id] = {"mode": "view"}
        await update.message.reply_text("Выбери таблицу:",
            reply_markup=ReplyKeyboardMarkup([[t] for t in tables] + [['Назад']], resize_keyboard=True))

    elif text == "Создать новую таблицу":
        STATE[update.effective_user.id] = {"mode": "create_name"}
        await update.message.reply_text("Введи название новой таблицы:")

    elif user_state := STATE.get(update.effective_user.id):
        mode = user_state.get("mode")

        if mode == "insert" and "table" not in user_state:
            STATE[update.effective_user.id]["table"] = text

            if text == "potions":
                await update.message.reply_text(
                    "Введи отвар в формате:\nКатегория//Название//Травы (через запятую)//Рецепт")
            elif text == "herbs":
                await update.message.reply_text(
                    "Введи траву в формате:\nКатегория//Название//Стихия//Планета//Описание применения")
            elif text == "rituals":
                await update.message.reply_text(
                    "Введи ритуал в формате:\nКатегория//Название//Время ритуала//Инструменты//Для чего делается?//Эффект ритуала//Пошаговое описание ритуала и воздействие")
            else:
                await update.message.reply_text("Напиши строку в формате:\nКатегория//Предсказание")

        elif mode == "insert":
            table = user_state["table"]
            try:
                entries = text.strip().split("\n")
                data_to_insert = []

                if table == "potions":
                    for entry in entries:
                        try:
                            category, name, grows, recipe = map(str.strip, entry.split("//", 3))
                            data_to_insert.append((category, name, grows, recipe))
                        except ValueError:
                            continue

                    if data_to_insert:
                        with get_connection() as conn:
                            with conn.cursor() as cur:
                                cur.executemany(
                                    "INSERT INTO potions (category, name, grows, recipe) VALUES (%s, %s, %s, %s)",
                                    data_to_insert)
                                conn.commit()
                        await update.message.reply_text(f"Добавлено {len(data_to_insert)} отваров!")
                    else:
                        await update.message.reply_text("Нет валидных отваров для добавления.")

                elif table == "herbs":
                    data_to_insert = []
                    if entries:
                        with get_connection() as conn:
                            with conn.cursor() as cur:
                                # Получим все существующие имена трав из БД
                                cur.execute("SELECT name FROM herbs")
                                # Приводим к "базовому" виду (без пометок)
                                existing_names = set(row[0].split(" (")[0].strip() for row in cur.fetchall())

                        for entry in entries:
                            try:
                                category, name, caste, planet, use_in = map(str.strip, entry.split("//", 4))
                                base_name = name.split(" (")[0].strip()
                                if base_name not in existing_names:
                                    data_to_insert.append((category, name, caste, planet, use_in))
                                    existing_names.add(
                                        base_name)  # добавляем в набор, чтобы избежать повторов в одной сессии
                            except ValueError:
                                continue
                        if data_to_insert:
                            with get_connection() as conn:
                                with conn.cursor() as cur:
                                    cur.executemany(

                                        "INSERT INTO herbs (category, name, caste, planet, use_in) VALUES (%s, %s, %s, %s, %s)",

                                        data_to_insert)
                                    conn.commit()
                            await update.message.reply_text(f"Добавлено {len(data_to_insert)} новых трав!")
                        else:
                            await update.message.reply_text("Нет новых валидных трав для добавления.")
                elif table == "rituals":
                    for entry in entries:
                        try:
                            category, name, times_useful, instruments, for_what, effect, doing_ritual = map(str.strip, entry.split("//", 6))
                            data_to_insert.append((category, name, times_useful, instruments, for_what, effect, doing_ritual))
                        except ValueError:
                            continue

                    if data_to_insert:
                        with get_connection() as conn:
                            with conn.cursor() as cur:
                                cur.executemany(
                                    "INSERT INTO rituals (category, name, times_useful, instruments, for_what, effect, doing_ritual) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                                    data_to_insert)
                                conn.commit()
                        await update.message.reply_text(f"Добавлено {len(data_to_insert)} ритуалов!")
                    else:
                        await update.message.reply_text("Нет валидных ритуалов для добавления.")
                else:
                    for entry in entries:
                        try:
                            category, prediction = map(str.strip, entry.split("//", 1))
                            data_to_insert.append((category, prediction))
                        except ValueError:
                            continue

                    if data_to_insert:
                        with get_connection() as conn:
                            with conn.cursor() as cur:
                                cur.executemany(
                                    f"INSERT INTO {table} (category, prediction) VALUES (%s, %s)",
                                    data_to_insert)
                                conn.commit()
                        await update.message.reply_text(f"Добавлено {len(data_to_insert)} записей!")
                    else:
                        await update.message.reply_text("Нет валидных данных для добавления.")

                STATE.pop(update.effective_user.id)

            except Exception as e:
                await update.message.reply_text(f"Ошибка: {e}")

        elif mode == "view":
            table = text
            try:
                with get_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute(f"SELECT * FROM {table} LIMIT 5")
                        rows = cur.fetchall()
                        reply = "\n".join(str(r) for r in rows) or "Нет записей."
                        await update.message.reply_text(reply)
                STATE.pop(update.effective_user.id)
            except Exception as e:
                await update.message.reply_text(f"Ошибка: {e}")
        elif mode == "create_name":
                STATE[update.effective_user.id] = {"mode": "create_structure", "table_name": text}
                await update.message.reply_text("Теперь введи структуру таблицы (пример: id SERIAL PRIMARY KEY, category TEXT, text TEXT)")

        elif mode == "create_structure":
            table_name = user_state["table_name"]
            try:
                with get_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute(f"CREATE TABLE {table_name} ({text})")
                        conn.commit()
                await update.message.reply_text(f"Таблица {table_name} создана.")
                STATE.pop(update.effective_user.id)
            except Exception as e:
                await update.message.reply_text(f"Ошибка создания таблицы: {e}")

async def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT, message_handler))

    await app.run_polling()

if __name__ == "__main__":
    import nest_asyncio

    nest_asyncio.apply()  # <- позволяет повторно использовать цикл событий

    asyncio.run(main())