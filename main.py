import os
import sqlite3
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

# 1. Cargar el token de forma segura desde las variables de entorno
TOKEN = os.getenv("TELEGRAM_TOKEN")

if not TOKEN:
    raise ValueError("No se encontró el TELEGRAM_TOKEN en las variables de entorno.")

bot = Bot(token=TOKEN)
dp = Dispatcher()

# 2. Inicializar la base de datos local SQLite
def init_db():
    conn = sqlite3.connect("comunidad.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            socio TEXT
        )
    """)
    conn.commit()
    conn.close()

# 3. Manejador para el comando /start con soporte para sub-afiliados (ej: /start socio_juan)
@dp.message(CommandStart())
async def cmd_start(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or "Sin username"
    
    # Extraer el argumento que viene después de /start (el socio/afiliado)
    args = message.text.split(maxsplit=1)
    socio = args[1] if len(args) > 1 else "ninguno"

    # Guardar o actualizar en la base de datos
    conn = sqlite3.connect("comunidad.db")
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO usuarios (user_id, username, socio)
        VALUES (?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET socio=excluded.socio
    """, (user_id, username, socio))
    conn.commit()
    conn.close()

    # Mensaje de respuesta para el usuario
    texto_bienvenida = (
        f"¡Hola! Bienvenido a la comunidad.\n"
        f"Tu registro ha sido vinculado correctamente.\n"
        f"Socio asignado: <b>{socio}</b>"
    )
    await message.answer(texto_bienvenida, parse_mode="HTML")

# 4. Comando de reporte rápido para verificar los socios (ej: /stats o /reporte)
@dp.message(Command("reporte"))
async def cmd_reporte(message: Message):
    conn = sqlite3.connect("comunidad.db")
    cursor = conn.cursor()
    cursor.execute("SELECT socio, COUNT(*) FROM usuarios GROUP BY socio")
    resultados = cursor.fetchall()
    conn.close()

    if not resultados:
        await message.answer("Aún no hay usuarios registrados en la base de datos.")
        return

    reporte = "<b>📊 Reporte de Afiliados:</b>\n\n"
    for socio, total in resultados:
        reporte += f"• Socio <code>{socio}</code>: {total} usuarios\n"

    await message.answer(reporte, parse_mode="HTML")

# 5. Función principal de arranque
async def main():
    init_db()
    print("Bot iniciado correctamente. Esperando mensajes...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())