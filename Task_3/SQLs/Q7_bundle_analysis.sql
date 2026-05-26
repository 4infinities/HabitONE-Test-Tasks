-- Q7: Bundle catalog analysis — how many bundle SKUs each brand sells and at what price
SELECT
    b.name                                                                            AS brand,
    COUNT(DISTINCT pr.id)                                                             AS bundle_sku_count,
    ROUND(AVG(CASE WHEN p.purchase_type = 'single'       THEN p.price_usd END), 2)  AS single_avg_price,
    ROUND(AVG(CASE WHEN p.purchase_type = 'subscription' THEN p.price_usd END), 2)  AS sub_avg_price
FROM products pr
JOIN brands b  ON b.id  = pr.brand_id
JOIN prices p  ON p.product_id = pr.id
WHERE pr.format = 'bundle'
GROUP BY b.name
ORDER BY bundle_sku_count DESC;
