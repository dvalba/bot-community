import asyncio
import html
import os
import sqlite3

from dotenv import load_dotenv

from aiogram import Bot, Dispatcher
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

# Cargar .env (override=True para que el .env gane sobre variables ya exportadas)
load_dotenv(override=True)

TOKEN = os.getenv("TELEGRAM_TOKEN")
if not TOKEN:
    raise ValueError("No se encontró TELEGRAM_TOKEN en el entorno ni en .env")

DB_PATH = "comunidad.db"

bot = Bot(token=TOKEN)
dp = Dispatcher()


def init_db() -> None:
    """Crea la tabla si no existe."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS usuarios (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                socio TEXT
            )
        """)


def guardar_usuario(user_id: int, username: str, socio: str) -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            INSERT INTO usuarios (user_id, username, socio)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username = excluded.username,
                socio = excluded.socio
        """, (user_id, username, socio))


def obtener_reporte() -> list[tuple[str, int]]:
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.execute(
            "SELECT socio, COUNT(*) FROM usuarios GROUP BY socio ORDER BY COUNT(*) DESC"
        )
        return cursor.fetchall()


@dp.message(CommandStart())
async def cmd_start(message: Message) -> None:
    user_id = message.from_user.id
    username = message.from_user.username or "Sin username"

    # message.text puede ser None en teoría; lo protegemos
    texto = message.text or ""
    partes = texto.split(maxsplit=1)
    socio = partes[1] if len(partes) > 1 else "ninguno"

    # Limitar longitud del socio para evitar abusos
    socio = socio[:50]

    # SQLite es bloqueante: lo sacamos del event loop
    await asyncio.to_thread(guardar_usuario, user_id, username, socio)

    texto_bienvenida = (
        "¡Hola! Bienvenido a la comunidad.\n"
        "Tu registro ha sido vinculado correctamente.\n"
        f"Socio asignado: <b>{html.escape(socio)}</b>"
    )
    await message.answer(texto_bienvenida, parse_mode="HTML")


@dp.message(Command("reporte"))
async def cmd_reporte(message: Message) -> None:
    resultados = await asyncio.to_thread(obtener_reporte)

    if not resultados:
        await message.answer("Aún no hay usuarios registrados en la base de datos.")
        return

    reporte = "<b>📊 Reporte de Afiliados:</b>\n\n"
    for socio, total in resultados:
        reporte += f"• Socio <code>{html.escape(socio)}</code>: {total} usuarios\n"

    await message.answer(reporte, parse_mode="HTML")


async def main() -> None:
    init_db()
    print("Bot iniciado correctamente. Esperando mensajes...")
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())