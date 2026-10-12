"""Testes dos lançamentos e categorias: criar, editar, excluir, filtrar, exportar."""
import csv
import html
import io

import pytest

from conftest import id_categoria


def novo(logado, banco, **campos):
    dados = {
        "descricao": "Supermercado", "valor": "250.50", "tipo": "despesa", "data": "2026-10-09",
        "categoria_id": id_categoria(banco, "Alimentação"), "forma_pagamento": "pix", "observacao": "",
    }
    dados.update(campos)
    return logado.post("/lancamentos/novo", data=dados)


def lancamentos(banco):
    return banco.execute(
        "SELECT descricao, valor_centavos, tipo, data, forma_pagamento FROM lancamentos ORDER BY id"
    ).fetchall()


# ---------- criar ----------

def test_criar_lancamento_grava_em_centavos(logado, banco):
    assert novo(logado, banco).status_code == 302
    assert [tuple(l) for l in lancamentos(banco)] == [("Supermercado", 25050, "despesa", "2026-10-09", "pix")]


def test_mensagem_de_confirmacao_aparece_uma_vez(logado, banco):
    novo(logado, banco)
    pagina = html.unescape(logado.get("/lancamentos").get_data(as_text=True))
    assert 'Lançamento "Supermercado" salvo.' in pagina
    assert "salvo." not in logado.get("/lancamentos").get_data(as_text=True)   # flash some depois de exibido


def descartar_mensagens(logado):
    """Abre uma página qualquer para a mensagem de confirmação ("... salvo.") ser exibida e sumir."""
    logado.get("/categorias")


@pytest.mark.parametrize("valor, centavos", [("19.99", 1999), ("0.1", 10), ("1234.5", 123450), ("250,50", 25050)])
def test_conversao_para_centavos_sem_erro_de_arredondamento(logado, banco, valor, centavos):
    novo(logado, banco, valor=valor)
    assert lancamentos(banco)[0]["valor_centavos"] == centavos


@pytest.mark.parametrize("campos, mensagem", [
    ({"valor": "0"}, "maior que zero"),
    ({"valor": "-5"}, "maior que zero"),
    ({"valor": "abc"}, "valor válido"),
    ({"descricao": ""}, "Informe a descrição"),
    ({"data": ""}, "Informe a data"),
    ({"forma_pagamento": "credito"}, "forma de pagamento"),
    ({"tipo": "receita"}, "não corresponde ao tipo da categoria"),
])
def test_criar_lancamento_invalido_nao_grava(logado, banco, campos, mensagem):
    resposta = novo(logado, banco, **campos)
    assert mensagem in resposta.get_data(as_text=True)
    assert lancamentos(banco) == []


def test_formulario_com_erro_mantem_o_que_foi_digitado(logado, banco):
    resposta = novo(logado, banco, tipo="receita", descricao="Texto digitado")
    assert 'value="Texto digitado"' in resposta.get_data(as_text=True)


# ---------- editar e excluir ----------

def test_editar_lancamento_atualiza_e_marca_atualizado_em(logado, banco):
    novo(logado, banco)
    banco.execute("UPDATE lancamentos SET atualizado_em = '2000-01-01 00:00:00'")
    banco.commit()
    lid = banco.execute("SELECT id FROM lancamentos").fetchone()[0]
    logado.post(f"/lancamentos/editar/{lid}", data={
        "descricao": "Mercado", "valor": "300", "tipo": "despesa", "data": "2026-10-10",
        "categoria_id": id_categoria(banco, "Alimentação"), "forma_pagamento": "debito", "observacao": "",
    })
    linha = banco.execute("SELECT descricao, valor_centavos, atualizado_em FROM lancamentos").fetchone()
    assert (linha["descricao"], linha["valor_centavos"]) == ("Mercado", 30000)
    assert linha["atualizado_em"] > "2000-01-01"


