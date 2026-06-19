import anthropic
import base64
import os

client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

SYSTEM_PROMPT = """You are an expert Automotive Quality Engineer assistant with deep knowledge in:
- APQP, PPAP, PFMEA, Control Plans
- 8D Problem Solving methodology
- GP12 / Customer Specific Requirements
- IATF 16949 and ISO 9001 standards
- Statistical Process Control (SPC)
- Corrective and Preventive Actions (CAPA)
- PPM tracking and quality metrics
- Supplier quality management

Always respond in the same language the user writes in.
Be concise, technical, and actionable.
When generating 8D reports, use the standard D1-D8 format.
When generating quality alerts, use a clear structured format."""

async def ask_claude(question: str) -> str:
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": question}]
    )
    return message.content[0].text

async def analyze_pdf_text(pdf_text: str) -> str:
    prompt = f"""Analyze this quality document and provide:
1. Key findings
2. Main defects or risks identified
3. Recommended actions

Document content:
{pdf_text}"""
    return await ask_claude(prompt)

async def generate_8d(problem_description: str) -> str:
    prompt = f"""Generate a complete 8D report for the following problem:

{problem_description}

Format each discipline as D1 through D8 with clear, actionable content."""
    return await ask_claude(prompt)

async def generate_quality_alert(image1_data: bytes, image2_data: bytes, description: str) -> str:
    image1_b64 = base64.standard_b64encode(image1_data).decode("utf-8")
    image2_b64 = base64.standard_b64encode(image2_data).decode("utf-8")

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": f"Generate a quality alert based on these two images. Additional context: {description}\n\nFormat the alert as:\n🚨 QUALITY ALERT\n📅 Date: [today]\n🔍 Defect Description:\n📸 Visual Evidence: [describe what you see in both images]\n⚠️ Risk Level: [Low/Medium/High]\n✅ Acceptance Criteria:\n❌ Rejection Criteria:\n🔧 Recommended Action:\n📋 Containment:"},
                {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": image1_b64}},
                {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": image2_b64}}
            ]
        }]
    )
    return message.content[0].text
import os
import fitz
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler
from database import init_db, registrar_defecto, obtener_defectos, registrar_accion
from claude_helper import ask_claude, analyze_pdf_text, generate_8d, generate_quality_alert

TOKEN = os.environ.get("TELEGRAM_TOKEN")

# Conversation states
PARTE, DESCRIPCION, CANTIDAD, TURNO = range(4)
PROBLEMA_8D = range(1)
ESPERANDO_FOTO1, ESPERANDO_FOTO2, ESPERANDO_DESCRIPCION_ALERTA = range(3)

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
        "🔧 Asistente de Calidad\n\nSelecciona una opción:",
        parse_mode="Markdown",
        reply_markup=reply_markup
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data == "cmd_ask":
        context.user_data["waiting_for_ask"] = True
        await query.message.reply_text(
            "✏️ Escribe tu pregunta de calidad:",
            parse_mode="Markdown"
        )
    elif data == "cmd_defecto":
        update.message = query.message
        await defecto_start(update, context)
    elif data == "cmd_historial":
        update.message = query.message
        await historial(update, context)
    elif data == "cmd_8d":
        update.message = query.message
        await eighd_start(update, context)
    elif data == "cmd_alerta":
        update.message = query.message
        await alerta_start(update, context)

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("waiting_for_ask"):
        context.user_data["waiting_for_ask"] = False
        await update.message.reply_text("🔍 Analizando...")
        response = await ask_claude(update.message.text)
        await update.message.reply_text(response)
    

# ── /ask ────────────────────────────────────────────────
async def ask(update: Update, context: ContextTypes.DEFAULT_TYPE):
    question = " ".join(context.args)
    if not question:
        await update.message.reply_text("Usage: /ask your question here")
        return
    await update.message.reply_text("🔍 Analyzing...")
    response = await ask_claude(question)
    await update.message.reply_text(response)

