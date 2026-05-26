-- Q2: Effective price per gram after applying discounts
SELECT
    b.name                                                                      AS brand,
    ROUND(AVG(p.price_usd * (1 - p.discount_pct / 100.0) / p.volume_g), 4)   AS effective_price_per_g
FROM prices p
JOIN products pr ON pr.id = p.product_id
JOIN brands b    ON b.id  = pr.brand_id
WHERE p.volume_g IS NOT NULL AND p.volume_g > 0
GROUP BY b.name
ORDER BY effective_price_per_g;
