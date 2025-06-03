import os
import asyncio
import ssl
import smtplib
import requests
from pathlib import Path
from email.message import EmailMessage
from datetime import datetime
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from flask import Flask, jsonify, request, abort

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
CALLBACK_URL = os.getenv("CALLBACK_URL")

API_PAINEL_URL = os.getenv("API_PAINEL_URL")
CHAVE_PAINEL = os.getenv("CHAVE_PAINEL")
CHAVE_SECRETA_BOT_INTERNA = os.getenv("CHAVE_PAINEL")

SECRET_KEY_PAINEL = os.getenv("SECRET_KEY_PAINEL")
USUARIO_PAINEL = os.getenv("USUARIO_PAINEL")
SENHA_PAINEL = os.getenv("SENHA_PAINEL")

EMAIL_ORIGEM = os.getenv("EMAIL_ORIGEM")
SENHA_EMAIL = os.getenv("SENHA_EMAIL")
EMAIL_DESTINO = os.getenv("EMAIL_DESTINO")

WEBHOOK_URL = os.getenv("WEBHOOK_URL")

bot = None
# usuarios_aprovados = {} # <---- DELETAR/COMENTAR

pasta_comprovantes = os.path.join(os.getcwd(), "comprovantes")
os.makedirs(pasta_comprovantes, exist_ok=True)

# Ler aprovados
# try: <---- DELETAR/COMENTAR ESTE BLOCO
#    with open("aprovados.txt", "r") as f:
#        for linha in f:
#            partes = linha.strip().split(" | ")
#            if len(partes) == 2:
#                u, cid = partes
#               usuarios_aprovados[u] = int(cid)
#           else:
#                print(f"[AVISO] Linha ignorada (formato inválido): {linha.strip()}")
#except FileNotFoundError:
#    pass <---- FIM DO BLOCO COMENTADO/DELETADO

#def salvar_aprovados(): <---- COMENTAR/DELETAR FUNCAO
#    with open("aprovados.txt", "w") as f:
#        for u, cid in usuarios_aprovados.items():
#            f.write(f"{u}|{cid}\n") <---- FIM DA FUNCAO DELETADA/COMENTADA

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

