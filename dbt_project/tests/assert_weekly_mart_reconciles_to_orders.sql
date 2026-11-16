-- Customer-week mart must carry every order and every pound of revenue.
select 1
from (select sum(orders) o, sum(revenue) r from {{ ref('mart_customer_weekly') }}) w,
     (select count(*) o, sum(revenue) r from {{ ref('fct_orders') }}) f
where w.o <> f.o or abs(w.r - f.r) > 0.01
