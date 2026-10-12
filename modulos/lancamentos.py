"""Lançamentos: listar com filtros, criar, editar, excluir e exportar para o Excel."""
import csv
import io

from flask import Blueprint, Response, abort, redirect, render_template, request, url_for

import relogio
from db import get_db_connection
from util import (
    FORMAS_FORMULARIO,
    data_br,
    forma,
    numero_br,
    para_centavos,
)
from modulos.categorias import buscar_categorias, tipo_confere_com_categoria

bp = Blueprint("lancamentos", __name__)


CAMPOS_LANCAMENTO = (
    "descricao", "valor", "tipo", "data", "categoria_id", "forma_pagamento", "observacao",
)


def ler_formulario_lancamento():
    """Lê os campos do formulário como textos. Se der erro, eles voltam para a tela."""
    return {campo: request.form.get(campo, "").strip() for campo in CAMPOS_LANCAMENTO}


def dados_do_lancamento(lancamento):
    """Converte uma linha do banco nos textos que o formulário espera (25050 → '250.50')."""
    return {
        "descricao": lancamento["descricao"],
        "valor": f"{lancamento['valor_centavos'] / 100:.2f}",
        "tipo": lancamento["tipo"],
        "data": lancamento["data"],
        "categoria_id": str(lancamento["categoria_id"]),
        "forma_pagamento": lancamento["forma_pagamento"],
        "observacao": lancamento["observacao"] or "",
    }


def validar_lancamento(conn, dados):
    """Confere as regras de negócio. Devolve a mensagem de erro, ou None se estiver tudo certo."""
    if not dados["descricao"]:
        return "Informe a descrição."
    try:
        centavos = para_centavos(dados["valor"])
    except (ValueError, OverflowError):
        return "Informe um valor válido, por exemplo 250,50."
    if centavos <= 0:
        return "O valor deve ser maior que zero."
    if not dados["data"]:
        return "Informe a data."
    if dados["forma_pagamento"] not in FORMAS_FORMULARIO:
        return "Escolha a forma de pagamento."
    if not tipo_confere_com_categoria(conn, dados["categoria_id"], dados["tipo"]):
        return "O tipo do lançamento não corresponde ao tipo da categoria. Escolha uma categoria de " + (
            "receita." if dados["tipo"] == "receita" else "despesa."
        )
    return None


def buscar_lancamentos_filtrados():
    """Lê os filtros da URL e busca os lançamentos. Usada pela lista E pela exportação,
    para o arquivo baixado ter exatamente o que está na tela. Devolve (filtros, filtrando, lançamentos)."""
    # Filtros vindos do formulário (GET). Campo vazio = sem filtro
    filtros = {
        "inicio": request.args.get("inicio", ""),
        "fim": request.args.get("fim", ""),
        "tipo": request.args.get("tipo", ""),
        "categoria_id": request.args.get("categoria_id", ""),
        "forma_pagamento": request.args.get("forma_pagamento", ""),
    }

    # Monta o WHERE aos poucos: só entram as condições que foram preenchidas.
    # Os VALORES continuam indo pelos "?" (nunca colados no texto do SQL)
    condicoes = []
    parametros = []
    if filtros["inicio"]:
        condicoes.append("l.data >= ?")
        parametros.append(filtros["inicio"])
    if filtros["fim"]:
        condicoes.append("l.data <= ?")
        parametros.append(filtros["fim"])
    if filtros["tipo"]:
        condicoes.append("l.tipo = ?")
        parametros.append(filtros["tipo"])
    if filtros["categoria_id"]:
        condicoes.append("l.categoria_id = ?")
        parametros.append(filtros["categoria_id"])
    if filtros["forma_pagamento"]:
        condicoes.append("l.forma_pagamento = ?")
        parametros.append(filtros["forma_pagamento"])

    where = ""
    if condicoes:
        where = "WHERE " + " AND ".join(condicoes)  # ["a", "b"] → "a AND b"

    conn = get_db_connection()
    lancamentos = conn.execute(
        f"""
        SELECT l.id, l.descricao, l.valor_centavos, l.tipo, l.data, l.forma_pagamento,
               l.data_compra, l.compra_id, l.parcela_numero, l.parcela_total, l.recorrencia_id,
               l.observacao, c.nome AS categoria, ca.nome AS cartao, ca.titular
        FROM lancamentos l
        JOIN categorias c ON c.id = l.categoria_id
        LEFT JOIN compras_cartao cc ON cc.id = l.compra_id      -- LEFT: nem todo lançamento é compra
        LEFT JOIN cartoes ca ON ca.id = cc.cartao_id
        {where}
        ORDER BY l.data DESC, l.id DESC
        """,
        parametros,
    ).fetchall()
    conn.close()
    return filtros, bool(condicoes), lancamentos