def test_excluir_lancamento(logado, banco):
    novo(logado, banco)
    lid = banco.execute("SELECT id FROM lancamentos").fetchone()[0]
    logado.post(f"/lancamentos/excluir/{lid}")
    assert lancamentos(banco) == []


def test_excluir_por_get_nao_funciona(logado, banco):
    novo(logado, banco)
    lid = banco.execute("SELECT id FROM lancamentos").fetchone()[0]
    assert logado.get(f"/lancamentos/excluir/{lid}").status_code == 405
    assert len(lancamentos(banco)) == 1


def test_editar_inexistente_da_404(logado):
    assert logado.get("/lancamentos/editar/9999").status_code == 404


# ---------- lista e filtros ----------

def test_filtros_combinados(logado, banco):
    novo(logado, banco, descricao="Mercado out", data="2026-10-05")
    novo(logado, banco, descricao="Mercado set", data="2026-09-05")
    novo(logado, banco, descricao="Salário", tipo="receita", forma_pagamento="transferencia",
         categoria_id=id_categoria(banco, "Salário", "receita"), valor="5000", data="2026-10-05")
    descartar_mensagens(logado)
    pagina = logado.get("/lancamentos?inicio=2026-10-01&fim=2026-10-31&tipo=despesa").get_data(as_text=True)
    assert "Mercado out" in pagina and "Mercado set" not in pagina and "Salário</td>" not in pagina


def test_filtro_nao_aceita_sql_injection(logado, banco):
    novo(logado, banco)
    descartar_mensagens(logado)
    pagina = logado.get("/lancamentos?tipo=despesa' OR 1=1 --").get_data(as_text=True)
    assert "Supermercado" not in pagina


# ---------- exportar ----------

def test_exportar_csv_para_excel(logado, banco):
    novo(logado, banco)
    novo(logado, banco, descricao="Salário", tipo="receita", forma_pagamento="transferencia",
         categoria_id=id_categoria(banco, "Salário", "receita"), valor="5000", data="2026-10-05")
    resposta = logado.get("/lancamentos/exportar.csv?inicio=2026-10-01&fim=2026-10-31")
    assert resposta.data.startswith(b"\xef\xbb\xbf")          # BOM: acentos certos no Excel
    linhas = list(csv.reader(io.StringIO(resposta.data.decode("utf-8-sig")), delimiter=";"))
    assert linhas[0][0] == "Data"
    valores = {linha[1]: linha[9] for linha in linhas[1:]}
    assert valores == {"Supermercado": "-250,50", "Salário": "5000,00"}   # despesa negativa


# ---------- categorias ----------

def test_categoria_nova_e_duplicada(logado, banco):
    logado.post("/categorias/nova", data={"nome": "  Pet  ", "tipo": "despesa"})
    assert banco.execute("SELECT COUNT(*) FROM categorias WHERE nome = 'Pet'").fetchone()[0] == 1
    resposta = logado.post("/categorias/nova", data={"nome": "Pet", "tipo": "despesa"})
    assert "Já existe" in resposta.get_data(as_text=True)


def test_categoria_em_uso_nao_pode_ser_excluida(logado, banco):
    novo(logado, banco)
    cid = id_categoria(banco, "Alimentação")
    resposta = logado.post(f"/categorias/excluir/{cid}")
    assert "não pode ser excluída" in resposta.get_data(as_text=True)
    assert banco.execute("SELECT COUNT(*) FROM categorias WHERE id = ?", (cid,)).fetchone()[0] == 1


def test_categoria_sem_uso_pode_ser_excluida(logado, banco):
    cid = id_categoria(banco, "Lazer")
    logado.post(f"/categorias/excluir/{cid}")
    assert banco.execute("SELECT COUNT(*) FROM categorias WHERE id = ?", (cid,)).fetchone()[0] == 0


def test_categorias_ordenadas_sem_acento(logado):
    html = logado.get("/categorias").get_data(as_text=True)
    assert html.index("Água") < html.index("Alimentação")
