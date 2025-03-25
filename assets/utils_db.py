import os, sys, psycopg2, time, platform, logging
from collections import OrderedDict
from pathlib import Path
from .utils import Config, FileUtils as FU

# class DBConn():
#   def __init__(self, host, port, dbname, uname, pswd):
#     self.host = host
#     self.port = port
#     self.dbname = dbname
#     self.uname = uname
#     self.pswd = pswd

class PGClient():
  def __init__(self, db, dbClientPath):
    self.db = db
    self.dbClientPath = dbClientPath

    """Database connections manages using PGPASSFILE as outlined in https://www.postgresql.org/docs/9.3/libpq-pgpass.html"""
    pgpassFileName = ".vicmap_load_{0}.pgpgpass".format(str(time.time()).replace(".", ""))
    self.pgpass_file = os.path.join(Path.home(), pgpassFileName)
    if not os.path.exists(Path.home()):
      if platform.system().lower() == "linux":
        self.pgpass_file = os.path.join("/tmp", pgpassFileName)
      else:
        self.pgpass_file = os.path.join("D:\\temp", pgpassFileName)

    os.environ["PGPASSFILE"] = self.pgpass_file

    self.checkEnv()

  def checkEnv(self):
      
    if "LIB_PATH" in os.environ.keys():
      logging.debug("Library data path: {0}".format(os.environ["LIB_PATH"]))

    #Check enviroment variables set for pgsql
    PGSQL_APPLICATION_NAME = "pgsql"
    pgsql_search_key = "/{0}".format(PGSQL_APPLICATION_NAME)
    plfm = platform.system().lower()
    logging.debug(f"platform: {plfm}")

    # NB: This block is a mess due to earlier exhaustive testing reuired on aws al2 machines
    if platform.system().lower() == "linux" and "LIB_PATH" in os.environ.keys():
      library_root = os.environ["LIB_PATH"]
      logging.debug(f"pgsql_search_key: {pgsql_search_key}")
      logging.debug("LD_LIBRARY_PATH: " + os.environ["LD_LIBRARY_PATH"])
      logging.debug("PATH: " + os.environ["PATH"])
      if pgsql_search_key not in os.environ["LD_LIBRARY_PATH"] or pgsql_search_key not in os.environ["PATH"] :
        pgsql_dir_bin = None
        pgsql_dir_lib = None
        logging.debug("Searching {0} to find pgsql ...".format(library_root))
        for root, dirs, files in os.walk(library_root):
          if root.split(os.path.sep)[-1:][0] == "bin":
            pgsql_dir_bin = root
          if root.split(os.path.sep)[-1:][0] == "lib":
            pgsql_dir_lib = root
        logging.debug("pgsql_dir_lib: {0}".format(pgsql_dir_lib))
        if pgsql_dir_lib not in os.environ["LD_LIBRARY_PATH"]:
          logging.debug("Adding {0} to LD_LIBRARY_PATH".format(pgsql_dir_lib))
          os.environ["LD_LIBRARY_PATH"] = "{0}:{1}".format(os.environ["LD_LIBRARY_PATH"], pgsql_dir_lib)
        if pgsql_dir_bin not in os.environ["PATH"]:
          logging.debug("Adding {0} to PATH".format(pgsql_dir_bin))
          os.environ["PATH"] = "{0}:{1}".format(os.environ['PATH'], pgsql_dir_bin)
    else:
        # sys.path.append(self.dbClientPath) # use this, from the config file to pg_dump & pg_restore.
        os.environ["PATH"] += os.pathsep + self.dbClientPath
        # logging.debug(f"sysPath: {sys.path}")
      
  def create_credential(self):
    """Creates a pg credential file to connect to the database."""
    pgpFile = os.open(self.pgpass_file, os.O_CREAT | os.O_WRONLY, 0o600)
    os.write(pgpFile, str.encode(self.db.getCredStr()))
    os.close(pgpFile)
  
  def delete_credential(self):
    """Deletes the pg credentials file."""
    if os.path.exists(self.pgpass_file):
      os.remove(self.pgpass_file)
  
  #@staticmethod
  def run_command(self, command_parts:list): # Sequence[str]
    _msgStr = ""
    if self.db: self.create_credential() # NB: "--version" check does not require credentials.
    
    try:
      _msgStr = FU.run_sub(command_parts)
    except Exception as ex:
      raise Exception(str(ex))
    finally:
      self.delete_credential()
    
    return _msgStr

  def restore_file(self, file: str): # used in λ.VML_restore.restore()
    """imports a table from a pgdump file"""
    """pg_restore --host=localhost --port=5432 --dbname=vicmap --username=vicmap --clean --if-exists --no-owner --no-privileges --no-acl --no-security-labels --no-tablespaces  vmreftab.hy_substance_extracted"""
    # NB: will not drop table if it has a dependant view, resulting in duplicate records.
    command_parts = ["pg_restore"]
    command_parts.extend(self.db.getConnArgs())
    command_parts.extend(["--clean", "--if-exists", "--no-owner", "--no-privileges", "--no-acl", "--no-security-labels", "--no-tablespaces"])
    command_parts.append(file)
    return self.run_command(command_parts)
      
  def get_restore_version(self): #used in VML_setup.vicmap_deploy
    """Get version of pg restore operation."""
    return self.run_command(["pg_restore","--version"])
  # def get_dump_version(self): # not currently used.
  #     """Get version of pg dump operation."""
  #     return self.run_command(["pg_dump","--version"])

  def dump_file(self, table: str, file: str):
    command_parts = ["pg_dump"]
    command_parts.extend(self.db.getConnArgs())
    command_parts.extend(["--format=c", f"--table={table}", f"--file={file}"])
    return self.run_command(command_parts)
  
  def dump_ddl(self, table: str, file: str):
    command_parts = ["pg_dump"]
    command_parts.extend(self.db.getConnArgs())
    command_parts.extend(["--schema-only", f"--table={table}", f"--file={file}"])
    return self.run_command(command_parts)
    
