select
    cast(d as date)                              as date_day,
    cast(date_trunc('week', d) as date)          as week_start,
    cast(date_trunc('month', d) as date)         as month_start,
    extract('day' from d)                        as day_of_month,
    extract('dow' from d)                        as day_of_week,
    cast(last_day(d) as date)                    as month_end
from range(date '2009-12-01', date '2011-12-31', interval 1 day) t(d)
