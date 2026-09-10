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
    BotCommand,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

# ---------- Config ----------

load_dotenv(override=True)

TOKEN = os.getenv("TELEGRAM_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0") or "0")
BASE_URL_REGISTRO = os.getenv("BASE_URL_REGISTRO", "https://example.com/register")

if not TOKEN:
    raise ValueError("Falta TELEGRAM_TOKEN en el entorno o en .env")

DB_PATH = "comunidad.db"

bot = Bot(token=TOKEN)
dp = Dispatcher()


class Registro(StatesGroup):
    esperando_id_plataforma = State()


# ---------- Base de datos ----------

def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with _connect() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS socios (
                socio_id TEXT PRIMARY KEY,
                telegram_id INTEGER,
                nombre TEXT,
                porcentaje REAL DEFAULT 30.0,
                activo INTEGER DEFAULT 1,
                creado TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS secciones (
                clave TEXT PRIMARY KEY,
                titulo TEXT NOT NULL,
                contenido TEXT NOT NULL,
                orden INTEGER DEFAULT 0
            );
        """)

        cols = {r[1] for r in conn.execute("PRAGMA table_info(usuarios)")}

        if not cols:
            conn.execute("""
                CREATE TABLE usuarios (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    socio_id TEXT,
                    estado TEXT DEFAULT 'nuevo',
                    id_plataforma TEXT,
                    fecha_registro TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
        else:
            if "socio" in cols and "socio_id" not in cols:
                conn.execute("ALTER TABLE usuarios RENAME COLUMN socio TO socio_id")
            for col, tipo in [
                ("estado", "TEXT DEFAULT 'nuevo'"),
                ("id_plataforma", "TEXT"),
                ("fecha_registro", "TEXT"),
            ]:
                if col not in cols:
                    conn.execute(f"ALTER TABLE usuarios ADD COLUMN {col} {tipo}")


def get_socio(socio_id):
    with _connect() as conn:
        row = conn.execute(
            "SELECT socio_id, nombre FROM socios WHERE socio_id = ? AND activo = 1",
            (socio_id,),
        ).fetchone()
        return dict(row) if row else None


def registrar_usuario(user_id, username, socio_id):
    with _connect() as conn:
        conn.execute("""
            INSERT INTO usuarios (user_id, username, socio_id)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username = excluded.username,
                socio_id = COALESCE(usuarios.socio_id, excluded.socio_id)
        """, (user_id, username, socio_id))


def get_socio_de_usuario(user_id):
    with _connect() as conn:
        row = conn.execute(
            "SELECT socio_id FROM usuarios WHERE user_id = ?", (user_id,)
        ).fetchone()
        return row[0] if row else None


def guardar_id_plataforma(user_id, id_plataforma):
    with _connect() as conn:
        conn.execute("""
            UPDATE usuarios
            SET id_plataforma = ?, estado = 'registrado'
            WHERE user_id = ?
        """, (id_plataforma, user_id))


def get_secciones():
    with _connect() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT clave, titulo FROM secciones ORDER BY orden"
        )]


def get_seccion(clave):
    with _connect() as conn:
        row = conn.execute(
            "SELECT titulo, contenido FROM secciones WHERE clave = ?", (clave,)
        ).fetchone()
        return dict(row) if row else None


def get_reporte_por_socio():
    with _connect() as conn:
        return [dict(r) for r in conn.execute("""
            SELECT s.socio_id, s.nombre, COUNT(u.user_id) AS total
            FROM socios s
            LEFT JOIN usuarios u ON u.socio_id = s.socio_id
            GROUP BY s.socio_id
            ORDER BY total DESC
        """)]


# ---------- UI ----------

def kb_principal():
    filas = [
        [InlineKeyboardButton(text=s["titulo"], callback_data=f"sec:{s['clave']}")]
        for s in get_secciones()
    ]
    filas.append([InlineKeyboardButton(
        text="✅ Quiero registrarme", callback_data="reg:iniciar"
    )])
    return InlineKeyboardMarkup(inline_keyboard=filas)


def kb_volver():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Volver al menú", callback_data="menu:home")]
    ])


def kb_registro():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Ya me registré", callback_data="reg:ya_hecho")],
        [InlineKeyboardButton(text="⬅️ Volver", callback_data="menu:home")],
    ])


def texto_bienvenida(username: str, socio: str | None) -> str:
    lineas = [
        f"¡Hola, <b>{html.escape(username)}</b>! 👋",
        "",
        "Bienvenido a <b>iGamingCuba</b>, la comunidad donde aprendes, "
        "conectas y ganas.",
        "",
    ]
    if socio:
        lineas += [
            f"🔗 Estás vinculado al socio: <code>{html.escape(socio)}</code>",
            "",
        ]
    lineas += [
        "<b>Comandos disponibles:</b>",
        "/start — Menú principal",
        "/secciones — Ver secciones de la comunidad",
        "/registro — Iniciar registro en la plataforma",
        "/ayuda — Cómo usar el bot",
        "",
        "O usa los botones de abajo 👇",
    ]
    return "\n".join(lineas)


