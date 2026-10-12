"""Orçamento mensal por categoria: previsto × gasto, contas fixas e projeção do mês."""
from datetime import date

from flask import Blueprint, redirect, render_template, request, url_for

from db import get_db_connection
from util import (
    limites_do_mes,
    mes_atual,
    mes_valido,
    mes_vizinho,
    para_centavos,
    sem_acento,
)
from faturas import vencimento_da_fatura
from modulos.categorias import categorias_de_despesa

bp = Blueprint("orcamento", __name__)


def faixa_orcamento(percentual):
    """Cor da barra: até 80% normal, até 100% atenção, acima disso estourou."""
    if percentual > 100:
        return "estourou"
    if percentual >= 80:
        return "atencao"
    return "normal"


def contas_fixas_do_mes(conn, mes):
    """Contas recorrentes de DESPESA cujo dinheiro sai neste mês.

    Cuidado: uma recorrente no crédito cai na fatura — que pode ser do mês seguinte.
    (Netflix no dia 20/10 num cartão que fecha dia 3 → fatura de 10/11 → conta em NOVEMBRO.)
    Por isso olhamos as recorrências do mês anterior e do próprio mês, e ficamos com as que
    "aterrissam" neste mês. Devolve {categoria_id: {"fixas": total, "pendentes": ainda não lançadas}}.
    """
    resultado = {}
    for mes_referencia in (mes_vizinho(mes, -1), mes):
        recorrencias = conn.execute(
            """
            SELECT r.*, ca.dia_fechamento, ca.dia_vencimento,
                   EXISTS (
                       SELECT 1 FROM lancamentos l
                       WHERE l.recorrencia_id = r.id AND l.mes_referencia = ?
                   ) AS ja_lancada
            FROM recorrencias r
            LEFT JOIN cartoes ca ON ca.id = r.cartao_id
            WHERE r.ativa = 1 AND r.tipo = 'despesa'
              AND r.mes_inicio <= ? AND (r.mes_fim IS NULL OR r.mes_fim >= ?)
            """,
            (mes_referencia, mes_referencia, mes_referencia),
        ).fetchall()
        for r in recorrencias:
            dia = date.fromisoformat(f"{mes_referencia}-{r['dia_do_mes']:02d}")
            if r["forma_pagamento"] == "credito" and r["dia_fechamento"]:
                dia = vencimento_da_fatura(dia, r["dia_fechamento"], r["dia_vencimento"])
            if dia.strftime("%Y-%m") != mes:
                continue   # o dinheiro desta conta sai em outro mês
            totais = resultado.setdefault(r["categoria_id"], {"fixas": 0, "pendentes": 0})
            totais["fixas"] += r["valor_centavos"]
            if not r["ja_lancada"]:
                totais["pendentes"] += r["valor_centavos"]
    return resultado


def buscar_orcamento(conn, mes):
    """Para cada categoria de despesa: previsto (orçamento), gasto (realizado),
    quanto do gasto veio do cartão, contas fixas e a projeção do mês."""
    inicio, fim = limites_do_mes(mes)
    linhas = conn.execute(
        """
        SELECT c.id, c.nome,
               o.valor_centavos AS previsto,
               COALESCE(SUM(l.valor_centavos), 0) AS realizado,
               COALESCE(SUM(CASE WHEN l.compra_id IS NOT NULL THEN l.valor_centavos END), 0) AS do_cartao
        FROM categorias c
        LEFT JOIN orcamentos o ON o.categoria_id = c.id AND o.mes = ?
        LEFT JOIN lancamentos l ON l.categoria_id = c.id AND l.tipo = 'despesa'
                               AND l.data BETWEEN ? AND ?
        WHERE c.tipo = 'despesa'
        GROUP BY c.id
        """,
        (mes, inicio, fim),
    ).fetchall()
    fixas = contas_fixas_do_mes(conn, mes)

    itens = []
    for linha in linhas:
        item = dict(linha)   # sqlite3.Row → dicionário comum, para poder acrescentar campos
        item["fixas"] = fixas.get(item["id"], {}).get("fixas", 0)
        item["pendentes"] = fixas.get(item["id"], {}).get("pendentes", 0)
        # Projeção: o que já foi gasto + as contas fixas que ainda vão ser lançadas.
        # (As já lançadas estão dentro do "realizado": somar de novo seria contar duas vezes.)
        item["projecao"] = item["realizado"] + item["pendentes"]
        if item["previsto"]:
            item["percentual"] = item["realizado"] * 100 / item["previsto"]
            item["percentual_pendente"] = item["pendentes"] * 100 / item["previsto"]
            item["faixa"] = faixa_orcamento(item["percentual"])
            item["faixa_projecao"] = faixa_orcamento(item["projecao"] * 100 / item["previsto"])
            item["fixas_acima"] = item["fixas"] > item["previsto"]   # nasce estourado
        itens.append(item)
    # Orçadas primeiro (as mais "apertadas" pela projeção no topo); depois as sem orçamento
    itens.sort(key=lambda i: (
        i["previsto"] is None,
        -(i["projecao"] * 100 / i["previsto"] if i["previsto"] else 0),
        sem_acento(i["nome"]),
    ))
    return itens


