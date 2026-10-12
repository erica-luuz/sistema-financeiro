import calendar
import sqlite3
import unicodedata
from datetime import date

from flask import Flask, render_template, request, redirect, url_for, abort  # traz a classe Flask do pacote flask
from db import get_db_connection
from faturas import gerar_parcelas

app = Flask(__name__)   # cria a aplicação (o "servidor")


@app.template_filter("moeda")
def moeda(centavos):
    """Converte centavos em texto no formato brasileiro: 25050 → 'R$ 250,50'."""
    sinal = "-" if centavos < 0 else ""                  # saldo negativo: -R$ 310,50
    texto = f"{abs(centavos) / 100:,.2f}"               # 25050 → '250.50' / 123456 → '1,234.56'
    texto = texto.replace(",", "X").replace(".", ",").replace("X", ".")  # troca , e .
    return f"{sinal}R$ {texto}"


@app.template_filter("data_br")
def data_br(data_iso):
    """Converte '2026-10-09' em '09/10/2026'."""
    ano, mes, dia = data_iso.split("-")
    return f"{dia}/{mes}/{ano}"


def sem_acento(texto):
    """'Água' → 'agua'. Usado para ordenar nomes em português corretamente."""
    decomposto = unicodedata.normalize("NFKD", texto)  # 'Á' vira 'A' + acento separado
    return "".join(c for c in decomposto if not unicodedata.combining(c)).lower()


def ordenar_categorias(categorias):
    """Ordena por tipo e depois por nome, ignorando acentos (a 'Água' vem antes de 'Alimentação')."""
    return sorted(categorias, key=lambda c: (c["tipo"], sem_acento(c["nome"])))


def buscar_categorias():
    """Devolve todas as categorias, ordenadas por tipo e nome."""
    conn = get_db_connection()
    categorias = conn.execute("SELECT id, nome, tipo FROM categorias").fetchall()
    conn.close()
    return ordenar_categorias(categorias)


def buscar_categorias_com_uso():
    """Devolve as categorias com a quantidade de lançamentos que usam cada uma."""
    conn = get_db_connection()
    categorias = conn.execute(
        """
        SELECT c.id, c.nome, c.tipo, COUNT(l.id) AS qtd_lancamentos
        FROM categorias c
        LEFT JOIN lancamentos l ON l.categoria_id = c.id
        GROUP BY c.id
        """
    ).fetchall()
    conn.close()
    return ordenar_categorias(categorias)


def tipo_confere_com_categoria(conn, categoria_id, tipo):
    """Regra de negócio: o tipo do lançamento deve ser igual ao tipo da categoria."""
    categoria = conn.execute(
        "SELECT tipo FROM categorias WHERE id = ?", (categoria_id,)
    ).fetchone()
    return categoria is not None and categoria["tipo"] == tipo


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

# Deixa os dicionários disponíveis em todos os templates
app.jinja_env.globals["FORMAS_PAGAMENTO"] = FORMAS_PAGAMENTO
app.jinja_env.globals["FORMAS_FORMULARIO"] = FORMAS_FORMULARIO


@app.template_filter("forma")
def forma(chave):
    """'debito' → 'Débito'."""
    return FORMAS_PAGAMENTO.get(chave, chave)


CAMPOS_LANCAMENTO = (
    "descricao", "valor", "tipo", "data", "categoria_id", "forma_pagamento", "observacao",
)


def ler_formulario_lancamento():
    """Lê os campos do formulário como textos. Se der erro, eles voltam para a tela."""
    return {campo: request.form.get(campo, "").strip() for campo in CAMPOS_LANCAMENTO}


def dados_do_lancamento(lancamento):
    """Converte uma linha do banco nos textos que o formulário espera (25050 → '250.50')."""
    return {
        "descricao": lancamento["descricao"],
        "valor": f"{lancamento['valor_centavos'] / 100:.2f}",
        "tipo": lancamento["tipo"],
        "data": lancamento["data"],
        "categoria_id": str(lancamento["categoria_id"]),
        "forma_pagamento": lancamento["forma_pagamento"],
        "observacao": lancamento["observacao"] or "",
    }


def para_centavos(valor_texto):
    """'250.50' ou '250,50' → 25050."""
    return round(float(valor_texto.replace(",", ".")) * 100)


