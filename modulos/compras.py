"""Compras no cartão de crédito: cada compra vira uma parcela por fatura."""
from datetime import date

from flask import Blueprint, abort, redirect, render_template, request, url_for

import relogio
from db import get_db_connection
from util import para_centavos
from faturas import gerar_parcelas
from modulos.cartoes import buscar_cartoes
from modulos.categorias import categorias_de_despesa, tipo_confere_com_categoria

bp = Blueprint("compras", __name__)


CAMPOS_COMPRA = ("cartao_id", "descricao", "valor", "parcelas", "data_compra", "categoria_id", "observacao")


def ler_formulario_compra():
    return {campo: request.form.get(campo, "").strip() for campo in CAMPOS_COMPRA}


def dados_da_compra(compra):
    """Converte uma compra do banco nos textos que o formulário espera."""
    return {
        "cartao_id": str(compra["cartao_id"]),
        "descricao": compra["descricao"],
        "valor": f"{compra['valor_total_centavos'] / 100:.2f}",
        "parcelas": str(compra["parcelas"]),
        "data_compra": compra["data_compra"],
        "categoria_id": str(compra["categoria_id"]),
        "observacao": compra["observacao"] or "",
    }


def cartoes_para_compra(cartao_atual_id=None):
    """Cartões ativos (e o cartão atual da compra, mesmo se já foi desativado)."""
    return [
        c for c in buscar_cartoes()
        if c["ativo"] or str(c["id"]) == str(cartao_atual_id)
    ]


def validar_compra(conn, dados, cartao_atual_id=None):
    """Devolve (erro, cartao). O cartão é usado depois para calcular as faturas."""
    cartao = conn.execute(
        "SELECT * FROM cartoes WHERE id = ?", (dados["cartao_id"],)
    ).fetchone()
    if cartao is None:
        return "Escolha o cartão.", None
    if not cartao["ativo"] and str(cartao["id"]) != str(cartao_atual_id):
        return "Este cartão está inativo. Escolha outro cartão.", None
    if not dados["descricao"]:
        return "Informe a descrição.", None
    try:
        total = para_centavos(dados["valor"])
    except (ValueError, OverflowError):
        return "Informe um valor válido, por exemplo 1200,00.", None
    if total <= 0:
        return "O valor deve ser maior que zero.", None
    if not dados["parcelas"].isdigit() or not 1 <= int(dados["parcelas"]) <= 24:
        return "O número de parcelas deve ser de 1 a 24.", None
    if total < int(dados["parcelas"]):
        return "Valor pequeno demais para tantas parcelas (cada parcela precisa de pelo menos R$ 0,01).", None
    try:
        date.fromisoformat(dados["data_compra"])
    except ValueError:
        return "Informe a data da compra.", None
    if not tipo_confere_com_categoria(conn, dados["categoria_id"], "despesa"):
        return "Escolha uma categoria de despesa.", None
    return None, cartao


def gravar_parcelas(conn, compra_id, dados, cartao, recorrencia_id=None, mes_referencia=None):
    """Cria um lançamento para cada parcela, cada um na sua fatura.

    recorrencia_id/mes_referencia: preenchidos quando a compra foi gerada por uma conta recorrente.
    """
    total = para_centavos(dados["valor"])
    quantidade = int(dados["parcelas"])
    data_compra = date.fromisoformat(dados["data_compra"])
    parcelas = gerar_parcelas(
        total, quantidade, data_compra, cartao["dia_fechamento"], cartao["dia_vencimento"]
    )
    for numero, valor, vencimento in parcelas:
        conn.execute(
            """
            INSERT INTO lancamentos
                (descricao, valor_centavos, tipo, data, categoria_id, forma_pagamento, observacao,
                 data_compra, compra_id, parcela_numero, parcela_total, recorrencia_id, mes_referencia)
            VALUES (?, ?, 'despesa', ?, ?, 'credito', ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                dados["descricao"], valor, vencimento.isoformat(), dados["categoria_id"],
                dados["observacao"] or None, dados["data_compra"],
                compra_id, numero, quantidade, recorrencia_id, mes_referencia,
            ),
        )


def form_compra(titulo, dados, erro=None, compra=None):
    return render_template(
        "compra_form.html",
        titulo=titulo,
        dados=dados,
        erro=erro,
        compra=compra,
        cartoes=cartoes_para_compra(compra["cartao_id"] if compra else None),
        categorias=categorias_de_despesa(),
    )


@bp.route("/compras/nova", methods=["GET", "POST"])
def nova():
    if request.method == "POST":
        dados = ler_formulario_compra()
        conn = get_db_connection()
        erro, cartao = validar_compra(conn, dados)
        if erro:
            conn.close()
            return form_compra("Compra no cartão", dados, erro)

        # "with conn:" = transação: a compra e TODAS as parcelas são gravadas juntas,
        # ou nada é gravado (se der erro no meio, o Python desfaz tudo sozinho)
        with conn:
            cursor = conn.execute(
                """
                INSERT INTO compras_cartao
                    (cartao_id, descricao, valor_total_centavos, parcelas, data_compra,
                     categoria_id, observacao)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    cartao["id"], dados["descricao"], para_centavos(dados["valor"]),
                    int(dados["parcelas"]), dados["data_compra"], dados["categoria_id"],
                    dados["observacao"] or None,
                ),
            )
            compra_id = cursor.lastrowid   # o id que o banco acabou de gerar para a compra
            gravar_parcelas(conn, compra_id, dados, cartao)
        conn.close()
        return redirect(url_for("compras.ver", compra_id=compra_id))

    # GET: cartão pré-escolhido se veio da página de cartões (?cartao_id=...)
    dados = {
        "data_compra": relogio.hoje().isoformat(),
        "parcelas": "1",
        "cartao_id": request.args.get("cartao_id", ""),
    }
    return form_compra("Compra no cartão", dados)


