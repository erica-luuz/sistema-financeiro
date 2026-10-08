from flask import Flask, render_template   # traz a classe Flask do pacote flask
from db import get_db_connection

app = Flask(__name__)   # cria a aplicação (o "servidor")

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

if __name__ == "__main__":
    app.run(debug=True)