def resumo_orcamento(itens):
    orcados = [i for i in itens if i["previsto"]]
    return {
        "previsto": sum(i["previsto"] for i in orcados),
        "realizado": sum(i["realizado"] for i in orcados),
        "projecao": sum(i["projecao"] for i in orcados),
        "pendentes": sum(i["pendentes"] for i in itens),
        "fora": sum(i["realizado"] for i in itens if not i["previsto"]),  # gasto sem orçamento
        "estouradas": sum(1 for i in orcados if i["faixa"] == "estourou"),
        "vao_estourar": [i for i in orcados if i["faixa"] != "estourou" and i["faixa_projecao"] == "estourou"],
        "fixas_acima": [i for i in orcados if i["fixas_acima"]],
        "sem_orcamento_com_fixas": sum(1 for i in itens if not i["previsto"] and i["fixas"]),
        "tem_orcamento": bool(orcados),
    }


@bp.route("/orcamento", methods=["GET", "POST"])
def mes():
    mes = request.values.get("mes", "")   # values = args (GET) ou form (POST)
    if not mes_valido(mes):
        mes = mes_atual()
    conn = get_db_connection()
    erro = None

    if request.method == "POST":
        # Um campo por categoria: valor_4, valor_7... Vazio ou zero = sem orçamento
        novos = {}
        for categoria in categorias_de_despesa():
            texto = request.form.get(f"valor_{categoria['id']}", "").strip()
            if not texto:
                novos[categoria["id"]] = 0
                continue
            try:
                novos[categoria["id"]] = para_centavos(texto)
            except (ValueError, OverflowError):
                erro = f"Valor inválido em {categoria['nome']}."
                break
            if novos[categoria["id"]] < 0:
                erro = f"O orçamento de {categoria['nome']} não pode ser negativo."
                break

        if not erro:
            with conn:
                for categoria_id, valor in novos.items():
                    if valor == 0:
                        conn.execute(
                            "DELETE FROM orcamentos WHERE categoria_id = ? AND mes = ?",
                            (categoria_id, mes),
                        )
                    else:
                        # UPSERT: insere; se já existe (UNIQUE categoria+mês), atualiza o valor
                        conn.execute(
                            """
                            INSERT INTO orcamentos (categoria_id, mes, valor_centavos)
                            VALUES (?, ?, ?)
                            ON CONFLICT (categoria_id, mes)
                            DO UPDATE SET valor_centavos = excluded.valor_centavos
                            """,
                            (categoria_id, mes, valor),
                        )
            conn.close()
            return redirect(url_for("orcamento.mes", mes=mes))

    itens = buscar_orcamento(conn, mes)
    tem_anterior = conn.execute(
        "SELECT COUNT(*) FROM orcamentos WHERE mes = ?", (mes_vizinho(mes, -1),)
    ).fetchone()[0]
    conn.close()
    return render_template(
        "orcamento.html",
        mes=mes,
        mes_anterior=mes_vizinho(mes, -1),
        mes_seguinte=mes_vizinho(mes, 1),
        itens=itens,
        resumo=resumo_orcamento(itens),
        tem_anterior=tem_anterior,
        erro=erro,
    )


@bp.route("/orcamento/copiar", methods=["POST"])
def copiar():
    mes = request.form.get("mes", "")
    if not mes_valido(mes):
        mes = mes_atual()
    conn = get_db_connection()
    # INSERT ... SELECT: copia as linhas do mês anterior trocando só o mês.
    # OR IGNORE: categorias que já têm valor neste mês ficam como estão.
    conn.execute(
        """
        INSERT OR IGNORE INTO orcamentos (categoria_id, mes, valor_centavos)
        SELECT categoria_id, ?, valor_centavos FROM orcamentos WHERE mes = ?
        """,
        (mes, mes_vizinho(mes, -1)),
    )
    conn.commit()
    conn.close()
    return redirect(url_for("orcamento.mes", mes=mes))


@bp.route("/orcamento/preencher-fixas", methods=["POST"])
def preencher_fixas():
    """Usa a soma das contas fixas como ponto de partida — só nas categorias SEM orçamento."""
    mes = request.form.get("mes", "")
    if not mes_valido(mes):
        mes = mes_atual()
    conn = get_db_connection()
    with conn:
        for categoria_id, totais in contas_fixas_do_mes(conn, mes).items():
            # OR IGNORE: categoria que já tem orçamento fica como está
            conn.execute(
                "INSERT OR IGNORE INTO orcamentos (categoria_id, mes, valor_centavos) VALUES (?, ?, ?)",
                (categoria_id, mes, totais["fixas"]),
            )
    conn.close()
    return redirect(url_for("orcamento.mes", mes=mes))