# (Verifique se API_PAINEL_URL e CHAVE_PAINEL estão carregadas do .env)
# A API /api/bot/planos que fizemos não exige chave, mas se exigisse, você a enviaria nos headers.

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Limpar escolhas anteriores de plano para este usuário, caso existam
    if 'plano_selecionado_id' in context.user_data:
        del context.user_data['plano_selecionado_id']
    if 'plano_selecionado_nome' in context.user_data:
        del context.user_data['plano_selecionado_nome']

    api_url_get_planos = f"{API_PAINEL_URL}/api/bot/planos"
    keyboard = []
    fetched_plans_data = {} # Para armazenar detalhes dos planos para handle_planos

    try:
        print(f"Buscando planos da API: {api_url_get_planos}")
        response = requests.get(api_url_get_planos, timeout=10) # Adicionado timeout
        response.raise_for_status() # Levanta erro para status 4xx/5xx
        
        data = response.json()
        if data.get("status") == "sucesso" and data.get("planos"):
            planos_da_api = data["planos"]
            if planos_da_api:
                for plano_api in planos_da_api:
                    # Guardamos os detalhes completos do plano no bot_data para acesso rápido
                    # Usamos id_plano como chave
                    fetched_plans_data[plano_api['id_plano']] = plano_api
                    
                    # Cria o botão
                    # Usamos nome_exibicao e preco para o texto do botão
                    # (Você pode ajustar o formato do preço se quiser)
                    texto_botao = f"{plano_api['nome_exibicao']} - R${plano_api['preco']:.2f}"
                    keyboard.append([InlineKeyboardButton(texto_botao, callback_data=plano_api['id_plano'])])
                
                # Armazena os dados dos planos buscados no contexto do bot para uso em handle_planos
                # Isso evita chamar a API novamente em handle_planos, mas o ideal seria um cache melhor
                # ou buscar em handle_planos se não encontrar aqui.
                # Por simplicidade, vamos armazenar em bot_data.
                # ATENÇÃO: context.bot_data é compartilhado entre todos os usuários.
                # Se os planos mudam raramente, isso é OK. Se mudam muito, buscar sempre ou usar um cache
                # com tempo de expiração seria melhor.
                context.bot_data['planos_detalhados_api'] = fetched_plans_data

            else: # Nenhum plano ativo retornado pela API
                await update.message.reply_text("😕 Desculpe, não há planos disponíveis no momento. Tente mais tarde.")
                return
        else: # API não retornou sucesso ou não retornou planos
            print(f"API de planos não retornou sucesso ou planos: {data}")
            await update.message.reply_text("😕 Não consegui carregar os planos no momento. Tente mais tarde.")
            return

    except requests.exceptions.RequestException as e:
        print(f"Erro ao buscar planos da API: {e}")
        await update.message.reply_text("😕 Ops! Tive um problema para buscar os planos. Por favor, tente novamente em alguns instantes.")
        return
    except Exception as e_geral: # Pega outros erros como JSONDecodeError se a resposta não for JSON
        print(f"Erro geral ao processar planos da API: {e_geral}")
        await update.message.reply_text("😕 Ops! Erro ao processar os planos. Por favor, tente novamente em alguns instantes.")
        return

    # Adiciona o botão de suporte se houver planos
    if keyboard:
        keyboard.append([InlineKeyboardButton("📞 Suporte", url=LINK_SUPORTE)])
    else: # Caso o try/except falhe de uma forma que keyboard fique vazio
        await update.message.reply_text("Não há planos para exibir ou ocorreu um erro. Contate o suporte.")
        return

    markup = InlineKeyboardMarkup(keyboard)
    
    # Enviar foto e caption
    # Você precisa garantir que a foto "fotos/GABI_PIJAMA.jpeg" existe no servidor do bot
    try:
        with open("fotos/GABI_PIJAMA.jpeg", "rb") as foto:
            await update.message.reply_photo(
                photo=foto,
                caption="Pronto pra perder o juízo?\nEscolha seu plano e garanta acesso ao meu conteúdo EXCLUSIVO! 🔥",
                reply_markup=markup
            )
    except FileNotFoundError:
        print("ERRO: Arquivo de foto GABI_PIJAMA.jpeg não encontrado.")
        await update.message.reply_text(
            "Pronto pra perder o juízo?\nEscolha seu plano e garanta acesso ao meu conteúdo EXCLUSIVO! 🔥",
            reply_markup=markup
        ) # Envia apenas texto se a foto falhar

async def handle_planos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    plano_selecionado_id = update.callback_query.data # Ex: "plano_mensal_basico"

    # Pega os detalhes dos planos que foram buscados pela API e armazenados em /start
    planos_detalhados_cache = context.bot_data.get('planos_detalhados_api', {})
    
    # Pega os detalhes do plano específico que foi selecionado
    detalhes_do_plano_selecionado = planos_detalhados_cache.get(plano_selecionado_id)

    if not detalhes_do_plano_selecionado:
        await update.callback_query.message.reply_text(
            "😕 Ops! Não encontrei os detalhes para este plano. "
            "Por favor, tente selecionar novamente usando /start."
        )
        return

    # Guarda o ID do plano selecionado nos dados do usuário para uso em receber_comprovante
    context.user_data['plano_selecionado_id'] = plano_selecionado_id
    context.user_data['plano_selecionado_nome'] = detalhes_do_plano_selecionado.get('nome_exibicao', 'Plano Selecionado')

    # Monta a mensagem com os dados dinâmicos do plano
    nome_plano_formatado = f"*{detalhes_do_plano_selecionado.get('nome_exibicao', '')}* - R${detalhes_do_plano_selecionado.get('preco', 0.0):.2f}"
    descricao_plano = detalhes_do_plano_selecionado.get('descricao', 'Descrição não disponível.')
    
    texto_plano_completo = f"{nome_plano_formatado}\n\n{descricao_plano}"

    # Mensagens para o usuário
    msg_detalhes_plano = (
        f"{texto_plano_completo}\n\n"
        "✅ *Envio Imediato!* (Após confirmação do pagamento/comprovante)\n"
        "🔑 Chave Pix: `055.336.041-89` (COPIA E COLA)\n\n" # LEMBRE-SE DE COLOCAR SUA CHAVE PIX REAL AQUI
    )
    msg_instrucao_comprovante = "Após o pagamento, envie o comprovante aqui neste chat para validarmos seu acesso! 🙈🔥"

    await update.callback_query.message.reply_text(msg_detalhes_plano, parse_mode="Markdown")
    await update.callback_query.message.reply_text(msg_instrucao_comprovante, parse_mode="Markdown")

