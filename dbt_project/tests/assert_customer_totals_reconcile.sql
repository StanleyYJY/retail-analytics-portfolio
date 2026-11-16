select 1
from (select sum(orders) o, sum(revenue) r from {{ ref('dim_customer') }}) c,
     (select count(*) o, sum(revenue) r from {{ ref('fct_orders') }}) f
where c.o <> f.o or abs(c.r - f.r) > 0.01
