"""Testes do fuso horário: o sistema precisa usar o horário de Brasília, mesmo num servidor em UTC."""
from datetime import datetime

import pytest

import relogio


@pytest.fixture
def noite_de_31_de_outubro(monkeypatch):
    """Para o relógio em 31/10/2026 às 22h30 de Brasília — que já é 01/11 01h30 em UTC.

    É exatamente o horário em que um servidor em UTC erraria o dia E o mês.
    """
    momento = datetime(2026, 10, 31, 22, 30, tzinfo=relogio.FUSO)
    monkeypatch.setattr(relogio, "agora", lambda: momento)


def test_hoje_e_mes_atual_em_brasilia(noite_de_31_de_outubro):
    assert relogio.hoje().isoformat() == "2026-10-31"
    assert relogio.mes_atual() == "2026-10"


def test_utc_do_banco_vira_horario_de_brasilia():
    # 01/11 01h30 em UTC (como o CURRENT_TIMESTAMP grava) = 31/10 22h30 em Brasília
    local = relogio.utc_para_local("2026-11-01 01:30:00")
    assert (local.day, local.month, local.hour) == (31, 10, 22)


def test_novo_lancamento_vem_com_a_data_de_brasilia(noite_de_31_de_outubro, logado):
    html = logado.get("/lancamentos/novo").get_data(as_text=True)
    assert 'value="2026-10-31"' in html


def test_dashboard_abre_no_mes_de_brasilia(noite_de_31_de_outubro, logado):
    html = logado.get("/").get_data(as_text=True)
    assert "01/10/2026 a 31/10/2026" in html