async def pegar_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"Seu ID: {update.effective_user.id}")

async def receber_comprovante(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    username = user.username # Pode ser None, o painel lida com isso
    first_name = user.first_name
    chat_id = user.id

    # Verifica se um plano foi selecionado anteriormente
    plano_id_selecionado = context.user_data.get('plano_selecionado_id')
    if not plano_id_selecionado:
        await update.message.reply_text("Por favor, primeiro selecione um plano usando /start ou /planos.")
        return

    if not (update.message.photo or update.message.document and update.message.document.mime_type == 'application/pdf'):
        await update.message.reply_text("❌ Envie uma imagem (foto) ou PDF do comprovante.")
        return

    # Lógica para salvar e enviar e-mail com comprovante (pode ser mantida)
    agora = datetime.now(ZoneInfo("America/Sao_Paulo")).strftime("%Y-%m-%d_%H-%M-%S")
    # username_para_arquivo é usado para nomear o arquivo, se username for None, usa first_name
    username_fs = user.username if user.username else user.first_name.replace(" ", "_")

    nome_base = f"{pasta_comprovantes}/{username_fs}_{agora}"
    file_path_comprovante = None # Inicializa

    try:
        if update.message.photo:
            file = await update.message.photo[-1].get_file()
            file_path_comprovante = f"{nome_base}.jpg"
            await file.download_to_drive(file_path_comprovante)
        elif update.message.document:
            file = await update.message.document.get_file()
            file_path_comprovante = f"{nome_base}.pdf" # Assumindo que o filtro já garantiu PDF
            await file.download_to_drive(file_path_comprovante)
        
        if file_path_comprovante: # Se o arquivo foi salvo
            enviar_email_comprovante(
                EMAIL_DESTINO,
                f"📩 Novo comprovante de @{username or first_name}",
                f"Comprovante enviado por @{username or first_name} (ID: {chat_id}, Plano: {plano_id_selecionado}) em {agora}.",
                file_path_comprovante
            )
            await update.message.reply_text("✅ Comprovante por e-mail enviado ao admin!")
        else:
            await update.message.reply_text("❌ Falha ao processar o arquivo do comprovante.")
            return
            
    except Exception as e:
        await update.message.reply_text(f"❌ Falha ao salvar ou enviar comprovante por e-mail. Erro: {e}")
        # Não retorna aqui necessariamente, podemos tentar registrar no painel mesmo assim se quisermos

    # Preparar dados para a API do Painel
    payload_para_painel = {
        "chave_api_bot": CHAVE_PAINEL,
        "chat_id": chat_id,
        "username": username, # Envia None se não houver
        "first_name": first_name,
        "id_plano": plano_id_selecionado,
        "status_pagamento": "pendente_comprovante" # Status inicial
    }

    api_url_registrar = f"{API_PAINEL_URL}/api/bot/registrar_assinatura"

    try:
        print(f"Enviando para API do Painel: {api_url_registrar}, payload: {payload_para_painel}") # Log
        response = requests.post(api_url_registrar, json=payload_para_painel)
        response.raise_for_status() # Levanta um erro para status HTTP 4xx/5xx

        response_data = response.json()
        if response_data.get("status") == "sucesso":
            await update.message.reply_text("📩 Seu comprovante foi recebido e registrado! Em breve o admin irá verificar e liberar seu acesso. Use /status para checar.")
            
            # Notificar o admin (mantendo esta parte)
            admin_username_display = user.username if user.username else first_name
            try:
                await context.bot.send_message(
                    chat_id=int(USUARIO_ADMIN),
                    text=f"📢 Novo comprovante (e registro no painel OK) enviado por @{admin_username_display} (ID: {chat_id}) para o plano {plano_id_selecionado}.\nVerifique no painel web para aprovar."
                )
            except Exception as e_admin_msg:
                print(f"Erro ao notificar admin sobre registro no painel: {e_admin_msg}")
        else:
            # Mensagem de erro vinda da API do painel
            await update.message.reply_text(f"⚠️ Falha ao registrar sua solicitação no painel: {response_data.get('mensagem', 'Erro desconhecido do painel.')}")

    except requests.exceptions.HTTPError as http_err:
        await update.message.reply_text(f"❌ Erro de HTTP ao comunicar com o painel: {http_err}")
        print(f"Erro HTTP da API do Painel: {http_err.response.status_code} - {http_err.response.text}")
    except requests.exceptions.RequestException as req_err:
        await update.message.reply_text(f"❌ Erro de conexão ao comunicar com o painel: {req_err}")
        print(f"Erro de Conexão com API do Painel: {req_err}")
    except Exception as e:
        await update.message.reply_text(f"❌ Ocorreu um erro inesperado ao processar seu comprovante: {e}")
        print(f"Erro inesperado em receber_comprovante: {e}")
    finally:
        # Limpa o plano selecionado para que o usuário precise escolher novamente para uma nova compra
        if 'plano_selecionado_id' in context.user_data:
            del context.user_data['plano_selecionado_id']
        if 'plano_selecionado_nome' in context.user_data: # Limpa também o nome do plano
            del context.user_data['plano_selecionado_nome']


#async def liberar(update: Update, context: ContextTypes.DEFAULT_TYPE): <---- COMANDO /liberar NO BOT, NAO É MAIS UTILIZADA
#    if str(update.effective_user.id) != USUARIO_ADMIN:
#        await update.message.reply_text("🚫 Você não tem permissão para isso.")
#        return
#
#    if not context.args:
#        await update.message.reply_text("Uso: /liberar @usuario")
#        return
#
#    username = context.args[0].lstrip("@")
#    chat_id = usuarios_aprovados.get(username)
#
#    if chat_id:
#        try:
#            await context.bot.send_message(
#                chat_id=chat_id,
#                text=f"✅ Pagamento confirmado!\nBem-vindo ao grupo VIP 🔥\nAcesse o conteúdo aqui: {GRUPO_EXCLUSIVO}"
#            )
#            await update.message.reply_text(f"✅ @{username} liberado com sucesso!")
#        except Exception as e:
#            await update.message.reply_text(f"⚠️ Erro ao notificar @{username}: {e}")
#    else:
#        await update.message.reply_text(f"⚠️ Não encontrei o chat_id de @{username}.")

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat_id = user.id
    username_display = user.username if user.username else user.first_name

    payload_para_painel = {
        "chave_api_bot": CHAVE_PAINEL, # Usando a CHAVE_PAINEL do .env
        "chat_id": chat_id
        # Poderíamos enviar 'id_plano' se quiséssemos o status de um plano específico,
        # mas a API do painel que fizemos busca a assinatura mais relevante se 'id_plano' for omitido.
    }
    api_url_verificar_status = f"{API_PAINEL_URL}/api/bot/verificar_status"

    try:
        print(f"Verificando status para {chat_id} na API: {api_url_verificar_status}") # Log
        response = requests.post(api_url_verificar_status, json=payload_para_painel)
        response.raise_for_status() # Levanta erro para status 4xx/5xx

        data = response.json()
        if data.get("status") == "sucesso":
            if data.get("assinatura_ativa"):
                status_pagamento = data.get("status_pagamento", "desconhecido")
                nome_plano = data.get("nome_plano", "seu plano") # Nome do plano vindo da API
                
                if "aprovado" in status_pagamento.lower() or "pago" in status_pagamento.lower():
                    link_conteudo = data.get("link_conteudo")
                    if link_conteudo:
                        await update.message.reply_text(
                            f"✅ Olá {username_display}! Seu acesso ao {nome_plano} está liberado!\n\n"
                            f"🔥 Acesse o conteúdo aqui: {link_conteudo}"
                        )
                    else:
                        await update.message.reply_text(
                            f"✅ Olá {username_display}! Seu acesso ao {nome_plano} está confirmado, "
                            f"mas houve um problema ao obter o link. Contate o suporte."
                        )
                elif status_pagamento == "pendente_comprovante":
                    await update.message.reply_text(
                        f"⏳ Olá {username_display}. Seu comprovante para o {nome_plano} foi recebido e está em análise. "
                        f"Aguarde a liberação pelo administrador."
                    )
                else: # Outros status pendentes ou desconhecidos
                    await update.message.reply_text(
                        f"⏳ Olá {username_display}. O status do seu pagamento para o {nome_plano} é: {status_pagamento}. "
                        f"Se já enviou o comprovante, aguarde. Caso contrário, envie o comprovante ou contate o suporte."
                    )
            else: # Nenhuma assinatura encontrada
                await update.message.reply_text(
                    "🤔 Não encontrei uma assinatura ativa ou pendente para você. "
                    "Use /start para ver os planos e realizar uma nova assinatura."
                )
        else: # Erro na resposta da API do painel
            await update.message.reply_text(f"⚠️ Não consegui verificar seu status no momento: {data.get('mensagem', 'Erro do servidor do painel')}")

    except requests.exceptions.HTTPError as http_err:
        await update.message.reply_text(f"❌ Erro de HTTP ao consultar seu status: Verifique os logs do bot.")
        print(f"Erro HTTP da API do Painel (status): {http_err.response.status_code} - {http_err.response.text}")
    except requests.exceptions.RequestException as req_err:
        await update.message.reply_text(f"❌ Erro de conexão ao consultar seu status. Tente mais tarde.")
        print(f"Erro de Conexão com API do Painel (status): {req_err}")
    except Exception as e:
        await update.message.reply_text(f"❌ Ocorreu um erro inesperado ao verificar seu status.")
        print(f"Erro inesperado em status: {e}")

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
        BotCommand("meuid", "Verifica qual o seu ID"),
        BotCommand("ajuda", "Explica como funciona o bot"),
        BotCommand("liberar", "Admin: liberar acesso de um usuário")
    ]
    
    await bot.set_my_commands(comandos)

