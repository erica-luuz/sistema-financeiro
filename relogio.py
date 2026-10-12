"""Que dia e que horas são — sempre no horário de Brasília.

Por que existe: o servidor (PythonAnywhere) usa o horário UTC, 3 horas à frente de Brasília.
Com date.today(), depois das 21h o sistema acharia que já é o dia seguinte (e, no último dia
do mês, que já é o mês seguinte). Todo o sistema pergunta a data AQUI, nunca direto ao Python.

Use sempre como relogio.hoje() (e não "from relogio import hoje"): assim os testes conseguem
"parar o relógio" num momento escolhido.
"""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo   # no Windows, precisa do pacote tzdata (está no requirements.txt)

FUSO = ZoneInfo("America/Sao_Paulo")


def agora():
    """Data e hora atuais em Brasília."""
    return datetime.now(FUSO)


def hoje():
    """Data de hoje em Brasília."""
    return agora().date()


def mes_atual():
    """Mês atual em Brasília, no formato '2026-10'."""
    return agora().strftime("%Y-%m")


def utc_para_local(texto_utc):
    """'2026-10-12 23:30:00' (UTC, como o CURRENT_TIMESTAMP do SQLite grava) → datetime em Brasília."""
    momento = datetime.fromisoformat(texto_utc).replace(tzinfo=timezone.utc)
    return momento.astimezone(FUSO)