# ── /defecto ────────────────────────────────────────────
async def defecto_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📋 Registrar Defecto\n\n¿Cuál es el nombre o número de parte?", parse_mode="Markdown")
    return PARTE

async def defecto_parte(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["parte"] = update.message.text
    await update.message.reply_text("Describe el defecto:")
    return DESCRIPCION

async def defecto_descripcion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["descripcion"] = update.message.text
    await update.message.reply_text("¿Cuántas piezas están afectadas?")
    return CANTIDAD

async def defecto_cantidad(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["cantidad"] = update.message.text
    await update.message.reply_text("¿Qué turno? (1 / 2 / 3)")
    return TURNO

async def defecto_turno(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["turno"] = update.message.text
    user = update.message.from_user.first_name
    defecto_id = registrar_defecto(
        parte=context.user_data["parte"],
        descripcion=context.user_data["descripcion"],
        cantidad=context.user_data["cantidad"],
        turno=context.user_data["turno"],
        reportado_por=user
    )
    await update.message.reply_text(
        f"✅ Defecto registrado\n\n"
        f"🆔 ID: {defecto_id}\n"
        f"🔩 Parte: {context.user_data['parte']}\n"
        f"📝 Descripción: {context.user_data['descripcion']}\n"
        f"🔢 Cantidad: {context.user_data['cantidad']}\n"
        f"🕐 Turno: {context.user_data['turno']}\n"
        f"👤 Reportado por: {user}",
        parse_mode="Markdown"
    )
    return ConversationHandler.END

async def defecto_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Registro cancelado.")
    return ConversationHandler.END

async def historial(update: Update, context: ContextTypes.DEFAULT_TYPE):
    defectos = obtener_defectos()
    if not defectos:
        await update.message.reply_text("No hay defectos registrados aún.")
        return
    msg = "📊 Últimos 20 defectos:\n\n"
    for d in defectos:
        msg += f"🆔 {d[0]} | {d[1]}\n🔩 {d[2]} — {d[3]}\n🔢 Cant: {d[4]} | Turno: {d[5]}\n👤 {d[6]}\n\n"
    await update.message.reply_text(msg, parse_mode="Markdown")

async def eighd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📋 Generador de Reporte 8D\n\nDescribe el problema en detalle:", parse_mode="Markdown")
    return PROBLEMA_8D

async def eighd_generate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⚙️ Generando reporte 8D...")
    response = await generate_8d(update.message.text)
    await update.message.reply_text(response)
    return ConversationHandler.END

async def alerta_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["fotos"] = []
    await update.message.reply_text("📸 Alerta de Calidad\n\nEnvía la primera foto (pieza buena o referencia):", parse_mode="Markdown")
    return ESPERANDO_FOTO1

async def alerta_foto1(update: Update, context: ContextTypes.DEFAULT_TYPE):
    photo = update.message.photo[-1]
    file = await photo.get_file()
    data = await file.download_as_bytearray()
    context.user_data["foto1"] = bytes(data)
    await update.message.reply_text("✅ Primera foto recibida.\n\nAhora envía la segunda foto (pieza defectuosa):")
    return ESPERANDO_FOTO2

async def alerta_foto2(update: Update, context: ContextTypes.DEFAULT_TYPE):
    photo = update.message.photo[-1]
    file = await photo.get_file()
    data = await file.download_as_bytearray()
    context.user_data["foto2"] = bytes(data)
    await update.message.reply_text("✅ Segunda foto recibida.\n\nAgrega una breve descripción (nombre de parte, operación, etc.):")
    return ESPERANDO_DESCRIPCION_ALERTA

async def alerta_generar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🚨 Generando alerta de calidad...")
    response = await generate_quality_alert(
        context.user_data["foto1"],
        context.user_data["foto2"],
        update.message.text
    )
    await update.message.reply_text(response)
    return ConversationHandler.END

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
# ── /historial ──────────────────────────────────────────
async def historial(update: Update, context: ContextTypes.DEFAULT_TYPE):
    defectos = obtener_defectos()
    if not defectos:
        await update.message.reply_text("No defects registered yet.")
        return
    msg = "📊 Last 20 defects:\n\n"
    for d in defectos:
        msg += f"🆔 {d[0]} | {d[1]}\n🔩 {d[2]} — {d[3]}\n🔢 Qty: {d[4]} | Shift: {d[5]}\n👤 {d[6]}\n\n"
    await update.message.reply_text(msg, parse_mode="Markdown")

# ── /8d ─────────────────────────────────────────────────
async def eighd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📋 8D Report Generator\n\nDescribe the problem in detail:", parse_mode="Markdown")
    return PROBLEMA_8D

async def eighd_generate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⚙️ Generating 8D report...")
    response = await generate_8d(update.message.text)
    await update.message.reply_text(response)
    return ConversationHandler.END

# ── /alerta ─────────────────────────────────────────────
async def alerta_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["fotos"] = []
    await update.message.reply_text("📸 Quality Alert\n\nSend the first photo (good part or reference):", parse_mode="Markdown")
    return ESPERANDO_FOTO1

async def alerta_foto1(update: Update, context: ContextTypes.DEFAULT_TYPE):
    photo = update.message.photo[-1]
    file = await photo.get_file()
    data = await file.download_as_bytearray()
    context.user_data["foto1"] = bytes(data)
    await update.message.reply_text("✅ First photo received.\n\nNow send the second photo (defective part):")
    return ESPERANDO_FOTO2

async def alerta_foto2(update: Update, context: ContextTypes.DEFAULT_TYPE):
    photo = update.message.photo[-1]
    file = await photo.get_file()
    data = await file.download_as_bytearray()
    context.user_data["foto2"] = bytes(data)
    await update.message.reply_text("✅ Second photo received.\n\nAdd a brief description or context (part name, operation, etc.):")
    return ESPERANDO_DESCRIPCION_ALERTA

async def alerta_generar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🚨 Generating quality alert...")
    response = await generate_quality_alert(
        context.user_data["foto1"],
        context.user_data["foto2"],
        update.message.text
    )
    await update.message.reply_text(response)
    return ConversationHandler.END

# ── PDF handler ─────────────────────────────────────────
async def handle_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📄 Analyzing PDF...")
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
    app.add_handler(CommandHandler("ask", ask))
    app.add_handler(CommandHandler("historial", historial))

    app.add_handler(ConversationHandler( 
              entry_points=[CommandHandler("defecto", defecto_start)],
        states={
            PARTE: [MessageHandler(filters.TEXT & ~filters.COMMAND, defecto_parte)],
            DESCRIPCION: [MessageHandler(filters.TEXT & ~filters.COMMAND, defecto_descripcion)],
            CANTIDAD: [MessageHandler(filters.TEXT & ~filters.COMMAND, defecto_cantidad)],
            TURNO: [MessageHandler(filters.TEXT & ~filters.COMMAND, defecto_turno)],
        },
        fallbacks=[CommandHandler("cancel", defecto_cancel)]
    ))

    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("8d", eighd_start)],
        states={
            0: [MessageHandler(filters.TEXT & ~filters.COMMAND, eighd_generate)],
        },
        fallbacks=[CommandHandler("cancel", defecto_cancel)]
    ))

    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("alerta", alerta_start)],
        states={
            0: [MessageHandler(filters.PHOTO, alerta_foto1)],
            1: [MessageHandler(filters.PHOTO, alerta_foto2)],
            2: [MessageHandler(filters.TEXT & ~filters.COMMAND, alerta_generar)],
        },
        fallbacks=[CommandHandler("cancel", defecto_cancel)]
    ))

    app.add_handler(MessageHandler(filters.Document.PDF, handle_pdf))

    print("✅ Bot running...")
    app.run_polling()

if __name__ == "__main__":
    main()