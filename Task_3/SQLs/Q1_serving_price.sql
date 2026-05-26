-- Q1: Average serving price by brand and purchase type (single vs subscription)
-- Excludes bundles and RTD. Uses serving_price where available;
-- computes price_usd / serving_count when serving_price is NULL but serving_count is known.
SELECT
    b.name                                                                AS brand,
    p.purchase_type,
    ROUND(AVG(
        CASE
            WHEN p.serving_price IS NOT NULL                                   THEN p.serving_price
            WHEN pr.serving_count IS NOT NULL AND pr.serving_count > 0         THEN p.price_usd / pr.serving_count
        END
    ), 3)                                                                 AS avg_serving_price,
    COUNT(*)                                                              AS sku_count
FROM prices p
JOIN products pr ON pr.id = p.product_id
JOIN brands b    ON b.id  = pr.brand_id
WHERE pr.format NOT IN ('bundle', 'rtd')
  AND p.purchase_type IS NOT NULL
GROUP BY b.name, p.purchase_type
ORDER BY b.name, p.purchase_type;
