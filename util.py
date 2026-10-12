"""Funções de apoio usadas em todo o sistema: dinheiro (R$, centavos), datas e meses,
formas de pagamento e ordenação sem acento.

As que viram filtros de template (| moeda, | data_br...) são registradas no app.py.
"""
import calendar
import unicodedata
from datetime import date

import relogio
from faturas import somar_meses


def moeda(centavos):
    """Converte centavos em texto no formato brasileiro: 25050 → 'R$ 250,50'."""
    sinal = "-" if centavos < 0 else ""                  # saldo negativo: -R$ 310,50
    texto = f"{abs(centavos) / 100:,.2f}"               # 25050 → '250.50' / 123456 → '1,234.56'
    texto = texto.replace(",", "X").replace(".", ",").replace("X", ".")  # troca , e .
    return f"{sinal}R$ {texto}"


def data_br(data_iso):
    """Converte '2026-10-09' em '09/10/2026'."""
    ano, mes, dia = data_iso.split("-")
    return f"{dia}/{mes}/{ano}"


def data_local(texto_utc):
    """Datas gravadas pelo banco (CURRENT_TIMESTAMP, em UTC) → '12/10/2026' em Brasília."""
    return relogio.utc_para_local(texto_utc).strftime("%d/%m/%Y")


MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho",
         "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"]


def mes_ano(data_iso):
    """'2026-11-10' → 'novembro/2026'."""
    ano, mes = data_iso.split("-")[:2]
    return f"{MESES[int(mes) - 1]}/{ano}"


def sem_acento(texto):
    """'Água' → 'agua'. Usado para ordenar nomes em português corretamente."""
    decomposto = unicodedata.normalize("NFKD", texto)  # 'Á' vira 'A' + acento separado
    return "".join(c for c in decomposto if not unicodedata.combining(c)).lower()


# Formas de pagamento: valor no banco → texto na tela (a ordem é a das listas)
FORMAS_PAGAMENTO = {
    "pix": "Pix",
    "debito": "Débito",
    "credito": "Crédito",
    "dinheiro": "Dinheiro",
    "boleto": "Boleto",
    "transferencia": "Transferência",
}


# No formulário comum, sem "credito": compras no crédito são lançadas pelo cartão (Etapa 12)
FORMAS_FORMULARIO = {chave: texto for chave, texto in FORMAS_PAGAMENTO.items() if chave != "credito"}


def forma(chave):
    """'debito' → 'Débito'."""
    return FORMAS_PAGAMENTO.get(chave, chave)


def para_centavos(valor_texto):
    """'250.50' ou '250,50' → 25050."""
    return round(float(valor_texto.replace(",", ".")) * 100)


def numero_br(centavos):
    """25050 → '250,50' (sem 'R$' e sem ponto de milhar: o Excel entende como número)."""
    return f"{centavos / 100:.2f}".replace(".", ",")


def periodo_mes_atual():
    """Devolve o primeiro e o último dia do mês atual, no formato AAAA-MM-DD."""
    hoje = relogio.hoje()
    ultimo_dia = calendar.monthrange(hoje.year, hoje.month)[1]  # 28, 29, 30 ou 31
    inicio = hoje.replace(day=1)
    fim = hoje.replace(day=ultimo_dia)
    return inicio.isoformat(), fim.isoformat()


def mes_atual():
    return relogio.mes_atual()   # '2026-10', no horário de Brasília


def mes_valido(texto):
    """Confere o formato AAAA-MM (o que o <input type="month"> envia)."""
    try:
        date.fromisoformat(texto + "-01")
        return len(texto) == 7
    except ValueError:
        return False


def mes_vizinho(mes, quantidade):
    """'2026-10', -1 → '2026-09'."""
    ano, numero = somar_meses(int(mes[:4]), int(mes[5:]), quantidade)
    return f"{ano}-{numero:02d}"


def limites_do_mes(mes):
    """'2026-02' → ('2026-02-01', '2026-02-28')."""
    ultimo_dia = calendar.monthrange(int(mes[:4]), int(mes[5:]))[1]
    return f"{mes}-01", f"{mes}-{ultimo_dia}"
