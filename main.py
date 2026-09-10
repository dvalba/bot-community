import asyncio
import html
import os
import re
import sqlite3

from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message,
)

load_dotenv(override=True)

TOKEN = os.getenv("TELEGRAM_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
if not TOKEN:
    raise ValueError("No se encontró TELEGRAM_TOKEN")

DB_PATH = "comunidad.db"
BASE_URL_REGISTRO = "https://1w.example.com/registration"  # cámbialo

bot = Bot(token=TOKEN)
dp = Dispatcher()


# ---------------- FSM ----------------

class Registro(StatesGroup):
    esperando_id_plataforma = State()


# ---------------- DB ----------------

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS socios (
                socio_id TEXT PRIMARY KEY,
                telegram_id INTEGER,
                nombre TEXT,
                porcentaje REAL DEFAULT 30.0,
                activo INTEGER DEFAULT 1,
                creado TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS usuarios (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                socio_id TEXT,
                estado TEXT DEFAULT 'nuevo',
                id_plataforma TEXT,
                fecha_registro TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (socio_id) REFERENCES socios(socio_id)
            );
            CREATE TABLE IF NOT EXISTS secciones (
                clave TEXT PRIMARY KEY,
                titulo TEXT NOT NULL,
                contenido TEXT NOT NULL,
                orden INTEGER DEFAULT 0
            );
        """)


def get_socio(socio_id):
    with sqlite3.connect(DB_PATH) as conn:
        return conn.execute(
            "SELECT socio_id, nombre, activo FROM socios WHERE socio_id = ? AND activo = 1",
            (socio_id,),
        ).fetchone()


def registrar_usuario(user_id, username, socio_id):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            INSERT INTO usuarios (user_id, username, socio_id)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username = excluded.username,
                socio_id = COALESCE(usuarios.socio_id, excluded.socio_id)
        """, (user_id, username, socio_id))


def get_socio_de_usuario(user_id):
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT socio_id FROM usuarios WHERE user_id = ?", (user_id,)
        ).fetchone()
        return row[0] if row else None


