-- One row per raw invoice line, typed and flagged. The only rows removed here are exact
-- duplicates (same invoice, item, quantity, price, timestamp, and customer): 34,337 rows,
-- about 3.2% of the file. Downstream models decide what counts as a sale.
with src as (
    select * from {{ source('raw', 'online_retail_ii') }}
    qualify row_number() over (
        partition by invoice, stock_code, quantity, unit_price, invoice_ts, customer_id
        order by description
    ) = 1
)
select
    row_number() over (order by invoice_ts, invoice, stock_code)        as line_id,
    trim(invoice)                                                        as invoice,
    upper(trim(stock_code))                                              as stock_code,
    nullif(trim(description), '')                                        as description,
    cast(quantity as integer)                                            as quantity,
    cast(unit_price as double)                                           as unit_price,
    cast(quantity as integer) * cast(unit_price as double)               as line_amount,
    cast(invoice_ts as timestamp)                                        as invoice_ts,
    cast(invoice_ts as date)                                             as invoice_date,
    customer_id,
    trim(country)                                                        as country,
    starts_with(trim(invoice), 'C')                                      as is_cancellation,
    upper(trim(stock_code)) in ('POST', 'DOT', 'M', 'D', 'C2', 'BANK CHARGES', 'AMAZONFEE',
                                 'CRUK', 'PADS', 'S', 'B', 'ADJUST', 'ADJUST2', 'TEST001', 'TEST002')
        or regexp_matches(upper(trim(stock_code)), '^(GIFT_|TEST)')      as is_non_product
from src
