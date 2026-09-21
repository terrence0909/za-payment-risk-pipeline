
    select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
  
    
    



select bop_category_code
from "za_payments"."main_raw"."sample_payments"
where bop_category_code is null



  
  
      
    ) dbt_internal_test