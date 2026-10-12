"""Configuração compartilhada pelos testes (o pytest lê este arquivo automaticamente).

Os testes não usam o .env de verdade: recebem uma SECRET_KEY própria, só para testar.
"""
import os

import pytest

os.environ.setdefault("SECRET_KEY", "chave-somente-para-testes-" + "x" * 32)

import db  # noqa: E402  (precisa vir depois da SECRET_KEY)

SENHA_ERICA = "senha-forte-123"


@pytest.fixture
def app_teste(tmp_path, monkeypatch):
    """O app apontando para um banco NOVO e temporário, com a usuária 'erica'.

    monkeypatch troca valores só durante o teste e desfaz tudo no final —
    os dados reais nunca são tocados.
    """
    monkeypatch.setattr(db, "CAMINHO_BANCO", str(tmp_path / "teste.db"))
    monkeypatch.setattr(db, "PASTA_BACKUPS", tmp_path / "backups")
    db.init_db()

    from app import app
    from auth import salvar_usuario

    conn = db.get_db_connection()
    salvar_usuario(conn, "Érica", "erica", SENHA_ERICA)
    conn.close()
    return app


@pytest.fixture
def cliente(app_teste, monkeypatch):
    """Navegador de teste SEM a checagem de CSRF (para testar as outras regras com simplicidade).

    A proteção CSRF tem os seus próprios testes, com ela ligada (tests/test_seguranca.py).
    """
    monkeypatch.setitem(app_teste.config, "WTF_CSRF_ENABLED", False)
    return app_teste.test_client()


@pytest.fixture
def logado(cliente):
    """Navegador de teste já logado como Érica (CSRF desligado)."""
    cliente.post("/login", data={"login": "erica", "senha": SENHA_ERICA})
    return cliente


@pytest.fixture
def banco(app_teste):
    """Conexão com o banco temporário do teste, para conferir o que foi gravado."""
    conn = db.get_db_connection()
    yield conn          # yield: entrega a conexão ao teste e, quando ele termina, continua daqui
    conn.close()


def id_categoria(conn, nome, tipo="despesa"):
    return conn.execute(
        "SELECT id FROM categorias WHERE nome = ? AND tipo = ?", (nome, tipo)
    ).fetchone()[0]


@pytest.fixture
def cliente_csrf(app_teste, monkeypatch):
    """Navegador de teste COM a checagem de CSRF ligada, como em produção."""
    monkeypatch.setitem(app_teste.config, "WTF_CSRF_ENABLED", True)
    return app_teste.test_client()
