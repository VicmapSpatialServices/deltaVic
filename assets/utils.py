import os
import logging
import configparser
import platform
from collections.abc import KeysView
import io
import zipfile
import shutil
from subprocess import Popen, PIPE
from pathlib import Path
from typing import TYPE_CHECKING, Any

# Only for the annotations. utils_db imports this module, so importing it back at
# runtime would be a cycle.
if TYPE_CHECKING:
  from .utils_db import DB
  from .utils_api import ApiUtils

# The postgresql major version.
PG_MAJOR = '18'


# Different OS's install postgresql in unique locations, so check for platform
# and use the appropriate path.
def pgBinDefault() -> str:
  match platform.system().lower():
    case 'windows':
      return rf"C:\Program Files\PostgreSQL\{PG_MAJOR}\bin"
    case 'darwin':
      return f"/Library/PostgreSQL/{PG_MAJOR}/bin"
    case _:
      return f"/usr/lib/postgresql/{PG_MAJOR}/bin"


class FileUtils:
  def __init__(self):
    pass

  @staticmethod
  def sizeof_fmt(num: float, suffix: str = "B") -> str:
    for unit in ["", "Ki", "Mi", "Gi", "Ti", "Pi", "Ei", "Zi"]:
      if abs(num) < 1024.0:
        return f"{num:3.1f}{unit}{suffix}"
      num /= 1024.0
    return f"{num:.1f}Yi{suffix}"

  @staticmethod
  def createDir(pathy: str) -> str:
    Path(pathy).mkdir(parents=True, exist_ok=True)
    return pathy

  @staticmethod
  def remove(path: str | Path) -> None:
    logging.debug(f"removing path {path}")
    _path = Path(path)
    if _path.is_file():
      _path.unlink()
    elif _path.is_dir():
      shutil.rmtree(_path)
    else:
      logging.warning(f"{path} is not a file or a dir!! It may not exist")

  @staticmethod
  # create_dir create a directory with the name of the archive to place the contents of the archive into.
  def extract(vml_bucket: Any, srcZipPath: str, tgt: str) -> None:
    logging.info(f"Extracting: {srcZipPath} to {tgt}")
    file_stream = io.BytesIO()
    vml_bucket.download_fileobj(srcZipPath, file_stream)
    zf = zipfile.ZipFile(file_stream)
    zf.extractall(tgt)
    # return tgt

  # @staticmethod
  # def runProc(procArgs: list):
  #   logging.info(f"Running process {procArgs}")
  #   p = Popen(procArgs, stdout=PIPE, stderr=PIPE)
  #   stdout, stderr = p.communicate()

  @staticmethod
  def run_sub(params: list[str]) -> str:
    _msgStr, _errStr = "", ""
    logging.debug(f"Sending Command: {' '.join(params)}")
    # logging.debug("FU.LD_LIBRARY_PATH: " + os.environ["LD_LIBRARY_PATH"])
    logging.debug("FU.PATH: " + os.environ["PATH"])

    # ["chmod","-R","a+x",dir] -- set execute recursive on dir
    # ["chmod","-R","a+rw",dir] -- set read/write recursive on dir
    # ["chmod","-R","a+r",dir] -- set read recursive on dir
    # the following will not pick up things that are on the path, hence the exceptions.
    if (
      params[0]
      not in [
        'uname',
        'ps',
        'scp',
        'env',
        'chmod',
        'pg_restore',
        'pg_dump',
        'psql',
      ]
      and not Path(params[0]).exists()
    ):
      raise Exception(f"Path {params[0]} does not exist")

    proc = Popen(params, stderr=PIPE, stdout=PIPE)
    stdout, stderr = proc.communicate()

    if _msgStr := stdout.decode().rstrip():
      logging.debug(f"Command Response:{_msgStr}")
    if _errStr := stderr.decode():
      logging.error(f"Command Response Error:{_errStr}")
      raise Exception(_errStr)

    return _msgStr

  @staticmethod
  def runSubprocess(command: list[str] | str) -> None:
    import subprocess

    subprocess.call(command, stdout=subprocess.DEVNULL)


