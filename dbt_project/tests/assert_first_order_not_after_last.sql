select * from {{ ref('dim_customer') }} where first_order_date > last_order_date
