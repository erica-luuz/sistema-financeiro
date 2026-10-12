"""Testes do cartão (compras e faturas), recorrências, orçamento e dashboard."""
import json
import re

import pytest

from conftest import id_categoria


@pytest.fixture
def cartao(logado, banco):
    """Cartão da Érica que fecha dia 3 e vence dia 10, com limite de R$ 5.000."""
    logado.post("/cartoes/novo", data={
        "nome": "Itaú", "titular": "Érica", "dia_fechamento": "3", "dia_vencimento": "10", "limite": "5000",
    })
    return banco.execute("SELECT id FROM cartoes").fetchone()[0]


def comprar(logado, banco, cartao, **campos):
    dados = {
        "cartao_id": cartao, "descricao": "Geladeira", "valor": "1000", "parcelas": "3",
        "data_compra": "2026-10-25", "categoria_id": id_categoria(banco, "Compras"), "observacao": "",
    }
    dados.update(campos)
    return logado.post("/compras/nova", data=dados)


def parcelas(banco):
    return [tuple(p) for p in banco.execute(
        "SELECT parcela_numero, valor_centavos, data, forma_pagamento FROM lancamentos "
        "WHERE compra_id IS NOT NULL ORDER BY data"
    )]


# ---------- compras no cartão ----------

def test_compra_parcelada_cai_nas_faturas_certas(logado, banco, cartao):
    comprar(logado, banco, cartao)
    assert parcelas(banco) == [
        (1, 33334, "2026-11-10", "credito"),
        (2, 33333, "2026-12-10", "credito"),
        (3, 33333, "2027-01-10", "credito"),
    ]


def test_editar_compra_recalcula_parcelas(logado, banco, cartao):
    comprar(logado, banco, cartao)
    compra = banco.execute("SELECT id FROM compras_cartao").fetchone()[0]
    logado.post(f"/compras/editar/{compra}", data={
        "cartao_id": cartao, "descricao": "Geladeira", "valor": "600", "parcelas": "2",
        "data_compra": "2026-10-02", "categoria_id": id_categoria(banco, "Compras"), "observacao": "",
    })
    assert parcelas(banco) == [(1, 30000, "2026-10-10", "credito"), (2, 30000, "2026-11-10", "credito")]


def test_excluir_compra_apaga_todas_as_parcelas(logado, banco, cartao):
    comprar(logado, banco, cartao)
    compra = banco.execute("SELECT id FROM compras_cartao").fetchone()[0]
    logado.post(f"/compras/excluir/{compra}")
    assert parcelas(banco) == []


def test_parcela_nao_e_editada_sozinha(logado, banco, cartao):
    comprar(logado, banco, cartao)
    pid, compra = banco.execute("SELECT id, compra_id FROM lancamentos").fetchone()
    assert logado.get(f"/lancamentos/editar/{pid}").headers["Location"] == f"/compras/{compra}"


def test_cartao_com_compras_nao_pode_ser_excluido(logado, banco, cartao):
    comprar(logado, banco, cartao)
    resposta = logado.post(f"/cartoes/excluir/{cartao}")
    assert "não pode ser excluído" in resposta.get_data(as_text=True)


@pytest.mark.parametrize("campos, mensagem", [
    ({"parcelas": "25"}, "de 1 a 24"),
    ({"valor": "0.05", "parcelas": "24"}, "pequeno demais"),
    ({"categoria_id": "1"}, "categoria de despesa"),
])
def test_compra_invalida(logado, banco, cartao, campos, mensagem):
    resposta = comprar(logado, banco, cartao, **campos)
    assert mensagem in resposta.get_data(as_text=True)
    assert parcelas(banco) == []


def test_pagina_de_faturas(logado, banco, cartao):
    comprar(logado, banco, cartao)
    html = logado.get(f"/cartoes/{cartao}/faturas").get_data(as_text=True)
    assert "Fatura de novembro/2026" in html and "R$ 333,34" in html


# ---------- recorrências ----------

def recorrencia(logado, banco, **campos):
    dados = {
        "descricao": "Internet", "valor": "120", "tipo": "despesa",
        "categoria_id": id_categoria(banco, "Internet"), "forma_pagamento": "debito", "cartao_id": "",
        "dia_do_mes": "15", "mes_inicio": "2026-10", "mes_fim": "",
    }
    dados.update(campos)
    return logado.post("/recorrencias/nova", data=dados)


