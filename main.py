import os
import datetime
import threading
import asyncio
import smtplib
import ssl
from email.message import EmailMessage

from dotenv import load_dotenv
from flask import Flask, request

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import (
    ApplicationBuilder, CommandHandler,
    CallbackQueryHandler, MessageHandler,
    filters, ContextTypes
)

# 🔑 Carregar variáveis do .env
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
LINK_SUPORTE = os.getenv("LINK_SUPORTE")
GRUPO_EXCLUSIVO = os.getenv("GRUPO_EXCLUSIVO")
USUARIO_ADMIN = os.getenv("USUARIO_ADMIN")

EMAIL_ORIGEM = os.getenv("EMAIL_ORIGEM")
SENHA_EMAIL = os.getenv("SENHA_EMAIL")
EMAIL_DESTINO = os.getenv("EMAIL_DESTINO")

bot = None

# 🗂️ Pasta de comprovantes
pasta_comprovantes = os.path.join(os.getcwd(), "comprovantes")
os.makedirs(pasta_comprovantes, exist_ok=True)

# ✅ Usuários aprovados
usuarios_aprovados = {}
try:
    with open("aprovados.txt", "r") as f:
        for linha in f:
            partes = linha.strip().split("|")
            if len(partes) == 2:
                usuarios_aprovados[partes[0]] = int(partes[1])
except FileNotFoundError:
    pass


def salvar_aprovados():
    with open("aprovados.txt", "w") as f:
        for username, chat_id in usuarios_aprovados.items():
            f.write(f"{username}|{chat_id}\n")


# 📧 Função para envio de e-mail
def enviar_email_comprovante(destinatario, assunto, corpo, arquivo_path):
    mensagem = EmailMessage()
    mensagem["From"] = EMAIL_ORIGEM
    mensagem["To"] = destinatario
    mensagem["Subject"] = assunto
    mensagem.set_content(corpo)

    with open(arquivo_path, "rb") as arquivo:
        nome_arquivo = os.path.basename(arquivo_path)
        mensagem.add_attachment(
            arquivo.read(),
            maintype="application",
            subtype="octet-stream",
            filename=nome_arquivo
        )

    contexto = ssl.create_default_context()
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=contexto) as servidor:
        servidor.login(EMAIL_ORIGEM, SENHA_EMAIL)
        servidor.send_message(mensagem)

    print("📨 E-mail enviado com sucesso!")


# 🚀 Webhook PicPay
flask_app = Flask(__name__)

@flask_app.route('/webhook-picpay', methods=['POST'])
def webhook_picpay():
    data = request.json
    print("Webhook PicPay recebido:", data)

    status = data.get('status')
    referencia = data.get('referenceId')

    if status == 'paid' and referencia:
        username = referencia.lstrip("@")
        if username not in usuarios_aprovados:
            print(f"Pagamento recebido de @{username}, mas chat_id desconhecido.")
        else:
            chat_id = usuarios_aprovados.get(username)
            if bot and chat_id:
                try:
                    asyncio.run_coroutine_threadsafe(
                        bot.send_message(
                            chat_id=chat_id,
                            text=f"✅ Pagamento confirmado automaticamente!\nBem-vindo ao clube dos insanos 🔥\nAcesse o grupo aqui: {GRUPO_EXCLUSIVO}"
                        ),
                        loop=bot.loop
                    )
                except Exception as e:
                    print(f"Erro ao enviar mensagem pra @{username}: {e}")
            else:
                print("Bot não iniciado ou chat_id não disponível.")
    else:
        print(f"Webhook ignorado: status '{status}' ou referência inválida.")

    return '', 200


# 🧠 Comandos do bot
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🔥 Mensal R$9,90 🔥", callback_data='plano_mensal')],
        [InlineKeyboardButton("😈 3 Meses R$19,90 😈", callback_data='plano_trimestral')],
        [InlineKeyboardButton("👑 Permanente R$49,90 👑", callback_data='plano_vitalicio')],
        [InlineKeyboardButton("📞 Suporte", url=LINK_SUPORTE)]
    ]
    markup = InlineKeyboardMarkup(keyboard)

    await context.bot.send_photo(
        chat_id=update.effective_chat.id,
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


# 🧾 Receber comprovante
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

        # 📨 Enviar e-mail após salvar
        try:
            enviar_email_comprovante(
                destinatario=EMAIL_DESTINO,
                assunto=f"📩 Novo comprovante de @{username}",
                corpo=f"Comprovante enviado por @{username} (ID: {chat_id}) em {agora}.",
                arquivo_path=file_path
            )
        except Exception as e:
            print(f"❌ Erro ao enviar e-mail: {e}")

    except Exception as e:
        await update.message.reply_text(f"❌ Falha ao salvar comprovante. Erro: {e}")
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
    remetente_id = update.effective_user.id

    if str(remetente_id) != USUARIO_ADMIN:
        await update.message.reply_text("🚫 Você não tem permissão pra isso.")
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
            await update.message.reply_text(f"⚠️ Erro ao notificar @{username}.\n{e}")
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


# 🌐 Flask paralelo
def start_flask():
    port = int(os.environ.get('PORT', 10000))
    flask_app.run(host='0.0.0.0', port=port)


# 🚀 Inicializar
if __name__ == "__main__":
    flask_thread = threading.Thread(target=start_flask)
    flask_thread.daemon = True
    flask_thread.start()

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

    app.post_init = lambda app: definir_comandos(app)

    print("BOT RODANDO 🔥")
    app.run_polling()