class Logger:
  @staticmethod
  def get():
    log_formatter = logging.Formatter('%(asctime)s[%(levelname)s]  %(message)s')  # - %(name)s -
    _rootLog = logging.getLogger()
    _rootLog.level = logging.INFO
    try:  # on aws the getLogger command get a handler automatically
      hdlr = _rootLog.handlers[0]
      hdlr.setFormatter(log_formatter)
    except IndexError:  # otherwise we have to make the handler ourselves
      # log_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
      console_handler = logging.StreamHandler()
      console_handler.setFormatter(
        log_formatter
      )  #'%(asctime)s - %(name)s - %(levelname)s - %(message)s'
      _rootLog.addHandler(console_handler)

      # formatter = logging.Formatter('%(asctime)s(%(levelname)8s): %(message)s', datefmt='%Y%m%d-%H:%M:%S')
      logFile = 'deltaVic.log'
      fh = logging.FileHandler(logFile, 'a' if Path(logFile).exists() else 'w')
      fh.setLevel(logging.INFO)
      fh.setFormatter(log_formatter)
      _rootLog.addHandler(fh)

    return _rootLog


# Config keys the environment supplies, and the variable each one reads.
ENV_KEYS = {
  'dbHost': 'VES_DB_HOST',
  'dbPort': 'VES_DB_PORT',
  'dbName': 'VES_DB_NAME',
  'dbUser': 'VES_DB_USER',
  'dbPswd': 'VES_DB_PSWD',
  'dbClientPath': 'VES_DB_CLIENT_PATH',
  'baseUrl': 'VES_SYNC_BASE_URL',
  'email': 'VES_SYNC_EMAIL',
  'client_id': 'VES_SYNC_CLIENT_ID',
  'api_key': 'VES_SYNC_API_KEY',
}


class Config:
  def __init__(self, filename: str, stg: str):
    self.cfgFile = filename
    self.cp = configparser.ConfigParser()
    # Assigning over optionxform is how configparser documents keeping keys case
    # sensitive, and typeshed declares it as a method, so the assignment reads as an error.
    self.cp.optionxform = str  # pyright: ignore[reportAttributeAccessIssue]
    if not self.cp.read(self.cfgFile):
      self.initDefaults(stg)
    self.setStage(stg)

  def initDefaults(self, stg: str) -> None:
    # self.cp.add_section('default')
    self.cp[stg] = {
      'name': 'deltaVic',
      'baseUrl': 'https://c6w2u7gu3d.execute-api.ap-southeast-2.amazonaws.com/vmapi/',
      # Strings, because that is what configparser stores.
      'log_level': '20',
      'sync_all': 'False',
      'regComplete': 'False',
      'dbComplete': 'False',
    }
    # update config file
    self.write()

  def write(self) -> None:  # , cfg):
    with open(self.cfgFile, 'w') as newCfg:
      self.cp.write(newCfg)

  def append(self) -> None:  # , cfg):
    with open(self.cfgFile, 'a') as oldCfg:
      self.cp.write(oldCfg)

  def setStage(self, stg: str) -> None:
    if stg not in self.cp.sections():
      self.initDefaults(stg)
    self.stg = self.cp[stg]

  def getStage(self) -> str:
    return self.stg.name

  def get(self, key: str) -> str:
    if not self.stg:
      self.setStage('default')
    # The environment variables are set first, because a container has no config.ini to
    # read. Environment variables are set by ves_plus/deploy/iac/ves_sync.yml.
    if env := os.environ.get(ENV_KEYS.get(key, '')):
      return env
    # return self.stg[key] if key in self.keys() else '' # .keys() will return set(keys) from all sections.
    return self.stg.get(key, '')

  def set(self, keyValDict: dict[str, str]) -> None:
    if not self.stg:
      self.setStage('default')
    for key, val in keyValDict.items():
      self.stg[key] = val
    self.write()  # append()?

  def keys(self) -> KeysView[str]:
    return dict(self.cp.items('default')).keys()

  def assess(self, reqTpl: tuple[str, str, str]) -> None:
    # cfgReqTuples is of form (key, default, description)
    key, default, desc = reqTpl
    if not self.get(key):
      val = input(f"Enter {desc} (default:{default}): ") or default
      self.set({key: val})

  def keysExist(self, keyArr: list[str]) -> bool:  # cfg,
    # test vars from config that should exist
    for var in keyArr:
      if not (val := self.get(var)):
        raise Exception(f"No key for {var} in config.ini")
      if not val:
        raise Exception(f"No value for {var} in config.ini")
    return True