def validar_lancamento(conn, dados):
    """Confere as regras de negócio. Devolve a mensagem de erro, ou None se estiver tudo certo."""
    if not dados["descricao"]:
        return "Informe a descrição."
    try:
        centavos = para_centavos(dados["valor"])
    except (ValueError, OverflowError):
        return "Informe um valor válido, por exemplo 250,50."
    if centavos <= 0:
        return "O valor deve ser maior que zero."
    if not dados["data"]:
        return "Informe a data."
    if dados["forma_pagamento"] not in FORMAS_FORMULARIO:
        return "Escolha a forma de pagamento."
    if not tipo_confere_com_categoria(conn, dados["categoria_id"], dados["tipo"]):
        return "O tipo do lançamento não corresponde ao tipo da categoria. Escolha uma categoria de " + (
            "receita." if dados["tipo"] == "receita" else "despesa."
        )
    return None


def periodo_mes_atual():
    """Devolve o primeiro e o último dia do mês atual, no formato AAAA-MM-DD."""
    hoje = date.today()
    ultimo_dia = calendar.monthrange(hoje.year, hoje.month)[1]  # 28, 29, 30 ou 31
    inicio = hoje.replace(day=1)
    fim = hoje.replace(day=ultimo_dia)
    return inicio.isoformat(), fim.isoformat()


@app.route("/")
def dashboard():
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

    conn.close()

    return render_template(
        "dashboard.html",
        inicio=inicio,
        fim=fim,
        receitas=totais["receitas"],
        despesas=totais["despesas"],
        saldo=totais["receitas"] - totais["despesas"],  # SALDO = RECEITAS − DESPESAS
        qtd=totais["qtd"],
        despesas_por_categoria=despesas_por_categoria,
        ultimos=ultimos,
    )


@app.route("/categorias")
def categorias():
    return render_template("categorias.html", categorias=buscar_categorias_com_uso())


@app.route("/categorias/nova", methods=["GET", "POST"])
def nova_categoria():
    if request.method == "POST":
        nome = request.form["nome"].strip()  # strip() tira espaços do começo e do fim
        tipo = request.form["tipo"]

        if not nome:
            return render_template(
                "nova_categoria.html", tipo=tipo, erro="Informe o nome da categoria."
            )
        if tipo not in ("receita", "despesa"):
            return render_template(
                "nova_categoria.html", nome=nome, erro="Escolha o tipo: receita ou despesa."
            )

        conn = get_db_connection()
        try:
            conn.execute("INSERT INTO categorias (nome, tipo) VALUES (?, ?)", (nome, tipo))
            conn.commit()
        except sqlite3.IntegrityError:
            # O UNIQUE (nome, tipo) do schema recusou: essa categoria já existe
            erro = f"Já existe uma categoria '{nome}' do tipo {tipo}. Use outro nome."
            return render_template("nova_categoria.html", nome=nome, tipo=tipo, erro=erro)
        finally:
            conn.close()  # o finally roda sempre: com ou sem erro

        return redirect(url_for("categorias"))

    return render_template("nova_categoria.html")


@app.route("/categorias/excluir/<int:categoria_id>", methods=["POST"])
def excluir_categoria(categoria_id):
    conn = get_db_connection()

    # Regra de negócio: categorias em uso não podem ser excluídas
    qtd = conn.execute(
        "SELECT COUNT(*) FROM lancamentos WHERE categoria_id = ?", (categoria_id,)
    ).fetchone()[0]

    if qtd > 0:
        conn.close()
        erro = f"Esta categoria não pode ser excluída: ela é usada em {qtd} lançamento(s)."
        return render_template(
            "categorias.html", categorias=buscar_categorias_com_uso(), erro=erro
        )

    try:
        conn.execute("DELETE FROM categorias WHERE id = ?", (categoria_id,))
        conn.commit()
    except sqlite3.IntegrityError:
        # Segunda garantia: o ON DELETE RESTRICT do banco também recusa
        erro = "Esta categoria não pode ser excluída: ela está em uso."
        return render_template(
            "categorias.html", categorias=buscar_categorias_com_uso(), erro=erro
        )
    finally:
        conn.close()

    return redirect(url_for("categorias"))


