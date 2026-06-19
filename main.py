import os
import fitz
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (Application, CommandHandler, MessageHandler,
filters, ContextTypes, ConversationHandler,
CallbackQueryHandler)
from database import init_db, registrar_defecto, obtener_defectos
from claude_helper import ask_claude, analyze_pdf_text, generate_8d, generate_quality_alert

TOKEN = os.environ.get("TELEGRAM_TOKEN")

PARTE, DESCRIPCION, CANTIDAD, TURNO = range(4)
PROBLEMA_8D = 4
ESPERANDO_FOTO1, ESPERANDO_FOTO2, ESPERANDO_DESCRIPCION_ALERTA = 5, 6, 7

# ── /start ──────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🔍 Hacer una pregunta", callback_data="cmd_ask")],
        [InlineKeyboardButton("📋 Registrar defecto", callback_data="cmd_defecto")],
        [InlineKeyboardButton("📊 Ver historial", callback_data="cmd_historial")],
        [InlineKeyboardButton("🔧 Generar reporte 8D", callback_data="cmd_8d")],
        [InlineKeyboardButton("🚨 Alerta de calidad (2 fotos)", callback_data="cmd_alerta")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "🔧 *Asistente de Calidad*\n\nSelecciona una opción:",
        parse_mode="Markdown",
        reply_markup=reply_markup
    )

# ── Botones ─────────────────────────────────────────────
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
query = update.callback_query
await query.answer()
data = query.data

if data == "cmd_ask":
context.user_data["waiting_for_ask"] = True
await query.message.reply_text("✏️ Escribe tu pregunta de calidad:")

elif data == "cmd_historial":
defectos = obtener_defectos()
if not defectos:
await query.message.reply_text("No hay defectos registrados aún.")
return
msg = "📊 *Últimos 20 defectos:*\n\n"
for d in defectos:
msg += f"🆔 {d[0]} | {d[1]}\n🔩 {d[2]} — {d[3]}\n🔢 Cant: {d[4]} | Turno: {d[5]}\n👤 {d[6]}\n\n"
await query.message.reply_text(msg, parse_mode="Markdown")

elif data == "cmd_defecto":
context.user_data["conv"] = "defecto"
context.user_data["step"] = "parte"
await query.message.reply_text("📋 *Registrar Defecto*\n\n¿Cuál es el nombre o número de parte?", parse_mode="Markdown")

elif data == "cmd_8d":
context.user_data["conv"] = "8d"
await query.message.reply_text("📋 *Reporte 8D*\n\nDescribe el problema en detalle:", parse_mode="Markdown")

elif data == "cmd_alerta":
context.user_data["conv"] = "alerta"
context.user_data["step"] = "foto1"
context.user_data["fotos"] = []
await query.message.reply_text("📸 *Alerta de Calidad*\n\nEnvía la primera foto (pieza buena o referencia):", parse_mode="Markdown")

# ── Texto libre ──────────────────────────────────────────
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
conv = context.user_data.get("conv")
step = context.user_data.get("step")

# Pregunta libre
if context.user_data.get("waiting_for_ask"):
context.user_data["waiting_for_ask"] = False
await update.message.reply_text("🔍 Analizando...")
response = await ask_claude(update.message.text)
await update.message.reply_text(response)
return

# Flujo defecto
if conv == "defecto":
if step == "parte":
context.user_data["parte"] = update.message.text
context.user_data["step"] = "descripcion"
await update.message.reply_text("Describe el defecto:")
elif step == "descripcion":
context.user_data["descripcion"] = update.message.text
context.user_data["step"] = "cantidad"
await update.message.reply_text("¿Cuántas piezas están afectadas?")
elif step == "cantidad":
context.user_data["cantidad"] = update.message.text
context.user_data["step"] = "turno"
await update.message.reply_text("¿Qué turno? (1 / 2 / 3)")
elif step == "turno":
user = update.message.from_user.first_name
defecto_id = registrar_defecto(
parte=context.user_data["parte"],
descripcion=context.user_data["descripcion"],
cantidad=context.user_data["cantidad"],
turno=update.message.text,
reportado_por=user
)
await update.message.reply_text(
f"✅ *Defecto registrado*\n\n"
f"🆔 ID: {defecto_id}\n"
f"🔩 Parte: {context.user_data['parte']}\n"
f"📝 Descripción: {context.user_data['descripcion']}\n"
f"🔢 Cantidad: {context.user_data['cantidad']}\n"
f"🕐 Turno: {update.message.text}\n"
f"👤 Reportado por: {user}",
parse_mode="Markdown"
)
context.user_data.clear()

# Flujo 8D
elif conv == "8d":
await update.message.reply_text("⚙️ Generando reporte 8D...")
response = await generate_8d(update.message.text)
await update.message.reply_text(response)
context.user_data.clear()

# Flujo alerta — descripción final
elif conv == "alerta" and step == "descripcion":
await update.message.reply_text("🚨 Generando alerta de calidad...")
response = await generate_quality_alert(
context.user_data["foto1"],
context.user_data["foto2"],
update.message.text
)
await update.message.reply_text(response)
context.user_data.clear()

# ── Fotos ────────────────────────────────────────────────
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
conv = context.user_data.get("conv")
step = context.user_data.get("step")

if conv == "alerta":
photo = update.message.photo[-1]
file = await photo.get_file()
data = await file.download_as_bytearray()

if step == "foto1":
context.user_data["foto1"] = bytes(data)
context.user_data["step"] = "foto2"
await update.message.reply_text("✅ Primera foto recibida.\n\nAhora envía la segunda foto (pieza defectuosa):")
elif step == "foto2":
context.user_data["foto2"] = bytes(data)
context.user_data["step"] = "descripcion"
await update.message.reply_text("✅ Segunda foto recibida.\n\nAgrega una breve descripción (nombre de parte, operación, etc.):")

# ── PDF ──────────────────────────────────────────────────
async def handle_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE):
await update.message.reply_text("📄 Analizando PDF...")
file = await update.message.document.get_file()
data = await file.download_as_bytearray()
pdf = fitz.open(stream=bytes(data), filetype="pdf")
text = ""
for page in pdf:
text += page.get_text()
text = text[:8000]
response = await analyze_pdf_text(text)
await update.message.reply_text(response)

# ── Main ─────────────────────────────────────────────────
def main():
init_db()
app = Application.builder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CallbackQueryHandler(button_handler))
app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
app.add_handler(MessageHandler(filters.Document.PDF, handle_pdf))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

print("✅ Bot corriendo...")
app.run_polling()

if __name__ == "__main__":
main()