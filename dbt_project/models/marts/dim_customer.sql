with orders as (select * from {{ ref('fct_orders') }}),
country as (
    select customer_id, mode(country) as country
    from {{ ref('fct_order_lines') }} group by customer_id
)
select
    o.customer_id,
    c.country,
    min(o.order_date)                         as first_order_date,
    max(o.order_date)                         as last_order_date,
    count(*)                                  as orders,
    sum(o.revenue)                            as revenue,
    sum(o.revenue) / count(*)                 as avg_order_value
from orders o join country c using (customer_id)
group by o.customer_id, c.country
