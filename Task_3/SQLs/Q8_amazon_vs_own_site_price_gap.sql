-- Q8: Amazon vs own_site average price gap per brand
SELECT
    b.name                                                                          AS brand,
    ROUND(AVG(CASE WHEN p.channel = 'own_site'  THEN p.price_usd END), 2)         AS own_site_avg,
    ROUND(AVG(CASE WHEN p.channel = 'amazon'    THEN p.price_usd END), 2)         AS amazon_avg,
    ROUND(AVG(CASE WHEN p.channel = 'amazon'    THEN p.price_usd END)
        - AVG(CASE WHEN p.channel = 'own_site'  THEN p.price_usd END), 2)         AS gap_amazon_minus_own
FROM prices p
JOIN products pr ON pr.id = p.product_id
JOIN brands b    ON b.id  = pr.brand_id
GROUP BY b.name
HAVING own_site_avg IS NOT NULL AND amazon_avg IS NOT NULL
ORDER BY gap_amazon_minus_own DESC;
