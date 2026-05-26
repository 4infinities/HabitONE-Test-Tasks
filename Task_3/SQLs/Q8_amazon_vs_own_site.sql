-- Q8: Amazon vs own_site price gap per product
-- Own_site side uses the minimum-volume_g (smallest size) single-purchase SKU for each product,
-- since Amazon listings typically correspond to the base/smallest size.
-- Excludes bundles and RTD.
WITH own_min_vol AS (
    SELECT
        p.product_id,
        MIN(p.volume_g) AS min_volume_g
    FROM prices p
    JOIN products pr ON pr.id = p.product_id
    WHERE p.channel = 'own_site'
      AND pr.format NOT IN ('bundle', 'rtd')
      AND (p.purchase_type = 'single' OR p.purchase_type IS NULL)
    GROUP BY p.product_id
),
own_price AS (
    SELECT p.product_id, p.price_usd AS own_price, p.volume_g
    FROM prices p
    JOIN own_min_vol om ON om.product_id = p.product_id
                       AND om.min_volume_g = p.volume_g
    WHERE p.channel = 'own_site'
      AND (p.purchase_type = 'single' OR p.purchase_type IS NULL)
),
amz_price AS (
    SELECT p.product_id, p.price_usd AS amazon_price
    FROM prices p
    JOIN products pr ON pr.id = p.product_id
    WHERE p.channel = 'amazon'
      AND pr.format NOT IN ('bundle', 'rtd')
      AND (p.purchase_type = 'single' OR p.purchase_type IS NULL)
)
SELECT
    b.name                                          AS brand,
    pr.name                                         AS product,
    own.volume_g,
    own.own_price,
    amz.amazon_price,
    ROUND(amz.amazon_price - own.own_price, 2)      AS gap_amazon_minus_own
FROM own_price own
JOIN amz_price amz ON amz.product_id = own.product_id
JOIN products pr   ON pr.id = own.product_id
JOIN brands b      ON b.id  = pr.brand_id
ORDER BY gap_amazon_minus_own DESC;
