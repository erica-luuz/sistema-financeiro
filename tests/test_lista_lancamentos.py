"""Lista de lançamentos: mês atual por padrão, todos os períodos, busca e paginação."""
from datetime import datetime

import pytest

import relogio
from conftest import id_categoria


@pytest.fixture(autouse=True)
def relogio_parado(monkeypatch):
    """Todos os testes deste arquivo acontecem em 15/10/2026."""
    momento = datetime(2026, 10, 15, 12, 0, tzinfo=relogio.FUSO)
    monkeypatch.setattr(relogio, "agora", lambda: momento)


def inserir(banco, descricao, data, valor=1000, observacao=None):
    banco.execute(
        "INSERT INTO lancamentos (descricao, valor_centavos, tipo, data, categoria_id, observacao) "
        "VALUES (?, ?, 'despesa', ?, ?, ?)",
        (descricao, valor, data, id_categoria(banco, "Alimentação"), observacao),
    )
    banco.commit()


def test_abre_no_mes_atual(logado, banco):
    inserir(banco, "Mercado de outubro", "2026-10-05")
    inserir(banco, "Mercado de setembro", "2026-09-05")
    inserir(banco, "Parcela de dezembro", "2026-12-10")
    html = logado.get("/lancamentos").get_data(as_text=True)
    assert "Mercado de outubro" in html
    assert "Mercado de setembro" not in html and "Parcela de dezembro" not in html
    assert "01/10/2026 a 31/10/2026" in html


def test_todos_os_periodos(logado, banco):
    inserir(banco, "Mercado de outubro", "2026-10-05")
    inserir(banco, "Mercado de setembro", "2026-09-05")
    html = logado.get("/lancamentos?periodo=todos").get_data(as_text=True)
    assert "Mercado de outubro" in html and "Mercado de setembro" in html


def test_busca_na_descricao_e_na_observacao(logado, banco):
    inserir(banco, "Supermercado Extra", "2026-10-05")
    inserir(banco, "Padaria", "2026-10-06", observacao="pão e leite do mercado")
    inserir(banco, "Farmácia", "2026-10-07")
    html = logado.get("/lancamentos?q=MERCADO&periodo=todos").get_data(as_text=True)
    assert "Supermercado Extra" in html and "Padaria" in html and "Farmácia" not in html


def test_busca_com_caracteres_especiais(logado, banco):
    """% e _ digitados são procurados como texto, e não como "qualquer coisa" do LIKE."""
    inserir(banco, "Desconto 50%", "2026-10-05")
    inserir(banco, "Desconto 500", "2026-10-06")
    html = logado.get("/lancamentos?q=50%25&periodo=todos").get_data(as_text=True)   # %25 = "%"
    assert "Desconto 50%" in html and "Desconto 500" not in html


def test_paginacao_e_totais_de_tudo(logado, banco):
    for dia in range(1, 31):
        for n in range(2):                       # 60 lançamentos de R$ 10,00 em outubro
            inserir(banco, f"Item {dia:02d}-{n}", f"2026-10-{dia:02d}")
    pagina1 = logado.get("/lancamentos").get_data(as_text=True)
    assert pagina1.count('class="acao acao-perigo">Excluir<') == 50
    assert "60 lançamento(s)" in pagina1 and "R$ 600,00" in pagina1   # totais contam as 60
    assert "Página 1 de 2" in pagina1
    pagina2 = logado.get("/lancamentos?pagina=2").get_data(as_text=True)
    assert pagina2.count('class="acao acao-perigo">Excluir<') == 10
    assert "Item 01-0" in pagina2                 # os mais antigos ficam na última página


def test_pagina_invalida_vai_para_a_primeira(logado, banco):
    inserir(banco, "Mercado", "2026-10-05")
    for pagina in ("abc", "0", "-3", "999"):
        assert logado.get(f"/lancamentos?pagina={pagina}").status_code == 200


def test_exportar_sem_filtros_usa_o_mes_atual(logado, banco):
    inserir(banco, "Mercado de outubro", "2026-10-05")
    inserir(banco, "Mercado de setembro", "2026-09-05")
    csv = logado.get("/lancamentos/exportar.csv").data.decode("utf-8-sig")
    assert "Mercado de outubro" in csv and "Mercado de setembro" not in csv
