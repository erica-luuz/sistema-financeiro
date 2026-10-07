import sqlite3

def get_db_connection():
    conn = sqlite3.connect("database.db")
    conn.row_factory = sqlite3.Row    # acessar colunas pelo nome: linha["descricao"]
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

    
def init_db():
    conn = get_db_connection()           # 1. pegar a conexão
    with open("database/schema.sql", encoding="utf-8") as arquivo:   # 2. abrir o schema
        sql = arquivo.read()               # 3. ler o conteudo

    conn.executescript(sql)    # 4. executar o SQL lido
    conn.commit()          # 5. confirmar
    conn.close()           # 6. fechar


if __name__ == "__main__":
    init_db()
    print("Banco de dados criado com sucesso!")