@app.route("/lancamentos")
def lancamentos():
    # Filtros vindos do formulário (GET). Campo vazio = sem filtro
    filtros = {
        "inicio": request.args.get("inicio", ""),
        "fim": request.args.get("fim", ""),
        "tipo": request.args.get("tipo", ""),
        "categoria_id": request.args.get("categoria_id", ""),
        "forma_pagamento": request.args.get("forma_pagamento", ""),
    }

    # Monta o WHERE aos poucos: só entram as condições que foram preenchidas.
    # Os VALORES continuam indo pelos "?" (nunca colados no texto do SQL)
    condicoes = []
    parametros = []
    if filtros["inicio"]:
        condicoes.append("l.data >= ?")
        parametros.append(filtros["inicio"])
    if filtros["fim"]:
        condicoes.append("l.data <= ?")
        parametros.append(filtros["fim"])
    if filtros["tipo"]:
        condicoes.append("l.tipo = ?")
        parametros.append(filtros["tipo"])
    if filtros["categoria_id"]:
        condicoes.append("l.categoria_id = ?")
        parametros.append(filtros["categoria_id"])
    if filtros["forma_pagamento"]:
        condicoes.append("l.forma_pagamento = ?")
        parametros.append(filtros["forma_pagamento"])

    where = ""
    if condicoes:
        where = "WHERE " + " AND ".join(condicoes)  # ["a", "b"] → "a AND b"

    conn = get_db_connection()
    lancamentos = conn.execute(
        f"""
        SELECT l.id, l.descricao, l.valor_centavos, l.tipo, l.data, l.forma_pagamento,
               l.data_compra, l.compra_id, l.parcela_numero, l.parcela_total,
               c.nome AS categoria, ca.nome AS cartao, ca.titular
        FROM lancamentos l
        JOIN categorias c ON c.id = l.categoria_id
        LEFT JOIN compras_cartao cc ON cc.id = l.compra_id      -- LEFT: nem todo lançamento é compra
        LEFT JOIN cartoes ca ON ca.id = cc.cartao_id
        {where}
        ORDER BY l.data DESC, l.id DESC
        """,
        parametros,
    ).fetchall()
    conn.close()

    # Totais do resultado filtrado (em centavos inteiros)
    total_receitas = sum(l["valor_centavos"] for l in lancamentos if l["tipo"] == "receita")
    total_despesas = sum(l["valor_centavos"] for l in lancamentos if l["tipo"] == "despesa")

    return render_template(
        "lancamentos.html",
        lancamentos=lancamentos,
        categorias=buscar_categorias(),
        filtros=filtros,
        filtrando=bool(condicoes),
        total_receitas=total_receitas,
        total_despesas=total_despesas,
    )


@app.route("/lancamentos/novo", methods=["GET", "POST"])
def novo_lancamento():
    # POST: o usuário clicou em "Salvar"
    if request.method == "POST":
        dados = ler_formulario_lancamento()

        conn = get_db_connection()
        erro = validar_lancamento(conn, dados)
        if erro:
            conn.close()
            # Mostra o formulário de novo, COM os dados digitados, para só corrigir o que falta
            return render_template(
                "novo_lancamento.html", dados=dados, categorias=buscar_categorias(), erro=erro
            )

        # Grava no banco. Os "?" protegem contra SQL Injection
        conn.execute(
            "INSERT INTO lancamentos "
            "(descricao, valor_centavos, tipo, data, categoria_id, forma_pagamento, observacao) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                dados["descricao"],
                para_centavos(dados["valor"]),
                dados["tipo"],
                dados["data"],  # já vem como AAAA-MM-DD
                dados["categoria_id"],
                dados["forma_pagamento"],
                dados["observacao"] or None,
            ),
        )
        conn.commit()  # confirma a gravação
        conn.close()

        # Manda o navegador para outra página (evita duplicar ao apertar F5)
        return redirect(url_for("lancamentos"))

    # GET: formulário vazio, já com a data de hoje e o tipo "despesa"
    dados = {"tipo": "despesa", "data": date.today().isoformat(), "forma_pagamento": "pix"}
    return render_template("novo_lancamento.html", dados=dados, categorias=buscar_categorias())


