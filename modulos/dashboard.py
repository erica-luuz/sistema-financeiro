"""Dashboard: resumo do período, gráfico, próximas faturas, orçamento e contas a lançar."""
from flask import Blueprint, render_template, request

import relogio
from db import get_db_connection
from util import (
    MESES,
    limites_do_mes,
    mes_atual,
    mes_vizinho,
    periodo_mes_atual,
)
from faturas import proximo_vencimento, situacao_fatura
from modulos.cartoes import buscar_cartoes, total_fatura
from modulos.orcamento import buscar_orcamento
from modulos.recorrencias import recorrencias_pendentes

bp = Blueprint("dashboard", __name__)


@bp.route("/")
def inicio():
    # Período: vem do formulário (?inicio=...&fim=...) ou, por padrão, o mês atual
    inicio_padrao, fim_padrao = periodo_mes_atual()
    inicio = request.args.get("inicio") or inicio_padrao
    fim = request.args.get("fim") or fim_padrao

    if inicio > fim:  # datas ISO podem ser comparadas como texto
        inicio, fim = fim, inicio

    conn = get_db_connection()

    # Totais do período: uma consulta só, separando receitas e despesas com CASE
    totais = conn.execute(
        """
        SELECT
            COALESCE(SUM(CASE WHEN tipo = 'receita' THEN valor_centavos END), 0) AS receitas,
            COALESCE(SUM(CASE WHEN tipo = 'despesa' THEN valor_centavos END), 0) AS despesas,
            COUNT(*) AS qtd
        FROM lancamentos
        WHERE data BETWEEN ? AND ?
        """,
        (inicio, fim),
    ).fetchone()

    # Despesas agrupadas por categoria, da maior para a menor
    despesas_por_categoria = conn.execute(
        """
        SELECT c.nome, SUM(l.valor_centavos) AS total
        FROM lancamentos l
        JOIN categorias c ON c.id = l.categoria_id
        WHERE l.tipo = 'despesa' AND l.data BETWEEN ? AND ?
        GROUP BY c.id
        ORDER BY total DESC
        """,
        (inicio, fim),
    ).fetchall()

    # Os 5 lançamentos mais recentes do período
    ultimos = conn.execute(
        """
        SELECT l.descricao, l.valor_centavos, l.tipo, l.data, l.forma_pagamento,
               l.parcela_numero, l.parcela_total, c.nome AS categoria
        FROM lancamentos l
        JOIN categorias c ON c.id = l.categoria_id
        WHERE l.data BETWEEN ? AND ?
        ORDER BY l.data DESC, l.id DESC
        LIMIT 5
        """,
        (inicio, fim),
    ).fetchall()

    # Compras no cartão FEITAS no período: não entram no saldo (contam no mês da fatura),
    # mas o aviso mostra que esse dinheiro já está comprometido
    compras_cartao = conn.execute(
        """
        SELECT COUNT(*) AS qtd, COALESCE(SUM(valor_total_centavos), 0) AS total
        FROM compras_cartao
        WHERE data_compra BETWEEN ? AND ?
        """,
        (inicio, fim),
    ).fetchone()

    # Próxima fatura de cada cartão ativo, a partir de hoje
    hoje = relogio.hoje()
    proximas_faturas = []
    for cartao in buscar_cartoes():
        if not cartao["ativo"]:
            continue
        vencimento = proximo_vencimento(hoje, cartao["dia_vencimento"])
        proximas_faturas.append({
            "cartao": cartao,
            "vencimento": vencimento.isoformat(),
            "total": total_fatura(conn, cartao["id"], vencimento),
            "situacao": situacao_fatura(
                vencimento, cartao["dia_fechamento"], cartao["dia_vencimento"], hoje
            ),
        })

    # Contas recorrentes do mês atual que ainda não foram lançadas
    pendentes = recorrencias_pendentes(conn, mes_atual())

    # Evolução: receitas × despesas dos 6 meses que terminam no mês do fim do período
    ultimo_mes = fim[:7]
    meses_grafico = [mes_vizinho(ultimo_mes, -i) for i in range(5, -1, -1)]   # do mais antigo ao atual
    por_mes = {
        linha["mes"]: linha
        for linha in conn.execute(
            """
            SELECT substr(data, 1, 7) AS mes,   -- '2026-10-15' → '2026-10'
                   COALESCE(SUM(CASE WHEN tipo = 'receita' THEN valor_centavos END), 0) AS receitas,
                   COALESCE(SUM(CASE WHEN tipo = 'despesa' THEN valor_centavos END), 0) AS despesas
            FROM lancamentos
            WHERE data BETWEEN ? AND ?
            GROUP BY mes
            """,
            (f"{meses_grafico[0]}-01", limites_do_mes(ultimo_mes)[1]),
        )
    }
    # Meses sem lançamentos entram com zero (senão sumiriam do gráfico)
    evolucao = [
        {
            "mes": mes,
            "rotulo": MESES[int(mes[5:]) - 1][:3] + "/" + mes[2:4],   # 'out/26'
            "receitas": por_mes[mes]["receitas"] if mes in por_mes else 0,
            "despesas": por_mes[mes]["despesas"] if mes in por_mes else 0,
        }
        for mes in meses_grafico
    ]

    # Orçamento do mês em que o período começa (só as categorias orçadas)
    mes_orcamento = inicio[:7]
    orcamento_itens = [i for i in buscar_orcamento(conn, mes_orcamento) if i["previsto"]]

    conn.close()

    return render_template(
        "dashboard.html",
        recorrencias_pendentes=pendentes,
        mes_pendentes=mes_atual(),
        mes_orcamento=mes_orcamento,
        orcamento_itens=orcamento_itens,
        evolucao=evolucao,
        inicio=inicio,
        fim=fim,
        receitas=totais["receitas"],
        despesas=totais["despesas"],
        saldo=totais["receitas"] - totais["despesas"],  # SALDO = RECEITAS − DESPESAS
        qtd=totais["qtd"],
        despesas_por_categoria=despesas_por_categoria,
        ultimos=ultimos,
        compras_cartao=compras_cartao,
        proximas_faturas=proximas_faturas,
    )
