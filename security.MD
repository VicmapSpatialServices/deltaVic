# ATTENTION:
please report any security flaws to vicmap@transport.vic.gov.au
These may include
-any authentication bypass behaviours of the Vicmap Manager API endpoints in use, (eg: usage without an active client-id, aside from registration).
-any restricted datasets that can be accessed by the default Open Data API key provided by the registration process.

# advice regarding securing your local postgres datastores.

VLRS is provided under an MIT fair use Open Data policy that accepts no responsibility for your implementation of the system.
caveat emptor - it is the customers responsibility to ensure (QA) that the datastore is up to date and is functioning as designed.

The VLRS is designed to be a Disposable Spatial Data Infrastructure (DSDI).
It is assumed that you can migrate to a new database and reseed your local datastore at any time.
Since you can reseed at any time, this means you only need a low level of security for your local vicmap postgis database.

View it like internet passwords:
  Tier 1 - banking passwords
  Tier 2 - social media passwords
  Tier 3 - low impact breach - online forums, download sites, etc.
Your VLRS postgres instance can be lowest security Tier. (the client does not use passwords, it uses an internal client-id).

Given that, for your local database, VLRS recommends:
-using the default database port 5432
-a database instance called 'vicmap' (Adhere to the most basic of security prortcols by not utilising the default 'postgres' database instance.).
-a user for that database called 'vicmap' (which has rights only to the vicmap database)
-a password for that user of 'vicmap'

Caveat: This is of course determined by your own organisations security protocols, you may need to batten it down if required by your use case.
-If for example your database is public facing, (endpoint and port are open to the internet), it is not recommended to use the default port.
-You can also whitelist your port to a specific range of IP addresses (when using cloud services such as AWS) by adding a security group to your RDS and allowing only certain IP addresses access to that port.
-the VLRS client works on the default internet ports of 80 & 443

VLRS is designed that your local instance target is your STAGING database.
-only after conducting due-diligence QA and reviewing aspects such as data currency and layers errors that may be present should you turn off the VLRS, sync to your PROD instance, then turn VLRS back on again. 
-any integrations you create with VLRS to your downstream systems should have a new user created appropriate for those systems.
-It is recommended that VLRS be used for your staging instance on an hourly basis. It should be executed to prod on your schedule when satisfied with your QA results in staging. (You can check the activity in the staging instance either via the logs or via metadata in the vm_meta.data table.).