def texto_registro(socio_id: str | None) -> str:
    enlace = generar_enlace(socio_id)
    return (
        "Para acceder al grupo VIP y activar beneficios exclusivos, "
        "el primer paso es registrarte en nuestra plataforma asociada.\n\n"
        f"👉 <a href='{html.escape(enlace)}'>Regístrate aquí</a>\n\n"
        "Cuando termines, pulsa el botón de abajo y envíame tu ID de usuario."
    )


def generar_enlace(socio_id: str | None) -> str:
    if socio_id:
        sep = "&" if "?" in BASE_URL_REGISTRO else "?"
        return f"{BASE_URL_REGISTRO}{sep}ref={socio_id}"
    return BASE_URL_REGISTRO


# ---------- Handlers ----------

@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    username = message.from_user.username or "Sin username"

    partes = (message.text or "").split(maxsplit=1)
    socio_id = partes[1].strip()[:50] if len(partes) > 1 else None

    if socio_id:
        if not await asyncio.to_thread(get_socio, socio_id):
            await message.answer("❌ Ese código de socio no es válido.")
            return
        await asyncio.to_thread(registrar_usuario, user_id, username, socio_id)

    await message.answer(
        texto_bienvenida(username, socio_id),
        parse_mode="HTML",
        reply_markup=kb_principal(),
    )


@dp.message(Command("secciones"))
async def cmd_secciones(message: Message):
    await message.answer("Elige una sección:", reply_markup=kb_principal())


@dp.message(Command("ayuda"))
async def cmd_ayuda(message: Message):
    texto = (
        "<b>¿Cómo usar iGamingCubaBot?</b>\n\n"
        "1. Usa /start para ver el menú principal.\n"
        "2. Explora las secciones con los botones.\n"
        "3. Cuando estés listo, pulsa <b>Quiero registrarme</b>.\n"
        "4. Completa tu registro en la plataforma y envíanos tu ID.\n\n"
        "Si tienes un código de socio, envíalo directamente "
        "o usa /start CODIGO.\n\n"
        "<b>Comandos:</b>\n"
        "/start — Menú principal\n"
        "/secciones — Lista de secciones\n"
        "/registro — Iniciar registro\n"
        "/ayuda — Esta ayuda"
    )
    await message.answer(texto, parse_mode="HTML")


@dp.message(Command("registro"))
async def cmd_registro(message: Message):
    socio = await asyncio.to_thread(get_socio_de_usuario, message.from_user.id)
    await message.answer(
        texto_registro(socio),
        parse_mode="HTML",
        reply_markup=kb_registro(),
        disable_web_page_preview=True,
    )


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
            await message.answer(
                texto_bienvenida(username, texto),
                parse_mode="HTML",
                reply_markup=kb_principal(),
            )
            return
    await message.answer(
        "No entendí. Usa /start para ver el menú o envía un código de socio válido."
    )


@dp.callback_query(F.data == "menu:home")
async def cb_menu(cq: CallbackQuery, state: FSMContext):
    await state.clear()
    username = cq.from_user.username or "Sin username"
    socio = await asyncio.to_thread(get_socio_de_usuario, cq.from_user.id)
    texto = texto_bienvenida(username, socio)
    try:
        await cq.message.edit_text(
            texto, parse_mode="HTML", reply_markup=kb_principal()
        )
    except Exception:
        await cq.message.answer(
            texto, parse_mode="HTML", reply_markup=kb_principal()
        )
    await cq.answer()


@dp.callback_query(F.data.startswith("sec:"))
async def cb_seccion(cq: CallbackQuery):
    clave = cq.data.split(":", 1)[1]
    seccion = await asyncio.to_thread(get_seccion, clave)
    if not seccion:
        await cq.answer("Sección no encontrada", show_alert=True)
        return
    await cq.message.edit_text(
        f"<b>{html.escape(seccion['titulo'])}</b>\n\n{seccion['contenido']}",
        parse_mode="HTML",
        reply_markup=kb_volver(),
        disable_web_page_preview=True,
    )
    await cq.answer()


@dp.callback_query(F.data == "reg:iniciar")
async def cb_registro(cq: CallbackQuery):
    socio = await asyncio.to_thread(get_socio_de_usuario, cq.from_user.id)
    await cq.message.edit_text(
        texto_registro(socio),
        parse_mode="HTML",
        reply_markup=kb_registro(),
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
                f"🆕 Nuevo registro\n"
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
    for f in filas:
        txt += (
            f"• <code>{html.escape(f['socio_id'])}</code> "
            f"({html.escape(f['nombre'] or '-')}): {f['total']}\n"
        )
    await message.answer(txt, parse_mode="HTML")


# ---------- Arranque ----------

async def configurar_comandos():
    await bot.set_my_commands([
        BotCommand(command="start", description="Menú principal"),
        BotCommand(command="secciones", description="Ver secciones"),
        BotCommand(command="registro", description="Iniciar registro"),
        BotCommand(command="ayuda", description="Cómo usar el bot"),
        BotCommand(command="reporte", description="Reporte (solo admin)"),
    ])


async def main():
    init_db()
    await configurar_comandos()
    print("iGamingCubaBot iniciado. Esperando mensajes...")
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())