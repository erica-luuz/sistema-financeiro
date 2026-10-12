"""Categorias: listar, criar e excluir (com proteção para categorias em uso)."""
import sqlite3

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from db import get_db_connection
from util import sem_acento

bp = Blueprint("categorias", __name__)


def ordenar_categorias(categorias):
    """Ordena por tipo e depois por nome, ignorando acentos (a 'Água' vem antes de 'Alimentação')."""
    return sorted(categorias, key=lambda c: (c["tipo"], sem_acento(c["nome"])))


def buscar_categorias():
    """Devolve todas as categorias, ordenadas por tipo e nome."""
    conn = get_db_connection()
    categorias = conn.execute("SELECT id, nome, tipo FROM categorias").fetchall()
    conn.close()
    return ordenar_categorias(categorias)


def buscar_categorias_com_uso():
    """Devolve as categorias com a quantidade de lançamentos que usam cada uma."""
    conn = get_db_connection()
    categorias = conn.execute(
        """
        SELECT c.id, c.nome, c.tipo, COUNT(l.id) AS qtd_lancamentos
        FROM categorias c
        LEFT JOIN lancamentos l ON l.categoria_id = c.id
        GROUP BY c.id
        """
    ).fetchall()
    conn.close()
    return ordenar_categorias(categorias)


def tipo_confere_com_categoria(conn, categoria_id, tipo):
    """Regra de negócio: o tipo do lançamento deve ser igual ao tipo da categoria."""
    categoria = conn.execute(
        "SELECT tipo FROM categorias WHERE id = ?", (categoria_id,)
    ).fetchone()
    return categoria is not None and categoria["tipo"] == tipo


def categorias_de_despesa():
    return [c for c in buscar_categorias() if c["tipo"] == "despesa"]


@bp.route("/categorias")
def listar():
    return render_template("categorias.html", categorias=buscar_categorias_com_uso())


@bp.route("/categorias/nova", methods=["GET", "POST"])
def nova():
    if request.method == "POST":
        nome = request.form["nome"].strip()  # strip() tira espaços do começo e do fim
        tipo = request.form["tipo"]

        if not nome:
            return render_template(
                "nova_categoria.html", tipo=tipo, erro="Informe o nome da categoria."
            )
        if tipo not in ("receita", "despesa"):
            return render_template(
                "nova_categoria.html", nome=nome, erro="Escolha o tipo: receita ou despesa."
            )

        conn = get_db_connection()
        try:
            conn.execute("INSERT INTO categorias (nome, tipo) VALUES (?, ?)", (nome, tipo))
            conn.commit()
        except sqlite3.IntegrityError:
            # O UNIQUE (nome, tipo) do schema recusou: essa categoria já existe
            erro = f"Já existe uma categoria '{nome}' do tipo {tipo}. Use outro nome."
            return render_template("nova_categoria.html", nome=nome, tipo=tipo, erro=erro)
        finally:
            conn.close()  # o finally roda sempre: com ou sem erro

        flash(f"Categoria \"{nome}\" criada.", "sucesso")
        return redirect(url_for("categorias.listar"))

    return render_template("nova_categoria.html")


def categoria_em_uso(conn, categoria_id):
    """True se algum lançamento, compra, conta recorrente ou orçamento usa a categoria."""
    return conn.execute(
        """
        SELECT EXISTS (SELECT 1 FROM lancamentos    WHERE categoria_id = :id)
            OR EXISTS (SELECT 1 FROM compras_cartao WHERE categoria_id = :id)
            OR EXISTS (SELECT 1 FROM recorrencias   WHERE categoria_id = :id)
            OR EXISTS (SELECT 1 FROM orcamentos     WHERE categoria_id = :id)
        """,
        {"id": categoria_id},   # :id = parâmetro com nome (o mesmo valor usado 4 vezes)
    ).fetchone()[0]


@bp.route("/categorias/editar/<int:categoria_id>", methods=["GET", "POST"])
def editar(categoria_id):
    conn = get_db_connection()
    categoria = conn.execute("SELECT * FROM categorias WHERE id = ?", (categoria_id,)).fetchone()
    if categoria is None:
        conn.close()
        abort(404)
    # Categoria em uso pode mudar de NOME, mas não de TIPO: os lançamentos dela ficariam
    # com tipo diferente do da categoria (regra de negócio nº 4)
    tipo_travado = categoria_em_uso(conn, categoria_id)

    if request.method == "POST":
        nome = request.form.get("nome", "").strip()
        tipo = categoria["tipo"] if tipo_travado else request.form.get("tipo", "")
        erro = None
        if not nome:
            erro = "Informe o nome da categoria."
        elif tipo not in ("receita", "despesa"):
            erro = "Escolha o tipo: receita ou despesa."
        else:
            try:
                conn.execute(
                    "UPDATE categorias SET nome = ?, tipo = ? WHERE id = ?", (nome, tipo, categoria_id)
                )
                conn.commit()
            except sqlite3.IntegrityError:
                erro = f"Já existe uma categoria '{nome}' do tipo {tipo}. Use outro nome."
        conn.close()
        if erro:
            return render_template(
                "nova_categoria.html", categoria=categoria, tipo_travado=tipo_travado,
                nome=nome, tipo=tipo, erro=erro,
            )
        flash(f"Categoria \"{nome}\" atualizada.", "sucesso")
        return redirect(url_for("categorias.listar"))

    conn.close()
    return render_template(
        "nova_categoria.html", categoria=categoria, tipo_travado=tipo_travado,
        nome=categoria["nome"], tipo=categoria["tipo"],
    )


@bp.route("/categorias/excluir/<int:categoria_id>", methods=["POST"])
def excluir(categoria_id):
    conn = get_db_connection()

    # Regra de negócio: categorias em uso não podem ser excluídas
    qtd = conn.execute(
        "SELECT COUNT(*) FROM lancamentos WHERE categoria_id = ?", (categoria_id,)
    ).fetchone()[0]

    if qtd > 0:
        conn.close()
        erro = f"Esta categoria não pode ser excluída: ela é usada em {qtd} lançamento(s)."
        return render_template(
            "categorias.html", categorias=buscar_categorias_com_uso(), erro=erro
        )

    try:
        conn.execute("DELETE FROM categorias WHERE id = ?", (categoria_id,))
        conn.commit()
    except sqlite3.IntegrityError:
        # Segunda garantia: o ON DELETE RESTRICT do banco também recusa
        erro = "Esta categoria não pode ser excluída: ela está em uso."
        return render_template(
            "categorias.html", categorias=buscar_categorias_com_uso(), erro=erro
        )
    finally:
        conn.close()

    flash("Categoria excluída.", "sucesso")
    return redirect(url_for("categorias.listar"))
