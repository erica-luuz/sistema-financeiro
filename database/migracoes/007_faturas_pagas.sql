-- Migração 007: marcar faturas do cartão como pagas
-- Uma fatura é identificada pelo cartão + data de vencimento (todas as parcelas dela vencem nesse dia).

CREATE TABLE faturas_pagas (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    cartao_id  INTEGER NOT NULL REFERENCES cartoes(id) ON DELETE CASCADE,
    vencimento TEXT    NOT NULL,                              -- AAAA-MM-DD
    pago_em    TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (cartao_id, vencimento)                            -- cada fatura só pode ser paga uma vez
);
