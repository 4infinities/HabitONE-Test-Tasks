-- Q7: Average serving price by brand (broader coverage than price/g — 795 vs 573 rows)
SELECT
    b.name                                    AS brand,
    ROUND(AVG(p.serving_price), 3)            AS avg_serving_price,
    COUNT(*)                                  AS n
FROM prices p
JOIN products pr ON pr.id = p.product_id
JOIN brands b    ON b.id  = pr.brand_id
WHERE p.serving_price IS NOT NULL
GROUP BY b.name
ORDER BY avg_serving_price;