def guardar_id_plataforma(user_id, id_plataforma):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            UPDATE usuarios
            SET id_plataforma = ?, estado = 'registrado'
            WHERE user_id = ?
        """, (id_plataforma, user_id))


def get_secciones():
    with sqlite3.connect(DB_PATH) as conn:
        return conn.execute(
            "SELECT clave, titulo FROM secciones ORDER BY orden"
        ).fetchall()


def get_seccion(clave):
    with sqlite3.connect(DB_PATH) as conn:
        return conn.execute(
            "SELECT titulo, contenido FROM secciones WHERE clave = ?", (clave,)
        ).fetchone()


def get_reporte_por_socio():
    with sqlite3.connect(DB_PATH) as conn:
        return conn.execute("""
            SELECT s.socio_id, s.nombre, COUNT(u.user_id)
            FROM socios s
            LEFT JOIN usuarios u ON u.socio_id = s.socio_id
            GROUP BY s.socio_id
            ORDER BY COUNT(u.user_id) DESC
        """).fetchall()


# ---------------- Keyboards ----------------

def kb_principal():
    filas = [[InlineKeyboardButton(text=titulo, callback_data=f"sec:{clave}")]
             for clave, titulo in get_secciones()]
    filas.append([InlineKeyboardButton(text="✅ Quiero registrarme",
                                       callback_data="reg:iniciar")])
    return InlineKeyboardMarkup(inline_keyboard=filas)


def kb_volver():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Volver al menú", callback_data="menu:home")]
    ])


def generar_enlace(socio_id):
    if socio_id:
        return f"{BASE_URL_REGISTRO}?ref={socio_id}"
    return BASE_URL_REGISTRO


# ---------------- Handlers ----------------

@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    username = message.from_user.username or "Sin username"

    partes = (message.text or "").split(maxsplit=1)
    socio_id = partes[1].strip()[:50] if len(partes) > 1 else None

    if socio_id:
        if not await asyncio.to_thread(get_socio, socio_id):
            await message.answer("Ese código de socio no es válido.")
            return
        await asyncio.to_thread(registrar_usuario, user_id, username, socio_id)

    await mostrar_menu(message, username)


async def mostrar_menu(message: Message, username: str):
    texto = (
        f"¡Hola, <b>{html.escape(username)}</b>! 👋\n\n"
        "Bienvenido a <b>iGamingCuba</b>, la comunidad donde aprendes, "
        "conectas y ganas.\n\n"
        "Explora las secciones y, cuando estés listo, regístrate."
    )
    await message.answer(texto, parse_mode="HTML", reply_markup=kb_principal())


@dp.message(F.text & ~F.text.startswith("/"))
async def texto_libre(message: Message, state: FSMContext):
    if await state.get_state() is not None:
        return
    texto = (message.text or "").strip()
    if re.fullmatch(r"[A-Za-z0-9_-]{3,30}", texto):
        if await asyncio.to_thread(get_socio, texto):
            username = message.from_user.username or "Sin username"
            await asyncio.to_thread(
                registrar_usuario, message.from_user.id, username, texto
            )
            await message.answer(
                f"✅ Código <b>{html.escape(texto)}</b> aplicado. "
                "Quedaste vinculado a ese socio.",
                parse_mode="HTML",
            )
            await mostrar_menu(message, username)
            return
    await message.answer(
        "No entendí. Usa /start para ver el menú o envía un código de socio."
    )


@dp.callback_query(F.data == "menu:home")
async def cb_menu(cq: CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        await cq.message.edit_text(
            "Menú principal. Elige una sección:", reply_markup=kb_principal()
        )
    except Exception:
        await cq.message.answer(
            "Menú principal. Elige una sección:", reply_markup=kb_principal()
        )
    await cq.answer()


@dp.callback_query(F.data.startswith("sec:"))
async def cb_seccion(cq: CallbackQuery):
    clave = cq.data.split(":", 1)[1]
    seccion = await asyncio.to_thread(get_seccion, clave)
    if not seccion:
        await cq.answer("Sección no encontrada", show_alert=True)
        return
    titulo, contenido = seccion
    await cq.message.edit_text(
        f"<b>{html.escape(titulo)}</b>\n\n{contenido}",
        parse_mode="HTML",
        reply_markup=kb_volver(),
        disable_web_page_preview=True,
    )
    await cq.answer()


@dp.callback_query(F.data == "reg:iniciar")
async def cb_registro(cq: CallbackQuery):
    socio_id = await asyncio.to_thread(get_socio_de_usuario, cq.from_user.id)
    enlace = generar_enlace(socio_id)
    await cq.message.edit_text(
        "Para acceder al grupo VIP y activar beneficios exclusivos, "
        "el primer paso es registrarte en nuestra plataforma asociada.\n\n"
        f"👉 <a href='{html.escape(enlace)}'>Regístrate aquí</a>\n\n"
        "Cuando termines, pulsa el botón y envíame tu ID de usuario.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Ya me registré",
                                  callback_data="reg:ya_hecho")],
            [InlineKeyboardButton(text="⬅️ Volver", callback_data="menu:home")],
        ]),
        disable_web_page_preview=True,
    )
    await cq.answer()


@dp.callback_query(F.data == "reg:ya_hecho")
async def cb_ya_hecho(cq: CallbackQuery, state: FSMContext):
    await state.set_state(Registro.esperando_id_plataforma)
    await cq.message.edit_text(
        "Perfecto. Envíame tu <b>ID de usuario</b> de la plataforma "
        "(el número de cuenta que te dio al registrarte).",
        parse_mode="HTML",
    )
    await cq.answer()


@dp.message(Registro.esperando_id_plataforma)
async def recibir_id(message: Message, state: FSMContext):
    id_plataforma = (message.text or "").strip()[:50]
    if not id_plataforma:
        await message.answer("Necesito un ID válido.")
        return
    await asyncio.to_thread(guardar_id_plataforma, message.from_user.id, id_plataforma)
    await state.clear()
    await message.answer(
        "✅ ¡Registro completado! En breve recibirás acceso al grupo VIP."
    )
    if ADMIN_ID:
        try:
            await bot.send_message(
                ADMIN_ID,
                f"🆕 Nuevo registro:\n"
                f"user_id: <code>{message.from_user.id}</code>\n"
                f"username: @{message.from_user.username or '-'}\n"
                f"id_plataforma: <code>{html.escape(id_plataforma)}</code>",
                parse_mode="HTML",
            )
        except Exception:
            pass


@dp.message(Command("reporte"))
async def cmd_reporte(message: Message):
    if ADMIN_ID and message.from_user.id != ADMIN_ID:
        await message.answer("No autorizado.")
        return
    filas = await asyncio.to_thread(get_reporte_por_socio)
    if not filas:
        await message.answer("Sin datos aún.")
        return
    txt = "<b>📊 Reporte por socio:</b>\n\n"
    for socio_id, nombre, total in filas:
        txt += (f"• <code>{html.escape(socio_id)}</code> "
                f"({html.escape(nombre or '-')}): {total}\n")
    await message.answer(txt, parse_mode="HTML")


# ---------------- Arranque ----------------

async def main():
    init_db()
    print("iGamingCubaBot iniciado.")
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())