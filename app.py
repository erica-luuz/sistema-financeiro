from flask import Flask, render_template, request, redirect, url_for  # traz a classe Flask do pacote flask
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


@app.route("/")   # quando acessarem o endereço "/"...
def dashboard():  # ...o Flask executa esta função...
    return render_template("dashboard.html")  # ..e devolve a página montada pelo template


@app.route("/categorias")
def categorias():
    return render_template("categorias.html", categorias=buscar_categorias())


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

        # Regra de negócio: o tipo do lançamento deve ser igual ao tipo da categoria
        categoria = conn.execute(
            "SELECT tipo FROM categorias WHERE id = ?", (categoria_id,)
        ).fetchone()

        if categoria is None or categoria["tipo"] != tipo:
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


if __name__ == "__main__":
    app.run(debug=True)
