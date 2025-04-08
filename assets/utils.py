import os, logging, configparser, io, zipfile, shutil
from subprocess import Popen, PIPE
from glob import glob

class FileUtils():
  def __init__(self):
    pass

  @staticmethod
  def findFilesInRoot(root, fileName):
    findRegEx = "{}/**/{}".format(root, fileName) # regEx to find file.
    logging.debug(findRegEx)
    fileArr = glob(findRegEx, recursive=True) # py3.10 will allow root_dir as an arg here. https://docs.python.org/3.10/library/glob.html
    if not len(fileArr):
      logging.warning("Cannot find file(s) {} in root {}".format(fileName, root))
      return None
    else:
      return fileArr
  
  @staticmethod
  def sizeof_fmt(num, suffix="B"):
    for unit in ["", "Ki", "Mi", "Gi", "Ti", "Pi", "Ei", "Zi"]:
      if abs(num) < 1024.0:
        return f"{num:3.1f}{unit}{suffix}"
      num /= 1024.0
    return f"{num:.1f}Yi{suffix}"
  
  @staticmethod
  def createDir(pathy):
    if not os.path.exists(pathy):
      os.makedirs(pathy)
    return pathy
  
  @staticmethod
  def remove(path):
    logging.debug(f"removing path {path}")
    if os.path.isfile(path): os.remove(path)
    elif os.path.isdir(path): shutil.rmtree(path)
    else: logging.warn(f"{path} is not a file or a dir!! It may not exist")
  
  @staticmethod
  #create_dir create a directory with the name of the archive to place the contents of the archive into.
  def extract(vml_bucket, srcZipPath:str, tgt:str):
    logging.info("Extracting: {0} to {1}".format(srcZipPath, tgt))
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
  def run_sub(params:list):
    _msgStr, _errStr = "",""
    logging.debug(f"Sending Command: {' '.join(params)}")
    # logging.debug("FU.LD_LIBRARY_PATH: " + os.environ["LD_LIBRARY_PATH"])
    logging.debug("FU.PATH: " + os.environ["PATH"])
    
    # ["chmod","-R","a+x",dir] -- set execute recursive on dir
    # ["chmod","-R","a+rw",dir] -- set read/write recursive on dir
    # ["chmod","-R","a+r",dir] -- set read recursive on dir
    # the following will not pick up things that are on the path, hence the exceptions.
    if params[0] not in ['uname','ps','scp','env','chmod','pg_restore','pg_dump','psql'] and not os.path.exists(params[0]):
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
  def runSubprocess(command):
    import subprocess
    devnull = open(os.devnull, 'w')
    subprocess.call(command, stdout=devnull)

class Logger():
  @staticmethod
  def get():
    log_formatter = logging.Formatter('%(asctime)s[%(levelname)s]  %(message)s') # - %(name)s -
    _rootLog = logging.getLogger()
    _rootLog.level = logging.INFO
    try: # on aws the getLogger command get a handler automatically
      hdlr = _rootLog.handlers[0]
      hdlr.setFormatter(log_formatter)
    except IndexError: # otherwise we have to make the handler ourselves
      # log_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
      console_handler = logging.StreamHandler()
      console_handler.setFormatter(log_formatter)#'%(asctime)s - %(name)s - %(levelname)s - %(message)s'
      _rootLog.addHandler(console_handler)

      # formatter = logging.Formatter('%(asctime)s(%(levelname)8s): %(message)s', datefmt='%Y%m%d-%H:%M:%S')
      logFile = 'deltaVic.log'
      fh = logging.FileHandler(logFile, 'a' if os.path.exists(logFile) else 'w')
      fh.setLevel(logging.INFO)
      fh.setFormatter(log_formatter)
      _rootLog.addHandler(fh)

    return _rootLog