@bp.route("/lancamentos")
def listar():
    filtros, filtrando, lancamentos = buscar_lancamentos_filtrados()

    # Totais do resultado filtrado (em centavos inteiros)
    total_receitas = sum(l["valor_centavos"] for l in lancamentos if l["tipo"] == "receita")
    total_despesas = sum(l["valor_centavos"] for l in lancamentos if l["tipo"] == "despesa")

    return render_template(
        "lancamentos.html",
        lancamentos=lancamentos,
        categorias=buscar_categorias(),
        filtros=filtros,
        filtrando=filtrando,
        total_receitas=total_receitas,
        total_despesas=total_despesas,
    )


@bp.route("/lancamentos/exportar.csv")
def exportar():
    filtros, filtrando, lancamentos = buscar_lancamentos_filtrados()

    # Monta o arquivo na memória (StringIO = um "arquivo" que é só um texto)
    saida = io.StringIO()
    # Excel em português: separador ";" (porque a vírgula é o separador decimal)
    escritor = csv.writer(saida, delimiter=";")
    escritor.writerow([
        "Data", "Descrição", "Parcela", "Categoria", "Tipo", "Forma de pagamento",
        "Cartão", "Titular", "Data da compra", "Valor", "Observação",
    ])
    for l in lancamentos:
        valor = l["valor_centavos"] if l["tipo"] == "receita" else -l["valor_centavos"]  # despesa negativa: dá para somar a coluna
        escritor.writerow([
            data_br(l["data"]),
            l["descricao"],
            f"{l['parcela_numero']}/{l['parcela_total']}" if l["parcela_total"] and l["parcela_total"] > 1 else "",
            l["categoria"],
            l["tipo"].capitalize(),
            forma(l["forma_pagamento"]),
            l["cartao"] or "",
            l["titular"] or "",
            data_br(l["data_compra"]) if l["data_compra"] else "",
            numero_br(valor),
            l["observacao"] or "",
        ])

    # Nome do arquivo com o período, quando houver: lancamentos_2026-10-01_a_2026-10-31.csv
    nome = "lancamentos"
    if filtros["inicio"] or filtros["fim"]:
        nome += f"_{filtros['inicio'] or 'inicio'}_a_{filtros['fim'] or 'hoje'}"

    return Response(
        # utf-8-sig = UTF-8 com BOM: a "marca" que faz o Excel abrir os acentos corretamente
        saida.getvalue().encode("utf-8-sig"),
        mimetype="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{nome}.csv"'},  # baixar, não abrir
    )


