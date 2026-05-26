-- Q10: Total SKU count per brand (catalog breadth)
SELECT
    b.name                          AS brand,
    COUNT(DISTINCT pr.id)           AS product_count,
    COUNT(DISTINCT p.id)            AS price_row_count
FROM products pr
JOIN brands b    ON b.id  = pr.brand_id
LEFT JOIN prices p ON p.product_id = pr.id
GROUP BY b.name
ORDER BY product_count DESC;
