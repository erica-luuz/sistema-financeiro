"""Testes do login (Versão 3, seção 4). Rode com:  python -m pytest

Cada teste recebe um banco NOVO e temporário (fixture "cliente"): nunca mexe nos dados reais.
"""
import pytest

import db


@pytest.fixture
def cliente(tmp_path, monkeypatch):
    """Banco temporário com as tabelas e um usuário 'erica', e um navegador de teste."""
    # monkeypatch troca valores só durante o teste e desfaz tudo no final
    monkeypatch.setattr(db, "CAMINHO_BANCO", str(tmp_path / "teste.db"))
    monkeypatch.setattr(db, "PASTA_BACKUPS", tmp_path / "backups")
    db.init_db()

    from app import app
    from auth import salvar_usuario

    conn = db.get_db_connection()
    salvar_usuario(conn, "Érica", "erica", "senha-forte-123")
    conn.close()
    return app.test_client()


def entrar(cliente, login="erica", senha="senha-forte-123", **extras):
    return cliente.post("/login", data={"login": login, "senha": senha, **extras})


# ---------- sem login, nada abre ----------

@pytest.mark.parametrize("pagina", [
    "/", "/lancamentos", "/lancamentos/novo", "/cartoes", "/orcamento",
    "/recorrencias", "/categorias", "/lancamentos/exportar.csv",
])
def test_paginas_exigem_login(cliente, pagina):
    resposta = cliente.get(pagina)
    assert resposta.status_code == 302
    assert resposta.headers["Location"].startswith("/login")


def test_post_sem_login_nao_altera_nada(cliente):
    resposta = cliente.post("/categorias/nova", data={"nome": "Invasor", "tipo": "despesa"})
    assert resposta.headers["Location"].startswith("/login")
    conn = db.get_db_connection()
    assert conn.execute("SELECT COUNT(*) FROM categorias WHERE nome = 'Invasor'").fetchone()[0] == 0
    conn.close()


def test_login_e_css_abrem_sem_login(cliente):
    assert cliente.get("/login").status_code == 200
    assert cliente.get("/static/css/style.css").status_code == 200


# ---------- entrar ----------

def test_login_certo_entra(cliente):
    resposta = entrar(cliente)
    assert resposta.status_code == 302
    assert cliente.get("/").status_code == 200
    assert "Érica" in cliente.get("/").get_data(as_text=True)   # nome no menu


def test_login_aceita_maiusculas_e_espacos_no_login(cliente):
    entrar(cliente, login="  Erica ")
    assert cliente.get("/").status_code == 200


@pytest.mark.parametrize("login, senha", [
    ("erica", "senha-errada-123"),       # senha errada
    ("ninguem", "senha-forte-123"),      # login que não existe
    ("erica", ""),                       # senha vazia
])
def test_login_errado_mostra_a_mesma_mensagem(cliente, login, senha):
    resposta = entrar(cliente, login=login, senha=senha)
    assert resposta.status_code == 401
    assert "Login ou senha incorretos." in resposta.get_data(as_text=True)
    assert cliente.get("/").status_code == 302   # continua sem acesso


def test_volta_para_a_pagina_pedida(cliente):
    cliente.get("/orcamento?mes=2026-10")
    resposta = entrar(cliente, proximo="/orcamento?mes=2026-10")
    assert resposta.headers["Location"] == "/orcamento?mes=2026-10"


@pytest.mark.parametrize("proximo", ["https://site-falso.com", "//site-falso.com"])
def test_nao_redireciona_para_outro_site(cliente, proximo):
    resposta = entrar(cliente, proximo=proximo)
    assert resposta.headers["Location"] == "/"


# ---------- sair ----------

def test_sair_encerra_a_sessao(cliente):
    entrar(cliente)
    cliente.post("/logout")
    assert cliente.get("/").status_code == 302


def test_sair_nao_funciona_por_get(cliente):
    entrar(cliente)
    assert cliente.get("/logout").status_code == 405
    assert cliente.get("/").status_code == 200   # continua logado


# ---------- senhas ----------

def test_senha_nunca_e_guardada(cliente):
    conn = db.get_db_connection()
    guardado = conn.execute("SELECT senha_hash FROM usuarios WHERE login = 'erica'").fetchone()[0]
    conn.close()
    assert "senha-forte-123" not in guardado


def test_senha_curta_e_recusada(cliente):
    from auth import salvar_usuario
    conn = db.get_db_connection()
    with pytest.raises(ValueError):
        salvar_usuario(conn, "Heberton", "heberton", "curta")
    conn.close()


def test_redefinir_senha(cliente):
    from auth import salvar_usuario
    conn = db.get_db_connection()
    salvar_usuario(conn, "Érica", "erica", "outra-senha-456")
    conn.close()
    assert entrar(cliente).status_code == 401                      # a antiga não vale mais
    assert entrar(cliente, senha="outra-senha-456").status_code == 302
