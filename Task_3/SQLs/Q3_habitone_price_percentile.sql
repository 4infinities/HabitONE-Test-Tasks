-- Q3: Where does HabitONE sit in the market — percentile rank by single and subscription serving price
-- Brands without subscriptions get NULL in sub columns.
WITH serving AS (
    SELECT
        b.name,
        b.is_habitone,
        p.purchase_type,
        CASE
            WHEN p.serving_price IS NOT NULL                            THEN p.serving_price
            WHEN pr.serving_count IS NOT NULL AND pr.serving_count > 0  THEN p.price_usd / pr.serving_count
        END AS sp
    FROM prices p
    JOIN products pr ON pr.id = p.product_id
    JOIN brands b    ON b.id  = pr.brand_id
    WHERE pr.format NOT IN ('bundle', 'rtd')
      AND p.purchase_type IS NOT NULL
),
brand_avg AS (
    SELECT
        name,
        is_habitone,
        purchase_type,
        ROUND(AVG(sp), 3) AS avg_sp
    FROM serving
    WHERE sp IS NOT NULL
    GROUP BY name, is_habitone, purchase_type
),
single_ranked AS (
    SELECT
        name,
        is_habitone,
        avg_sp AS single_avg,
        ROUND(
            100.0 * (ROW_NUMBER() OVER (ORDER BY avg_sp) - 1)
            / NULLIF(COUNT(*) OVER () - 1, 0),
            1
        ) AS single_pct_rank
    FROM brand_avg
    WHERE purchase_type = 'single'
),
sub_ranked AS (
    SELECT
        name,
        avg_sp AS sub_avg,
        ROUND(
            100.0 * (ROW_NUMBER() OVER (ORDER BY avg_sp) - 1)
            / NULLIF(COUNT(*) OVER () - 1, 0),
            1
        ) AS sub_pct_rank
    FROM brand_avg
    WHERE purchase_type = 'subscription'
)
SELECT
    s.name,
    s.is_habitone,
    s.single_avg,
    s.single_pct_rank,
    sub.sub_avg,
    sub.sub_pct_rank
FROM single_ranked s
LEFT JOIN sub_ranked sub ON sub.name = s.name
ORDER BY s.single_avg;
