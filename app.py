"""Finanças da Casa — ponto de partida do app.

Este arquivo só MONTA o app: configuração, segurança e o registro das partes.
As páginas ficam na pasta modulos/ (uma por assunto) e o login em auth.py:

    modulos/dashboard.py     /                      resumo do mês
    modulos/lancamentos.py   /lancamentos           lançamentos e exportação
    modulos/compras.py       /compras               compras no cartão (parcelas)
    modulos/cartoes.py       /cartoes               cartões e faturas
    modulos/orcamento.py     /orcamento             orçamento mensal
    modulos/recorrencias.py  /recorrencias          contas recorrentes
    modulos/categorias.py    /categorias            categorias
    auth.py                  /login /logout /conta  usuários e login

Regras que não dependem do Flask: faturas.py (cartão), relogio.py (fuso), util.py (formatação).
"""
import os

from dotenv import load_dotenv
from flask import Flask, render_template
from flask_wtf.csrf import CSRFError, CSRFProtect

import util

app = Flask(__name__)   # cria a aplicação (o "servidor")

# ---------- Configuração (Versão 3, seção 3) ----------
# Segredos ficam no arquivo .env (fora do Git). O load_dotenv() lê esse arquivo e coloca
# cada linha NOME=valor nas variáveis de ambiente, que o Python lê com os.environ.
load_dotenv()

SECRET_KEY = os.environ.get("SECRET_KEY", "")
if len(SECRET_KEY) < 32:
    # Sem chave forte o app NÃO inicia: melhor falhar do que rodar inseguro
    raise RuntimeError(
        "Falta a SECRET_KEY no arquivo .env (ou ela é curta demais).\n"
        "1. Copie o arquivo .env.exemplo para .env\n"
        "2. Gere uma chave com:  python -c \"import secrets; print(secrets.token_hex(32))\"\n"
        "3. Cole o resultado depois de SECRET_KEY= no .env"
    )
# A SECRET_KEY assina o cookie de sessão: é o que impede alguém de forjar um login
app.config["SECRET_KEY"] = SECRET_KEY

# ---------- Proteções (Versão 3, seções 4.5 e 5) ----------
# CSRF: todo POST precisa trazer o token secreto do formulário; POST vindo de outro site é recusado
app.config["WTF_CSRF_TIME_LIMIT"] = None   # o token vale enquanto a sessão valer (página aberta por horas não dá erro)
csrf = CSRFProtect(app)

# Cookie de sessão: o JavaScript da página não lê (HttpOnly), não vai em formulários de outros
# sites (SameSite) e, no servidor, só viaja por HTTPS (Secure — ligado pelo .env de produção)
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = os.environ.get("SESSAO_SOMENTE_HTTPS") == "1"


@app.errorhandler(CSRFError)
def token_invalido(erro):
    return render_template("erro_csrf.html"), 400


@app.after_request
def cabecalhos_de_seguranca(resposta):
    """Instruções extras de segurança enviadas ao navegador em toda resposta."""
    resposta.headers["X-Frame-Options"] = "DENY"               # ninguém coloca o app dentro de outro site (clickjacking)
    resposta.headers["X-Content-Type-Options"] = "nosniff"     # o navegador não "adivinha" o tipo dos arquivos
    resposta.headers["Referrer-Policy"] = "same-origin"        # endereços do app não vazam para outros sites
    return resposta


# ---------- Templates ----------
# Filtros: {{ 25050 | moeda }} → R$ 250,50 ; {{ "2026-10-09" | data_br }} → 09/10/2026 ...
for nome in ("moeda", "data_br", "data_local", "mes_ano", "forma"):
    app.add_template_filter(getattr(util, nome), nome)
# Variáveis disponíveis em todos os templates
app.jinja_env.globals["FORMAS_PAGAMENTO"] = util.FORMAS_PAGAMENTO
app.jinja_env.globals["FORMAS_FORMULARIO"] = util.FORMAS_FORMULARIO

# ---------- As partes do app ----------
# Os imports ficam aqui embaixo porque as partes dependem do app já configurado
from auth import DURACAO_SESSAO, bp as auth_bp  # noqa: E402
from modulos import (  # noqa: E402
    cartoes,
    categorias,
    compras,
    dashboard,
    lancamentos,
    orcamento,
    recorrencias,
)

app.config["PERMANENT_SESSION_LIFETIME"] = DURACAO_SESSAO
app.register_blueprint(auth_bp)   # login: "toda página exige login" fica em auth.py
for modulo in (dashboard, lancamentos, compras, cartoes, orcamento, recorrencias, categorias):
    app.register_blueprint(modulo.bp)


if __name__ == "__main__":
    # Debug só quando o .env pedir (FLASK_DEBUG=1) — no servidor ele fica desligado,
    # porque a página de erro do debug permite executar código Python no servidor
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1")
