"""Contas recorrentes: cadastradas uma vez, lançadas mês a mês sem duplicar."""
import calendar

from flask import Blueprint, abort, redirect, render_template, request, url_for

from db import get_db_connection
from util import (
    FORMAS_PAGAMENTO,
    mes_atual,
    mes_valido,
    para_centavos,
)
from modulos.cartoes import buscar_cartoes
from modulos.categorias import buscar_categorias, tipo_confere_com_categoria
from modulos.compras import gravar_parcelas

bp = Blueprint("recorrencias", __name__)


CAMPOS_RECORRENCIA = (
    "descricao", "valor", "tipo", "categoria_id", "forma_pagamento", "cartao_id",
    "dia_do_mes", "mes_inicio", "mes_fim",
)


def ler_formulario_recorrencia():
    dados = {campo: request.form.get(campo, "").strip() for campo in CAMPOS_RECORRENCIA}
    dados["ativa"] = "1" if request.form.get("ativa") else "0"
    return dados


def dados_da_recorrencia(r):
    return {
        "descricao": r["descricao"],
        "valor": f"{r['valor_centavos'] / 100:.2f}",
        "tipo": r["tipo"],
        "categoria_id": str(r["categoria_id"]),
        "forma_pagamento": r["forma_pagamento"],
        "cartao_id": str(r["cartao_id"] or ""),
        "dia_do_mes": str(r["dia_do_mes"]),
        "mes_inicio": r["mes_inicio"],
        "mes_fim": r["mes_fim"] or "",
        "ativa": str(r["ativa"]),
    }


def validar_recorrencia(conn, dados):
    if not dados["descricao"]:
        return "Informe a descrição."
    try:
        if para_centavos(dados["valor"]) <= 0:
            return "O valor deve ser maior que zero."
    except (ValueError, OverflowError):
        return "Informe um valor válido, por exemplo 120,00."
    if dados["forma_pagamento"] not in FORMAS_PAGAMENTO:
        return "Escolha a forma de pagamento."
    if not tipo_confere_com_categoria(conn, dados["categoria_id"], dados["tipo"]):
        return "O tipo não corresponde ao tipo da categoria."
    if dados["forma_pagamento"] == "credito":
        if dados["tipo"] != "despesa":
            return "Crédito só pode ser usado em despesas."
        cartao = conn.execute(
            "SELECT ativo FROM cartoes WHERE id = ?", (dados["cartao_id"] or None,)
        ).fetchone()
        if cartao is None:
            return "No crédito, escolha o cartão."
        if not cartao["ativo"]:
            return "Este cartão está inativo. Escolha outro cartão."
    if not dados["dia_do_mes"].isdigit() or not 1 <= int(dados["dia_do_mes"]) <= 28:
        return "O dia do mês deve ser de 1 a 28."
    if not mes_valido(dados["mes_inicio"]):
        return "Informe o mês de início."
    if dados["mes_fim"]:
        if not mes_valido(dados["mes_fim"]):
            return "Mês final inválido (ou deixe em branco)."
        if dados["mes_fim"] < dados["mes_inicio"]:
            return "O mês final deve ser depois do mês de início."
    return None


def valores_recorrencia(dados):
    credito = dados["forma_pagamento"] == "credito"
    return (
        dados["descricao"], para_centavos(dados["valor"]), dados["tipo"], dados["categoria_id"],
        dados["forma_pagamento"], dados["cartao_id"] if credito else None,
        int(dados["dia_do_mes"]), dados["mes_inicio"], dados["mes_fim"] or None, int(dados["ativa"]),
    )


def recorrencias_pendentes(conn, mes):
    """Recorrências ativas, valendo no mês, que ainda não têm lançamento nesse mês."""
    return conn.execute(
        """
        SELECT r.*, c.nome AS categoria
        FROM recorrencias r
        JOIN categorias c ON c.id = r.categoria_id
        WHERE r.ativa = 1
          AND r.mes_inicio <= ?
          AND (r.mes_fim IS NULL OR r.mes_fim >= ?)
          AND NOT EXISTS (
              SELECT 1 FROM lancamentos l
              WHERE l.recorrencia_id = r.id AND l.mes_referencia = ?
          )
        ORDER BY r.dia_do_mes
        """,
        (mes, mes, mes),
    ).fetchall()


