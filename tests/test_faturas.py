"""Testes da regra da fatura. Rode com:  python -m pytest

Cada função test_... é um caso. O pytest roda todas e avisa se algum "assert" falhar.
Os exemplos são os da documentação (docs/documentacao_v2.md, seções 5.2 e 5.4).
"""
from datetime import date

import pytest

from faturas import (
    data_fechamento,
    dividir_parcelas,
    gerar_parcelas,
    somar_meses,
    vencimento_da_fatura,
)


# ---------- somar_meses ----------

def test_somar_meses_no_mesmo_ano():
    assert somar_meses(2026, 3, 2) == (2026, 5)


def test_somar_meses_virando_o_ano():
    assert somar_meses(2026, 11, 3) == (2027, 2)


def test_subtrair_meses_voltando_o_ano():
    assert somar_meses(2026, 1, -1) == (2025, 12)


# ---------- data de fechamento ----------

def test_fechamento_antes_do_vencimento_fecha_no_mesmo_mes():
    # fecha dia 3, vence dia 10: a fatura que vence em 10/11 fecha em 03/11
    assert data_fechamento(3, 10, 2026, 11) == date(2026, 11, 3)


def test_fechamento_depois_do_vencimento_fecha_no_mes_anterior():
    # fecha dia 25, vence dia 5: a fatura que vence em 05/11 fecha em 25/10
    assert data_fechamento(25, 5, 2026, 11) == date(2026, 10, 25)


# ---------- em qual fatura cai a compra (exemplos da seção 5.2) ----------

# Cada linha: (data da compra, vencimento esperado) — cartão que fecha dia 3 e vence dia 10
@pytest.mark.parametrize("compra, vencimento", [
    (date(2026, 10, 2), date(2026, 10, 10)),   # antes do fechamento → fatura de outubro
    (date(2026, 10, 3), date(2026, 11, 10)),   # NO dia do fechamento → fatura seguinte
    (date(2026, 10, 25), date(2026, 11, 10)),
    (date(2026, 12, 15), date(2027, 1, 10)),   # virada de ano
])
def test_fatura_cartao_fecha_3_vence_10(compra, vencimento):
    assert vencimento_da_fatura(compra, 3, 10) == vencimento


# Cartão que fecha dia 25 e vence dia 5 (vencimento no mês seguinte ao fechamento)
@pytest.mark.parametrize("compra, vencimento", [
    (date(2026, 10, 20), date(2026, 11, 5)),
    (date(2026, 10, 25), date(2026, 12, 5)),   # no dia do fechamento → próxima
    (date(2026, 10, 31), date(2026, 12, 5)),
    (date(2026, 12, 26), date(2027, 2, 5)),    # virada de ano
])
def test_fatura_cartao_fecha_25_vence_5(compra, vencimento):
    assert vencimento_da_fatura(compra, 25, 5) == vencimento


# ---------- divisão das parcelas ----------

def test_dividir_sobra_vai_na_primeira_parcela():
    assert dividir_parcelas(100000, 3) == [33334, 33333, 33333]


def test_dividir_valor_exato():
    assert dividir_parcelas(60000, 6) == [10000] * 6


def test_a_vista_e_uma_parcela_so():
    assert dividir_parcelas(25050, 1) == [25050]


@pytest.mark.parametrize("total, quantidade", [(100, 3), (99999, 7), (1, 1), (5, 24), (123457, 12)])
def test_soma_das_parcelas_e_sempre_o_total(total, quantidade):
    parcelas = dividir_parcelas(total, quantidade)
    assert sum(parcelas) == total
    assert len(parcelas) == quantidade


# ---------- parcelas completas (exemplo da seção 5.4) ----------

def test_geladeira_em_3x():
    # R$ 1.000,00 em 3x, comprada em 25/10/2026, cartão que fecha dia 3 e vence dia 10
    assert gerar_parcelas(100000, 3, date(2026, 10, 25), 3, 10) == [
        (1, 33334, date(2026, 11, 10)),
        (2, 33333, date(2026, 12, 10)),
        (3, 33333, date(2027, 1, 10)),
    ]


def test_parcelas_atravessando_varios_anos():
    parcelas = gerar_parcelas(240000, 24, date(2026, 10, 25), 3, 10)
    assert parcelas[0][2] == date(2026, 11, 10)
    assert parcelas[-1][2] == date(2028, 10, 10)
