from flask import Flask, render_template, request, redirect, url_for
import os

app = Flask(__name__)

ARQUIVO_APROVADOS = "aprovados.txt"


def ler_aprovados():
    aprovados = []
    if os.path.exists(ARQUIVO_APROVADOS):
        with open(ARQUIVO_APROVADOS, "r") as f:
            for linha in f:
                username, chat_id = linha.strip().split("|")
                aprovados.append({"username": username, "chat_id": chat_id})
    return aprovados


def salvar_aprovados(aprovados):
    with open(ARQUIVO_APROVADOS, "w") as f:
        for usuario in aprovados:
            f.write(f"{usuario['username']}|{usuario['chat_id']}\n")


@app.route("/")
def index():
    aprovados = ler_aprovados()
    return render_template("index.html", aprovados=aprovados)


@app.route("/adicionar", methods=["POST"])
def adicionar():
    username = request.form.get("username").lstrip("@").strip()
    chat_id = request.form.get("chat_id").strip()

    if username and chat_id:
        aprovados = ler_aprovados()
        aprovados.append({"username": username, "chat_id": chat_id})
        salvar_aprovados(aprovados)

    return redirect(url_for("index"))


@app.route("/remover/<username>")
def remover(username):
    aprovados = ler_aprovados()
    aprovados = [u for u in aprovados if u["username"] != username]
    salvar_aprovados(aprovados)
    return redirect(url_for("index"))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
