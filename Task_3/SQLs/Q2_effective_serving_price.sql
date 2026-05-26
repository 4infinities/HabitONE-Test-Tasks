-- Q2: Effective serving price after discount, by brand and purchase type
-- Replaces Q9 (subscription discount depth). Excludes bundles and RTD.
-- Uses serving_price where available; computes from price_usd / serving_count otherwise.
SELECT
    b.name                                                                AS brand,
    p.purchase_type,
    ROUND(AVG(
        CASE
            WHEN p.serving_price IS NOT NULL AND pr.serving_count IS NOT NULL AND pr.serving_count > 0
                THEN p.serving_price * (1 - p.discount_pct / 100.0)
            WHEN p.serving_price IS NOT NULL
                THEN p.serving_price * (1 - p.discount_pct / 100.0)
            WHEN pr.serving_count IS NOT NULL AND pr.serving_count > 0
                THEN p.price_usd * (1 - p.discount_pct / 100.0) / pr.serving_count
        END
    ), 3)                                                                 AS effective_serving_price,
    COUNT(*)                                                              AS sku_count
FROM prices p
JOIN products pr ON pr.id = p.product_id
JOIN brands b    ON b.id  = pr.brand_id
WHERE pr.format NOT IN ('bundle', 'rtd')
  AND p.purchase_type IS NOT NULL
GROUP BY b.name, p.purchase_type
ORDER BY b.name, p.purchase_type;