@app.route("/lancamentos/editar/<int:lancamento_id>", methods=["GET", "POST"])
def editar_lancamento(lancamento_id):
    conn = get_db_connection()
    lancamento = conn.execute(
        "SELECT * FROM lancamentos WHERE id = ?", (lancamento_id,)
    ).fetchone()

    # Se o id não existe (ex.: /lancamentos/editar/999), responde "Página não encontrada"
    if lancamento is None:
        conn.close()
        abort(404)

    # Parcela de compra no cartão: é editada pela compra, nunca sozinha (regra 6)
    if lancamento["compra_id"]:
        conn.close()
        return redirect(url_for("ver_compra", compra_id=lancamento["compra_id"]))

    # POST: o usuário clicou em "Salvar alterações"
    if request.method == "POST":
        dados = ler_formulario_lancamento()

        erro = validar_lancamento(conn, dados)
        if erro:
            conn.close()
            return render_template(
                "editar_lancamento.html",
                lancamento=lancamento,
                dados=dados,
                categorias=buscar_categorias(),
                erro=erro,
            )

        # Atualiza o lançamento. O WHERE garante que só ESTE lançamento muda
        conn.execute(
            """
            UPDATE lancamentos
               SET descricao = ?, valor_centavos = ?, tipo = ?, data = ?,
                   categoria_id = ?, forma_pagamento = ?, observacao = ?,
                   atualizado_em = CURRENT_TIMESTAMP
             WHERE id = ?
            """,
            (
                dados["descricao"],
                para_centavos(dados["valor"]),
                dados["tipo"],
                dados["data"],
                dados["categoria_id"],
                dados["forma_pagamento"],
                dados["observacao"] or None,
                lancamento_id,
            ),
        )
        conn.commit()
        conn.close()
        return redirect(url_for("lancamentos"))

    # GET: mostrar o formulário já preenchido com os dados atuais
    conn.close()
    return render_template(
        "editar_lancamento.html",
        lancamento=lancamento,
        dados=dados_do_lancamento(lancamento),
        categorias=buscar_categorias(),
    )


@app.route("/lancamentos/excluir/<int:lancamento_id>", methods=["POST"])
def excluir_lancamento(lancamento_id):
    conn = get_db_connection()
    lancamento = conn.execute(
        "SELECT compra_id FROM lancamentos WHERE id = ?", (lancamento_id,)
    ).fetchone()
    if lancamento and lancamento["compra_id"]:
        # Parcela de compra no cartão: exclui-se a compra inteira, na página da compra
        conn.close()
        return redirect(url_for("ver_compra", compra_id=lancamento["compra_id"]))

    conn.execute("DELETE FROM lancamentos WHERE id = ?", (lancamento_id,))  # o WHERE é essencial!
    conn.commit()
    conn.close()
    return redirect(url_for("lancamentos"))


# ---------- Cartões de crédito ----------

def ler_formulario_cartao():
    """Lê os campos do cartão como textos. Se der erro, eles voltam para a tela."""
    return {
        "nome": request.form.get("nome", "").strip(),
        "titular": request.form.get("titular", "").strip(),
        "dia_fechamento": request.form.get("dia_fechamento", "").strip(),
        "dia_vencimento": request.form.get("dia_vencimento", "").strip(),
        "limite": request.form.get("limite", "").strip(),
        "ativo": "1" if request.form.get("ativo") else "0",  # checkbox desmarcado não é enviado
    }


def dados_do_cartao(cartao):
    """Converte uma linha do banco nos textos que o formulário espera."""
    limite = cartao["limite_centavos"]
    return {
        "nome": cartao["nome"],
        "titular": cartao["titular"],
        "dia_fechamento": str(cartao["dia_fechamento"]),
        "dia_vencimento": str(cartao["dia_vencimento"]),
        "limite": f"{limite / 100:.2f}" if limite else "",
        "ativo": str(cartao["ativo"]),
    }


def validar_cartao(dados):
    """Devolve a mensagem de erro, ou None se estiver tudo certo."""
    if not dados["nome"]:
        return "Informe o nome do cartão."
    if not dados["titular"]:
        return "Informe o titular do cartão."
    for campo, rotulo in (("dia_fechamento", "fechamento"), ("dia_vencimento", "vencimento")):
        if not dados[campo].isdigit() or not 1 <= int(dados[campo]) <= 28:
            return f"O dia de {rotulo} deve ser um número de 1 a 28."
    if dados["limite"]:
        try:
            if para_centavos(dados["limite"]) <= 0:
                return "O limite deve ser maior que zero (ou deixe em branco)."
        except (ValueError, OverflowError):
            return "Informe um limite válido, por exemplo 5000,00 (ou deixe em branco)."
    return None


