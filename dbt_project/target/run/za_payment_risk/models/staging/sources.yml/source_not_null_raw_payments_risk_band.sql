
    select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
  
    
    



select risk_band
from "za_payments"."main_raw"."sample_payments"
where risk_band is null



  
  
      
    ) dbt_internal_test