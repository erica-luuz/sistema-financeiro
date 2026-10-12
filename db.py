import sqlite3
from pathlib import Path

import relogio

CAMINHO_BANCO = "database.db"
CAMINHO_SCHEMA = Path("database/schema.sql")
PASTA_MIGRACOES = Path("database/migracoes")
PASTA_BACKUPS = Path("backups")


def get_db_connection():
    conn = sqlite3.connect(CAMINHO_BANCO)
    conn.row_factory = sqlite3.Row    # acessar colunas pelo nome: linha["descricao"]
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def fazer_backup():
    """Copia o banco para backups/database_AAAA-MM-DD_HHMMSS.db e devolve o caminho da cópia."""
    if not Path(CAMINHO_BANCO).exists():
        return None
    PASTA_BACKUPS.mkdir(exist_ok=True)
    destino = PASTA_BACKUPS / f"database_{relogio.agora():%Y-%m-%d_%H%M%S}.db"

    # A função backup() do sqlite3 copia o banco com segurança, mesmo se ele estiver em uso
    origem = sqlite3.connect(CAMINHO_BANCO)
    copia = sqlite3.connect(destino)
    origem.backup(copia)
    copia.close()
    origem.close()
    return destino


def listar_migracoes():
    """Devolve [(1, caminho), (2, caminho), ...] a partir dos arquivos 001_nome.sql, 002_nome.sql..."""
    migracoes = []
    for arquivo in PASTA_MIGRACOES.glob("*.sql"):
        numero = int(arquivo.name.split("_")[0])  # "001_forma_pagamento.sql" → 1
        migracoes.append((numero, arquivo))
    return sorted(migracoes)


def aplicar_migracoes(conn):
    """Roda, em ordem, as migrações que o banco ainda não recebeu. Devolve as que foram aplicadas."""
    # user_version: um número guardado dentro do próprio arquivo do banco (começa em 0)
    versao_atual = conn.execute("PRAGMA user_version").fetchone()[0]
    pendentes = [(numero, arquivo) for numero, arquivo in listar_migracoes() if numero > versao_atual]

    for numero, arquivo in pendentes:
        sql = arquivo.read_text(encoding="utf-8")
        try:
            # Tudo dentro de uma transação: ou a migração inteira funciona, ou nada muda
            conn.executescript(f"BEGIN;\n{sql}\nPRAGMA user_version = {numero};\nCOMMIT;")
        except sqlite3.Error:
            conn.rollback()
            raise
    return pendentes


def init_db():
    """Cria as tabelas do MVP (se não existirem) e aplica as migrações pendentes."""
    conn = get_db_connection()

    # 1. Estrutura do MVP: idempotente (IF NOT EXISTS / INSERT OR IGNORE)
    conn.executescript(CAMINHO_SCHEMA.read_text(encoding="utf-8"))
    conn.commit()

    # 2. Migrações: só as que faltam, com backup antes
    versao_atual = conn.execute("PRAGMA user_version").fetchone()[0]
    tem_pendentes = any(numero > versao_atual for numero, _ in listar_migracoes())
    backup = fazer_backup() if tem_pendentes else None
    aplicadas = aplicar_migracoes(conn)
    versao_final = conn.execute("PRAGMA user_version").fetchone()[0]
    conn.close()

    return backup, aplicadas, versao_final


if __name__ == "__main__":
    backup, aplicadas, versao = init_db()
    if backup:
        print(f"Backup criado: {backup}")
    for numero, arquivo in aplicadas:
        print(f"Migração aplicada: {arquivo.name}")
    if not aplicadas:
        print("Nenhuma migração pendente.")
    print(f"Banco de dados pronto (versão {versao}).")
