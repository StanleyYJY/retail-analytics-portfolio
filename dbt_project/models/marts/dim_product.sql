select
    stock_code,
    mode(description)          as description,
    median(unit_price)         as median_unit_price,
    count(distinct invoice)    as orders
from {{ ref('stg_transactions') }}
where not is_non_product and not is_cancellation and quantity > 0
group by stock_code
