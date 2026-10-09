-- Cada pergunta feita ao bot vira uma linha. Serve para medir custo, qualidade (feedback)
-- e descobrir o que falta na FAQ (perguntas não respondidas).
CREATE TABLE IF NOT EXISTS interacoes (
    id              BIGSERIAL PRIMARY KEY,
    -- HMAC do ID do Discord: dá para agrupar por usuário sem guardar quem ele é (LGPD)
    usuario_hash    TEXT        NOT NULL,
    pergunta        TEXT        NOT NULL,
    resposta        TEXT        NOT NULL,
    respondida      BOOLEAN     NOT NULL,
    trechos_usados  TEXT[]      NOT NULL DEFAULT '{}',
    util            BOOLEAN,    -- NULL = aluno não clicou no feedback
    tokens_entrada  INTEGER     NOT NULL DEFAULT 0,
    tokens_saida    INTEGER     NOT NULL DEFAULT 0,
    custo_usd       NUMERIC(12, 6) NOT NULL DEFAULT 0,
    modelo          TEXT        NOT NULL,
    criado_em       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_interacoes_criado_em ON interacoes (criado_em);
CREATE INDEX IF NOT EXISTS ix_interacoes_nao_respondidas
    ON interacoes (criado_em) WHERE NOT respondida;

