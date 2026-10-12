"""Testes das proteções (Versão 3, seções 4.4, 4.5 e 5): CSRF, bloqueio, trocar senha."""
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import db
from conftest import SENHA_ERICA


def entrar(cliente, senha=SENHA_ERICA, **extras):
    return cliente.post("/login", data={"login": "erica", "senha": senha, **extras})


def token_da_pagina(cliente, pagina):
    """Abre a página e pega o token CSRF escondido no formulário (como o navegador faz)."""
    html = cliente.get(pagina).get_data(as_text=True)
    return re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)


# ---------- CSRF ----------

def test_todo_formulario_post_tem_token_csrf():
    """Varre TODOS os templates: nenhum <form method="post"> pode ficar sem o token.
    Se alguém criar um formulário novo e esquecer, este teste avisa."""
    sem_token = []
    for arquivo in Path("templates").glob("*.html"):
        texto = arquivo.read_text(encoding="utf-8")
        for formulario in re.findall(r'<form[^>]*method="post".*?</form>', texto, re.S | re.I):
            if "csrf_token()" not in formulario:
                sem_token.append(arquivo.name)
    assert sem_token == []


def test_post_sem_token_e_recusado(cliente_csrf):
    resposta = cliente_csrf.post("/login", data={"login": "erica", "senha": SENHA_ERICA})
    assert resposta.status_code == 400
    assert "A página expirou" in resposta.get_data(as_text=True)
    assert cliente_csrf.get("/").status_code == 302   # não entrou


def test_post_com_token_funciona(cliente_csrf):
    token = token_da_pagina(cliente_csrf, "/login")
    resposta = cliente_csrf.post(
        "/login", data={"login": "erica", "senha": SENHA_ERICA, "csrf_token": token}
    )
    assert resposta.status_code == 302
    assert cliente_csrf.get("/").status_code == 200


def test_acao_logada_sem_token_e_recusada(cliente_csrf):
    """Mesmo logada, um POST sem token (como o de um site malicioso) não altera nada."""
    token = token_da_pagina(cliente_csrf, "/login")
    cliente_csrf.post("/login", data={"login": "erica", "senha": SENHA_ERICA, "csrf_token": token})
    resposta = cliente_csrf.post("/categorias/nova", data={"nome": "Invasor", "tipo": "despesa"})
    assert resposta.status_code == 400
    conn = db.get_db_connection()
    assert conn.execute("SELECT COUNT(*) FROM categorias WHERE nome = 'Invasor'").fetchone()[0] == 0
    conn.close()


# ---------- bloqueio por tentativas ----------

def test_cinco_senhas_erradas_bloqueiam(cliente):
    for _ in range(5):
        assert entrar(cliente, senha="errada-123456").status_code == 401
    resposta = entrar(cliente)   # agora até a senha CERTA é recusada
    assert resposta.status_code == 429
    assert "bloqueado" in resposta.get_data(as_text=True)
    assert cliente.get("/").status_code == 302


def test_bloqueio_acaba_depois_do_tempo(cliente):
    for _ in range(5):
        entrar(cliente, senha="errada-123456")
    # Simula que os 15 minutos já passaram
    passado = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    conn = db.get_db_connection()
    conn.execute("UPDATE usuarios SET bloqueado_ate = ? WHERE login = 'erica'", (passado,))
    conn.commit()
    conn.close()
    assert entrar(cliente).status_code == 302


def test_acertar_a_senha_zera_o_contador(cliente):
    for _ in range(4):
        entrar(cliente, senha="errada-123456")
    entrar(cliente)            # acertou na 5ª
    cliente.post("/logout")
    for _ in range(4):         # mais 4 erros não bloqueiam (o contador recomeçou)
        entrar(cliente, senha="errada-123456")
    assert entrar(cliente).status_code == 302


# ---------- trocar senha ----------

def trocar(cliente, atual=SENHA_ERICA, nova="nova-senha-789", confirmacao=None):
    return cliente.post("/conta/senha", data={
        "senha_atual": atual, "nova_senha": nova,
        "confirmacao": nova if confirmacao is None else confirmacao,
    })


def test_trocar_senha_exige_login(cliente):
    assert cliente.get("/conta/senha").headers["Location"].startswith("/login")


def test_trocar_senha_funciona(cliente):
    entrar(cliente)
    resposta = trocar(cliente)
    assert resposta.status_code == 302
    assert "Senha alterada com sucesso." in cliente.get("/").get_data(as_text=True)
    cliente.post("/logout")
    assert entrar(cliente).status_code == 401                       # a antiga não vale mais
    assert entrar(cliente, senha="nova-senha-789").status_code == 302


@pytest.mark.parametrize("dados, mensagem", [
    ({"atual": "errada-123456"}, "A senha atual está incorreta."),
    ({"nova": "curta"}, "pelo menos 10 caracteres"),
    ({"confirmacao": "outra-coisa-123"}, "A confirmação não é igual"),
    ({"nova": SENHA_ERICA}, "precisa ser diferente da atual"),
])
def test_trocar_senha_recusa(cliente, dados, mensagem):
    entrar(cliente)
    resposta = trocar(cliente, **dados)
    assert resposta.status_code == 400
    assert mensagem in resposta.get_data(as_text=True)


def test_trocar_senha_com_senha_atual_errada_conta_para_o_bloqueio(cliente):
    entrar(cliente)
    for _ in range(5):
        trocar(cliente, atual="errada-123456")
    resposta = trocar(cliente)   # mesmo com a senha atual certa
    assert "bloqueado" in resposta.get_data(as_text=True)


# ---------- cabeçalhos de segurança ----------

def test_cabecalhos_de_seguranca(cliente):
    resposta = cliente.get("/login")
    assert resposta.headers["X-Frame-Options"] == "DENY"
    assert resposta.headers["X-Content-Type-Options"] == "nosniff"