def gerar_recorrencias(conn, mes):
    """Cria os lançamentos do mês para as recorrências pendentes. Devolve quantos criou."""
    pendentes = recorrencias_pendentes(conn, mes)
    with conn:   # transação: gera todas ou nenhuma
        for r in pendentes:
            dia = f"{mes}-{r['dia_do_mes']:02d}"   # '2026-10' + dia 5 → '2026-10-05'
            if r["forma_pagamento"] == "credito":
                # No crédito vira uma compra à vista no cartão (cai na fatura certa)
                cartao = conn.execute("SELECT * FROM cartoes WHERE id = ?", (r["cartao_id"],)).fetchone()
                cursor = conn.execute(
                    """
                    INSERT INTO compras_cartao
                        (cartao_id, descricao, valor_total_centavos, parcelas, data_compra, categoria_id)
                    VALUES (?, ?, ?, 1, ?, ?)
                    """,
                    (r["cartao_id"], r["descricao"], r["valor_centavos"], dia, r["categoria_id"]),
                )
                dados = {
                    "descricao": r["descricao"], "valor": f"{r['valor_centavos'] / 100:.2f}",
                    "parcelas": "1", "data_compra": dia, "categoria_id": r["categoria_id"],
                    "observacao": "",
                }
                gravar_parcelas(conn, cursor.lastrowid, dados, cartao, r["id"], mes)
            else:
                conn.execute(
                    """
                    INSERT INTO lancamentos
                        (descricao, valor_centavos, tipo, data, categoria_id, forma_pagamento,
                         recorrencia_id, mes_referencia)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        r["descricao"], r["valor_centavos"], r["tipo"], dia, r["categoria_id"],
                        r["forma_pagamento"], r["id"], mes,
                    ),
                )
    return len(pendentes)


def form_recorrencia(titulo, dados, erro=None, recorrencia=None):
    return render_template(
        "recorrencia_form.html",
        titulo=titulo,
        dados=dados,
        erro=erro,
        recorrencia=recorrencia,
        categorias=buscar_categorias(),
        cartoes=[c for c in buscar_cartoes() if c["ativo"] or str(c["id"]) == dados.get("cartao_id")],
    )


@bp.route("/recorrencias")
def listar():
    conn = get_db_connection()
    lista = conn.execute(
        """
        SELECT r.*, c.nome AS categoria, ca.nome AS cartao, ca.titular,
               (SELECT COUNT(*) FROM lancamentos l WHERE l.recorrencia_id = r.id) AS qtd_gerados
        FROM recorrencias r
        JOIN categorias c ON c.id = r.categoria_id
        LEFT JOIN cartoes ca ON ca.id = r.cartao_id
        ORDER BY r.ativa DESC, r.tipo DESC, r.dia_do_mes
        """
    ).fetchall()
    pendentes = recorrencias_pendentes(conn, mes_atual())
    conn.close()
    return render_template(
        "recorrencias.html", recorrencias=lista, pendentes=pendentes, mes=mes_atual()
    )


@bp.route("/recorrencias/nova", methods=["GET", "POST"])
def nova():
    if request.method == "POST":
        dados = ler_formulario_recorrencia()
        dados["ativa"] = "1"
        conn = get_db_connection()
        erro = validar_recorrencia(conn, dados)
        if erro:
            conn.close()
            return form_recorrencia("Nova conta recorrente", dados, erro)
        conn.execute(
            """
            INSERT INTO recorrencias
                (descricao, valor_centavos, tipo, categoria_id, forma_pagamento, cartao_id,
                 dia_do_mes, mes_inicio, mes_fim, ativa)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            valores_recorrencia(dados),
        )
        conn.commit()
        conn.close()
        return redirect(url_for("recorrencias.listar"))

    dados = {"tipo": "despesa", "forma_pagamento": "pix", "mes_inicio": mes_atual(), "ativa": "1"}
    return form_recorrencia("Nova conta recorrente", dados)


@bp.route("/recorrencias/editar/<int:recorrencia_id>", methods=["GET", "POST"])
def editar(recorrencia_id):
    conn = get_db_connection()
    recorrencia = conn.execute(
        "SELECT * FROM recorrencias WHERE id = ?", (recorrencia_id,)
    ).fetchone()
    if recorrencia is None:
        conn.close()
        abort(404)

    if request.method == "POST":
        dados = ler_formulario_recorrencia()
        erro = validar_recorrencia(conn, dados)
        if erro:
            conn.close()
            return form_recorrencia("Editar conta recorrente", dados, erro, recorrencia)
        # Muda só os PRÓXIMOS meses: os lançamentos já gerados continuam como estão
        conn.execute(
            """
            UPDATE recorrencias
               SET descricao = ?, valor_centavos = ?, tipo = ?, categoria_id = ?,
                   forma_pagamento = ?, cartao_id = ?, dia_do_mes = ?, mes_inicio = ?,
                   mes_fim = ?, ativa = ?
             WHERE id = ?
            """,
            (*valores_recorrencia(dados), recorrencia_id),
        )
        conn.commit()
        conn.close()
        return redirect(url_for("recorrencias.listar"))

    conn.close()
    return form_recorrencia(
        "Editar conta recorrente", dados_da_recorrencia(recorrencia), recorrencia=recorrencia
    )


@bp.route("/recorrencias/excluir/<int:recorrencia_id>", methods=["POST"])
def excluir(recorrencia_id):
    conn = get_db_connection()
    # ON DELETE SET NULL: os lançamentos já gerados continuam existindo
    conn.execute("DELETE FROM recorrencias WHERE id = ?", (recorrencia_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("recorrencias.listar"))


@bp.route("/recorrencias/gerar", methods=["POST"])
def gerar():
    mes = request.form.get("mes", "")
    if not mes_valido(mes):
        mes = mes_atual()
    conn = get_db_connection()
    gerar_recorrencias(conn, mes)
    conn.close()
    # Volta para a página de onde veio o clique (dashboard ou recorrências)
    destino = request.form.get("voltar_para")
    if destino == "dashboard":
        return redirect(url_for("dashboard.inicio"))
    ano, numero_mes = int(mes[:4]), int(mes[5:])
    ultimo_dia = calendar.monthrange(ano, numero_mes)[1]
    return redirect(url_for("lancamentos.listar", inicio=f"{mes}-01", fim=f"{mes}-{ultimo_dia}"))
