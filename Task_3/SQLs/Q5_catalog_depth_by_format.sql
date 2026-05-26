-- Q5: SKU count by brand and format — shows catalog depth and gaps
SELECT
    b.name       AS brand,
    pr.format,
    COUNT(*)     AS sku_count
FROM products pr
JOIN brands b ON b.id = pr.brand_id
GROUP BY b.name, pr.format
ORDER BY b.name, sku_count DESC;
