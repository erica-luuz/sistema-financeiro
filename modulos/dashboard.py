"""Dashboard: resumo do período, saldo em conta, gráfico, próximas faturas, orçamento e contas a lançar."""
from datetime import date

from flask import Blueprint, flash, redirect, render_template, request, url_for

import relogio
from db import get_db_connection
from util import (
    MESES,
    limites_do_mes,
    mes_atual,
    mes_vizinho,
    para_centavos,
    periodo_mes_atual,
)
from faturas import proximo_vencimento, situacao_fatura
from modulos.cartoes import buscar_cartoes, fatura_esta_paga, total_fatura
from modulos.orcamento import buscar_orcamento
from modulos.recorrencias import recorrencias_pendentes

bp = Blueprint("dashboard", __name__)


# ---------- Saldo em conta (saldo acumulado) ----------

def ler_saldo_inicial(conn):
    """O saldo informado pela casa: {"centavos": 350000, "data": "2026-10-01"}, ou None se não houver."""
    valores = dict(conn.execute(
        "SELECT chave, valor FROM configuracoes "
        "WHERE chave IN ('saldo_inicial_centavos', 'saldo_inicial_data')"
    ).fetchall())
    if len(valores) < 2:
        return None
    return {"centavos": int(valores["saldo_inicial_centavos"]), "data": valores["saldo_inicial_data"]}


def saldo_em(conn, saldo_inicial, data_ate):
    """Quanto há na conta no FIM do dia data_ate: saldo inicial + receitas − despesas desde a data dele.

    No crédito, a despesa conta no vencimento da fatura (é quando o dinheiro sai da conta).
    Antes da data do saldo inicial não há como saber: devolve None.
    """
    if data_ate < saldo_inicial["data"]:
        return None
    movimento = conn.execute(
        """
        SELECT COALESCE(SUM(CASE WHEN tipo = 'receita' THEN valor_centavos ELSE -valor_centavos END), 0)
        FROM lancamentos
        WHERE data >= ? AND data <= ?
        """,
        (saldo_inicial["data"], data_ate),
    ).fetchone()[0]
    return saldo_inicial["centavos"] + movimento


@bp.route("/saldo-inicial", methods=["GET", "POST"])
def saldo_inicial():
    conn = get_db_connection()
    atual = ler_saldo_inicial(conn)

    if request.method == "POST":
        valor = request.form.get("valor", "").strip()
        data = request.form.get("data", "").strip()
        erro = None
        if not valor:
            # Campo vazio = deixar de usar o saldo em conta
            conn.execute("DELETE FROM configuracoes WHERE chave LIKE 'saldo_inicial_%'")
            conn.commit()
            conn.close()
            flash("Saldo inicial removido.", "sucesso")
            return redirect(url_for("dashboard.inicio"))
        try:
            centavos = para_centavos(valor)    # pode ser negativo (conta no vermelho)
            date.fromisoformat(data)
        except (ValueError, OverflowError):
            erro = "Informe um valor (ex.: 3500,00 ou -200,00) e uma data válidos."
        if erro:
            conn.close()
            return render_template("saldo_inicial.html", erro=erro, valor=valor, data=data, atual=atual), 400
        with conn:
            for chave, texto in (("saldo_inicial_centavos", str(centavos)), ("saldo_inicial_data", data)):
                conn.execute(
                    "INSERT INTO configuracoes (chave, valor) VALUES (?, ?) "
                    "ON CONFLICT (chave) DO UPDATE SET valor = excluded.valor",
                    (chave, texto),
                )
        conn.close()
        flash("Saldo inicial salvo.", "sucesso")
        return redirect(url_for("dashboard.inicio"))

    conn.close()
    return render_template(
        "saldo_inicial.html",
        atual=atual,
        valor=f"{atual['centavos'] / 100:.2f}" if atual else "",
        data=atual["data"] if atual else relogio.hoje().isoformat(),
    )


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
            "paga": fatura_esta_paga(conn, cartao["id"], vencimento),
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
    # Saldo em conta: hoje e no fim do período (só se o saldo inicial foi informado)
    inicial = ler_saldo_inicial(conn)
    saldo_conta = None
    if inicial:
        saldo_conta = {
            "hoje": saldo_em(conn, inicial, hoje.isoformat()),
            "fim_periodo": saldo_em(conn, inicial, fim),
            "inicial": inicial,
        }

    # Meses sem lançamentos entram com zero (senão sumiriam do gráfico)
    evolucao = [
        {
            "mes": mes,
            "rotulo": MESES[int(mes[5:]) - 1][:3] + "/" + mes[2:4],   # 'out/26'
            "receitas": por_mes[mes]["receitas"] if mes in por_mes else 0,
            "despesas": por_mes[mes]["despesas"] if mes in por_mes else 0,
            # Saldo em conta no último dia do mês (None antes da data do saldo inicial)
            "saldo_conta": saldo_em(conn, inicial, limites_do_mes(mes)[1]) if inicial else None,
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
        saldo_conta=saldo_conta,
        hoje=hoje.isoformat(),
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
