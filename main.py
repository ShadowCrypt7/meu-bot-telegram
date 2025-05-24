import os
import datetime
import threading
import asyncio

from dotenv import load_dotenv
from flask import Flask, request


from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import (
    ApplicationBuilder, CommandHandler,
    CallbackQueryHandler, MessageHandler,
    filters, ContextTypes
)

# 🔐 Carregar variáveis do .env
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
LINK_SUPORTE = os.getenv("LINK_SUPORTE")
GRUPO_EXCLUSIVO = os.getenv("GRUPO_EXCLUSIVO")
USUARIO_ADMIN = os.getenv("USUARIO_ADMIN")

# Variável global pro bot
bot = None

# 🗂️ Pasta de comprovantes
os.makedirs("comprovantes", exist_ok=True)

# 🧠 Carrega usuários aprovados: dicionário {username: chat_id}
usuarios_aprovados = {}
try:
    with open("aprovados.txt", "r") as f:
        for linha in f:
            partes = linha.strip().split("|")
            if len(partes) == 2:
                usuarios_aprovados[partes[0]] = int(partes[1])
except FileNotFoundError:
    pass

# 🔄 Salvar aprovados no arquivo
def salvar_aprovados():
    with open("aprovados.txt", "w") as f:
        for username, chat_id in usuarios_aprovados.items():
            f.write(f"{username}|{chat_id}\n")

# ------ Flask + Webhook PicPay ------
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
            # Se não temos chat_id, não adiciona ainda, só avisa no print
            print(f"Pagamento recebido de @{username}, mas chat_id desconhecido. Aguarde o comprovante para salvar chat_id.")
            # Opcional: você pode armazenar numa fila temporária pra liberar depois, se quiser

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

# ------ Funções do Bot ------

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

    msg2 = (
        "Deu certo amor? Envie o comprovante aqui pra liberar seu conteúdo! 🙈🔥"
    )

    await update.callback_query.message.reply_text(msg, parse_mode="Markdown")
    await update.callback_query.message.reply_text(msg2, parse_mode="Markdown")

async def pegar_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"Seu ID: {update.effective_user.id}")

async def receber_comprovante(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    username = user.username or user.first_name
    chat_id = user.id

    # >>>>> Verificação REMOVIDA: <<<<<
    # if username in usuarios_aprovados:
    #     await update.message.reply_text("✅ Você já foi aprovado!")
    #     return

    if not (update.message.photo or update.message.document):
        await update.message.reply_text("❌ Envie uma imagem ou PDF do comprovante.")
        print(f"[DEBUG] Usuário @{username} enviou algo diferente de imagem ou PDF.")
        return

    agora = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    nome_base = f"comprovantes/{username}_{agora}"

    try:
        if update.message.photo:
            print(f"[DEBUG] Recebi foto de @{username}.")
            file = await update.message.photo[-1].get_file()
            await file.download_to_drive(f"{nome_base}.jpg")
            print(f"[DEBUG] Foto salva como {nome_base}.jpg")
        elif update.message.document:
            print(f"[DEBUG] Recebi documento de @{username}.")
            file = await update.message.document.get_file()
            await file.download_to_drive(f"{nome_base}.pdf")
            print(f"[DEBUG] Documento salvo como {nome_base}.pdf")
    except Exception as e:
        await update.message.reply_text(f"❌ Falha ao salvar comprovante. Erro: {e}")
        print(f"[DEBUG] Erro ao salvar arquivo: {e}")
        return

    # Salva no dicionário e arquivo com chat_id
    usuarios_aprovados[username] = chat_id
    salvar_aprovados()
    print(f"[DEBUG] @{username} e chat_id {chat_id} salvo no arquivo aprovados.txt.")

    await update.message.reply_text("📩 Comprovante recebido! Aguarde confirmação do admin...")

    try:
        await context.bot.send_message(
            chat_id=int(USUARIO_ADMIN),
            text=f"📢 Novo comprovante enviado por @{username}.\nUse /liberar @{username} se estiver tudo certo!"
        )
        print(f"[DEBUG] Notificação enviada pro admin sobre @{username}.")
    except Exception as e:
        print(f"[DEBUG] Erro ao notificar admin: {e}")


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
        await update.message.reply_text(f"⚠️ Não encontrei o chat_id de @{username}. Provavelmente a pessoa não enviou nenhum comprovante ainda.")

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

# 🔧 Definir comandos do menu do bot
async def definir_comandos(app):
    comandos = [
        BotCommand("start", "Ver planos disponíveis"),
        BotCommand("planos", "Ver os planos novamente"),
        BotCommand("status", "Verificar se já foi aprovado"),
        BotCommand("ajuda", "Explica como funciona o bot"),
        BotCommand("liberar", "Admin: liberar acesso de um usuário")
    ]
    await app.bot.set_my_commands(comandos)

# 🔃 Iniciar Flask em thread paralela
def start_flask():
    port = int(os.environ.get('PORT', 10000))
    print(f" * Servidor Flask rodando na porta {port}...")
    print(f" * Use a URL pública do seu servidor para configurar o webhook PicPay (ex: https://seusite.com/webhook-picpay)")

    flask_app.run(host='0.0.0.0', port=port)



# 🚀 MAIN
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
    #app.run_polling()
