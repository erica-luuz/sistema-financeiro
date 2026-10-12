"""Login, logout e usuários (Versão 3, seção 4).

Um Blueprint é um "pedaço" do app com as suas próprias rotas. Ele é registrado no app.py
com app.register_blueprint(). As rotas daqui são chamadas com o prefixo "auth.":
url_for("auth.login"), url_for("auth.logout").
"""
import re
from datetime import timedelta

import click
from flask import Blueprint, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from db import get_db_connection

# cli_group=None: o comando fica "flask criar-usuario" (e não "flask auth criar-usuario")
bp = Blueprint("auth", __name__, cli_group=None)

TAMANHO_MINIMO_SENHA = 10
DURACAO_SESSAO = timedelta(days=30)        # "Manter conectado"
PAGINAS_LIVRES = {"auth.login", "static"}  # as únicas que abrem sem login

# Hash de uma senha qualquer: usado quando o login digitado não existe, para o sistema
# demorar o mesmo tempo nos dois casos (senão daria para descobrir quais logins existem
# medindo quanto tempo a resposta leva)
HASH_FALSO = generate_password_hash("senha-qualquer-so-para-gastar-o-mesmo-tempo")


def salvar_usuario(conn, nome, login, senha):
    """Cria o usuário; se o login já existe, redefine a senha (e desbloqueia)."""
    if len(senha) < TAMANHO_MINIMO_SENHA:
        raise ValueError(f"A senha precisa ter pelo menos {TAMANHO_MINIMO_SENHA} caracteres.")
    conn.execute(
        """
        INSERT INTO usuarios (nome, login, senha_hash) VALUES (?, ?, ?)
        ON CONFLICT (login) DO UPDATE SET
            senha_hash = excluded.senha_hash,
            tentativas_erradas = 0,
            bloqueado_ate = NULL
        """,
        (nome, login, generate_password_hash(senha)),
    )
    conn.commit()


def destino_seguro(proximo):
    """Só aceita voltar para um endereço DESTE site (ex.: '/orcamento').

    Sem isso, um link malicioso como /login?proximo=https://site-falso.com
    mandaria a pessoa para outro site logo depois do login.
    """
    if proximo and proximo.startswith("/") and not proximo.startswith("//"):
        return proximo
    return url_for("dashboard")


@bp.before_app_request
def exigir_login():
    """Roda ANTES de toda requisição do app: carrega quem está logado ou manda para o login."""
    g.usuario = None   # g = "global" que vale só durante esta requisição
    usuario_id = session.get("usuario_id")
    if usuario_id:
        conn = get_db_connection()
        g.usuario = conn.execute(
            "SELECT id, nome, login FROM usuarios WHERE id = ?", (usuario_id,)
        ).fetchone()
        conn.close()
        if g.usuario is None:   # usuário apagado do banco: a sessão não vale mais
            session.clear()

    if g.usuario is None and request.endpoint not in PAGINAS_LIVRES:
        # Guarda para onde a pessoa queria ir, para voltar lá depois de entrar
        destino = request.full_path if request.query_string else request.path
        return redirect(url_for("auth.login", proximo=destino))


@bp.route("/login", methods=["GET", "POST"])
def login():
    if g.usuario:
        return redirect(url_for("dashboard"))
    proximo = request.values.get("proximo", "")

    if request.method == "POST":
        login_digitado = request.form.get("login", "").strip().lower()
        senha = request.form.get("senha", "")

        conn = get_db_connection()
        usuario = conn.execute(
            "SELECT * FROM usuarios WHERE login = ?", (login_digitado,)
        ).fetchone()
        conn.close()

        # Compara o hash do que foi digitado com o hash guardado (a senha em si nunca é guardada)
        senha_confere = check_password_hash(usuario["senha_hash"] if usuario else HASH_FALSO, senha)
        if usuario and senha_confere:
            session.clear()   # começa uma sessão nova, limpa
            session["usuario_id"] = usuario["id"]
            session.permanent = bool(request.form.get("manter_conectado"))
            return redirect(destino_seguro(proximo))

        # Mesma mensagem nos dois casos: não revela se o login existe
        return render_template(
            "login.html", erro="Login ou senha incorretos.", login=login_digitado, proximo=proximo
        ), 401

    return render_template("login.html", proximo=proximo)


@bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("auth.login"))


@bp.cli.command("criar-usuario")
def criar_usuario_comando():
    """Cria um usuário, ou redefine a senha de um que já existe.

    Uso:  flask --app app criar-usuario
    """
    login = click.prompt("Login (minúsculo, sem espaços — ex.: erica)").strip().lower()
    if not re.fullmatch(r"[a-z0-9._-]{3,30}", login):
        raise click.ClickException("Login inválido: use de 3 a 30 letras minúsculas, números, ponto, - ou _.")

    conn = get_db_connection()
    existente = conn.execute("SELECT nome FROM usuarios WHERE login = ?", (login,)).fetchone()
    if existente:
        click.confirm(f"O login '{login}' ({existente['nome']}) já existe. Redefinir a senha?", abort=True)
        nome = existente["nome"]
    else:
        nome = click.prompt("Nome que aparece no menu (ex.: Érica)").strip()

    # hide_input: a senha não aparece enquanto é digitada; confirmation_prompt: pede duas vezes
    senha = click.prompt(
        f"Senha (mínimo {TAMANHO_MINIMO_SENHA} caracteres)",
        hide_input=True,
        confirmation_prompt="Digite a senha de novo",
    )
    try:
        salvar_usuario(conn, nome, login, senha)
    except ValueError as erro:
        raise click.ClickException(str(erro))
    finally:
        conn.close()

    click.echo(f"Pronto! {'Senha redefinida' if existente else 'Usuário criado'}: {nome} (login: {login})")
