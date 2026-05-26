-- Q4: Share of SKUs with active discounts per brand (excludes bundles and RTD)
SELECT
    b.name                                                                                    AS brand,
    COUNT(*)                                                                                  AS total_skus,
    SUM(CASE WHEN p.discount_pct > 0 THEN 1 ELSE 0 END)                                      AS discounted_skus,
    ROUND(100.0 * SUM(CASE WHEN p.discount_pct > 0 THEN 1 ELSE 0 END) / COUNT(*), 1)         AS discount_coverage_pct
FROM prices p
JOIN products pr ON pr.id = p.product_id
JOIN brands b    ON b.id  = pr.brand_id
WHERE pr.format NOT IN ('bundle', 'rtd')
GROUP BY b.name
ORDER BY discount_coverage_pct DESC;
