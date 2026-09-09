import asyncio
import logging
import sqlite3
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import InlineKeyboardBuilder

# Configuración de logs
logging.basicConfig(level=logging.INFO)

# CONFIGURA TU TOKEN AQUÍ
TOKEN = "8706816060:AAHANJNJ9kLrIXqLlyqbWQKMjho7EXCH5aA"

# CONFIGURACIÓN DE SOCIOS Y SUS ENLACES
# Aquí defines qué enlace de 1win le corresponde a cada socio o a ti directamente
SOCIOS_CONFIG = {
    "directo_david": {
        "nombre": "David (Nodo Central)",
        "link_1win": "https://1win.xxx/tu-link-maestro?p=tu_codigo"
    },
    "socio_juan": {
        "nombre": "Juan",
        "link_1win": "https://1win.xxx/link-de-juan?p=codigo_juan"
    },
    "socio_ana": {
        "nombre": "Ana",
        "link_1win": "https://1win.xxx/link-de-ana?p=codigo_ana"
    }
}

# Inicializar Base de Datos SQLite local
def init_db():
    conn = sqlite3.connect("comunidad.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            telegram_id INTEGER PRIMARY KEY,
            username TEXT,
            partner TEXT,
            win_id TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db()

# Estados para la máquina de estados (FSM) al registrar el ID de 1win
class RegistroStates(StatesGroup):
    esperando_win_id = State()

# Inicializar Bot y Dispatcher
bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# 1. Comando /start con detección de socios (Ej: t.me/TuBot?start=socio_juan)
@dp.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    args = message.text.split(maxsplit=1)
    # Si entra sin parámetro, por defecto se asigna al nodo principal 'directo_david'
    partner_key = args[1] if len(args) > 1 else "directo_david"
    
    # Validar si el socio existe, si no, usar el predeterminado
    if partner_key not in SOCIOS_CONFIG:
        partner_key = "directo_david"

    user_id = message.from_user.id
    username = message.from_user.username or "Sin username"

    # Guardar o actualizar usuario en la base de datos con su partner asignado
    conn = sqlite3.connect("comunidad.db")
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO usuarios (telegram_id, username, partner) 
        VALUES (?, ?, ?)
        ON CONFLICT(telegram_id) DO UPDATE SET partner = ?
    """, (user_id, username, partner_key, partner_key))
    conn.commit()
    conn.close()

    socio_info = SOCIOS_CONFIG[partner_key]

    # Construir botón para ir a 1win
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="🎰 Registrarse en 1win", url=socio_info["link_1win"]))
    builder.row(types.InlineKeyboardButton(text="✅ Ya me registré (Enviar mi ID)", callback_data="enviar_id"))

    texto = (
        f"¡Bienvenido a la comunidad privada!\n\n"
        f"Hemos detectado tu acceso a través de nuestro canal de referencia.\n"
        f"Para acceder al grupo VIP y activar beneficios exclusivos, el primer paso es registrarte en nuestra plataforma asociada:\n\n"
        f"👉 Haz clic en el botón de abajo, crea tu cuenta y luego haz clic en 'Ya me registré' para enviar tu ID de usuario."
    )

    await message.answer(texto, reply_markup=builder.as_markup())

# 2. Botón para que el usuario envíe su ID de 1win
@dp.callback_query(F.data == "enviar_id")
async def process_callback_id(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Por favor, escribe aquí tu **ID de usuario de 1win** (es el número de cuenta que te da la plataforma):")
    await state.set_state(RegistroStates.esperando_win_id)
    await callback.answer()

# 3. Capturar el ID de 1win que escribe el usuario
@dp.message(RegistroStates.esperando_win_id)
async def recibir_win_id(message: types.Message, state: FSMContext):
    win_id = message.text.strip()
    user_id = message.from_user.id

    # Guardar el ID de 1win en la base de datos
    conn = sqlite3.connect("comunidad.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE usuarios SET win_id = ? WHERE telegram_id = ?", (win_id, user_id))
    conn.commit()
    conn.close()

    await state.clear()

    # Enlace a tu grupo VIP principal de Telegram
    link_grupo_vip = "https://t.me/+TU_ENLACE_DE_GRUPO_VIP"

    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="🚀 Entrar al Grupo VIP", url=link_grupo_vip))

    await message.answer(
        f"¡Perfecto! Tu ID `{win_id}` ha quedado registrado y vinculado correctamente.\n\n"
        f"Ya puedes unirte a nuestro grupo exclusivo de estrategias:",
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )

# 4. Panel Secreto para ti o para los socios (Ej: /reporte socio_juan)
@dp.message(Command("reporte"))
async def cmd_reporte(message: types.Message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("Uso correcto: `/reporte socio_juan` o `/reporte directo_david`", parse_mode="Markdown")
        return

    partner_key = args[1].strip()
    
    conn = sqlite3.connect("comunidad.db")
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*), SUM(CASE WHEN win_id IS NOT NULL THEN 1 ELSE 0 END) FROM usuarios WHERE partner = ?", (partner_key,))
    total_registrados, con_win_id = cursor.fetchone()
    conn.close()

    await message.answer(
        f"📊 **Reporte para el socio: `{partner_key}`**\n\n"
        f"• Total usuarios que entraron por su link: `{total_registrados or 0}`\n"
        f"• Usuarios con ID de 1win vinculado: `{con_win_id or 0}`",
        parse_mode="Markdown"
    )

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())