@bp.route("/lancamentos/novo", methods=["GET", "POST"])
def novo():
    # POST: o usuário clicou em "Salvar"
    if request.method == "POST":
        dados = ler_formulario_lancamento()

        conn = get_db_connection()
        erro = validar_lancamento(conn, dados)
        if erro:
            conn.close()
            # Mostra o formulário de novo, COM os dados digitados, para só corrigir o que falta
            return render_template(
                "novo_lancamento.html", dados=dados, categorias=buscar_categorias(), erro=erro
            )

        # Grava no banco. Os "?" protegem contra SQL Injection
        conn.execute(
            "INSERT INTO lancamentos "
            "(descricao, valor_centavos, tipo, data, categoria_id, forma_pagamento, observacao) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                dados["descricao"],
                para_centavos(dados["valor"]),
                dados["tipo"],
                dados["data"],  # já vem como AAAA-MM-DD
                dados["categoria_id"],
                dados["forma_pagamento"],
                dados["observacao"] or None,
            ),
        )
        conn.commit()  # confirma a gravação
        conn.close()

        # Manda o navegador para outra página (evita duplicar ao apertar F5)
        return redirect(url_for("lancamentos.listar"))

    # GET: formulário vazio, já com a data de hoje e o tipo "despesa"
    dados = {"tipo": "despesa", "data": relogio.hoje().isoformat(), "forma_pagamento": "pix"}
    return render_template("novo_lancamento.html", dados=dados, categorias=buscar_categorias())


@bp.route("/lancamentos/editar/<int:lancamento_id>", methods=["GET", "POST"])
def editar(lancamento_id):
    conn = get_db_connection()
    lancamento = conn.execute(
        "SELECT * FROM lancamentos WHERE id = ?", (lancamento_id,)
    ).fetchone()

    # Se o id não existe (ex.: /lancamentos/editar/999), responde "Página não encontrada"
    if lancamento is None:
        conn.close()
        abort(404)

    # Parcela de compra no cartão: é editada pela compra, nunca sozinha (regra 6)
    if lancamento["compra_id"]:
        conn.close()
        return redirect(url_for("compras.ver", compra_id=lancamento["compra_id"]))

    # POST: o usuário clicou em "Salvar alterações"
    if request.method == "POST":
        dados = ler_formulario_lancamento()

        erro = validar_lancamento(conn, dados)
        if erro:
            conn.close()
            return render_template(
                "editar_lancamento.html",
                lancamento=lancamento,
                dados=dados,
                categorias=buscar_categorias(),
                erro=erro,
            )

        # Atualiza o lançamento. O WHERE garante que só ESTE lançamento muda
        conn.execute(
            """
            UPDATE lancamentos
               SET descricao = ?, valor_centavos = ?, tipo = ?, data = ?,
                   categoria_id = ?, forma_pagamento = ?, observacao = ?,
                   atualizado_em = CURRENT_TIMESTAMP
             WHERE id = ?
            """,
            (
                dados["descricao"],
                para_centavos(dados["valor"]),
                dados["tipo"],
                dados["data"],
                dados["categoria_id"],
                dados["forma_pagamento"],
                dados["observacao"] or None,
                lancamento_id,
            ),
        )
        conn.commit()
        conn.close()
        return redirect(url_for("lancamentos.listar"))

    # GET: mostrar o formulário já preenchido com os dados atuais
    conn.close()
    return render_template(
        "editar_lancamento.html",
        lancamento=lancamento,
        dados=dados_do_lancamento(lancamento),
        categorias=buscar_categorias(),
    )


@bp.route("/lancamentos/excluir/<int:lancamento_id>", methods=["POST"])
def excluir(lancamento_id):
    conn = get_db_connection()
    lancamento = conn.execute(
        "SELECT compra_id FROM lancamentos WHERE id = ?", (lancamento_id,)
    ).fetchone()
    if lancamento and lancamento["compra_id"]:
        # Parcela de compra no cartão: exclui-se a compra inteira, na página da compra
        conn.close()
        return redirect(url_for("compras.ver", compra_id=lancamento["compra_id"]))

    conn.execute("DELETE FROM lancamentos WHERE id = ?", (lancamento_id,))  # o WHERE é essencial!
    conn.commit()
    conn.close()
    return redirect(url_for("lancamentos.listar"))
