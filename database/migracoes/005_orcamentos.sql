-- Migração 005: orçamento mensal por categoria (Versão 2, seção 7)
-- Quanto se pretende gastar em cada categoria de despesa, em cada mês.

CREATE TABLE orcamentos (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    categoria_id   INTEGER NOT NULL REFERENCES categorias(id) ON DELETE CASCADE,
    mes            TEXT    NOT NULL,   -- AAAA-MM
    valor_centavos INTEGER NOT NULL CHECK (valor_centavos > 0),
    UNIQUE (categoria_id, mes)         -- um valor por categoria por mês
);
