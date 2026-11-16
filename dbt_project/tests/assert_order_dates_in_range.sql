select * from {{ ref('fct_orders') }} where order_date < date '2009-12-01' or order_date > date '2011-12-31'
