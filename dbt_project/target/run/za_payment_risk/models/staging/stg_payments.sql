
  
  create view "za_payments"."main"."stg_payments__dbt_tmp" as (
    -- stg_payments.sql
-- Casts, renames and enriches raw scored payment events.

with source as (

    select * from "za_payments"."main_raw"."sample_payments"

),

renamed as (

    select
        -- identifiers
        cast(transaction_id as varchar)                     as transaction_id,
        cast(bank_code as varchar)                          as bank_code,
        cast(originator_id as varchar)                      as originator_id,

        -- timestamps
        cast(timestamp as timestamptz)                      as transaction_at,
        cast(processed_at as timestamptz)                   as processed_at,

        -- payment details
        cast(amount_zar as decimal(18,2))                   as amount_zar,
        upper(cast(currency as varchar))                    as currency,
        cast(exchange_rate as decimal(12,6))                as exchange_rate,
        cast(amount_foreign as decimal(18,2))               as amount_foreign,

        -- compliance fields
        upper(cast(bop_category_code as varchar))           as bop_category_code,
        cast(bop_description as varchar)                    as bop_description,
        upper(cast(beneficiary_country as varchar))         as beneficiary_country,
        upper(cast(swift_bic as varchar))                   as swift_bic,
        cast(transaction_purpose as varchar)                as transaction_purpose,

        -- ADA tracking
        cast(ada_ytd_used as decimal(18,2))                 as ada_ytd_used,
        cast(ada_limit as decimal(18,2))                    as ada_limit,
        round(
            (cast(ada_ytd_used as decimal(18,2)) + cast(amount_zar as decimal(18,2)))
            / nullif(cast(ada_limit as decimal(18,2)), 0) * 100
        , 2)                                                as ada_utilisation_pct,

        -- entity
        cast(is_resident as boolean)                        as is_resident,
        upper(cast(entity_type as varchar))                 as entity_type,

        -- risk scoring
        cast(risk_score as integer)                         as risk_score,
        upper(cast(risk_band as varchar))                   as risk_band,
        cast(compliance_passed as boolean)                  as compliance_passed,
        cast(requires_sar as boolean)                       as requires_sar,
        cast(finsurvreportable as boolean)                  as finsurvreportable,
        cast(violation_count as integer)                    as violation_count,
        cast(warning_count as integer)                      as warning_count,

        -- metadata
        cast(source_system as varchar)                      as source_system,
        cast(schema_version as varchar)                     as schema_version

    from source

),

enriched as (

    select *,
        case when risk_band = 'CRITICAL' then true else false end    as is_critical,
        case when risk_band in ('HIGH','CRITICAL') then true
             else false end                                          as needs_review,
        case when ada_utilisation_pct > 100 then true
             else false end                                          as is_ada_breached,
        case when ada_utilisation_pct between 85 and 100 then true
             else false end                                          as is_ada_approaching

    from renamed

)

select * from enriched
  );
