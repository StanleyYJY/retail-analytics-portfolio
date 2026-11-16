select
    o.customer_id,
    d.week_start,
    count(*)        as orders,
    sum(o.revenue)  as revenue
from {{ ref('fct_orders') }} o
join {{ ref('dim_date') }} d on d.date_day = o.order_date
group by 1, 2
