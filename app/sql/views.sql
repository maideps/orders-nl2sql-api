-- Reporting views over the clean `orders` table.
-- A sale is an order with status 'completed'. Pending, cancelled and refunded orders
-- are not revenue, so they are left out of both views.

DROP VIEW IF EXISTS sales_by_month_country;
CREATE VIEW sales_by_month_country AS
SELECT
    strftime('%Y-%m', order_date) AS month,        -- e.g. '2025-03'
    country,
    COUNT(*)                      AS orders,
    ROUND(SUM(amount), 2)         AS total_sales   -- NULL amounts add nothing
FROM orders
WHERE status = 'completed'
GROUP BY month, country;

DROP VIEW IF EXISTS top_10_customers;
CREATE VIEW top_10_customers AS
SELECT
    customer,
    country,
    COUNT(*)              AS orders,
    ROUND(SUM(amount), 2) AS total_spent
FROM orders
WHERE status = 'completed'
GROUP BY customer, country
ORDER BY total_spent DESC, customer
LIMIT 10;
