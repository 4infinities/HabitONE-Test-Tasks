-- Q1: Average price per gram by brand (full listed price, no discount applied)
SELECT
    b.name                                        AS brand,
    ROUND(AVG(p.price_usd / p.volume_g), 4)      AS avg_price_per_g,
    COUNT(*)                                       AS sku_count
FROM prices p
JOIN products pr ON pr.id = p.product_id
JOIN brands b    ON b.id  = pr.brand_id
WHERE p.volume_g IS NOT NULL AND p.volume_g > 0
GROUP BY b.name
ORDER BY avg_price_per_g;
