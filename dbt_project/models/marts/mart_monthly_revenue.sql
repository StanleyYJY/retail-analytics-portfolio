with orders as (
    select o.*, d.month_start
    from {{ ref('fct_orders') }} o
    join {{ ref('dim_date') }} d on d.date_day = o.order_date
),
firsts as (
    select customer_id, cast(date_trunc('month', first_order_date) as date) as first_month
    from {{ ref('dim_customer') }}
)
select
    o.month_start,
    count(*)                                                        as orders,
    count(distinct o.customer_id)                                   as active_customers,
    count(distinct case when f.first_month = o.month_start then o.customer_id end) as new_customers,
    sum(o.revenue)                                                  as revenue,
    sum(o.revenue) / count(*)                                       as avg_order_value
from orders o join firsts f using (customer_id)
group by 1
