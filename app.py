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


@app.route("/")   # quando acessarem o endereço "/"...
def dashboard():  # ...o Flask executa esta função...
    return render_template("dashboard.html")  # ..e devolve a página montada pelo template


@app.route("/categorias")
def categorias():                                            # nome da função = nome da página
    conn = get_db_connection()
    categorias = conn.execute(
        "SELECT id, nome, tipo FROM categorias ORDER BY tipo, nome"   # ordenar por tipo e depois por nome
    ).fetchall()
    conn.close()                                        # fechar a conexão
    return render_template("categorias.html", categorias=categorias)          # mas agora a rota devolve uma página montada a partir de um template

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
    # POST: o usuário clicou em "Salvar" → gravar no banco
    if request.method == "POST":
        # Lê os campos do formulário (pelo "name" de cada campo no HTML)
        descricao = request.form["descricao"]
        valor_centavos = round(float(request.form["valor"]) * 100)  # "19.99" → 1999
        tipo = request.form["tipo"]
        data = request.form["data"]  # já vem como AAAA-MM-DD
        categoria_id = request.form["categoria_id"]
        observacao = request.form["observacao"]

        # Grava no banco. Os "?" protegem contra SQL Injection
        conn = get_db_connection()
        conn.execute(
            "INSERT INTO lancamentos (descricao, valor_centavos, tipo, data, categoria_id, observacao) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (descricao, valor_centavos, tipo, data, categoria_id, observacao),
        )
        conn.commit()  # confirma a gravação
        conn.close()

        # Manda o navegador para outra página (evita duplicar ao apertar F5)
        return redirect(url_for("lancamentos"))

    # GET: mostrar o formulário vazio, com as categorias do banco
    conn = get_db_connection()
    categorias = conn.execute(
        "SELECT id, nome, tipo FROM categorias ORDER BY tipo, nome"
    ).fetchall()
    conn.close()
    return render_template("novo_lancamento.html", categorias=categorias)



if __name__ == "__main__":
    app.run(debug=True)
