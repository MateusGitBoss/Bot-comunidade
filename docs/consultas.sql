-- Consultas para acompanhar o bot. Rodar no SQL Editor do Supabase ou no psql.

-- 1. Custo e qualidade por dia
SELECT date_trunc('day', criado_em)::date               AS dia,
       count(*)                                         AS perguntas,
       round(100.0 * count(*) FILTER (WHERE respondida) / count(*), 1) AS pct_respondidas,
       count(*) FILTER (WHERE util)                     AS uteis,
       count(*) FILTER (WHERE util = false)             AS nao_uteis,
       round(sum(custo_usd), 4)                         AS custo_usd
FROM interacoes
GROUP BY 1
ORDER BY 1 DESC;

-- 2. O que falta na FAQ: perguntas que a base não cobriu nos últimos 7 dias
SELECT criado_em, pergunta
FROM interacoes
WHERE NOT respondida AND criado_em >= now() - interval '7 days'
ORDER BY criado_em DESC;

-- 3. Trechos que mais geraram resposta ruim (candidatos a reescrever)
SELECT trecho, count(*) AS vezes
FROM interacoes, unnest(trechos_usados) AS trecho
WHERE util = false
GROUP BY trecho
ORDER BY vezes DESC
LIMIT 10;

-- 4. Usuários que mais perguntam (hash, não o ID real)
SELECT left(usuario_hash, 12) AS usuario, count(*) AS perguntas
FROM interacoes
WHERE criado_em >= now() - interval '1 day'
GROUP BY usuario_hash
ORDER BY perguntas DESC
LIMIT 10;

-- 5. Custo médio por pergunta respondida
SELECT round(avg(custo_usd), 6) AS custo_medio_usd,
       round(avg(tokens_entrada)) AS tokens_entrada_medio,
       round(avg(tokens_saida))   AS tokens_saida_medio
FROM interacoes
WHERE respondida;