def valores_cartao(dados):
    """Os valores, já convertidos, na ordem das colunas do banco."""
    return (
        dados["nome"],
        dados["titular"],
        int(dados["dia_fechamento"]),
        int(dados["dia_vencimento"]),
        para_centavos(dados["limite"]) if dados["limite"] else None,
        int(dados["ativo"]),
    )


def cartao_repetido(dados):
    return f"{dados['titular']} já tem um cartão chamado '{dados['nome']}'. Use outro nome."


def buscar_titulares():
    """Os titulares já cadastrados, para sugerir no formulário (ex.: ['Érica', 'Heberton'])."""
    conn = get_db_connection()
    linhas = conn.execute("SELECT DISTINCT titular FROM cartoes").fetchall()
    conn.close()
    return sorted((linha["titular"] for linha in linhas), key=sem_acento)


def buscar_cartoes():
    """Todos os cartões: ativos primeiro, agrupados por titular (ordem sem acento: Érica antes de Heberton)."""
    conn = get_db_connection()
    lista = conn.execute("SELECT * FROM cartoes").fetchall()
    conn.close()
    return sorted(lista, key=lambda c: (-c["ativo"], sem_acento(c["titular"]), sem_acento(c["nome"])))


@app.route("/cartoes")
def cartoes():
    return render_template("cartoes.html", cartoes=buscar_cartoes())


@app.route("/cartoes/novo", methods=["GET", "POST"])
def novo_cartao():
    if request.method == "POST":
        dados = ler_formulario_cartao()
        dados["ativo"] = "1"  # cartão novo sempre começa ativo
        erro = validar_cartao(dados)
        if not erro:
            conn = get_db_connection()
            try:
                conn.execute(
                    "INSERT INTO cartoes "
                    "(nome, titular, dia_fechamento, dia_vencimento, limite_centavos, ativo) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    valores_cartao(dados),
                )
                conn.commit()
                return redirect(url_for("cartoes"))
            except sqlite3.IntegrityError:
                erro = cartao_repetido(dados)
            finally:
                conn.close()
        return render_template(
            "cartao_form.html", titulo="Novo cartão", dados=dados, erro=erro,
            titulares=buscar_titulares(),
        )

    return render_template(
        "cartao_form.html", titulo="Novo cartão", dados={"ativo": "1"},
        titulares=buscar_titulares(),
    )


@app.route("/cartoes/editar/<int:cartao_id>", methods=["GET", "POST"])
def editar_cartao(cartao_id):
    conn = get_db_connection()
    cartao = conn.execute("SELECT * FROM cartoes WHERE id = ?", (cartao_id,)).fetchone()
    if cartao is None:
        conn.close()
        abort(404)

    if request.method == "POST":
        dados = ler_formulario_cartao()
        erro = validar_cartao(dados)
        if not erro:
            try:
                conn.execute(
                    "UPDATE cartoes SET nome = ?, titular = ?, dia_fechamento = ?, "
                    "dia_vencimento = ?, limite_centavos = ?, ativo = ? WHERE id = ?",
                    (*valores_cartao(dados), cartao_id),  # * "espalha" a tupla dentro da outra
                )
                conn.commit()
                conn.close()
                return redirect(url_for("cartoes"))
            except sqlite3.IntegrityError:
                erro = cartao_repetido(dados)
        conn.close()
        return render_template(
            "cartao_form.html", titulo="Editar cartão", cartao=cartao, dados=dados, erro=erro,
            titulares=buscar_titulares(),
        )

    conn.close()
    return render_template(
        "cartao_form.html", titulo="Editar cartão", cartao=cartao,
        dados=dados_do_cartao(cartao), titulares=buscar_titulares(),
    )


