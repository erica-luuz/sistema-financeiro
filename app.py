from flask import Flask    # traz a classe Flask do pacote flask

app = Flask(__name__)   # cria a aplicação (o "servidor")

@app.route("/")   # quando acessarem o endereço "/"...
def dashboard():  # ...o Flask executa esta função...
    return "Finanças da casa"   # ...e devolve este texto ao navegador


if __name__ == "__main__":
    app.run(debug=True)
