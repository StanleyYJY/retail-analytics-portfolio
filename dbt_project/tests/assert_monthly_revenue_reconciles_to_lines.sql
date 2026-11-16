-- Monthly revenue mart must equal the sum of completed lines (to the cent).
with lines as (
    select cast(date_trunc('month', invoice_date) as date) as month_start, sum(line_amount) as revenue
    from {{ ref('fct_order_lines') }} group by 1
)
select l.month_start, l.revenue, m.revenue
from lines l full join {{ ref('mart_monthly_revenue') }} m using (month_start)
where abs(coalesce(l.revenue, 0) - coalesce(m.revenue, 0)) > 0.01
