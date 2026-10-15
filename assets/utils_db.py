import os
from pathlib import Path
import psycopg2
import time
import platform
import logging
from collections import OrderedDict
from typing import Any, TypeVar
from collections.abc import Sequence
from .utils import Config, FileUtils as FU, Supplies

# The row class a caller asks getRecSet for, so it gets that class back rather than
# a list of anything. Not bound to DBTable, which lives in a module that imports this one.
_Row = TypeVar("_Row")

# What psycopg2 gives back: a tuple per row, whatever the columns hold. Named here so
# every wrapper below says the same thing.
Row = tuple[Any, ...]
Rows = list[Row]

# class DBConn():
#   def __init__(self, host, port, dbname, uname, pswd):
#     self.host = host
#     self.port = port
#     self.dbname = dbname
#     self.uname = uname
#     self.pswd = pswd


class PGClient:
  def __init__(self, db: DB, dbClientPath: str, dPath: str = 'temp'):  # pass in config?
    self.db = db
    self.dbClientPath = dbClientPath

    """Database connections manages using PGPASSFILE as outlined in https://www.postgresql.org/docs/9.3/libpq-pgpass.html"""
    _strTime = str(time.time()).replace('.', '')
    pgpassFileName = f".{db.dbname}_{_strTime}.pgpgpass"
    Path(dPath).mkdir(parents=True, exist_ok=True)
    self.pgPassPath = str(Path(dPath) / pgpassFileName)

  def clientPath(self, client: str) -> str:
    path = str(Path(self.dbClientPath) / client)
    if platform.system().lower() == 'windows':
      path += '.exe'
    return path

  def create_credential(self):
    # print(f"create_credential: {self.db.getCredStr()}")
    """Creates a pg credential file to connect to the database."""
    pgpFile = os.open(self.pgPassPath, os.O_CREAT | os.O_WRONLY, 0o600)
    os.write(pgpFile, str.encode(self.db.getCredStr()))
    os.close(pgpFile)
    os.environ["PGPASSFILE"] = (
      self.pgPassPath
    )  # need to redeclare in case we are using 2*PGClients.

  def delete_credential(self):
    """Deletes the pg credentials file."""
    Path(self.pgPassPath).unlink(missing_ok=True)
    del os.environ["PGPASSFILE"]

  # @staticmethod
  def run_command(self, command_parts: list[str]) -> str:
    _msgStr = ""
    try:
      if self.db:  # NB: "--version" check does not require credentials.
        self.create_credential()
      _msgStr = FU.run_sub(command_parts)
    except Exception as ex:
      raise Exception(str(ex)) from ex
    finally:
      self.delete_credential()

    return _msgStr

  def restore_file(self, fileStr: str, plain: bool = False):  # used in λ.VML_restore.restore()
    """imports a table from a pgdump file"""
    """pg_restore --host=localhost --port=5432 --dbname=vicmap --username=vicmap --clean --if-exists --no-owner --no-privileges --no-acl --no-security-labels --no-tablespaces  vmreftab.hy_substance_extracted"""
    # NB: will not drop table if it has a dependant view, resulting in duplicate records.
    if plain:
      # NB: command_parts array failing on password for psql. Introduced subprocess caller instead
      command = f"{self.clientPath('psql')} -h localhost -d vicmap -U vicmap -f {fileStr}"
      os.environ["PGPASSWORD"] = "vicmap"
      _msgStr = FU.runSubprocess(command)
      del os.environ["PGPASSWORD"]  # os.environ.pop("PGPASSWORD")
      return _msgStr
    command_parts = [self.clientPath("pg_restore")]
    command_parts.extend(self.db.getConnArgs())
    command_parts.extend(
      [
        "--clean",
        "--if-exists",
        "--no-owner",
        "--no-privileges",
        "--no-acl",
        "--no-security-labels",
        "--no-tablespaces",
      ]
    )
    command_parts.append(fileStr)
    return self.run_command(command_parts)

  def get_restore_version(self):  # used in VML_setup.vicmap_deploy
    """Get version of pg restore operation."""
    return self.run_command([self.clientPath("pg_restore"), "--version"])

  # def get_dump_version(self): # not currently used.
  #     """Get version of pg dump operation."""
  #     return self.run_command([self.clientPath("pg_dump"),"--version"])

  def dump_file(self, table: str, file: str, args: list[str] | None = None) -> str:
    command_parts = [self.clientPath("pg_dump")]
    command_parts.extend(self.db.getConnArgs())
    command_parts.extend(["--format=c", f"--table={table}", f"--file={file}"])
    if args:
      command_parts.extend(args)
    return self.run_command(command_parts)

  def dump_ddl(self, table: str, file: str) -> str:
    command_parts = [self.clientPath("pg_dump")]
    command_parts.extend(self.db.getConnArgs())
    command_parts.extend(["--schema-only", f"--table={table}", f"--file={file}"])
    return self.run_command(command_parts)


