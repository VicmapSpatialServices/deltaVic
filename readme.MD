# Vicmap Replication Service

This project allows download and sync of the vicmap suite of data products to a local PostGis database.

Author: Warwick Wilson
Company: Department of Transport and Planning (Victoria)
Date: 13/11/23
Revised: 19/9/24

## Prerequisites

### deltaVic Git repo

Clone this repository locally to the machine you wish to use.
I recommend using an IDE such as VS Code to view and make edits to the python workspace.

### Install/Configure Database - PostGIS 17 (or above)

**Note: installations with PostGres 16 will fail to update data created after 28-02-2025.**

[Install PostGres](https://www.postgresql.org/download/) v17 or above.
> If your installer offers, add the spatial extension PostGIS.

It is recommended that you create a secondary instance in your database called 'vicmap' with a user called 'vicmap' that only has access to the vicmap instance, (so as not to expose the superuser role or admin capabilities to the deltaVic client application.).

eg: log in as the **postgres** database master (set up during install) and use:

```sql
CREATE DATABASE vicmap;

CREATE EXTENSION PostGIS;

CREATE ROLE vicmap NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT LOGIN NOREPLICATION NOBYPASSRLS PASSWORD 'vicmap';
-- OR
CREATE ROLE vicmap with PASSWORD 'vicmap' WITH LOGIN;

GRANT CREATE ON DATABASE vicmap TO vicmap;
```

> Early testing of deltaVic idenitifed that using an HDD as your postgis data folder is not a good idea and will lead to performanmce degradation. Ensure you have a solid state (SSD) Hard Disk underlying your postgres installation.
> NB: EDB installer can use a second step called stack builder to install the spatial extension for you.
> NB2: Minor cleanup -- You can delete the tiger/tiger_data/topoology schemas.

### Database GUI

Install a database client to allow access to your local database instance, (for maintenance and configuration.).
PGAdmin4 generally comes packaged with PostGres, but I would recommend [installing DBeaver](https://dbeaver.io/download/).

### Python 3.10 (or above)

[Install python](https://www.python.org/downloads/) version 3.10 or better, (3.12 recommended)

use pip to install the required **requests** and **psycopg2** libraries. Some variations you may encoundter are displayed below:

```bash
pip3 install requests
pip install requests
python -m pip install requests

pip3 install psycopg2
```

> If psycopg2 is unavailable via pip for your python/os version, then use psycopg2-binary

NB: Step 1 has an alternative GUI that can be used to configure the config details. The GUI is now the default action when running deltavic.py.

## Step 1: SETUP

### Populate your config.ini

file with your email address and you database connection details ( dbHost/dbPort/dbName/dbUser/dbPswd ).
> If you are using multiple instances, you can use the plus extension to your email handle.
> ie: person@example.com and person+prod@example.com can coexist and are equivalent.

### Execute the setup step

Exceuting the scripts will depend on how you have configured python on your system, it may look like the following:

```bash
deltaVic setup
deltaVic.py setup
python3.12 deltaVic.py setup
```

This will request a new client-id for you via the APIs and place it in your config.ini file, triggering a verification email and exiting.

### Verify your Email

> Check your email account and confirm deltaVic by clicking the link so it becomes activated on our backend.

### Execute the setup step, again

Run setup a second time. Now that the client-id exists and is activated, the database will go ahead to populate the "vm_meta.data" tracking table and create the vicmap schemas.

```bash
deltaVic.py setup
```

> It will place the default public api-key in the config.ini file.
> It will then create the vicmap schemas and populate the table vm_meta.data table (with 500+ public layers)

### Configure your target datasets

If you do not want all datasets delivered, use your DB GUI (DBeaver) to go to the data table and set active flag on each layer to true/false.

```sql
update vm_meta.data set active=true;
update vm_meta.data set active=false;
update vm_meta.data set active=true where not (identity like 'vlat%' or identity like 'vtt%');
update vm_meta.data set active=true where identity='vmtrans.tr_road';
update vm_meta.data set active=true where identity in ('vmadd.address', 'vmprop.centroid');
update vm_meta.data set active=true where (identity like 'vlat%') and sup='VLAT';
update vm_meta.data set active=true where sup='VLAT'; --VLAT--VTT
update vm_meta.data set active=true where not (identity like 'vtt%') and sup='VTT';
```

## Step 2: POPULATE

Manually run the comamnd

```bash
deltaVic.py sync
```

It will populate your active layers with downloads from the Vicmap Manager application. Processing time will depend on your internet download speed and choice of storage hardware. (As atated above, never use a magnetic drive for postgis, or you will have a bad time waiting around a lot.).

## Step 3: AUTOMATE

Queue a cron job or windows scheduler to run every hour with the command:

```bash
deltaVic.py sync
```

Please set it for a random minute duing the hour to spread the load on our API service.
Ensure that the process is not already running when instantiating.

If configured correctly, the incremental update each week for vicmap should take about 10 minutes for all datasets, significantly less if you are not synccing all the tables. If it takes longer please reach out to us with any observations.

The Vicmap data generally updates on a Friday night after business hours. You could always just kick this off manually every Monday monring to bring your data into sync.
