import sqlite3

from flask import Flask, render_template, request, redirect, url_for, abort  # traz a classe Flask do pacote flask
from db import get_db_connection

app = Flask(__name__)   # cria a aplicação (o "servidor")


@app.template_filter("moeda")
def moeda(centavos):
    """Converte centavos em texto no formato brasileiro: 25050 → 'R$ 250,50'."""
    texto = f"{centavos / 100:,.2f}"                    # 25050 → '250.50' / 123456 → '1,234.56'
    texto = texto.replace(",", "X").replace(".", ",").replace("X", ".")  # troca , e .
    return f"R$ {texto}"


@app.template_filter("data_br")
def data_br(data_iso):
    """Converte '2026-10-09' em '09/10/2026'."""
    ano, mes, dia = data_iso.split("-")
    return f"{dia}/{mes}/{ano}"


def buscar_categorias():
    """Devolve todas as categorias, ordenadas por tipo e nome."""
    conn = get_db_connection()
    categorias = conn.execute(
        "SELECT id, nome, tipo FROM categorias ORDER BY tipo, nome"
    ).fetchall()
    conn.close()
    return categorias


def buscar_categorias_com_uso():
    """Devolve as categorias com a quantidade de lançamentos que usam cada uma."""
    conn = get_db_connection()
    categorias = conn.execute(
        """
        SELECT c.id, c.nome, c.tipo, COUNT(l.id) AS qtd_lancamentos
        FROM categorias c
        LEFT JOIN lancamentos l ON l.categoria_id = c.id
        GROUP BY c.id
        ORDER BY c.tipo, c.nome
        """
    ).fetchall()
    conn.close()
    return categorias


def tipo_confere_com_categoria(conn, categoria_id, tipo):
    """Regra de negócio: o tipo do lançamento deve ser igual ao tipo da categoria."""
    categoria = conn.execute(
        "SELECT tipo FROM categorias WHERE id = ?", (categoria_id,)
    ).fetchone()
    return categoria is not None and categoria["tipo"] == tipo


@app.route("/")   # quando acessarem o endereço "/"...
def dashboard():  # ...o Flask executa esta função...
    return render_template("dashboard.html")  # ..e devolve a página montada pelo template


@app.route("/categorias")
def categorias():
    return render_template("categorias.html", categorias=buscar_categorias_com_uso())


@app.route("/categorias/nova", methods=["GET", "POST"])
def nova_categoria():
    if request.method == "POST":
        nome = request.form["nome"].strip()  # strip() tira espaços do começo e do fim
        tipo = request.form["tipo"]

        if not nome:
            return render_template("nova_categoria.html", erro="Informe o nome da categoria.")
        if tipo not in ("receita", "despesa"):
            return render_template("nova_categoria.html", erro="Tipo inválido.")

        conn = get_db_connection()
        try:
            conn.execute("INSERT INTO categorias (nome, tipo) VALUES (?, ?)", (nome, tipo))
            conn.commit()
        except sqlite3.IntegrityError:
            # O UNIQUE (nome, tipo) do schema recusou: essa categoria já existe
            erro = f"Já existe uma categoria '{nome}' do tipo {tipo}."
            return render_template("nova_categoria.html", erro=erro)
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
    conn = get_db_connection()
    lancamentos = conn.execute(
        """
        SELECT l.id, l.descricao, l.valor_centavos, l.tipo, l.data, c.nome AS categoria
        FROM lancamentos l
        JOIN categorias c ON c.id = l.categoria_id
        ORDER BY l.data DESC, l.id DESC
        """
    ).fetchall()
    conn.close()
    return render_template("lancamentos.html", lancamentos=lancamentos)


@app.route("/lancamentos/novo", methods=["GET", "POST"])
def novo_lancamento():
    # POST: o usuário clicou em "Salvar"
    if request.method == "POST":
        # Lê os campos do formulário (pelo "name" de cada campo no HTML)
        descricao = request.form["descricao"]
        valor_centavos = round(float(request.form["valor"]) * 100)  # "19.99" → 1999
        tipo = request.form["tipo"]
        data = request.form["data"]  # já vem como AAAA-MM-DD
        categoria_id = request.form["categoria_id"]
        observacao = request.form["observacao"]

        conn = get_db_connection()

        if not tipo_confere_com_categoria(conn, categoria_id, tipo):
            conn.close()
            erro = "O tipo do lançamento não corresponde ao tipo da categoria."
            return render_template(
                "novo_lancamento.html", categorias=buscar_categorias(), erro=erro
            )

        # Grava no banco. Os "?" protegem contra SQL Injection
        conn.execute(
            "INSERT INTO lancamentos (descricao, valor_centavos, tipo, data, categoria_id, observacao) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (descricao, valor_centavos, tipo, data, categoria_id, observacao),
        )
        conn.commit()  # confirma a gravação
        conn.close()

        # Manda o navegador para outra página (evita duplicar ao apertar F5)
        return redirect(url_for("lancamentos"))

    # GET: mostrar o formulário vazio
    return render_template("novo_lancamento.html", categorias=buscar_categorias())


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
        descricao = request.form["descricao"]
        valor_centavos = round(float(request.form["valor"]) * 100)
        tipo = request.form["tipo"]
        data = request.form["data"]
        categoria_id = request.form["categoria_id"]
        observacao = request.form["observacao"]

        if not tipo_confere_com_categoria(conn, categoria_id, tipo):
            conn.close()
            erro = "O tipo do lançamento não corresponde ao tipo da categoria."
            return render_template(
                "editar_lancamento.html",
                lancamento=lancamento,
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
            (descricao, valor_centavos, tipo, data, categoria_id, observacao, lancamento_id),
        )
        conn.commit()
        conn.close()
        return redirect(url_for("lancamentos"))

    # GET: mostrar o formulário já preenchido com os dados atuais
    conn.close()
    return render_template(
        "editar_lancamento.html", lancamento=lancamento, categorias=buscar_categorias()
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
