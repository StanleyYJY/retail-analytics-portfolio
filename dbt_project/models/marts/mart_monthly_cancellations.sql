select
    cast(date_trunc('month', invoice_date) as date)                          as month_start,
    sum(case when is_cancellation then -line_amount else 0 end)              as cancelled_amount,
    sum(case when not is_cancellation and quantity > 0 then line_amount else 0 end) as gross_amount,
    sum(case when is_cancellation then -line_amount else 0 end)
      / nullif(sum(case when not is_cancellation and quantity > 0 then line_amount else 0 end), 0) as cancellation_rate
from {{ ref('stg_transactions') }}
where not is_non_product and customer_id is not null
group by 1
