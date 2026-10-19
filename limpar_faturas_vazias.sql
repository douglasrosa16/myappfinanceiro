-- Limpeza de faturas órfãs no PostgreSQL.
--
-- Uma fatura é considerada vazia somente quando não possui:
--   1. parcelas de cartão vinculadas; e
--   2. títulos vinculados.
--
-- O script abrange todos os usuários e cartões.
-- Execute o arquivo inteiro para confirmar a exclusão com COMMIT.

BEGIN;

-- Prévia das faturas que atendem aos critérios de exclusão.
SELECT
    f.id,
    f.usuario_id,
    f.cartao_id,
    f.ciclo,
    f.status,
    f.total_bruto,
    f.total_creditos,
    f.total
FROM financeiro_fatura AS f
WHERE NOT EXISTS (
    SELECT 1
    FROM financeiro_parcelacartao AS p
    WHERE p.fatura_id = f.id
)
AND NOT EXISTS (
    SELECT 1
    FROM financeiro_titulo AS t
    WHERE t.fatura_id = f.id
)
ORDER BY f.ciclo DESC, f.id;

-- Exclui apenas as faturas que continuam vazias no momento da exclusão.
-- O RETURNING apresenta exatamente os registros removidos.
WITH faturas_excluidas AS (
    DELETE FROM financeiro_fatura AS f
    WHERE NOT EXISTS (
        SELECT 1
        FROM financeiro_parcelacartao AS p
        WHERE p.fatura_id = f.id
    )
    AND NOT EXISTS (
        SELECT 1
        FROM financeiro_titulo AS t
        WHERE t.fatura_id = f.id
    )
    RETURNING
        f.id,
        f.usuario_id,
        f.cartao_id,
        f.ciclo,
        f.status,
        f.total_bruto,
        f.total_creditos,
        f.total
)
SELECT *
FROM faturas_excluidas
ORDER BY ciclo DESC, id;

COMMIT;