flask_app = Flask(__name__)
app = None
loop = None

# ... outras importações e definições ...

# CHAVE_PAINEL já deve estar definida no seu .env e carregada no início do script
# Esta é a chave que o PAINEL usará para se autenticar com o BOT nesta rota interna 

@flask_app.route('/api/bot/notificar_aprovacao', methods=['POST'])
def rota_notificar_aprovacao():
    global app # Acesso à instância da Application do python-telegram-bot
    global loop # Acesso ao loop asyncio principal do bot

    if not app or not loop:
        print("ERRO INTERNO: Instância do bot (app) ou loop não disponível para notificar_aprovacao.")
        return jsonify({"status": "erro", "mensagem": "Erro interno do bot"}), 500

    try:
        data = request.get_json()
        if not data:
            return jsonify({"status": "erro", "mensagem": "Requisição sem JSON"}), 400

        # Verificação de segurança simples com a chave compartilhada
        if data.get("chave_secreta_interna") != CHAVE_SECRETA_BOT_INTERNA:
            print(f"Falha na autenticação para /api/bot/notificar_aprovacao. Chave recebida: {data.get('chave_secreta_interna')}")
            return jsonify({"status": "erro", "mensagem": "Não autorizado - Chave interna inválida"}), 403

        chat_id_usuario = data.get("chat_id")
        link_conteudo = data.get("link_conteudo")
        nome_plano = data.get("nome_plano", "seu plano") # Pega o nome do plano, se enviado

        if not chat_id_usuario or not link_conteudo:
            return jsonify({"status": "erro", "mensagem": "Dados incompletos: chat_id e link_conteudo são obrigatórios"}), 400

        mensagem_para_usuario = (
            f"🎉 Pagamento confirmado e acesso liberado!\n\n"
            f"Bem-vindo(a) ao {nome_plano}! 🔥\n"
            f"Acesse seu conteúdo exclusivo aqui: {link_conteudo}"
        )

        # Enviando a mensagem para o usuário através do bot
        # Usamos run_coroutine_threadsafe porque esta rota Flask roda em uma thread separada
        # do loop asyncio principal do bot.
        coro = app.bot.send_message(chat_id=int(chat_id_usuario), text=mensagem_para_usuario)
        asyncio.run_coroutine_threadsafe(coro, loop)

        print(f"Notificação de aprovação enviada para chat_id: {chat_id_usuario}")
        return jsonify({"status": "sucesso", "mensagem": "Notificação de aprovação agendada para envio."}), 200

    except Exception as e:
        print(f"Erro na rota /api/bot/notificar_aprovacao: {e}")
        return jsonify({"status": "erro", "mensagem": str(e)}), 500

@flask_app.route('/webhook', methods=['POST'])
def webhook():
    if request.method == "POST":
        update = Update.de_json(request.get_json(force=True), bot)
        asyncio.run_coroutine_threadsafe(app.update_queue.put(update), loop)
        print(f"METODO /POST FUNCIONANDO!") # tentativa falha de log
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
    