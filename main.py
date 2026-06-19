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
    await update.message.reply_text(
        "🔧 Quality Assistant Bot\n\n"
        "Available commands:\n"
        "/ask — Ask a quality question\n"
        "/defecto — Register a defect\n"
        "/historial — View last defects\n"
        "/8d — Generate an 8D report\n"
        "/alerta — Generate a quality alert from 2 photos\n\n"
        "You can also send a PDF for analysis.",
        parse_mode="Markdown"
    )

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
    await update.message.reply_text("📋 Register Defect\n\nWhat is the part name or number?", parse_mode="Markdown")
    return PARTE

async def defecto_parte(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["parte"] = update.message.text
    await update.message.reply_text("Describe the defect:")
    return DESCRIPCION

async def defecto_descripcion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["descripcion"] = update.message.text
    await update.message.reply_text("How many pieces are affected?")
    return CANTIDAD

async def defecto_cantidad(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["cantidad"] = update.message.text
    await update.message.reply_text("Which shift? (1 / 2 / 3)")
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
        f"✅ Defect registered\n\n"
        f"🆔 ID: {defecto_id}\n"
        f"🔩 Part: {context.user_data['parte']}\n"
        f"📝 Description: {context.user_data['descripcion']}\n"
        f"🔢 Qty: {context.user_data['cantidad']}\n"
        f"🕐 Shift: {context.user_data['turno']}\n"
        f"👤 Reported by: {user}",
        parse_mode="Markdown"
    )
    return ConversationHandler.END

async def defecto_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Registration cancelled.")
    return ConversationHandler.END

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

if _name_ == "_main_":
    main()