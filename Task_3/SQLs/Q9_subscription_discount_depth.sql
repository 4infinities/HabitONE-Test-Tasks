-- Q9: Subscription discount depth — single vs sub price per brand
SELECT
    b.name                                                                                          AS brand,
    ROUND(AVG(CASE WHEN p.purchase_type = 'single'       THEN p.price_usd END), 2)                AS single_avg,
    ROUND(AVG(CASE WHEN p.purchase_type = 'subscription' THEN p.price_usd END), 2)                AS sub_avg,
    ROUND(100.0 * (1 -
        AVG(CASE WHEN p.purchase_type = 'subscription' THEN p.price_usd END) /
        AVG(CASE WHEN p.purchase_type = 'single'       THEN p.price_usd END)
    ), 1)                                                                                           AS sub_discount_pct
FROM prices p
JOIN products pr ON pr.id = p.product_id
JOIN brands b    ON b.id  = pr.brand_id
GROUP BY b.name
HAVING single_avg IS NOT NULL AND sub_avg IS NOT NULL
ORDER BY sub_discount_pct DESC;
