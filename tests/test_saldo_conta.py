"""Saldo em conta (saldo acumulado): saldo inicial + receitas − despesas desde a data dele."""
import html
import json
import re
from datetime import datetime

import pytest

import relogio
from conftest import id_categoria


@pytest.fixture(autouse=True)
def quinze_de_outubro(monkeypatch):
    monkeypatch.setattr(relogio, "agora", lambda: datetime(2026, 10, 15, 12, 0, tzinfo=relogio.FUSO))


def inserir(banco, tipo, valor, data):
    categoria = id_categoria(banco, "Salário", "receita") if tipo == "receita" else id_categoria(banco, "Alimentação")
    banco.execute(
        "INSERT INTO lancamentos (descricao, valor_centavos, tipo, data, categoria_id) VALUES ('x', ?, ?, ?, ?)",
        (valor, tipo, data, categoria),
    )
    banco.commit()


def pagina(logado, url="/?inicio=2026-10-01&fim=2026-10-31"):
    return html.unescape(logado.get(url).get_data(as_text=True))


def test_sem_saldo_inicial_convida_a_informar(logado):
    assert "Informar saldo inicial" in pagina(logado)


def test_saldo_hoje_e_previsto_no_fim_do_mes(logado, banco):
    logado.post("/saldo-inicial", data={"valor": "1000", "data": "2026-10-01"})
    inserir(banco, "despesa", 50000, "2026-09-20")    # antes do saldo inicial: não conta
    inserir(banco, "receita", 500000, "2026-10-05")
    inserir(banco, "despesa", 30000, "2026-10-10")
    inserir(banco, "despesa", 20000, "2026-10-20")    # depois de hoje (15/10): só no previsto
    texto = pagina(logado)
    hoje = re.search(r"Saldo em conta hoje</p>\s*<p[^>]*>\s*(.*?)\s*</p>", texto).group(1)
    previsto = re.search(r"Previsto para 31/10/2026</p>\s*<p[^>]*>(.*?)</p>", texto).group(1)
    assert hoje == "R$ 5.700,00"          # 1.000 + 5.000 − 300
    assert previsto == "R$ 5.500,00"      # ... − 200 do dia 20


def test_saldo_negativo(logado, banco):
    logado.post("/saldo-inicial", data={"valor": "-200", "data": "2026-10-01"})
    texto = pagina(logado)
    assert "-R$ 200,00" in texto


def test_grafico_tem_a_linha_do_saldo(logado, banco):
    logado.post("/saldo-inicial", data={"valor": "1000", "data": "2026-09-01"})
    inserir(banco, "receita", 100000, "2026-09-10")
    evolucao = json.loads(re.search(r"const evolucao = (\[.*?\]);", pagina(logado), re.S).group(1))
    saldos = {m["mes"]: m["saldo_conta"] for m in evolucao}
    assert saldos["2026-08"] is None             # antes do saldo inicial: sem ponto
    assert saldos["2026-09"] == 200000 and saldos["2026-10"] == 200000


def test_saldo_inicial_invalido_e_remover(logado, banco):
    resposta = logado.post("/saldo-inicial", data={"valor": "abc", "data": "2026-10-01"})
    assert resposta.status_code == 400
    logado.post("/saldo-inicial", data={"valor": "1000", "data": "2026-10-01"})
    logado.post("/saldo-inicial", data={"valor": "", "data": "2026-10-01"})    # apagar = remover
    assert banco.execute("SELECT COUNT(*) FROM configuracoes").fetchone()[0] == 0