class Config():
  def __init__(self, filename, stg):
    self.cfgFile = filename
    self.cp = configparser.ConfigParser()
    self.cp.optionxform = str # keep it case sensitive
    if not self.cp.read(self.cfgFile):
      # create file
      self.cp[stg] = {'name':'deltaVic','log_level':20,'email':'somebody@example.org','baseUrl':'https://0mgxefxoib.execute-api.ap-southeast-2.amazonaws.com/vmmgr/'}
      # self.cp.add_section('default')
      self.write()
    self.setStage(stg)
  def write(self):#, cfg):
    with open(self.cfgFile, 'w') as newCfg:
      self.cp.write(newCfg)
  def append(self):#, cfg):
    with open(self.cfgFile, 'a') as oldCfg:
      self.cp.write(oldCfg)
  def setStage(self, stage):
    if stage not in self.cp.sections():
      # self.cp.add_section(stage)
      self.cp[stage] = {'name':'deltaVic','log_level':20,'email':'somebody@example.org','baseUrl':'https://0mgxefxoib.execute-api.ap-southeast-2.amazonaws.com/vmmgr/'}
      self.write()
    self.stg = self.cp[stage]
  def getStage(self):
    return self.stg.name
  def get(self, key):
    if not self.stg:
      self.setStage('default')
    # return self.stg[key] if key in self.keys() else '' # .keys() will return set(keys) from all sections.
    _val=''
    try:
      _val = self.stg[key]
    except KeyError:
      pass # _val = ''
    return _val
  def set(self, keyValDict):
    if not self.stg:
      self.setStage('default')
    for key,val in keyValDict.items():
      self.stg[key] = val
    self.write()#append()?
  def keys(self):
    return dict(self.cp.items('default')).keys()

  def keysExist(self, keyArr): #cfg, 
    # test vars from config that should exist
    for var in keyArr:
      if not (val := self.get(var)):
        raise Exception(f"No key for {var} in config.ini")
      if not val:
        raise Exception(f"No value for {var} in config.ini")
    return True
###########################################################################

class Test():
  def __init__(self):
    logging.info("initting test")
  def cfg(self):
    config = Config('config.ini', 'default')
    # logging.info(self.config.get('email'))
    print(config.get('dbname'))
    print(config.get('dbnames'))
    config.setStage('default')
    print(config.keys())
    print(config.getStage())

  def db(self, db):
    result = db.item("select count(*) from eisedit.mapindex_100d")
    logging.info(f"result: {result} *")
    result = db.row("select count(*), sum(ufi) from eisedit.mapindex_100d")
    logging.info(f"result: {result} *")
    result = db.rows("select * from eisedit.mapindex_100d")
    rows = '\r'.join([str(r) for r in result])
    logging.info(f" count:{len(result)}\r result: {rows} *")
  def api(self, api):
    api.getDatasets()

###########################################################################

class Supplies(dict):
  # load types
  FULL = "full" # seed
  INC = "inc" # incremental

  @staticmethod
  def meta(supId):
    supsDict = {
      Supply_Lat.supply_id:Supply_Lat,
      Supply_Topo.supply_id:Supply_Topo,
      Supply_Misc.supply_id:Supply_Misc
    }
    return supsDict[supId]
  
class Supply_Lat():
  supply_id = 'VLAT'
  fams = ['VLAT_VLAT','VLAT_VM']
  supplyPrefix = "vlat" # supply prefix in the jacobs bucket
  # database_schema = "lat"
  supplySchema = "latsupply"
  loadSchema = "latload"
  trackingTable = "lat_supply_table_instance"
  # schema_list_product = ["vmadd", "vmadmin", "vmcltenure", "vmprop"]
  ufiCreateCol = "ufi_created"
  ufiRetireCol = "ufi_retired"
  pfiRetireCol = "pfi_retired"

class Supply_Topo():
  supply_id = 'VTT'
  fams = ['VTT_VTT','VTT_VM']
  supplyPrefix = "topo" # supply prefix in the jacobs bucket
  # database_schema = "topo"
  supplySchema = "toposupply"
  loadSchema = "topoload"
  trackingTable = "topo_supply_table_instance"
  # schema_list_product = ["vmelev", "vmfeat", "vmhydro", "vmindex", "vmtrans", "vmveg"]
  ufiCreateCol = "create_date_ufi"
  ufiRetireCol = "retire_date_ufi"
  pfiRetireCol = "retire_date_pfi"

class Supply_Misc():
  supply_id = 'MISC'
  fams = ['MISC']
  supplyPrefix = None
  # database_schema = "misc"
  supplySchema = "miscsupply"
  loadSchema = "misc"
  trackingTable = None # "vmdd.instance_registry"
  ufiCreateCol = "ufi_created"
  ufiRetireCol = "ufi_retired"
  pfiRetireCol = "pfi_retired"

###########################################################################

if __name__ == '__main__':
  test = Test()
  test.cfg()
