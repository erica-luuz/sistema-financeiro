import calendar
import sqlite3
import unicodedata
from datetime import date

from flask import Flask, render_template, request, redirect, url_for, abort  # traz a classe Flask do pacote flask
from db import get_db_connection

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


CAMPOS_LANCAMENTO = ("descricao", "valor", "tipo", "data", "categoria_id", "observacao")


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
        SELECT l.descricao, l.valor_centavos, l.tipo, l.data, c.nome AS categoria
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

    where = ""
    if condicoes:
        where = "WHERE " + " AND ".join(condicoes)  # ["a", "b"] → "a AND b"

    conn = get_db_connection()
    lancamentos = conn.execute(
        f"""
        SELECT l.id, l.descricao, l.valor_centavos, l.tipo, l.data, c.nome AS categoria
        FROM lancamentos l
        JOIN categorias c ON c.id = l.categoria_id
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
            "INSERT INTO lancamentos (descricao, valor_centavos, tipo, data, categoria_id, observacao) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                dados["descricao"],
                para_centavos(dados["valor"]),
                dados["tipo"],
                dados["data"],  # já vem como AAAA-MM-DD
                dados["categoria_id"],
                dados["observacao"] or None,
            ),
        )
        conn.commit()  # confirma a gravação
        conn.close()

        # Manda o navegador para outra página (evita duplicar ao apertar F5)
        return redirect(url_for("lancamentos"))

    # GET: formulário vazio, já com a data de hoje e o tipo "despesa"
    dados = {"tipo": "despesa", "data": date.today().isoformat()}
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
                   categoria_id = ?, observacao = ?,
                   atualizado_em = CURRENT_TIMESTAMP
             WHERE id = ?
            """,
            (
                dados["descricao"],
                para_centavos(dados["valor"]),
                dados["tipo"],
                dados["data"],
                dados["categoria_id"],
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
    conn.execute("DELETE FROM lancamentos WHERE id = ?", (lancamento_id,))  # o WHERE é essencial!
    conn.commit()
    conn.close()
    return redirect(url_for("lancamentos"))


if __name__ == "__main__":
    app.run(debug=True)
