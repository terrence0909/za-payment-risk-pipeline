-- finsurvreport_daily.sql
-- Gold layer: daily FinSurv compliance summary per bank.
-- Maps directly to SARB FinSurv daily submission requirements.

with daily as (

    select
        cast(transaction_at as date)    as report_date,
        bank_code,
        beneficiary_country,
        bop_category_code,
        risk_band,
        compliance_passed,
        requires_sar,
        finsurvreportable,
        is_ada_breached,
        is_critical,
        amount_zar,
        violation_count

    from "za_payments"."main"."stg_payments"

)

select
    report_date,
    bank_code,

    -- Volume
    count(*)                                                as total_transactions,
    count(*) filter (where finsurvreportable)               as reportable_transactions,
    round(sum(amount_zar), 2)                               as total_volume_zar,
    round(avg(amount_zar), 2)                               as avg_transaction_zar,

    -- Compliance
    count(*) filter (where compliance_passed)               as passed_count,
    count(*) filter (where not compliance_passed)           as failed_count,
    round(
        count(*) filter (where compliance_passed) * 100.0
        / nullif(count(*), 0)
    , 2)                                                    as compliance_pass_rate_pct,

    -- Risk distribution
    count(*) filter (where risk_band = 'LOW')               as risk_low_count,
    count(*) filter (where risk_band = 'MEDIUM')            as risk_medium_count,
    count(*) filter (where risk_band = 'HIGH')              as risk_high_count,
    count(*) filter (where risk_band = 'CRITICAL')          as risk_critical_count,

    -- ADA
    count(*) filter (where is_ada_breached)                 as ada_breach_count,
    round(sum(amount_zar) filter (where is_ada_breached), 2) as ada_breach_volume_zar,

    -- SAR
    count(*) filter (where requires_sar)                    as sar_required_count,

    -- Violations
    sum(violation_count)                                    as total_violations,

    current_timestamp                                       as generated_at

from daily
group by 1, 2
order by report_date desc, total_volume_zar desc