class DB():
  def __init__(self, config):#host, port, dbname, uname, pswd):
    if type(config) == list:
      self.host = config[0]
      self.port = config[1]
      self.dbname = config[2]
      self.uname = config[3]
      self.pswd = config[4]
    elif type(config) == Config:
      self.host = config.get('dbHost')
      self.port = config.get('dbPort')
      self.dbname = config.get('dbName')
      self.uname = config.get('dbUser')
      self.pswd = config.get('dbPswd')
    else:
      raise Exception(f"Wrong object ({type(config)}) passed to DB.init")
  # def __init__(self, detail:object):
  #   if isinstance(detail, DBConn):
  #     self.dbConn = detail
  #   elif isinstance(detail, dict):
  #     self.dbConn = DBConn(detail)

  def getConnArgs(self):
    #returns a list of args for use in the pg client.
    command_parts = []
    command_parts.append("--host={}".format(self.host))
    command_parts.append("--port={}".format(self.port))
    command_parts.append("--dbname={}".format(self.dbname))
    command_parts.append("--username={}".format(self.uname))
    return command_parts
  
  def getCredStr(self):
    return ":".join([self.host, str(self.port), self.dbname, self.uname, self.pswd])

  def connect(self):
    return psycopg2.connect(host=self.host, port=self.port, dbname=self.dbname, user=self.uname, password=self.pswd)
    
  def execute(self, sqlStr, params=None):
    # psycopg2 will pass back a tuple of tuples: ((,,,),(,,,), ..)
    logging.debug(f"SQL: {sqlStr} Parameters: {params}")
    data = []

    cnxn = self.connect()
    cnxn.set_session(autocommit=True)
    curs = cnxn.cursor()

    try:
      curs.execute(sqlStr, params) if params else curs.execute(sqlStr)
    except Exception as e:
      if curs: curs.close()
      if cnxn: cnxn.close()
      raise e
  
    if curs.description == None:
      #Use this if autocommit has not been set using connection.set_session(autocommit=True)
      #connection.commit()
      pass
    else:
      data = curs.fetchall()
    # field_name_list = [desc.name for desc in curs.description]

    # if msg := curs.statusmessage:
    #   logging.info(msg)
    
    curs.close()
    cnxn.close()

    return data

  def rows(self, sqlStr, params=None):
    result = self.execute(sqlStr, params)
    return result or []
  def row(self, sqlStr, params=None):
    result = self.execute(sqlStr, params)
    return result[0] if result else []
  def item(self, sqlStr, params=None):
    result = self.execute(sqlStr, params)
    return result[0][0] if result else None
  
  def getRecSet(self, classyObj):
      data = self.rows(classyObj.listmaker())
      return [classyObj(row) for row in data] if data else []
  
  def getSchemas(self):
    sqlStr = "select schema_name from information_schema.schemata" + \
      " where schema_name not in ('public','tiger','information_schema','pg_catalog')" + \
      " order by schema_name asc"
    schemas = self.rows(sqlStr)
    return [sch[0] for sch in schemas] if schemas else []

  def createSch(self, sch):
    self.execute(f"CREATE SCHEMA IF NOT EXISTS {sch}")
  
  def getTables(self, schema:str):
    """ get all table names from a schema """
    sqlStr = f"SELECT table_name FROM information_schema.tables WHERE table_schema = '{schema}'"
    data = self.rows(sqlStr)
    return [t[0] for t in data] if data else []# return a list of the table names

  def getCount(self, table):
    sqlStr = "SELECT COUNT(*) FROM {}".format(table)
    data = self.execute(sqlStr)
    return data[0][0] if len(data) > 0 else 0
  
  def getTblStats(self, tblQual, ufiCreatedCol, pkey):
    colsDict = self.getAllColsDict(tblQual)
    _ufiCr = f"max({ufiCreatedCol})" if ufiCreatedCol in colsDict.keys() else "now()::timestamp"
    pkeyType = [cType for cName, cType in colsDict.items() if cName==pkey][0]
    logging.debug(f"pkeyType: {pkeyType}")

    if pkey=='none' or not any(pkeyType.startswith(cType) for cType in ['int','bigint']):
      sqlStr = f"SELECT {_ufiCr}, 0, COUNT(*), 0 FROM {tblQual}"
    else:
      sqlStr = f"SELECT {_ufiCr}, max({pkey}), COUNT({pkey}), SUM({pkey}) FROM {tblQual}"
    data = self.execute(sqlStr)
    if len(data) > 0:
      stats = list(data[0])
      stats[2] = stats[2] or -1 # if there was a table mal-structure, sql returns nulls. Avoid. These cause issues in Datasets()
      return stats
    else:
      raise Exception("Could not get table stats for {}. Does it exist?".format(tblQual))
  
  def analVac(self, ident): # analyze and vaccuume
    logging.debug(f"{ident}: Analysing and Vaccuuming")
    self.execute(f"analyze {ident}") # vmadd.address=14seconds
    self.execute(f"vacuum {ident}") # vmadd.address=12seconds
    
  ###########################################################################
  def table_exists(self, tblQual:str):
    """ Check table or view exists """        
    sqlStr = "SELECT table_name FROM information_schema.tables WHERE table_schema||'.'||table_name = '{}'".format(tblQual)
    table = self.item(sqlStr)
    return True if table else False # if len(data) > 0

  def truncate(self, tblQual:str):
    try:
      sqlStr = "TRUNCATE TABLE {}".format(tblQual)
      self.execute(sqlStr) # don't require return values
    except Exception as ex:
        return str(ex)
    return ""
    
  def dropTable(self, tblQual:str):
    logging.debug(f"Dropping table {tblQual}")
    self.execute(f"DROP TABLE IF EXISTS {tblQual} CASCADE") # don't require return values
    
  def columnExists(self, tblQual:str, tblCol:str):
    return True if tblCol in self.getAllCols(tblQual) else False

  def getAllCols(self, tblQual:str):
    """ get all table column names and data types from a table """        
    sqlStr = "SELECT column_name FROM information_schema.columns WHERE table_schema||'.'||table_name = '{}' order by ordinal_position asc".format(tblQual)
    data = self.execute(sqlStr)
    return [c[0] for c in data] # return a list of the column names

  def getAllColsDict(self, tblQual:str):
    """ get all table column names from a table """        
    sqlStr = "SELECT att.attname AS column_name, pg_catalog.format_type(att.atttypid, att.atttypmod) AS data_type" + \
      " FROM pg_catalog.pg_attribute att, pg_catalog.pg_class cls, pg_catalog.pg_namespace nmsp" + \
      " WHERE cls.oid = att.attrelid" + \
      " AND nmsp.oid = cls.relnamespace" + \
      " AND att.attnum > 0" + \
      " AND NOT att.attisdropped" + \
      f" AND nmsp.nspname||'.'||cls.relname = '{tblQual}'" + \
      " ORDER BY attnum ASC"
    data = self.execute(sqlStr)
    # return [f"{c[0]}::{c[1].replace('character varying','varchar')}" for c in data] # return a list of the column names
    _colDict = OrderedDict()#{}
    [_colDict.update({c[0]:c[1].replace('character varying','varchar')}) for c in data]
    return _colDict # return a dict of the column names and types
    # return [f"{c[0]}::{c[1].replace('character varying','varchar')}" for c in data] # return a list of the column names
        
    