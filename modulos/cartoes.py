"""Cartões de crédito: cadastro, faturas e limite."""
import sqlite3
from datetime import date

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

import relogio
from db import get_db_connection
from util import para_centavos, sem_acento
from faturas import data_fechamento, situacao_fatura

bp = Blueprint("cartoes", __name__)


def ler_formulario_cartao():
    """Lê os campos do cartão como textos. Se der erro, eles voltam para a tela."""
    return {
        "nome": request.form.get("nome", "").strip(),
        "titular": request.form.get("titular", "").strip(),
        "dia_fechamento": request.form.get("dia_fechamento", "").strip(),
        "dia_vencimento": request.form.get("dia_vencimento", "").strip(),
        "limite": request.form.get("limite", "").strip(),
        "ativo": "1" if request.form.get("ativo") else "0",  # checkbox desmarcado não é enviado
    }


def dados_do_cartao(cartao):
    """Converte uma linha do banco nos textos que o formulário espera."""
    limite = cartao["limite_centavos"]
    return {
        "nome": cartao["nome"],
        "titular": cartao["titular"],
        "dia_fechamento": str(cartao["dia_fechamento"]),
        "dia_vencimento": str(cartao["dia_vencimento"]),
        "limite": f"{limite / 100:.2f}" if limite else "",
        "ativo": str(cartao["ativo"]),
    }


def validar_cartao(dados):
    """Devolve a mensagem de erro, ou None se estiver tudo certo."""
    if not dados["nome"]:
        return "Informe o nome do cartão."
    if not dados["titular"]:
        return "Informe o titular do cartão."
    for campo, rotulo in (("dia_fechamento", "fechamento"), ("dia_vencimento", "vencimento")):
        if not dados[campo].isdigit() or not 1 <= int(dados[campo]) <= 28:
            return f"O dia de {rotulo} deve ser um número de 1 a 28."
    if dados["limite"]:
        try:
            if para_centavos(dados["limite"]) <= 0:
                return "O limite deve ser maior que zero (ou deixe em branco)."
        except (ValueError, OverflowError):
            return "Informe um limite válido, por exemplo 5000,00 (ou deixe em branco)."
    return None


def valores_cartao(dados):
    """Os valores, já convertidos, na ordem das colunas do banco."""
    return (
        dados["nome"],
        dados["titular"],
        int(dados["dia_fechamento"]),
        int(dados["dia_vencimento"]),
        para_centavos(dados["limite"]) if dados["limite"] else None,
        int(dados["ativo"]),
    )


def cartao_repetido(dados):
    return f"{dados['titular']} já tem um cartão chamado '{dados['nome']}'. Use outro nome."


def buscar_titulares():
    """Os titulares já cadastrados, para sugerir no formulário (ex.: ['Érica', 'Heberton'])."""
    conn = get_db_connection()
    linhas = conn.execute("SELECT DISTINCT titular FROM cartoes").fetchall()
    conn.close()
    return sorted((linha["titular"] for linha in linhas), key=sem_acento)


def buscar_cartoes():
    """Todos os cartões: ativos primeiro, agrupados por titular (ordem sem acento: Érica antes de Heberton)."""
    conn = get_db_connection()
    lista = conn.execute("SELECT * FROM cartoes").fetchall()
    conn.close()
    return sorted(lista, key=lambda c: (-c["ativo"], sem_acento(c["titular"]), sem_acento(c["nome"])))


@bp.route("/cartoes")
def listar():
    return render_template("cartoes.html", cartoes=buscar_cartoes())


@bp.route("/cartoes/novo", methods=["GET", "POST"])
def novo():
    if request.method == "POST":
        dados = ler_formulario_cartao()
        dados["ativo"] = "1"  # cartão novo sempre começa ativo
        erro = validar_cartao(dados)
        if not erro:
            conn = get_db_connection()
            try:
                conn.execute(
                    "INSERT INTO cartoes "
                    "(nome, titular, dia_fechamento, dia_vencimento, limite_centavos, ativo) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    valores_cartao(dados),
                )
                conn.commit()
                flash(f"Cartão \"{dados['nome']}\" cadastrado.", "sucesso")
                return redirect(url_for("cartoes.listar"))
            except sqlite3.IntegrityError:
                erro = cartao_repetido(dados)
            finally:
                conn.close()
        return render_template(
            "cartao_form.html", titulo="Novo cartão", dados=dados, erro=erro,
            titulares=buscar_titulares(),
        )

    return render_template(
        "cartao_form.html", titulo="Novo cartão", dados={"ativo": "1"},
        titulares=buscar_titulares(),
    )


