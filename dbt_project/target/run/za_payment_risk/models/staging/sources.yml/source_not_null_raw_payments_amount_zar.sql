
    select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
  
    
    



select amount_zar
from "za_payments"."main_raw"."sample_payments"
where amount_zar is null



  
  
      
    ) dbt_internal_test