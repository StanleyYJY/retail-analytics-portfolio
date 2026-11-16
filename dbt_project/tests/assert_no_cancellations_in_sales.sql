select * from {{ ref('fct_order_lines') }} where starts_with(invoice, 'C') or quantity <= 0 or unit_price <= 0
