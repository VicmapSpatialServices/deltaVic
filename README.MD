# VLRS client

The VLRS client downloads the Vicmap suite of data products into a PostGIS database you run, and keeps it current. It registers you with VLRS, lets you choose which layers you want, loads each one in full the first time, and on every later run applies the incremental changes VLRS has published since. It only does that when it runs, so to keep the database current you [schedule it](#schedule-it), hourly is the recommendation.

It runs two ways. With no arguments it opens a window for setting up, choosing layers and syncing. With an argument such as `sync` it runs from the command line, which is how you schedule it.

Two visual guides sit in the `guide` folder for people who would rather follow pictures:

- `guide/install_guide.html` walks through installing PostgreSQL, creating the database and running the client for the first time.
- `guide/gui_guide.html` explains every part of the client's window.

Open them in a browser straight from the folder. This README is the full reference.

Author: Vicmap Spatial Services, Department of Transport and Planning (Victoria)
Support: vicmap.help@transport.vic.gov.au

## Contents

1. [How it works](#how-it-works)
2. [Requirements](#requirements)
3. [Install the client](#install-the-client)
4. [Set up PostgreSQL and PostGIS](#set-up-postgresql-and-postgis)
5. [Register and configure](#register-and-configure)
6. [Choose your layers](#choose-your-layers)
7. [Sync](#sync)
8. [Schedule it](#schedule-it)
9. [Command reference](#command-reference)
10. [Configuration reference](#configuration-reference)
11. [Running in Docker](#running-in-docker)
12. [Troubleshooting](#troubleshooting)
13. [Security](#security)

## How it works

VLRS publishes each Vicmap layer as a series of supplies. A supply is either `full`, a complete copy of the table, or `inc`, the rows added and removed since the previous one. Each supply is a PostgreSQL dump file.

The client keeps a control table, `vm_meta.data`, with one row per layer: whether you want it (`active`), which supply you hold (`sup_ver`), and where it is in loading the next one (`status`). A sync compares that table with what VLRS offers and, for every active layer that is behind, works through these steps:

| Status | What happens |
|---|---|
| `QUEUED` | Asks VLRS for the next supply after the one held |
| `DOWNLOAD` | Downloads the dump file into the `temp` folder |
| `RESTORE` | Loads it with `pg_restore`. A full supply replaces the table, an incremental one lands in `vm_delta` |
| `OPS` | Incremental only. Deletes the changed rows from the table and inserts the new versions |
| `VACUUM`, `ANALYZE` | Incremental only. Tidies the table and refreshes its statistics |
| `RECONCILE` | Checks the table's row count and key checksum against the figures VLRS published |
| `CLEAN` | Deletes the dump file |
| `COMPLETE` | Up to date |
| `WAIT` | VLRS has announced a supply that is not ready yet. It is retried on the next sync |

A layer that fails a step is flagged with `err = true` and the message is kept in `extradata->>'error'`. A sync skips flagged layers until they are cleared. See [Troubleshooting](#troubleshooting).

A sync repeats this until nothing is left to do, so a layer several supplies behind catches up in one run. If VLRS withdraws a layer, the next sync drops your local table and its control row.

The data comes from three contracts, which the window colours differently:

- **VLAT** is address and property data (`vmadd`, `vmprop`, `vmadmin` and others).
- **VTT** is topographic data (`vmtrans`, `vmhydro`, `vmfeat` and others).
- **MISC** is maintained in house. It is the only kind that can be uploaded back to VLRS.

## Requirements

| What | Version | Needed for |
|---|---|---|
| Python | 3.12 or later, 3.14 recommended | Everything |
| Tk for Python | Any | The window only |
| PostgreSQL server | 18 or later | Syncing data |
| PostGIS extension | 3.x for your PostgreSQL | Syncing data |
| PostgreSQL client tools (`pg_restore`, `pg_dump`) | 18 or later | Syncing data |
| Git | Any | Optional, makes updating easier |

Python 3.12 is a hard floor. The code reuses quotes inside f-strings, which earlier versions cannot even parse.

The client tools matter as much as the server. `pg_restore` only reads dumps made by its own major version or older, and the supplies are made with 18. An older `pg_restore` fails with `unsupported version in file header`.

If you only want to browse the catalogue in the window, Python and Tk are enough. PostgreSQL is only needed once you sync.

Disk and bandwidth:

- Every layer, including the history archives in the `vmhist` schema, comes to roughly 110 GB of table data and about 150 GB once the indexes are built. The history archives are most of that.
- The current layers alone, everything outside `vmhist`, are about 32 GB of table data and under 50 GB with indexes.
- Leave headroom on top for the dumps while they load and for PostgreSQL's own working space. A 250 GB volume is comfortable for everything.
- Put the PostgreSQL data folder on an SSD. On a spinning disk a sync is many times slower.
- A first full sync of everything takes several hours, depending on your connection and disk. A weekly incremental sync of everything usually takes under 10 minutes.

Measured on a full install in October 2026 with 439 layers. To see where your own space goes:

```sql
SELECT n.nspname AS schema,
       pg_size_pretty(sum(pg_table_size(c.oid)))   AS tables,
       pg_size_pretty(sum(pg_indexes_size(c.oid))) AS indexes
  FROM vm_meta.data d
  JOIN pg_class c ON c.oid = to_regclass(d.identity)
  JOIN pg_namespace n ON n.oid = c.relnamespace
 GROUP BY 1
 ORDER BY sum(pg_total_relation_size(c.oid)) DESC;
```

The client talks to VLRS over HTTPS on port 443 only.

## Install the client

### Get the code

With git, from the folder you want it in:

```bash
git clone https://github.com/VicmapSpatialServices/deltaVic.git VLRS
cd VLRS
```

Without git, download the zip from the **Code** button on GitHub and unzip it. Git is better because `git pull` brings in fixes later.

### Install Python

Install Python from [python.org](https://www.python.org/downloads/).

- **Windows**: tick "Add python.exe to PATH" and leave "tcl/tk and IDLE" ticked.
- **macOS**: the system `python3` is too old. Use the python.org installer or Homebrew (`brew install python@3.14 python-tk@3.14`). Check with `python3 -V`.
- **Linux**: use your distribution's Python if it is 3.12 or later, and install Tk separately, for example `sudo apt install python3-tk python3-venv` on Ubuntu.

### Install the dependencies

Use a virtual environment so the client's packages stay separate from everything else. From the `VLRS` folder:

```bash
# macOS and Linux
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

```powershell
# Windows
py -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

`requirements.txt` installs `requests` for the API calls and `psycopg2-binary` for the database.

### Run it

Always run the client from inside the `VLRS` folder. It reads `config.ini` and `data.sql` from the current folder, writes its downloads to `temp` and its log to `deltaVic.log` there.

```bash
.venv/bin/python deltaVic.py           # macOS and Linux, opens the window
.venv\Scripts\python deltaVic.py       # Windows, opens the window
```

The rest of this README writes the command as `python deltaVic.py`. Substitute the form that suits your system, or activate the virtual environment first so `python` points at it.

## Set up PostgreSQL and PostGIS

Skip this section if you only want to browse the catalogue.

### Install

**Windows.** Download the EDB installer for PostgreSQL 18 from [postgresql.org](https://www.postgresql.org/download/windows/). Keep the default components, which include the server, pgAdmin and the command line tools. Note the password you set for the `postgres` superuser and keep port 5432. At the end, let it launch **Stack Builder**, choose your PostgreSQL 18 server, and under **Spatial Extensions** tick the PostGIS bundle. The client tools end up in `C:\Program Files\PostgreSQL\18\bin`.

**macOS.** Either the EDB installer as above, which puts the tools in `/Library/PostgreSQL/18/bin`, or [Postgres.app](https://postgresapp.com/), which includes PostGIS and puts them in `/Applications/Postgres.app/Contents/Versions/18/bin`. With Homebrew (`brew install postgresql@18 postgis`) they are in `/opt/homebrew/opt/postgresql@18/bin`.

**Linux (Debian and Ubuntu).** Most releases ship an older PostgreSQL, so add the PostgreSQL project's own apt repository first. These are the same steps the Dockerfile uses:

```bash
sudo apt install -y curl ca-certificates
sudo install -d /usr/share/postgresql-common/pgdg
sudo curl -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc --fail https://www.postgresql.org/media/keys/ACCC4CF8.asc
. /etc/os-release
echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] https://apt.postgresql.org/pub/repos/apt $VERSION_CODENAME-pgdg main" | sudo tee /etc/apt/sources.list.d/pgdg.list
sudo apt update
```

Then install the server, PostGIS and the client tools:

```bash
sudo apt install -y postgresql-18 postgresql-18-postgis-3
```

As a shortcut, the `postgresql-common` package carries a script that does the repository steps for you: `sudo apt install -y postgresql-common` then `sudo /usr/share/postgresql-common/pgdg/apt.postgresql.org.sh`.

On a machine that already runs an older PostgreSQL, the new server takes the next free port, usually 5433. `pg_lsclusters` shows which port each version listens on.

The tools are in `/usr/lib/postgresql/18/bin`.

### Create the database and user

Give the client its own database and a user that can reach only that database, so it never holds the superuser's password. Connect as the `postgres` superuser, with `psql -U postgres -h localhost` (or `sudo -u postgres psql` on Linux), or with the query tool in pgAdmin or DBeaver, and run:

```sql
CREATE ROLE vicmap LOGIN PASSWORD 'vicmap'
  NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS;

CREATE DATABASE vicmap;

GRANT CREATE ON DATABASE vicmap TO vicmap;
```

PostGIS has to be installed inside the `vicmap` database itself, still as the superuser. In `psql`, switch to it first:

```sql
\c vicmap
CREATE EXTENSION postgis;
SELECT postgis_full_version();
```

In pgAdmin or DBeaver, open a new query window connected to the `vicmap` database instead of `postgres` before running the `CREATE EXTENSION`. Creating the extension while connected to `postgres` is the most common setup mistake, and the client then reports that PostGIS is missing.

`GRANT CREATE` lets the `vicmap` user create the schemas it loads into. The client creates `vm_meta`, `vm_delta`, `miscsupply` and `home` when you first test the connection, then one schema per Vicmap product (`vmadd`, `vmtrans` and so on) as layers arrive.

If your installer added the `tiger`, `tiger_data` or `topology` schemas, you can drop them. The client does not use them.

The username and password `vicmap` are a deliberate low security default, explained under [Security](#security). Choose stronger ones if your organisation requires it.

### A database browser

pgAdmin comes with the EDB installer. [DBeaver](https://dbeaver.io/download/) is worth installing too because it can draw geometry, which makes checking a layer much quicker.

## Register and configure

You can configure the client in its window or on the command line. Both write the same `config.ini` in the `VLRS` folder. That file holds your API key and database password, so keep it to yourself. It is already excluded from git.

### In the window

Run `python deltaVic.py`. The window opens on **Setup & QA**.

1. **Register.** Enter your email and press **Refresh** in the registration checks. VLRS issues a client ID and emails you a validation link.
2. **Validate.** Click the link in the email, then press **Refresh** again. VLRS issues the default Open Data API key, both checks turn green, and the **Meta** tab fills in.
3. **Database.** Fill in Endpoint (the host), Instance (the database name), Port, Username and Password, which are `localhost`, `vicmap`, `5432`, `vicmap` and `vicmap` if you followed the steps above, and the Bin path holding `pg_restore`. The platform's usual location is filled in for you.
4. **Test.** Press **Test database**. It saves the form and checks, in order, that it can connect, that the client tools are there, that PostGIS is installed and that the `vm_meta` tables exist, creating them if they are not. It stops at the first failure.

Once all four pass, the **Data** tab fills in and the boxes on the **Meta** tab become active.

`guide/gui_guide.html` shows each of these controls with numbered pointers.

### On the command line

```bash
python deltaVic.py setup
```

The first run asks for your email, registers it, and exits once VLRS has sent the validation email. Click the link, then run it again:

```bash
python deltaVic.py setup
```

The second run fetches your API key and asks for each database setting in turn. Press Enter to accept the default shown in brackets. It then runs the same four checks as the window and loads the catalogue of layers into `vm_meta.data`.

### More than one setup

Each section of `config.ini` is a profile with its own registration and database. The window has a profile selector. The command line always uses the `default` profile. To register a second setup with the same mailbox, use a plus address, such as `someone+dev@example.com`.

## Choose your layers

New layers start switched off, so nothing downloads until you choose.

**In the window**, open the **Meta** tab, pick a schema, and tick the layers you want, or use **All on** and **All off** for the whole schema. Each change is saved to the database at once.

**In SQL**, set `active` in `vm_meta.data`:

```sql
-- everything
UPDATE vm_meta.data SET active = true;

-- nothing
UPDATE vm_meta.data SET active = false;

-- one layer, or a list
UPDATE vm_meta.data SET active = true WHERE identity = 'vmtrans.tr_road';
UPDATE vm_meta.data SET active = true WHERE identity IN ('vmadd.address', 'vmprop.centroid');

-- one contract
UPDATE vm_meta.data SET active = true WHERE sup = 'VLAT';
UPDATE vm_meta.data SET active = true WHERE sup = 'VTT';

-- everything except the history archives, which are most of the disk space
UPDATE vm_meta.data SET active = true WHERE identity NOT LIKE 'vmhist.%';
```

**For a small starter set**, `python deltaVic.py core` switches everything off and then switches on only the small, widely used schemas: `vmlite`, `vmposition`, `vmcltenure`, `vmreftab`, `vmadmin` and `vmindex`.

To have layers VLRS adds in future switched on automatically, set `sync_all = True` in your `config.ini` profile.

## Sync

**In the window**, press **SYNC** on the Setup & QA tab. It reads SYNCING while it runs, and the window stays usable. Progress is logged in the terminal the client was started from and in `deltaVic.log`.

**On the command line**:

```bash
python deltaVic.py sync
```

The first sync downloads every active layer in full, so expect it to take a while. Later syncs only fetch what has changed.

At the end of each run the log shows a timings report, the seconds spent in each step summed over every layer, and the total duration. The command exits with status 1 if the run failed, so a scheduler can tell.

To check what you hold:

```sql
SELECT identity, sup, sup_ver, sup_type, sup_date, status, err, edit_date
  FROM vm_meta.data
 WHERE active
 ORDER BY edit_date DESC;
```

## Schedule it

Run `sync` every hour, at a minute of your own choosing rather than on the hour, so the load on VLRS is spread out. Make sure a new run cannot start while the previous one is still going.

VLAT and VTT usually update on Friday night after business hours, but can be late, so do not rely on a single Saturday run. MISC layers can change at any time in the week.

How you schedule it matters less than two things: the run has to start in the `VLRS` folder, and a new run must not start while the last one is still going. A first full sync takes hours, so an hourly schedule will overlap it unless something stops the second run.

**Linux (systemd timer, recommended).** Any distribution that uses systemd already has everything needed. A timer never starts a service that is still running, so overlap cannot happen, the output goes to the journal, and a failed run shows up in `systemctl --failed`. Create two files as root, with your own user and paths.

`/etc/systemd/system/vlrs-sync.service`:

```ini
[Unit]
Description=VLRS sync
Wants=network-online.target
After=network-online.target postgresql.service

[Service]
Type=oneshot
User=you
WorkingDirectory=/home/you/VLRS
ExecStart=/home/you/VLRS/.venv/bin/python deltaVic.py sync
TimeoutStartSec=infinity
```

`/etc/systemd/system/vlrs-sync.timer`:

```ini
[Unit]
Description=Run the VLRS sync hourly

[Timer]
OnCalendar=hourly
RandomizedDelaySec=1h
FixedRandomDelay=true
Persistent=true

[Install]
WantedBy=timers.target
```

`RandomizedDelaySec` with `FixedRandomDelay` gives each machine its own fixed minute in the hour, which spreads the load on VLRS without you choosing one. `Persistent` runs a sync at boot if the machine was off when one was due.

Turn it on, then check it:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now vlrs-sync.timer
systemctl list-timers vlrs-sync.timer      # when it runs next
sudo systemctl start vlrs-sync.service     # run one now, it waits until the sync ends
journalctl -u vlrs-sync.service -e         # what the last runs printed
```

**Linux without systemd, and macOS (cron).** Cron starts a job on time whether or not the last one has finished, so it needs `flock` beside it to skip a run while one is still going. `flock` is part of util-linux and already installed on Debian and Ubuntu. Cron itself is not on every minimal install, and `sudo apt install cron` adds it. `crontab -e`, then a line like this, which runs at 17 minutes past each hour:

```cron
17 * * * * cd /path/to/VLRS && flock -n /tmp/vlrs-sync.lock .venv/bin/python deltaVic.py sync >/dev/null 2>&1
```

macOS has cron but no `flock`. Install it with `brew install flock`, or leave it out if you are sure a run never lasts an hour.

**Windows (Task Scheduler).** Create a task with:

- Trigger: daily, repeat every 1 hour, starting at a minute of your choosing.
- Action: start a program. Program `C:\path\to\VLRS\.venv\Scripts\python.exe`, arguments `deltaVic.py sync`, and **Start in** `C:\path\to\VLRS`. Without the Start in folder the client cannot find its configuration.
- Settings: "If the task is already running" set to "Do not start a new instance".

## Command reference

`python deltaVic.py <action> [arguments]`. Every action except `gui` and `upload` uses the `default` profile.

| Action | What it does |
|---|---|
| *(none)* or `gui` | Opens the window |
| `setup` | Registers, configures the database and loads the catalogue, prompting for anything missing |
| `status` | Prints the profile's settings, including the password and API key, then lists every layer in error with its message |
| `sync` | Brings every active layer up to date |
| `core` | Switches every layer off, then on for the small core schemas listed above |
| `fixErrs` | Clears every error and queues those layers for a full reload on the next sync |
| `clean db` | Runs `VACUUM` and `ANALYZE` on every table the client manages |
| `clean files` | Deletes leftover downloads in `temp` |
| `upload <profile> <schema.table>` | Uploads the changes in a local MISC table to VLRS as a new supply. Needs write rights on that layer |
| `scorch` | Drops every table the client manages and empties `vm_meta.data`. Irreversible, and the next sync starts again from nothing |

## Configuration reference

`config.ini` is created on first run. Each section is a profile, and `[default]` is the one the command line uses.

| Key | Meaning |
|---|---|
| `baseUrl` | The VLRS API address. Leave as created |
| `email` | Your registered email |
| `client_id`, `api_key` | Issued by VLRS when you register and validate. Do not share them |
| `dbHost`, `dbPort`, `dbName`, `dbUser`, `dbPswd` | Your PostGIS database |
| `dbClientPath` | Folder holding `pg_restore` and `pg_dump` |
| `sync_all` | `True` switches on layers VLRS adds in future as they appear. Default `False` |
| `log_level` | `10` debug, `20` info (default), `30` warnings only |
| `regComplete`, `dbComplete` | Written by the checks. Leave them alone |

Environment variables take precedence over the file, which lets a container run with no `config.ini` at all. The names carry a `VES_` prefix because the VES deployment is what sets them.

| Variable | Overrides |
|---|---|
| `VES_DB_HOST`, `VES_DB_PORT`, `VES_DB_NAME`, `VES_DB_USER`, `VES_DB_PSWD` | The database settings |
| `VES_DB_CLIENT_PATH` | `dbClientPath` |
| `VES_SYNC_BASE_URL` | `baseUrl` |
| `VES_SYNC_EMAIL`, `VES_SYNC_CLIENT_ID`, `VES_SYNC_API_KEY` | The registration |

## Running in Docker

The image bundles Python and the PostgreSQL 18 client tools, so only the database lives outside it. Build it from the `VLRS` folder:

```bash
docker build -t vlrs .
```

Configure it by mounting a `config.ini` from the host so the settings survive the container. Inside the image the client lives in `/deltaVic`.

```bash
touch config.ini
docker run -it --network=host -v "$PWD/config.ini:/deltaVic/config.ini" vlrs setup
```

- `-it` lets you answer the setup prompts.
- `--network=host` lets the container reach PostGIS on the host as `localhost`. On Docker Desktop for Windows and macOS, use `host.docker.internal` as the database host instead.
- When setup asks for the client path, give `/usr/lib/postgresql/18/bin`, the location inside the image.

Choose your layers as described in [Choose your layers](#choose-your-layers), then sync:

```bash
docker run --network=host -v "$PWD/config.ini:/deltaVic/config.ini" vlrs sync
```

Instead of mounting a file you can pass the settings as environment variables, listed in the [configuration reference](#configuration-reference).

## Troubleshooting

Start with the error recorded against the layer:

```sql
SELECT identity, status, extradata->>'error' AS error
  FROM vm_meta.data
 WHERE err;
```

or run `python deltaVic.py status`.

| Symptom | Cause and fix |
|---|---|
| `Supply misreconciled: count(...) chkSum(...)` | The table's rows no longer match what VLRS sent. Almost always the local table has been edited. Every later supply for that layer will fail the same way. Reload it with **Reseed** on the Meta tab, or `fixErrs` for every failed layer, then sync |
| `Problem getting stats` | The table is missing its key column or the column VLRS checks against. A reload fails at the same point. Report it to the support address |
| `unsupported version in file header` | `pg_restore` is older than 18. Install the 18 client tools and point the client path at them |
| PostGIS check fails, or `PostGis has not been installed in the vicmap database` | The extension was created in the wrong database. Connect to `vicmap` as the superuser and run `CREATE EXTENSION postgis;` |
| `Connection refused` | PostgreSQL is not running, or the host or port is wrong |
| `password authentication failed` | Wrong username or password in the profile |
| `relation "vm_meta.data" does not exist` | The database has not been set up yet. Press **Test database** or run `setup` |
| `Client_id not yet verified` | Click the validation link VLRS emailed you, then Refresh or run `setup` again |
| A layer sits at `WAIT` | VLRS has announced a supply that is not ready yet. The next sync picks it up |
| `config.ini` or `data.sql` not found, or a fresh `config.ini` appears somewhere unexpected | The client was started from another folder. Run it from inside `VLRS` |

Do not edit tables the client manages. Copy what you need into a schema of your own, such as `home`, and edit it there.

If an incremental sync of everything regularly takes much longer than 10 minutes, let the support team know at vicmap.help@transport.vic.gov.au.

## Security

Report any security flaw to vicmap.help@transport.vic.gov.au, in particular:

- any way to use the VLRS endpoints without an active client ID, other than registering
- any restricted dataset reachable with the default Open Data API key

### Securing your database

The client is provided under the MIT licence, and VLRS takes no responsibility for how you run it. Checking that your copy is current and working as intended is up to you.

A VLRS database is disposable. You can move to a new one and reload it from VLRS at any time, so it holds nothing that cannot be replaced. That is why the defaults are low security: port 5432, a database called `vicmap` rather than the `postgres` one, and a `vicmap` user with password `vicmap` that can reach only that database. The client authenticates to VLRS with its client ID, not with these credentials.

Tighten that to suit your organisation:

- If the database is reachable from the internet, change the port and use a strong password.
- On a cloud database, such as AWS RDS, allow only known addresses through a security group.
- Give each downstream system its own database user rather than sharing `vicmap`.

### Staging and production

Treat the database the client writes to as staging. Sync it hourly, check currency and errors there, through the log or `vm_meta.data`, and only copy to production on your own schedule once you are satisfied. Pause the scheduled sync while you copy.
