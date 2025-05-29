from flask import Flask, render_template, request, redirect, url_for, session, flash
import json
import os

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY_PAINEL")

# Usuário e senha do login
USUARIO_PAINEL = os.getenv("USUARIO_PAINEL")
SENHA_PAINEL = os.getenv("SENHA_PAINEL")

# Caminho do arquivo JSON
ARQUIVO = 'usuarios_aprovados.json'

# Função para carregar usuários
def carregar_usuarios():
    if os.path.exists(ARQUIVO):
        with open(ARQUIVO, 'r') as f:
            return json.load(f)
    return []

# Função para salvar usuários
def salvar_usuarios(usuarios):
    with open(ARQUIVO, 'w') as f:
        json.dump(usuarios, f, indent=4)

# Página de login
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        senha = request.form['password']
        if username == USUARIO_PAINEL and senha == SENHA_PAINEL:
            session['logado'] = True
            return redirect(url_for('index'))
        else:
            flash('Usuário ou senha incorretos!', 'danger')
    return render_template('login.html')

# Logout
@app.route('/logout')
def logout():
    session.pop('logado', None)
    return redirect(url_for('login'))

# Página principal
@app.route('/')
def index():
    if not session.get('logado'):
        return redirect(url_for('login'))

    aprovados = carregar_usuarios()
    return render_template('index.html', aprovados=aprovados)

# Adicionar usuário
@app.route('/adicionar', methods=['POST'])
def adicionar():
    if not session.get('logado'):
        return redirect(url_for('login'))

    username = request.form['username']
    chat_id = request.form['chat_id']
    aprovados = carregar_usuarios()
    aprovados.append({'username': username, 'chat_id': chat_id})
    salvar_usuarios(aprovados)
    return redirect(url_for('index'))

# Remover usuário
@app.route('/remover/<username>')
def remover(username):
    if not session.get('logado'):
        return redirect(url_for('login'))

    aprovados = carregar_usuarios()
    aprovados = [u for u in aprovados if u['username'] != username]
    salvar_usuarios(aprovados)
    return redirect(url_for('index'))

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
