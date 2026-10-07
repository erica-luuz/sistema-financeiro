CREATE TABLE IF NOT EXISTS categorias (
    id    INTEGER  PRIMARY KEY AUTOINCREMENT,
    nome  TEXT     NOT NULL,
    tipo  TEXT     NOT NULL CHECK (tipo IN ('receita', 'despesa')),
    UNIQUE (nome, tipo)
);

CREATE TABLE IF NOT EXISTS lancamentos (
    id              INTEGER       PRIMARY KEY AUTOINCREMENT,
    descricao       TEXT          NOT NULL,
    valor_centavos  INTEGER       NOT NULL CHECK (valor_centavos > 0),
    tipo            TEXT          NOT NULL CHECK (tipo IN ('receita', 'despesa')),
    data            TEXT          NOT NULL,      -- formato AAAA-MM-DD
    categoria_id    INTEGER       NOT NULL,
    observacao      TEXT,
    criado_em       TEXT          NOT NULL  DEFAULT CURRENT_TIMESTAMP,
    atualizado_em   TEXT          NOT NULL  DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY   (categoria_id) REFERENCES categorias(id) ON DELETE RESTRICT
);