def test_gerar_recorrencias_nao_duplica(logado, banco):
    recorrencia(logado, banco)
    logado.post("/recorrencias/gerar", data={"mes": "2026-10"})
    logado.post("/recorrencias/gerar", data={"mes": "2026-10"})
    linhas = banco.execute("SELECT data, valor_centavos FROM lancamentos").fetchall()
    assert [tuple(l) for l in linhas] == [("2026-10-15", 12000)]


def test_recorrencia_respeita_vigencia(logado, banco):
    recorrencia(logado, banco, descricao="Curso", mes_fim="2026-11")
    for mes in ("2026-10", "2026-11", "2026-12"):
        logado.post("/recorrencias/gerar", data={"mes": mes})
    datas = [l[0] for l in banco.execute("SELECT data FROM lancamentos ORDER BY data")]
    assert datas == ["2026-10-15", "2026-11-15"]


def test_recorrencia_no_credito_vira_compra_na_fatura(logado, banco, cartao):
    recorrencia(logado, banco, descricao="Netflix", valor="55.90", categoria_id=id_categoria(banco, "Lazer"),
                forma_pagamento="credito", cartao_id=cartao, dia_do_mes="20")
    logado.post("/recorrencias/gerar", data={"mes": "2026-10"})
    assert parcelas(banco) == [(1, 5590, "2026-11-10", "credito")]


# ---------- orçamento ----------

def test_orcamento_previsto_gasto_e_projecao(logado, banco):
    alimentacao = id_categoria(banco, "Alimentação")
    logado.post("/orcamento", data={"mes": "2026-10", f"valor_{alimentacao}": "300"})
    logado.post("/lancamentos/novo", data={
        "descricao": "Mercado", "valor": "250", "tipo": "despesa", "data": "2026-10-05",
        "categoria_id": alimentacao, "forma_pagamento": "pix", "observacao": "",
    })
    recorrencia(logado, banco, descricao="Vale", valor="100", categoria_id=alimentacao, dia_do_mes="25")

    from app import buscar_orcamento
    item = next(i for i in buscar_orcamento(banco, "2026-10") if i["id"] == alimentacao)
    assert (item["previsto"], item["realizado"], item["pendentes"], item["projecao"]) == (30000, 25000, 10000, 35000)
    assert item["faixa_projecao"] == "estourou"

    # Lançar a recorrência não pode contar duas vezes: a projeção continua a mesma
    logado.post("/recorrencias/gerar", data={"mes": "2026-10"})
    item = next(i for i in buscar_orcamento(banco, "2026-10") if i["id"] == alimentacao)
    assert (item["realizado"], item["pendentes"], item["projecao"]) == (35000, 0, 35000)


def test_copiar_orcamento_do_mes_anterior(logado, banco):
    lazer = id_categoria(banco, "Lazer")
    logado.post("/orcamento", data={"mes": "2026-10", f"valor_{lazer}": "200"})
    logado.post("/orcamento/copiar", data={"mes": "2026-11"})
    logado.post("/orcamento/copiar", data={"mes": "2026-11"})
    linhas = banco.execute("SELECT mes, valor_centavos FROM orcamentos WHERE categoria_id = ?", (lazer,)).fetchall()
    assert sorted(tuple(l) for l in linhas) == [("2026-10", 20000), ("2026-11", 20000)]


# ---------- dashboard ----------

def test_dashboard_totais_e_compra_no_mes_da_fatura(logado, banco, cartao):
    logado.post("/lancamentos/novo", data={
        "descricao": "Salário", "valor": "5000", "tipo": "receita", "data": "2026-10-05",
        "categoria_id": id_categoria(banco, "Salário", "receita"), "forma_pagamento": "transferencia", "observacao": "",
    })
    comprar(logado, banco, cartao, valor="300", parcelas="1", data_compra="2026-10-25")   # fatura de 10/11
    html_out = logado.get("/?inicio=2026-10-01&fim=2026-10-31").get_data(as_text=True)
    html_nov = logado.get("/?inicio=2026-11-01&fim=2026-11-30").get_data(as_text=True)
    assert "R$ 5.000,00" in html_out and "Geladeira" not in html_out
    assert "Geladeira" in html_nov and "-R$ 300,00" in html_nov


def test_dashboard_grafico_tem_6_meses(logado):
    html = logado.get("/?inicio=2026-10-01&fim=2026-10-31").get_data(as_text=True)
    evolucao = json.loads(re.search(r"const evolucao = (\[.*?\]);", html, re.S).group(1))
    assert [m["rotulo"] for m in evolucao] == ["mai/26", "jun/26", "jul/26", "ago/26", "set/26", "out/26"]
