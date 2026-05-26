-- Q3: Where does HabitONE sit in the market price distribution?
WITH brand_avg AS (
    SELECT
        b.name,
        b.is_habitone,
        AVG(p.price_usd / p.volume_g) AS avg_ppg
    FROM prices p
    JOIN products pr ON pr.id = p.product_id
    JOIN brands b    ON b.id  = pr.brand_id
    WHERE p.volume_g IS NOT NULL AND p.volume_g > 0
    GROUP BY b.name, b.is_habitone
),
ranked AS (
    SELECT
        name,
        is_habitone,
        ROUND(avg_ppg, 4) AS avg_ppg,
        ROUND(
            100.0 * (ROW_NUMBER() OVER (ORDER BY avg_ppg) - 1)
            / (COUNT(*) OVER () - 1),
            1
        ) AS pct_rank
    FROM brand_avg
)
SELECT * FROM ranked ORDER BY avg_ppg;