@bp.route("/cartoes/editar/<int:cartao_id>", methods=["GET", "POST"])
def editar(cartao_id):
    conn = get_db_connection()
    cartao = conn.execute("SELECT * FROM cartoes WHERE id = ?", (cartao_id,)).fetchone()
    if cartao is None:
        conn.close()
        abort(404)

    if request.method == "POST":
        dados = ler_formulario_cartao()
        erro = validar_cartao(dados)
        if not erro:
            try:
                conn.execute(
                    "UPDATE cartoes SET nome = ?, titular = ?, dia_fechamento = ?, "
                    "dia_vencimento = ?, limite_centavos = ?, ativo = ? WHERE id = ?",
                    (*valores_cartao(dados), cartao_id),  # * "espalha" a tupla dentro da outra
                )
                conn.commit()
                conn.close()
                flash("Cartão atualizado.", "sucesso")
                return redirect(url_for("cartoes.listar"))
            except sqlite3.IntegrityError:
                erro = cartao_repetido(dados)
        conn.close()
        return render_template(
            "cartao_form.html", titulo="Editar cartão", cartao=cartao, dados=dados, erro=erro,
            titulares=buscar_titulares(),
        )

    conn.close()
    return render_template(
        "cartao_form.html", titulo="Editar cartão", cartao=cartao,
        dados=dados_do_cartao(cartao), titulares=buscar_titulares(),
    )


def total_fatura(conn, cartao_id, vencimento):
    """Soma das parcelas de um cartão que vencem nessa data (ou seja, dessa fatura)."""
    return conn.execute(
        """
        SELECT COALESCE(SUM(l.valor_centavos), 0)
        FROM lancamentos l
        JOIN compras_cartao cc ON cc.id = l.compra_id
        WHERE cc.cartao_id = ? AND l.data = ?
        """,
        (cartao_id, vencimento.isoformat()),
    ).fetchone()[0]


def limite_usado(conn, cartao_id, hoje):
    """Parcelas que ainda não venceram: é o quanto do limite está comprometido."""
    return conn.execute(
        """
        SELECT COALESCE(SUM(l.valor_centavos), 0)
        FROM lancamentos l
        JOIN compras_cartao cc ON cc.id = l.compra_id
        WHERE cc.cartao_id = ? AND l.data >= ?
        """,
        (cartao_id, hoje.isoformat()),
    ).fetchone()[0]


@bp.route("/cartoes/<int:cartao_id>/faturas")
def faturas(cartao_id):
    conn = get_db_connection()
    cartao = conn.execute("SELECT * FROM cartoes WHERE id = ?", (cartao_id,)).fetchone()
    if cartao is None:
        conn.close()
        abort(404)

    hoje = relogio.hoje()
    inicio_mes = hoje.replace(day=1).isoformat()
    mostrar_anteriores = request.args.get("anteriores") == "1"

    parcelas = conn.execute(
        """
        SELECT l.data, l.data_compra, l.descricao, l.valor_centavos,
               l.parcela_numero, l.parcela_total, l.compra_id, c.nome AS categoria
        FROM lancamentos l
        JOIN compras_cartao cc ON cc.id = l.compra_id
        JOIN categorias c ON c.id = l.categoria_id
        WHERE cc.cartao_id = ? AND (? OR l.data >= ?)
        ORDER BY l.data, l.data_compra, l.id
        """,
        (cartao_id, mostrar_anteriores, inicio_mes),
    ).fetchall()
    qtd_anteriores = conn.execute(
        """
        SELECT COUNT(DISTINCT l.data) FROM lancamentos l
        JOIN compras_cartao cc ON cc.id = l.compra_id
        WHERE cc.cartao_id = ? AND l.data < ?
        """,
        (cartao_id, inicio_mes),
    ).fetchone()[0]
    usado = limite_usado(conn, cartao_id, hoje)
    conn.close()

    # Agrupa as parcelas por fatura (todas as parcelas de uma fatura têm a mesma data de vencimento)
    faturas = {}
    for parcela in parcelas:
        if parcela["data"] not in faturas:
            vencimento = date.fromisoformat(parcela["data"])
            faturas[parcela["data"]] = {
                "vencimento": parcela["data"],
                "fechamento": data_fechamento(
                    cartao["dia_fechamento"], cartao["dia_vencimento"], vencimento.year, vencimento.month
                ).isoformat(),
                "situacao": situacao_fatura(
                    vencimento, cartao["dia_fechamento"], cartao["dia_vencimento"], hoje
                ),
                "itens": [],
                "total": 0,
            }
        faturas[parcela["data"]]["itens"].append(parcela)
        faturas[parcela["data"]]["total"] += parcela["valor_centavos"]

    limite = cartao["limite_centavos"]
    return render_template(
        "cartao_faturas.html",
        cartao=cartao,
        faturas=list(faturas.values()),
        usado=usado,
        disponivel=(limite - usado) if limite else None,
        mostrar_anteriores=mostrar_anteriores,
        qtd_anteriores=qtd_anteriores,
    )


@bp.route("/cartoes/excluir/<int:cartao_id>", methods=["POST"])
def excluir(cartao_id):
    conn = get_db_connection()
    try:
        conn.execute("DELETE FROM cartoes WHERE id = ?", (cartao_id,))
        conn.commit()
    except sqlite3.IntegrityError:
        # A partir da Etapa 12, o ON DELETE RESTRICT das compras impede excluir cartão usado
        erro = "Este cartão tem compras e não pode ser excluído. Desative-o em Editar."
        return render_template("cartoes.html", cartoes=buscar_cartoes(), erro=erro)
    finally:
        conn.close()
    flash("Cartão excluído.", "sucesso")
    return redirect(url_for("cartoes.listar"))
