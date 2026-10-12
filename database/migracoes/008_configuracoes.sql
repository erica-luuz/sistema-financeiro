-- Migração 008: configurações gerais do sistema (chave → valor)
-- Primeiro uso: o saldo inicial da conta da casa, para calcular "quanto temos" (saldo acumulado).
--   saldo_inicial_centavos  → ex.: '350000' (R$ 3.500,00; pode ser negativo)
--   saldo_inicial_data      → ex.: '2026-10-01' (o saldo é o do começo desse dia)

CREATE TABLE configuracoes (
    chave TEXT PRIMARY KEY,
    valor TEXT NOT NULL
);
