-- Migração 002: cadastro de cartões de crédito (Versão 2, seção 5.1)
-- Cada cartão tem um titular (quem da casa é dono do cartão).
-- Os dias vão só até 28 porque todo mês tem dia 28.

CREATE TABLE cartoes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    nome            TEXT    NOT NULL,
    titular         TEXT    NOT NULL,
    dia_fechamento  INTEGER NOT NULL CHECK (dia_fechamento BETWEEN 1 AND 28),
    dia_vencimento  INTEGER NOT NULL CHECK (dia_vencimento BETWEEN 1 AND 28),
    limite_centavos INTEGER CHECK (limite_centavos IS NULL OR limite_centavos > 0),
    ativo           INTEGER NOT NULL DEFAULT 1 CHECK (ativo IN (0, 1)),
    UNIQUE (nome, titular)   -- duas pessoas podem ter um "Nubank" cada
);
