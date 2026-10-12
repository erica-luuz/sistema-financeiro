"""Regras do cartão de crédito: em qual fatura cai uma compra e como dividir as parcelas.

Funções "puras": só recebem valores e devolvem resultados, sem banco e sem Flask.
Por isso são fáceis de testar (ver tests/test_faturas.py).
Regras na documentação: docs/documentacao_v2.md, seções 5.2 e 5.4.
"""
from datetime import date


def somar_meses(ano, mes, quantidade):
    """(2026, 11) + 3 meses → (2027, 2). Aceita quantidade negativa."""
    indice = ano * 12 + (mes - 1) + quantidade   # conta os meses "em fila" desde o ano 0
    return indice // 12, indice % 12 + 1


def data_fechamento(dia_fechamento, dia_vencimento, ano_vencimento, mes_vencimento):
    """Dia em que fecha a fatura que vence em mes_vencimento/ano_vencimento.

    Se o fechamento vem antes do vencimento no calendário (fecha 3, vence 10),
    a fatura fecha no mesmo mês do vencimento. Senão (fecha 25, vence 5), fecha no mês anterior.
    """
    if dia_fechamento < dia_vencimento:
        return date(ano_vencimento, mes_vencimento, dia_fechamento)
    ano, mes = somar_meses(ano_vencimento, mes_vencimento, -1)
    return date(ano, mes, dia_fechamento)


def vencimento_da_fatura(data_compra, dia_fechamento, dia_vencimento):
    """Data de vencimento da fatura em que a compra cai.

    Regra: compra ANTES do dia de fechamento entra na fatura que fecha naquele dia;
    compra NO dia do fechamento ou depois vai para a fatura seguinte.
    """
    ano, mes = data_compra.year, data_compra.month
    while True:
        if data_compra < data_fechamento(dia_fechamento, dia_vencimento, ano, mes):
            return date(ano, mes, dia_vencimento)
        ano, mes = somar_meses(ano, mes, 1)


def proximo_vencimento(hoje, dia_vencimento):
    """Primeira data de vencimento a partir de hoje (inclusive). Ex.: hoje 12/10, vence dia 10 → 10/11."""
    vencimento = date(hoje.year, hoje.month, dia_vencimento)
    if vencimento < hoje:
        ano, mes = somar_meses(hoje.year, hoje.month, 1)
        vencimento = date(ano, mes, dia_vencimento)
    return vencimento


def situacao_fatura(vencimento, dia_fechamento, dia_vencimento, hoje):
    """Situação da fatura em relação a hoje:

    'futura'  → a fatura anterior ainda não fechou; esta só tem parcelas de compras antigas
    'aberta'  → é a fatura que está recebendo as compras de hoje
    'fechada' → já fechou, aguardando o vencimento
    'vencida' → o vencimento já passou
    """
    fechamento = data_fechamento(dia_fechamento, dia_vencimento, vencimento.year, vencimento.month)
    ano_anterior, mes_anterior = somar_meses(vencimento.year, vencimento.month, -1)
    fechamento_anterior = data_fechamento(dia_fechamento, dia_vencimento, ano_anterior, mes_anterior)
    if hoje < fechamento_anterior:
        return "futura"
    if hoje < fechamento:
        return "aberta"
    if hoje <= vencimento:
        return "fechada"
    return "vencida"


def dividir_parcelas(total_centavos, quantidade):
    """Divide em centavos inteiros; a sobra vai na 1ª parcela. 100000 em 3 → [33334, 33333, 33333]."""
    base, sobra = divmod(total_centavos, quantidade)   # divmod(100000, 3) → (33333, 1)
    return [base + sobra] + [base] * (quantidade - 1)


def gerar_parcelas(total_centavos, quantidade, data_compra, dia_fechamento, dia_vencimento):
    """Lista de (numero, valor_centavos, vencimento) — uma parcela por fatura, a partir da 1ª."""
    primeira = vencimento_da_fatura(data_compra, dia_fechamento, dia_vencimento)
    parcelas = []
    for indice, valor in enumerate(dividir_parcelas(total_centavos, quantidade)):
        ano, mes = somar_meses(primeira.year, primeira.month, indice)
        parcelas.append((indice + 1, valor, date(ano, mes, dia_vencimento)))
    return parcelas