@app.route("/cartoes/excluir/<int:cartao_id>", methods=["POST"])
def excluir_cartao(cartao_id):
    conn = get_db_connection()
    try:
        conn.execute("DELETE FROM cartoes WHERE id = ?", (cartao_id,))
        conn.commit()
    except sqlite3.IntegrityError:
        # A partir da Etapa 12, o ON DELETE RESTRICT das compras impede excluir cartão usado
        erro = "Este cartão tem compras e não pode ser excluído. Desative-o em Editar."
        return render_template("cartoes.html", cartoes=buscar_cartoes(), erro=erro)
    finally:
        conn.close()
    return redirect(url_for("cartoes"))


# ---------- Compras no cartão de crédito ----------

CAMPOS_COMPRA = ("cartao_id", "descricao", "valor", "parcelas", "data_compra", "categoria_id", "observacao")


def ler_formulario_compra():
    return {campo: request.form.get(campo, "").strip() for campo in CAMPOS_COMPRA}


def dados_da_compra(compra):
    """Converte uma compra do banco nos textos que o formulário espera."""
    return {
        "cartao_id": str(compra["cartao_id"]),
        "descricao": compra["descricao"],
        "valor": f"{compra['valor_total_centavos'] / 100:.2f}",
        "parcelas": str(compra["parcelas"]),
        "data_compra": compra["data_compra"],
        "categoria_id": str(compra["categoria_id"]),
        "observacao": compra["observacao"] or "",
    }


def cartoes_para_compra(cartao_atual_id=None):
    """Cartões ativos (e o cartão atual da compra, mesmo se já foi desativado)."""
    return [
        c for c in buscar_cartoes()
        if c["ativo"] or str(c["id"]) == str(cartao_atual_id)
    ]


def categorias_de_despesa():
    return [c for c in buscar_categorias() if c["tipo"] == "despesa"]


def validar_compra(conn, dados, cartao_atual_id=None):
    """Devolve (erro, cartao). O cartão é usado depois para calcular as faturas."""
    cartao = conn.execute(
        "SELECT * FROM cartoes WHERE id = ?", (dados["cartao_id"],)
    ).fetchone()
    if cartao is None:
        return "Escolha o cartão.", None
    if not cartao["ativo"] and str(cartao["id"]) != str(cartao_atual_id):
        return "Este cartão está inativo. Escolha outro cartão.", None
    if not dados["descricao"]:
        return "Informe a descrição.", None
    try:
        total = para_centavos(dados["valor"])
    except (ValueError, OverflowError):
        return "Informe um valor válido, por exemplo 1200,00.", None
    if total <= 0:
        return "O valor deve ser maior que zero.", None
    if not dados["parcelas"].isdigit() or not 1 <= int(dados["parcelas"]) <= 24:
        return "O número de parcelas deve ser de 1 a 24.", None
    if total < int(dados["parcelas"]):
        return "Valor pequeno demais para tantas parcelas (cada parcela precisa de pelo menos R$ 0,01).", None
    try:
        date.fromisoformat(dados["data_compra"])
    except ValueError:
        return "Informe a data da compra.", None
    if not tipo_confere_com_categoria(conn, dados["categoria_id"], "despesa"):
        return "Escolha uma categoria de despesa.", None
    return None, cartao


def gravar_parcelas(conn, compra_id, dados, cartao):
    """Cria um lançamento para cada parcela, cada um na sua fatura."""
    total = para_centavos(dados["valor"])
    quantidade = int(dados["parcelas"])
    data_compra = date.fromisoformat(dados["data_compra"])
    parcelas = gerar_parcelas(
        total, quantidade, data_compra, cartao["dia_fechamento"], cartao["dia_vencimento"]
    )
    for numero, valor, vencimento in parcelas:
        conn.execute(
            """
            INSERT INTO lancamentos
                (descricao, valor_centavos, tipo, data, categoria_id, forma_pagamento, observacao,
                 data_compra, compra_id, parcela_numero, parcela_total)
            VALUES (?, ?, 'despesa', ?, ?, 'credito', ?, ?, ?, ?, ?)
            """,
            (
                dados["descricao"], valor, vencimento.isoformat(), dados["categoria_id"],
                dados["observacao"] or None, dados["data_compra"],
                compra_id, numero, quantidade,
            ),
        )


def form_compra(titulo, dados, erro=None, compra=None):
    return render_template(
        "compra_form.html",
        titulo=titulo,
        dados=dados,
        erro=erro,
        compra=compra,
        cartoes=cartoes_para_compra(compra["cartao_id"] if compra else None),
        categorias=categorias_de_despesa(),
    )


