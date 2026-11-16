-- Completed product sales to identified customers.
select
    line_id, invoice, stock_code, quantity, unit_price, line_amount,
    invoice_ts, invoice_date, customer_id, country
from {{ ref('stg_transactions') }}
where not is_cancellation
  and not is_non_product
  and quantity > 0
  and unit_price > 0
  and customer_id is not null
