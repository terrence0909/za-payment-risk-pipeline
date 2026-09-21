-- corridor_exposure.sql
-- ZAR volume and risk distribution by destination country.

select
    cast(transaction_at as date)        as report_date,
    beneficiary_country,

    count(*)                            as transaction_count,
    round(sum(amount_zar), 2)           as total_volume_zar,
    round(avg(amount_zar), 2)           as avg_transaction_zar,
    round(max(amount_zar), 2)           as max_transaction_zar,

    count(*) filter (where is_critical) as critical_count,
    count(*) filter (where requires_sar) as sar_count,
    round(
        count(*) filter (where compliance_passed) * 100.0
        / nullif(count(*), 0)
    , 2)                                as pass_rate_pct

from {{ ref('stg_payments') }}
group by 1, 2
order by report_date desc, total_volume_zar desc