@app.route("/compras/nova", methods=["GET", "POST"])
def nova_compra():
    if request.method == "POST":
        dados = ler_formulario_compra()
        conn = get_db_connection()
        erro, cartao = validar_compra(conn, dados)
        if erro:
            conn.close()
            return form_compra("Compra no cartão", dados, erro)

        # "with conn:" = transação: a compra e TODAS as parcelas são gravadas juntas,
        # ou nada é gravado (se der erro no meio, o Python desfaz tudo sozinho)
        with conn:
            cursor = conn.execute(
                """
                INSERT INTO compras_cartao
                    (cartao_id, descricao, valor_total_centavos, parcelas, data_compra,
                     categoria_id, observacao)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    cartao["id"], dados["descricao"], para_centavos(dados["valor"]),
                    int(dados["parcelas"]), dados["data_compra"], dados["categoria_id"],
                    dados["observacao"] or None,
                ),
            )
            compra_id = cursor.lastrowid   # o id que o banco acabou de gerar para a compra
            gravar_parcelas(conn, compra_id, dados, cartao)
        conn.close()
        return redirect(url_for("ver_compra", compra_id=compra_id))

    # GET: cartão pré-escolhido se veio da página de cartões (?cartao_id=...)
    dados = {
        "data_compra": date.today().isoformat(),
        "parcelas": "1",
        "cartao_id": request.args.get("cartao_id", ""),
    }
    return form_compra("Compra no cartão", dados)


def buscar_compra(conn, compra_id):
    compra = conn.execute(
        """
        SELECT cc.*, ca.nome AS cartao, ca.titular, c.nome AS categoria
        FROM compras_cartao cc
        JOIN cartoes ca ON ca.id = cc.cartao_id
        JOIN categorias c ON c.id = cc.categoria_id
        WHERE cc.id = ?
        """,
        (compra_id,),
    ).fetchone()
    if compra is None:
        conn.close()
        abort(404)
    return compra


@app.route("/compras/<int:compra_id>")
def ver_compra(compra_id):
    conn = get_db_connection()
    compra = buscar_compra(conn, compra_id)
    parcelas = conn.execute(
        "SELECT * FROM lancamentos WHERE compra_id = ? ORDER BY parcela_numero", (compra_id,)
    ).fetchall()
    conn.close()
    return render_template("compra_detalhe.html", compra=compra, parcelas=parcelas)


@app.route("/compras/editar/<int:compra_id>", methods=["GET", "POST"])
def editar_compra(compra_id):
    conn = get_db_connection()
    compra = buscar_compra(conn, compra_id)

    if request.method == "POST":
        dados = ler_formulario_compra()
        erro, cartao = validar_compra(conn, dados, cartao_atual_id=compra["cartao_id"])
        if erro:
            conn.close()
            return form_compra("Editar compra", dados, erro, compra)

        with conn:   # transação: atualiza a compra e recria as parcelas, tudo ou nada
            conn.execute(
                """
                UPDATE compras_cartao
                   SET cartao_id = ?, descricao = ?, valor_total_centavos = ?, parcelas = ?,
                       data_compra = ?, categoria_id = ?, observacao = ?
                 WHERE id = ?
                """,
                (
                    cartao["id"], dados["descricao"], para_centavos(dados["valor"]),
                    int(dados["parcelas"]), dados["data_compra"], dados["categoria_id"],
                    dados["observacao"] or None, compra_id,
                ),
            )
            conn.execute("DELETE FROM lancamentos WHERE compra_id = ?", (compra_id,))
            gravar_parcelas(conn, compra_id, dados, cartao)
        conn.close()
        return redirect(url_for("ver_compra", compra_id=compra_id))

    conn.close()
    return form_compra("Editar compra", dados_da_compra(compra), compra=compra)


@app.route("/compras/excluir/<int:compra_id>", methods=["POST"])
def excluir_compra(compra_id):
    conn = get_db_connection()
    # ON DELETE CASCADE: apagar a compra apaga todas as parcelas dela
    conn.execute("DELETE FROM compras_cartao WHERE id = ?", (compra_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("lancamentos"))


if __name__ == "__main__":
    app.run(debug=True)
