-- Migração 004: contas recorrentes (Versão 2, seção 6)
-- Aluguel, internet, assinaturas, salário... cadastrados uma vez; os lançamentos são gerados mês a mês.

CREATE TABLE recorrencias (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    descricao       TEXT    NOT NULL,
    valor_centavos  INTEGER NOT NULL CHECK (valor_centavos > 0),
    tipo            TEXT    NOT NULL CHECK (tipo IN ('receita', 'despesa')),
    categoria_id    INTEGER NOT NULL REFERENCES categorias(id) ON DELETE RESTRICT,
    forma_pagamento TEXT    NOT NULL
        CHECK (forma_pagamento IN ('pix', 'debito', 'credito', 'dinheiro', 'boleto', 'transferencia')),
    cartao_id       INTEGER REFERENCES cartoes(id) ON DELETE RESTRICT,   -- só quando é no crédito
    dia_do_mes      INTEGER NOT NULL CHECK (dia_do_mes BETWEEN 1 AND 28),
    mes_inicio      TEXT    NOT NULL,   -- AAAA-MM
    mes_fim         TEXT,               -- AAAA-MM ou NULL (sem data para acabar)
    ativa           INTEGER NOT NULL DEFAULT 1 CHECK (ativa IN (0, 1))
);

-- Excluir uma recorrência NÃO apaga os lançamentos que ela já gerou (só desfaz a ligação)
ALTER TABLE lancamentos ADD COLUMN recorrencia_id INTEGER REFERENCES recorrencias(id) ON DELETE SET NULL;
ALTER TABLE lancamentos ADD COLUMN mes_referencia TEXT;   -- AAAA-MM: de qual mês é esta conta

-- Garante no máximo UM lançamento por recorrência por mês (gerar duas vezes não duplica)
CREATE UNIQUE INDEX idx_lancamento_recorrencia_mes ON lancamentos (recorrencia_id, mes_referencia);
