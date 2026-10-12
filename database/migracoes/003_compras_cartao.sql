-- Migração 003: compras no cartão de crédito e parcelas (Versão 2, seções 5.3 e 5.4)
-- Uma compra fica em compras_cartao; cada parcela vira um lançamento ligado a ela.

CREATE TABLE compras_cartao (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    cartao_id            INTEGER NOT NULL REFERENCES cartoes(id) ON DELETE RESTRICT,
    descricao            TEXT    NOT NULL,
    valor_total_centavos INTEGER NOT NULL CHECK (valor_total_centavos > 0),
    parcelas             INTEGER NOT NULL CHECK (parcelas BETWEEN 1 AND 24),
    data_compra          TEXT    NOT NULL,   -- AAAA-MM-DD
    categoria_id         INTEGER NOT NULL REFERENCES categorias(id) ON DELETE RESTRICT,
    observacao           TEXT,
    criado_em            TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- No crédito: "data" = vencimento da fatura; "data_compra" = dia em que a compra foi feita
ALTER TABLE lancamentos ADD COLUMN data_compra TEXT;
-- Excluir a compra apaga as parcelas (CASCADE)
ALTER TABLE lancamentos ADD COLUMN compra_id INTEGER REFERENCES compras_cartao(id) ON DELETE CASCADE;
ALTER TABLE lancamentos ADD COLUMN parcela_numero INTEGER;
ALTER TABLE lancamentos ADD COLUMN parcela_total INTEGER;

-- Índice: deixa rápido buscar as parcelas de uma compra
CREATE INDEX idx_lancamentos_compra ON lancamentos (compra_id);