###########################################################################


class Test:
  def __init__(self):
    logging.info("initting test")

  def cfg(self) -> None:
    config = Config('config.ini', 'default')
    # logging.info(self.config.get('email'))
    print(config.get('dbname'))
    print(config.get('dbnames'))
    config.setStage('default')
    print(config.keys())
    print(config.getStage())

  def db(self, db: DB) -> None:
    result = db.item("select count(*) from eisedit.mapindex_100d")
    logging.info(f"result: {result} *")
    result = db.row("select count(*), sum(ufi) from eisedit.mapindex_100d")
    logging.info(f"result: {result} *")
    result = db.rows("select * from eisedit.mapindex_100d")
    rows = '\r'.join([str(r) for r in result])
    logging.info(f" count:{len(result)}\r result: {rows} *")

  def api(self, api: ApiUtils) -> None:
    api.getData()


###########################################################################


class Supplies(dict[str, str]):
  # load types
  FULL = "full"  # seed
  DIFF = "diff"  # differencing - upload full table and let VLRS sort out the changes.
  INC = "inc"  # incremental

  @staticmethod
  def meta(supId: str) -> type[Supply_Lat | Supply_Topo | Supply_Misc]:
    supsDict = {
      Supply_Lat.supply_id: Supply_Lat,
      Supply_Topo.supply_id: Supply_Topo,
      Supply_Misc.supply_id: Supply_Misc,
    }
    return supsDict[supId]


class Supply_Lat:
  supply_id = 'VLAT'
  fams = ['VLAT_VLAT', 'VLAT_VM']
  supplyPrefix = "vlat"  # supply prefix in the jacobs bucket
  # database_schema = "lat"
  supplySchema = "latsupply"
  loadSchema = "latload"
  trackingTable = "lat_supply_table_instance"
  # schema_list_product = ["vmadd", "vmadmin", "vmcltenure", "vmprop"]
  ufiCreateCol = "ufi_created"
  ufiRetireCol = "ufi_retired"
  pfiRetireCol = "pfi_retired"


class Supply_Topo:
  supply_id = 'VTT'
  fams = ['VTT_VTT', 'VTT_VM']
  supplyPrefix = "topo"  # supply prefix in the jacobs bucket
  # database_schema = "topo"
  supplySchema = "toposupply"
  loadSchema = "topoload"
  trackingTable = "topo_supply_table_instance"
  # schema_list_product = ["vmelev", "vmfeat", "vmhydro", "vmindex", "vmtrans", "vmveg"]
  ufiCreateCol = "create_date_ufi"
  ufiRetireCol = "retire_date_ufi"
  pfiRetireCol = "retire_date_pfi"


class Supply_Misc:
  supply_id = 'MISC'
  fams = ['MISC']
  supplyPrefix = None
  # database_schema = "misc"
  supplySchema = "miscsupply"
  loadSchema = "misc"
  trackingTable = None  # "vmdd.instance_registry"
  ufiCreateCol = "ufi_created"
  ufiRetireCol = "ufi_retired"
  pfiRetireCol = "pfi_retired"


###########################################################################

if __name__ == '__main__':
  test = Test()
  test.cfg()
