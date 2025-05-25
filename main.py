import os
import datetime
import asyncio
import ssl
import smtplib
from email.message import EmailMessage

from dotenv import load_dotenv
from flask import Flask, request, abort

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import (
    ApplicationBuilder, CommandHandler,
    CallbackQueryHandler, MessageHandler,
    filters, ContextTypes
)

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
LINK_SUPORTE = os.getenv("LINK_SUPORTE")
GRUPO_EXCLUSIVO = os.getenv("GRUPO_EXCLUSIVO")
USUARIO_ADMIN = os.getenv("USUARIO_ADMIN")

EMAIL_ORIGEM = os.getenv("EMAIL_ORIGEM")
SENHA_EMAIL = os.getenv("SENHA_EMAIL")
EMAIL_DESTINO = os.getenv("EMAIL_DESTINO")

WEBHOOK_URL = os.getenv("WEBHOOK_URL")

bot = None
usuarios_aprovados = {}

pasta_comprovantes = os.path.join(os.getcwd(), "comprovantes")
os.makedirs(pasta_comprovantes, exist_ok=True)

# Ler aprovados
try:
    with open("aprovados.txt", "r") as f:
        for linha in f:
            u, cid = linha.strip().split("|")
            usuarios_aprovados[u] = int(cid)
except FileNotFoundError:
    pass

def salvar_aprovados():
    with open("aprovados.txt", "w") as f:
        for u, cid in usuarios_aprovados.items():
            f.write(f"{u}|{cid}\n")

def enviar_email_comprovante(dest, assunto, corpo, arquivo_path):
    msg = EmailMessage()
    msg["From"] = EMAIL_ORIGEM
    msg["To"] = dest
    msg["Subject"] = assunto
    msg.set_content(corpo)

    with open(arquivo_path, "rb") as arq:
        nome_arq = os.path.basename(arquivo_path)
        msg.add_attachment(arq.read(), maintype="application", subtype="octet-stream", filename=nome_arq)

    contexto = ssl.create_default_context()
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=contexto) as servidor:
        servidor.login(EMAIL_ORIGEM, SENHA_EMAIL)
        servidor.send_message(msg)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🔥 Mensal R$9,90 🔥", callback_data='plano_mensal')],
        [InlineKeyboardButton("😈 3 Meses R$19,90 😈", callback_data='plano_trimestral')],
        [InlineKeyboardButton("👑 Permanente R$49,90 👑", callback_data='plano_vitalicio')],
        [InlineKeyboardButton("📞 Suporte", url=LINK_SUPORTE)]
    ]
    markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_photo(
        photo="https://upload.wikimedia.org/wikipedia/commons/4/47/PNG_transparency_demonstration_1.png",
        caption="Pronto pra perder o juízo?\nEscolha seu plano e garanta acesso ao meu conteúdo EXCLUSIVO! 🔥",
        reply_markup=markup
    )

async def handle_planos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    plano = update.callback_query.data

    textos = {
        "plano_mensal": "*Plano Mensal* - R$ 9,90\n55+ vídeos & 100+ fotos\n\n🔥 Eu sei o que você quer… e vou te dar 😮‍💨🙈",
        "plano_trimestral": "*Plano Trimestral* - R$ 19,90\n100+ vídeos & 350+ fotos\n\n🔥 Prepare-se pra perder o controle… 🤤🔥",
        "plano_vitalicio": "*Plano Vitalício* - R$ 49,90\n450+ vídeos & 800+ fotos + conteúdo novo todo dia!\n\n👑 Acesso total, meu WhatsApp pessoal e muito mais… 😈"
    }

    texto = textos.get(plano, "Plano inválido.")
    msg = (
        f"{texto}\n\n"
        "✅ *Envio Imediato!* (Após pagamento)\n"
        "🔑 Chave Pix: `055.336.041-89`\n\n"
    )
    msg2 = "Deu certo amor? Envie o comprovante aqui pra liberar seu conteúdo! 🙈🔥"

    await update.callback_query.message.reply_text(msg, parse_mode="Markdown")
    await update.callback_query.message.reply_text(msg2, parse_mode="Markdown")

async def pegar_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"Seu ID: {update.effective_user.id}")

