import sqlite3

DB = "comunidad.db"

SECCIONES = [
    ("info", "🌐 ¿Qué es iGamingCuba?",
     "iGamingCuba es una comunidad privada donde compartimos estrategias, "
     "oportunidades y recursos del sector iGaming.\n\n"
     "Nuestro objetivo es ayudarte a crecer dentro del ecosistema con "
     "contenido exclusivo y una red de contactos de confianza.", 1),

    ("como", "🚀 Cómo funciona",
     "1) Explora las secciones para conocer la comunidad.\n"
     "2) Cuando estés listo, regístrate en nuestra plataforma asociada.\n"
     "3) Envíanos tu ID de usuario.\n"
     "4) Recibirás acceso al grupo VIP y a todos los beneficios.", 2),

    ("beneficios", "🎁 Beneficios",
     "• Acceso al grupo VIP\n"
     "• Soporte prioritario\n"
     "• Contenido y recursos exclusivos\n"
     "• Comunidad activa 24/7", 3),

    ("politicas", "📜 Políticas de la comunidad",
     "• Respeto entre todos los miembros.\n"
     "• Prohibido el spam o publicidad no autorizada.\n"
     "• No compartir contenido del grupo fuera.\n"
     "• Cualquier incumplimiento implica expulsión.", 4),

    ("faq", "❓ Preguntas frecuentes",
     "¿Es gratis? Sí, el acceso a la comunidad es gratuito.\n\n"
     "¿Cómo entro al VIP? Regístrate en la plataforma y envíanos tu ID.\n\n"
     "¿Necesito experiencia? No, hay contenido para todos los niveles.", 5),
]

SOCIOS_DEMO = [
    ("juan", "Juan Pérez", 30.0),
]


def crear_tablas(conn):
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
        CREATE TABLE IF NOT EXISTS usuarios (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            socio_id TEXT,
            estado TEXT DEFAULT 'nuevo',
            id_plataforma TEXT,
            fecha_registro TEXT DEFAULT CURRENT_TIMESTAMP
        );
    """)


with sqlite3.connect(DB) as conn:
    crear_tablas(conn)

    for clave, titulo, contenido, orden in SECCIONES:
        conn.execute("""
            INSERT INTO secciones (clave, titulo, contenido, orden)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(clave) DO UPDATE SET
                titulo = excluded.titulo,
                contenido = excluded.contenido,
                orden = excluded.orden
        """, (clave, titulo, contenido, orden))

    for socio_id, nombre, porcentaje in SOCIOS_DEMO:
        conn.execute("""
            INSERT INTO socios (socio_id, nombre, porcentaje)
            VALUES (?, ?, ?)
            ON CONFLICT(socio_id) DO UPDATE SET nombre = excluded.nombre
        """, (socio_id, nombre, porcentaje))

print(f"{len(SECCIONES)} secciones y {len(SOCIOS_DEMO)} socios cargados.")