def buscar_compra(conn, compra_id):
    compra = conn.execute(
        """
        SELECT cc.*, ca.nome AS cartao, ca.titular, c.nome AS categoria
        FROM compras_cartao cc
        JOIN cartoes ca ON ca.id = cc.cartao_id
        JOIN categorias c ON c.id = cc.categoria_id
        WHERE cc.id = ?
        """,
        (compra_id,),
    ).fetchone()
    if compra is None:
        conn.close()
        abort(404)
    return compra


@bp.route("/compras/<int:compra_id>")
def ver(compra_id):
    conn = get_db_connection()
    compra = buscar_compra(conn, compra_id)
    parcelas = conn.execute(
        "SELECT * FROM lancamentos WHERE compra_id = ? ORDER BY parcela_numero", (compra_id,)
    ).fetchall()
    conn.close()
    return render_template("compra_detalhe.html", compra=compra, parcelas=parcelas)


@bp.route("/compras/editar/<int:compra_id>", methods=["GET", "POST"])
def editar(compra_id):
    conn = get_db_connection()
    compra = buscar_compra(conn, compra_id)

    if request.method == "POST":
        dados = ler_formulario_compra()
        erro, cartao = validar_compra(conn, dados, cartao_atual_id=compra["cartao_id"])
        if erro:
            conn.close()
            return form_compra("Editar compra", dados, erro, compra)

        with conn:   # transação: atualiza a compra e recria as parcelas, tudo ou nada
            conn.execute(
                """
                UPDATE compras_cartao
                   SET cartao_id = ?, descricao = ?, valor_total_centavos = ?, parcelas = ?,
                       data_compra = ?, categoria_id = ?, observacao = ?
                 WHERE id = ?
                """,
                (
                    cartao["id"], dados["descricao"], para_centavos(dados["valor"]),
                    int(dados["parcelas"]), dados["data_compra"], dados["categoria_id"],
                    dados["observacao"] or None, compra_id,
                ),
            )
            # Se a compra veio de uma conta recorrente, a ligação precisa ser mantida nas novas
            # parcelas — senão o sistema acharia que a conta do mês ainda não foi lançada
            origem = conn.execute(
                "SELECT recorrencia_id, mes_referencia FROM lancamentos WHERE compra_id = ? LIMIT 1",
                (compra_id,),
            ).fetchone()
            conn.execute("DELETE FROM lancamentos WHERE compra_id = ?", (compra_id,))
            gravar_parcelas(
                conn, compra_id, dados, cartao,
                recorrencia_id=origem["recorrencia_id"] if origem else None,
                mes_referencia=origem["mes_referencia"] if origem else None,
            )
        conn.close()
        return redirect(url_for("compras.ver", compra_id=compra_id))

    conn.close()
    return form_compra("Editar compra", dados_da_compra(compra), compra=compra)


@bp.route("/compras/excluir/<int:compra_id>", methods=["POST"])
def excluir(compra_id):
    conn = get_db_connection()
    # ON DELETE CASCADE: apagar a compra apaga todas as parcelas dela
    conn.execute("DELETE FROM compras_cartao WHERE id = ?", (compra_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("lancamentos.listar"))
