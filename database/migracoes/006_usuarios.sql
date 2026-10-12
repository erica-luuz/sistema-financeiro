-- Migração 006: usuários do sistema (Versão 3, seção 4)
-- A senha NUNCA é guardada: só o hash dela (uma "impressão digital" de mão única).

CREATE TABLE usuarios (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    nome               TEXT    NOT NULL,          -- "Érica", "Heberton" (aparece no menu)
    login              TEXT    NOT NULL UNIQUE,   -- "erica", "heberton" (minúsculo, sem espaço)
    senha_hash         TEXT    NOT NULL,
    tentativas_erradas INTEGER NOT NULL DEFAULT 0,  -- usado na Etapa 20 (bloqueio)
    bloqueado_ate      TEXT,                        -- usado na Etapa 20 (bloqueio)
    criado_em          TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP
);
