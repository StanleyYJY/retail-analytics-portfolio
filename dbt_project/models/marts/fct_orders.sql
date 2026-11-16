select
    invoice,
    any_value(customer_id)        as customer_id,
    min(invoice_ts)               as order_ts,
    min(invoice_date)             as order_date,
    count(*)                      as line_count,
    sum(quantity)                 as units,
    sum(line_amount)              as revenue
from {{ ref('fct_order_lines') }}
group by invoice
