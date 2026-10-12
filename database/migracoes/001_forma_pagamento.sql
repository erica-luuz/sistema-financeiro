-- Migração 001: forma de pagamento nos lançamentos (Versão 2, seção 4)
-- Os lançamentos que já existem recebem 'pix' (podem ser editados depois).

ALTER TABLE lancamentos ADD COLUMN forma_pagamento TEXT NOT NULL DEFAULT 'pix'
    CHECK (forma_pagamento IN ('pix', 'debito', 'credito', 'dinheiro', 'boleto', 'transferencia'));
