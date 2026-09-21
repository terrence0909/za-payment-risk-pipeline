
    
    

select
    transaction_id as unique_field,
    count(*) as n_records

from "za_payments"."main_raw"."sample_payments"
where transaction_id is not null
group by transaction_id
having count(*) > 1