async def receber_comprovante(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    username = user.username or user.first_name
    chat_id = user.id

    if not (update.message.photo or update.message.document):
        await update.message.reply_text("❌ Envie uma imagem ou PDF do comprovante.")
        return

    agora = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    nome_base = f"{pasta_comprovantes}/{username}_{agora}"

    try:
        if update.message.photo:
            file = await update.message.photo[-1].get_file()
            file_path = f"{nome_base}.jpg"
            await file.download_to_drive(file_path)
        elif update.message.document:
            file = await update.message.document.get_file()
            file_path = f"{nome_base}.pdf"
            await file.download_to_drive(file_path)

        enviar_email_comprovante(
            EMAIL_DESTINO,
            f"📩 Novo comprovante de @{username}",
            f"Comprovante enviado por @{username} (ID: {chat_id}) em {agora}.",
            file_path
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Falha ao salvar ou enviar comprovante. Erro: {e}")
        return

    usuarios_aprovados[username] = chat_id
    salvar_aprovados()

    await update.message.reply_text("📩 Comprovante recebido! Aguarde confirmação do admin...")

    try:
        await context.bot.send_message(
            chat_id=int(USUARIO_ADMIN),
            text=f"📢 Novo comprovante enviado por @{username}.\nUse /liberar @{username} se estiver tudo certo!"
        )
    except Exception as e:
        print(f"Erro ao notificar admin: {e}")

async def liberar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != USUARIO_ADMIN:
        await update.message.reply_text("🚫 Você não tem permissão para isso.")
        return

    if not context.args:
        await update.message.reply_text("Uso: /liberar @usuario")
        return

    username = context.args[0].lstrip("@")
    chat_id = usuarios_aprovados.get(username)

    if chat_id:
        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"✅ Pagamento confirmado!\nBem-vindo ao clube dos insanos 🔥\nAcesse o grupo aqui: {GRUPO_EXCLUSIVO}"
            )
            await update.message.reply_text(f"✅ @{username} liberado com sucesso!")
        except Exception as e:
            await update.message.reply_text(f"⚠️ Erro ao notificar @{username}: {e}")
    else:
        await update.message.reply_text(f"⚠️ Não encontrei o chat_id de @{username}.")

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    username = update.effective_user.username or update.effective_user.first_name
    if username in usuarios_aprovados:
        await update.message.reply_text("✅ Você já foi aprovado e tem acesso ao conteúdo!")
    else:
        await update.message.reply_text("⏳ Seu pagamento ainda não foi aprovado. Envie o comprovante se não tiver enviado ainda!")

async def ajuda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = (
        "😈 *Bem-vindo ao suporte do melhor conteúdo!*\n\n"
        "1. Use /start ou /planos pra ver os planos.\n"
        "2. Faça o Pix e envie o comprovante aqui.\n"
        "3. Aguarde liberação automática ou do admin.\n"
        "4. Após aprovação, você recebe o link do conteúdo exclusivo!\n\n"
        "⚠️ Qualquer dúvida, toque no botão de suporte no menu."
    )
    await update.message.reply_text(texto, parse_mode="Markdown")

async def definir_comandos(app):
    comandos = [
        BotCommand("start", "Ver planos disponíveis"),
        BotCommand("planos", "Ver os planos novamente"),
        BotCommand("status", "Verificar se já foi aprovado"),
        BotCommand("ajuda", "Explica como funciona o bot"),
        BotCommand("liberar", "Admin: liberar acesso de um usuário")
    ]
    await app.bot.set_my_commands(comandos)

flask_app = Flask(__name__)
app = None
loop = None

@flask_app.route('/webhook', methods=['POST'])
def webhook():
    if request.method == "POST":
        update = Update.de_json(request.get_json(force=True), bot)
        asyncio.run_coroutine_threadsafe(app.update_queue.put(update), loop)
        return '', 200
    else:
        abort(405)

async def main():
    global app, bot, loop

    loop = asyncio.get_running_loop()

    app = ApplicationBuilder().token(TOKEN).build()
    bot = app.bot

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("planos", start))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("ajuda", ajuda))
    app.add_handler(CommandHandler("meuid", pegar_id))
    app.add_handler(CommandHandler("liberar", liberar))
    app.add_handler(CallbackQueryHandler(handle_planos))
    app.add_handler(MessageHandler(filters.PHOTO | filters.Document.PDF, receber_comprovante))

    app.post_init = definir_comandos

    await bot.set_webhook(WEBHOOK_URL)
    print(f"Webhook definido: {WEBHOOK_URL}")

    import threading
    thread = threading.Thread(target=lambda: flask_app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000))))
    thread.daemon = True
    thread.start()

    await app.initialize()
    await app.start()
    await asyncio.Event().wait()  # Mantém o bot rodando sem polling

if __name__ == "__main__":
    asyncio.run(main())