class DB:
  def __init__(self, config: Config | list[str]):  # host, port, dbname, uname, pswd):
    if isinstance(config, list):
      self.host = config[0]
      self.port = config[1]
      self.dbname = config[2]
      self.uname = config[3]
      self.pswd = config[4]
    elif isinstance(config, Config):  # pyright: ignore[reportUnnecessaryIsInstance]
      self.host = config.get('dbHost')
      self.port = config.get('dbPort')
      self.dbname = config.get('dbName')
      self.uname = config.get('dbUser')
      self.pswd = config.get('dbPswd')
    else:
      raise Exception(f"Wrong object ({type(config)}) passed to DB.init")

    # psycopg2 ships no stubs, so the connection and cursor are stated as Any here and
    # the untypedness stops at this line rather than spreading through every query.
    self.cnxn: Any
    self.curs: Any
    self.cnxn, self.curs = self.connect()

  def connect(self) -> tuple[Any, Any]:
    _cnxn = psycopg2.connect(
      host=self.host, port=self.port, dbname=self.dbname, user=self.uname, password=self.pswd
    )
    _cnxn.set_session(autocommit=True)
    return _cnxn, _cnxn.cursor()

  def close(self) -> None:
    self.curs.close()
    self.cnxn.close()

  def getConnArgs(self) -> list[str]:
    # returns a list of args for use in the pg client.
    command_parts: list[str] = []
    command_parts.append(f"--host={self.host}")
    command_parts.append(f"--port={self.port}")
    command_parts.append(f"--dbname={self.dbname}")
    command_parts.append(f"--username={self.uname}")
    return command_parts

  def getCredStr(self) -> str:
    return ":".join([self.host, str(self.port), self.dbname, self.uname, self.pswd])

  def execute(self, sqlStr: str, params: Sequence[object] | None = None) -> Rows:
    # psycopg2 will pass back a tuple of tuples as a result: ((,,,),(,,,), ..)
    logging.debug(f"SQL: {sqlStr} Parameters: {params}")
    self.curs.execute(sqlStr, params) if params else self.curs.execute(sqlStr)
    # field_name_list = [desc.name for desc in curs.description]
    # if msg := curs.statusmessage: logging.info(msg)
    data: Rows = []
    if self.curs.description is None:  # test if nothing is returned, ie: when running an update
      pass
    else:
      data = self.curs.fetchall()
    return data

  # rows(), row() & item() will wrap execute() and shape the returned tuples
  def rows(self, sqlStr: str, params: Sequence[object] | None = None) -> Rows:
    result = self.execute(sqlStr, params)
    return result or []

  def row(self, sqlStr: str, params: Sequence[object] | None = None) -> Sequence[Any]:
    result = self.execute(sqlStr, params)
    return result[0] if result else ()

  def item(self, sqlStr: str, params: Sequence[object] | None = None) -> Any:
    result = self.execute(sqlStr, params)
    return result[0][0] if result else None

  def getRecSet(self, classyObj: type[_Row]) -> list[_Row]:
    # listmaker and the row constructor are the contract every dbTable class keeps, and
    # naming that here would need the import this module cannot have.
    data = self.rows(classyObj.listmaker())  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType, reportUnknownArgumentType]
    return [classyObj(row) for row in data] if data else []  # pyright: ignore[reportCallIssue]

  def getSchemas(self) -> list[str]:
    sqlStr = (
      "select schema_name from information_schema.schemata"
      + " where schema_name not in ('public','tiger','information_schema')"
      + " and schema_name not like 'pg_%'"
      + " order by schema_name asc"
    )
    schemas = self.rows(sqlStr)
    return [sch[0] for sch in schemas] if schemas else []

  def createSch(self, sch: str) -> None:
    self.execute(f"CREATE SCHEMA IF NOT EXISTS {sch}")

  def getTables(self, schema: str) -> list[str]:
    """get all table names from a schema"""
    sqlStr = f"SELECT table_name FROM information_schema.tables WHERE table_schema = '{schema}' order by table_name"
    data = self.rows(sqlStr)
    return [t[0] for t in data] if data else []  # return a list of the table names

  def getCount(self, table: str) -> int:
    sqlStr = f"SELECT COUNT(*) FROM {table}"
    data = self.execute(sqlStr)
    return data[0][0] if len(data) > 0 else 0

  def getTblStats(self, tblQual: str, ufiCreatedCol: str, pkey: str | None) -> list[Any]:
    colsDict = self.getAllColsDict(tblQual)
    _ufiCr = f"max({ufiCreatedCol})" if ufiCreatedCol in colsDict else "now()::timestamp"
    # A dataset can say it has no key, in which case there is no type to look up. A
    # key that is named but absent from the table is a malformed dataset, so the
    # lookup is still left to raise.
    if pkey and pkey != 'none':
      pkeyType = [cType for cName, cType in colsDict.items() if cName == pkey][
        0
      ]  # throws IndexError if pkey does not exist in colset.
    else:
      pkeyType = ""
    logging.debug(f"pkeyType: {pkeyType}")

    if not any(pkeyType.startswith(cType) for cType in ['int', 'smallint', 'bigint']):
      sqlStr = f"SELECT {_ufiCr}, 0, COUNT(*), 0 FROM {tblQual}"
    else:
      sqlStr = f"SELECT {_ufiCr}, max({pkey}), COUNT({pkey}), SUM({pkey}) FROM {tblQual}"
    data = self.execute(sqlStr)
    if len(data) > 0:
      stats = list(data[0])
      stats[2] = (
        stats[2] or -1
      )  # if there was a table mal-structure, sql returns nulls. Avoid. These cause issues in Datasets()
      return stats
    raise Exception(f"Could not get table stats for {tblQual}. Does it exist?")

  def fixErrs(self, ident: str | None = None) -> None:
    if ident:
      sqlStr = f"update vm_meta.data set status='QUEUED', sup_ver=-1 , sup_type='{Supplies.FULL}' where identity='{ident}'"
    else:
      sqlStr = "update vm_meta.data set status='QUEUED', sup_ver=-1, err=false, extradata=jsonb(extradata)-'error' where err=true"
    self.execute(sqlStr)

  def analVac(self, ident: str) -> None:  # analyze and vaccuume
    logging.debug(f"{ident}: Analysing and Vaccuuming")
    self.execute(f"analyze {ident}")  # vmadd.address=14seconds
    self.execute(f"vacuum {ident}")  # vmadd.address=12seconds

  ###########################################################################
  def table_exists(self, tblQual: str) -> bool:
    """Check table or view exists"""
    sqlStr = f"SELECT table_name FROM information_schema.tables WHERE table_schema||'.'||table_name = '{tblQual}'"
    table = self.item(sqlStr)
    return bool(table)  # if len(data) > 0

  def truncate(self, tblQual: str):
    try:
      sqlStr = f"TRUNCATE TABLE {tblQual}"
      self.execute(sqlStr)  # don't require return values
    except Exception as ex:
      return str(ex)
    return ""

  def copyTable(self, srcTblQual: str, tgtTblQual: str) -> None:
    if self.table_exists(tgtTblQual):
      self.dropTable(tgtTblQual)
    self.execute(f"CREATE TABLE {tgtTblQual} as select * from {srcTblQual}")

  def dropTable(self, tblQual: str) -> None:
    logging.debug(f"Dropping table {tblQual}")
    self.execute(f"DROP TABLE IF EXISTS {tblQual} CASCADE")  # don't require return values

  def columnExists(self, tblQual: str, tblCol: str) -> bool:
    return tblCol in self.getAllCols(tblQual)

  def getAllCols(self, tblQual: str) -> list[str]:
    """get all table column names and data types from a table"""
    sqlStr = f"SELECT column_name FROM information_schema.columns WHERE table_schema||'.'||table_name = '{tblQual}' order by ordinal_position asc"
    data = self.execute(sqlStr)
    return [c[0] for c in data]  # return a list of the column names

  def getAllColsDict(self, tblQual: str) -> OrderedDict[str, str]:
    """get all table column names from a table"""
    sqlStr = (
      "SELECT att.attname AS column_name, pg_catalog.format_type(att.atttypid, att.atttypmod) AS data_type"
      + " FROM pg_catalog.pg_attribute att, pg_catalog.pg_class cls, pg_catalog.pg_namespace nmsp"
      + " WHERE cls.oid = att.attrelid"
      + " AND nmsp.oid = cls.relnamespace"
      + " AND att.attnum > 0"
      + " AND NOT att.attisdropped"
      + f" AND nmsp.nspname||'.'||cls.relname = '{tblQual}'"
      + " ORDER BY attnum ASC"
    )
    data = self.execute(sqlStr)
    # return [f"{c[0]}::{c[1].replace('character varying','varchar')}" for c in data] # return a list of the column names
    _colDict: OrderedDict[str, str] = OrderedDict()
    [_colDict.update({c[0]: c[1].replace('character varying', 'varchar')}) for c in data]
    return _colDict  # return a dict of the column names and types
    # return [f"{c[0]}::{c[1].replace('character varying','varchar')}" for c in data] # return a list of the column names
