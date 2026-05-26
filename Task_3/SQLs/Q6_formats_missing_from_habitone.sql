-- Q6: Formats competitors offer that HabitONE does not
SELECT DISTINCT pr.format
FROM products pr
JOIN brands b ON b.id = pr.brand_id
WHERE b.is_habitone = 0
  AND pr.format NOT IN (
      SELECT DISTINCT pr2.format
      FROM products pr2
      JOIN brands b2 ON b2.id = pr2.brand_id
      WHERE b2.is_habitone = 1
  )
  AND pr.format IS NOT NULL
ORDER BY pr.format;
