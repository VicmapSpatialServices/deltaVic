# Vicmap Load & Replication Service (VLRS)

This project allows download and sync of the vicmap suite of data products to a local PostGis database.

Author: Warwick Wilson  
Company: Department of Transport and Planning (Victoria)  
Date: 13/11/23  
Revised: 18/6/25  

# Prerequisites

## prereq 1. install git

Install a git client with all the defaults. Good download sites are [git-scm](https://git-scm.com/downloads) or [Atlassian](https://www.atlassian.com/git/tutorials/install-git) which has more detailed instructions.

>You can download a zip file of the code from github instead, (from the **Code** button dropdown). Using git is better though, as you can pull changes and bugfixes more easily.

## prereq 2. deltaVic git repo

Clone this repository locally to the machine you wish to use.
I recommend using an IDE such as [VS Code](https://code.visualstudio.com/download) to view and make edits to the python workspace. (Pycharm, Idle or a text editor are of course viable options, among many others.)

eg: in a command window, move to the folder you wish to put the VLRS client in and type
```bash
git clone https://github.com/VicmapSpatialServices/deltaVic.git VLRS
```
deltaVic can be downloaded from github without git, (by downloading a zip file from the **Code** button, but using git means you can update the application as improvements occur.).

## prereq 3. Python 3.10 (or above)

[Install python](https://www.python.org/downloads/) version 3.10 or better, (3.13 recommended)
> ensure you include "tk" when installing if you wish to use the GUI (it has been built in **tk**inter.).

Use python's pip to install the required **requests** (for API calls) and **psycopg2** (for database calls) libraries. Some variations on pip install you may encounter are displayed below:

```bash
pip3 install requests
pip install requests
python -m pip install requests

pip3 install psycopg2
```
> If psycopg2 is unavailable via pip for your python/os version, then use psycopg2-binary

Exceuting the deltavic.py script will may look like the following depending on how you have configured python:

```bash
deltaVic
deltaVic.py
py deltaVic.py
python deltaVic.py
python3.13 deltaVic.py
```
> the second option is used for examples thorughout this readme document

## prereq 4. Install/Configure Database - PostGIS 17 (or above)

**Note: You only require prereq steps 4 & 5 if you are going to sync data locally. If you are only using deltaVic to view metadata in the GUI, you only require is git and python, and to complete the setup's "register" steps.**

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

## prereq 5: Database GUI

Install a database client to allow direct access to interrogate your local database instance, (for maintenance and configuration.).
PGAdmin4 generally comes packaged with PostGres, but I would recommend [installing DBeaver](https://dbeaver.io/download/) as it has a built in geometry viewer.

# Setup and Configuration

There are 2 options to complete the setup. Either though the GUI, or via the command line.

## Using the GUI

Run the application by executing the deltavic.py script, the default action is to display the GUI.

The GUI consists of three tabs:
- Setup -> for registering and configuring your environment
- Meta -> Shows Metadata sourced from the Vicmap Manager APIs, allowing configuration of which layers you require syncced locally
- Data -> Shows your local datastore, including currency information and upload permissions if applicable.

### Registration (top frame)

Enter your email in the relevant field and press the "Refresh" button in the QA panel. This will generate a client ID and a validation email.
> Go to your email and click the validation link. Once done, return to the GUI and press "Refresh" again.
A validated email will obtain the default VLRS OpenData API key.

Once QA passes, the GUI's Meta tab will now be able to be populated.
> If you are using multiple independant deploy of VLRS, you can use the plus extension to your email handle. eg: someone+dev@example.com

### Database configuration (bottom frame)

Enter your database endpoint, port, instance Name, username and password that were configured in prerequisite 3 above. (localhost/vicmap/vicmap/vicmap by recommendation)

Press the "Test DB" button in the QA panel which will ensure that your configurations are correct.

Once QA passes, the GUIs Data tab will now be able to be populated, and the GUIs Meta tab will now have active checkboxes to set which datasets are syncced.

## Using the CLI (Command Line Interface)

### Register with the setup argument

Exceute the setup step and enter your email adress when requested:
```bash
deltaVic.py setup
```
> This will generate a new client-id for you via the APIs and place it in your config.ini file, triggering a verification email and exiting.
Check your email and use the link provided to verify your identity.

### Configure the database by executing the setup step again

Run setup a second time. Now that the client-id exists and verified.

```bash
deltaVic.py setup
```
> It will obtain and place the default Vicmap OpenData api-key in the config.ini file.

Prompts will ask for the database connection details and the location of your postgres17 client. (Press enter to accept the default values if correct.)
> The application will create your metadata storage table as vm_meta.data and populate it with the available vicmap datasets via the Vicmap Manager APIs.

# SELECT your target datasets

By default, no datasets will be selected for synchronisation.

GUI: Enter the **Meta** tab and select which schemas or datasets you wish to be active to syncronise to your local datastore by sing the checkboxes or the **all**"** buttons at the top of the layers tab.

Other: Access your database using DBeaver or a command line client such as psql to set the column active=true in the data table.

Via the database (DBeaver, psql or other):
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

# POPULATE
GUI: Hit the sync button on the Setup page (not wholly recommended in GUI, as the GUI is single threaded and it will hang while the sync occurs.). Logging will go to the window from where you executed the python script.

CLI: Manually run the sync comamnd via a terminal:
```bash
deltaVic.py sync
```

It will populate your active layers with downloads from the Vicmap Manager application. Processing time will depend on your internet download speed and choice of storage hardware. (As stated above, never use a magnetic drive for postgis, or you will have a much slower sync.).

# AUTOMATE

Setup a cron job or windows scheduler task to run every hour with the command:

```bash
deltaVic.py sync
```

Please set it for a random minute duing the hour to spread the load on our API service.
Ensure that the process is not already running when instantiating.

An initial full seed should take 2-3 hours, depending on your bandwidth for the 43GB of table data. (significantly less if you are not synccing all the tables).

The incremental update each week for vicmap should take less than 10 minutes for all datasets, (60-100 each week). If it takes longer please reach out to vicmap@transport.vic.gov.au for support with any observations.

The main Vicmap contracts **VLAT** (blue layers in the gui) and **VTT** (green) data generally updates on a Friday night after business hours, but can be late, (so don't rely exclusively on a saturday night job). Change management and in house **MISC** data loads (brown) can occur at any time during the week.

# Docker Installation

A containerised version of the application is available with [docker](https://docs.docker.com/engine/install/). To build the docker image, run the following command from the repository's root directory:

```bash
docker build -t deltavic .
```

## Configuration setup

deltaVic can be configured using the containerised application.

1. Create a new empty configuration file:

    ```bash
    touch config.ini
    ```

2. Launch the configuration setup wizard:

    ```bash
    docker run -v ${PWD}/config.ini:/deltaVic/config.ini --network=host -it deltavic setup
    ```

    - The `-v ${PWD}/config.ini:/deltaVic/config.ini` option mounts the `config.ini` file into the container to store the configuration persistently.
    - The `--network=host` flag ensures that the container can access your local network. This allows the container to access PostGIS running on the host machine.
    - The `-it` option enables interactive mode, allowing you to provide input directly to the setup wizard.

3. The database tables can then be configured by following the instructions provided [above](#select-your-target-datasets).

## Running a sync

A deltaVic sync can be run like so:

```bash
docker run -v ${PWD}/config.ini:/deltaVic/config.ini --network=host deltavic sync
```

- The `-v ${PWD}/config.ini:/deltaVic/config.ini` option mounts the `config.ini` file into the container.
- The `--network=host` flag ensures that the container can access your local network.
