import logging, re

from .utils_db import DB, PGClient
from .utils_api import ApiUtils
from .dbTable import LyrReg
from .utils import Supplies, Config

class Setup():
  def __init__(self, stg):
    self.config = Config('config.ini', stg)
    self.db = None
    self.dbSchemas = None

  def run(self):
    _qa = QA(self.config) # each event will throw an Exception unless it passes?
    
    # SETUP USER REGISTRATION
    print("\nAssessing registration...")
    cfgReqdTuples = [("email", "somebody+dvic@example.org", "your email")]
    [self.config.assess(crt) for crt in cfgReqdTuples]
    qaCode, qaMsg = _qa.checkApiClient()
    if qaCode < 2:
      print(qaMsg)
      return
      # self.logger.error(qaMsg)
      # raise Exception(qaMsg)
    
    # TEST DATABASE - exception will be thrown if it fails
    print("\nPerforming database configuration... (press enter for default).")
    cfgReqdTuples = [("dbHost", "localhost", "database host"), ("dbPort", "5432", "database port"), 
      ("dbName", "vicmap", "database name"), ("dbUser", "vicmap", "database username"), ("dbPswd", "vicmap", "database passowrd"), 
      ("dbClientPath", r"C:\Program Files\PostgreSQL\17\bin", "database client path")]
    [self.config.assess(crt) for crt in cfgReqdTuples]
    # CHECK THE DATABASE INTEGRITY
    if not _qa.checkDbControl(): return
    if not _qa.checkPostGis(): return
    if not _qa.checkPGClient(): return
    # POPULATE THE METADATA
    if not _qa.checkMetaData(): return
    
  def status(self):
    print(f"testing config file has all required keys for '{self.config.getStage()}' instance: {self.config}")
    print(f"dbCnxn: {self.config.stg['dbUser']}:{self.config.stg['dbPswd']}@{self.config.stg['dbHost']}:{self.config.stg['dbPort']}/{self.config.stg['dbName']}")
    print(f"Email: {self.config.stg['email']}")
    print(f"ClientId: {self.config.stg['client_id']}")
    print(f"ApiKey: {self.config.stg['api_key']}")
    print(f"deltaVic endpoint: {self.config.stg['baseUrl']}")

    _db = DB(self.config)
    lyrErrs = [ll for ll in _db.getRecSet(LyrReg) if ll.err]
    print("\nErrors:")
    for lyrErr in lyrErrs:
      print(f"{lyrErr.identity}: {lyrErr.extradata['error']}")
    # for key, val in self.config.items():
    #   print(f"{key}: {val}")#, self.cfg['key'])
  
  def core(self):
    self.db = DB(self.config)
    sqlFalsfier = "update vm_meta.data set active=false"
    self.db.execute(sqlFalsfier)
    # sqlNonHist = "update vm_meta.data set active=true where identity not like 'vlat%' and identity not like 'vtt%'"
    # self.db.execute(sqlNonHist)
    # sqlNonHist = "update vm_meta.data set active=true where identity not like 'vlat%' and identity not like 'vtt%'"
    # self.db.execute(sqlNonHist)
    # _sup="VLAT"
    # sqlSup = f"update vm_meta.data set active=true where sup='{_sup}'"
    # self.db.execute(sqlSup)
    sqlSmallButNumerous = ("update vm_meta.data set active=true where identity like 'vmlite%' or identity like 'vmposition%'"
      " or identity like 'vmcltenure%' or identity like 'vmreftab%' or identity like 'vmadmin%'"
      " or identity like 'vmindex%'")
    self.db.execute(sqlSmallButNumerous)
    
class QA():
  def __init__(self, cfg):
    self.cfg = cfg
    self.reset()
  def reset(self):
    self.qaDb = False
    self.qaSpat = False
    self.qaClt = False
    self.qaMeta = True
  
  def isDbReady(self):
    _success = "True" if all([self.qaDb, self.qaSpat, self.qaClt, self.qaMeta]) else "False"
    self.cfg.set({"dbComplete":_success})
    
  def checkApiClient(self):
    try:
      if not (_email := self.cfg.get('email')):
        return 0, "Email not set in config"
      elif _email == '':
        return 0, "You cannot register an empty email address" # checked on server end also.
      
      # if the client_id is null, we need to request/create it
      if not (_clientId := self.cfg.get('client_id')):
        logging.debug("Submitting email address to obtain a client_id")
        api = ApiUtils(self.cfg.get('baseUrl'), None, None) # No client-id passed
        rsp = api.post("register", {"email":_email})
        logging.debug("Updating config file with client_id...")
        _clientId = rsp['client_id']
        self.cfg.set({'client_id':_clientId})
        _msgStr = f"Client_id not yet verified, please check your inbox for {_email}"
        return 1, _msgStr # unverified
      
      if not (_apiKey := self.cfg.get("api_key")):
        logging.info("Submitting client_id to obtain an api-key")
        api = ApiUtils(self.cfg.get('baseUrl'), None, _clientId)
        rsp = api.post("register", {"email":_email})
        logging.info("Updating config file with api_key...")
        _apiKey = rsp['api_key']
        self.cfg.set({'api_key':_apiKey})
        # return 2
      
      self.cfg.set({"regComplete":"True"})
      # if all 3 registration attrs are present in config, then return 0?
      # try and avoind this registration call every time the gui is opened.
      # if the email adress has changed and is paired wiht the existing client-id, it is updated and revalidated?
      logging.debug(f"Submitting register call to obtain rights.")
      api = ApiUtils(self.cfg.get('baseUrl'), _apiKey, _clientId)
      rsp = api.post("register", {"email":_email})
      return 2, rsp['rights'] if 'rights' in rsp else "Registration"# "No rights" # all good to go for the OpenData
      # return 2, "Registration"
    except Exception as ex:
      if '\n' in (_errMsg := str(ex)):
        _errMsg = str(ex).split('\n')[0]
      print([f"**{ll}**" for ll in _errMsg.split('\n')])
      # _errMsg = filter(lambda x: not re.match(r'^\s*$', x), str(ex))
      return 0, _errMsg
      
  def checkDbControl(self):
    _db = None
    try:
      _db = DB(self.cfg)
      # check db has miscsupply/vm_meta/vm_delta schemas. If not create them and add data
      metaSch = ['home','miscsupply', 'vm_meta', 'vm_delta'] #, 'home'
      [_db.createSch(sch) for sch in metaSch if sch not in _db.getSchemas()]
      # check for the metadata table
      if 'data' not in _db.getTables('vm_meta'):
        with open('data.sql', 'r') as file:
          createStmt = file.read()
          _db.execute(createStmt)
      self.qaDb = True
      logging.info("db test successful")
      
    except Exception as ex:
      self.qaDb = False
      logging.error(f"db cnxn test failed. Error:{str(ex)}")
    
    if _db: _db.close()
    self.isDbReady()
    return self.qaDb
  
  def checkPostGis(self):
    _db = None
    # check db is spatial
    try:
      _db = DB(self.cfg)
      if result := _db.execute("SELECT PostGIS_full_version()"): # or "SELECT PostGIS_version()"
        logging.info(f"PostGis test successful: {result}")
        self.qaSpat = True
        return True
      else:
        raise Exception("No PostGis Version detected")
        # self.qaSpat = False
        # logging.error("No PostGis Version detected.")
        # return False
      
    except Exception as ex:
      self.qaSpat = False
      logging.warning(f"PostGis has not been installed in the {_db.dbname} database. Please install it as the database superuser using 'CREATE EXTENSION PostGIS;'")
      
    if _db: _db.close()
    self.isDbReady()
    return self.qaSpat
  
  def checkPGClient(self):
    _db = None
    try:
      _db = DB(self.cfg)
      ver = PGClient(_db, self.cfg.get('dbClientPath')).get_restore_version()
      logging.info(f"PostGres Client test successful. Version: {ver}")
      self.qaClt = True
    except Exception as ex:
      logging.error(f"PG Client test failed. Error: {str(ex)}")
      self.qaClt = False

    if _db: _db.close()
    self.isDbReady()
    return self.qaClt

  def checkMetaData(self):
    print("checking metadata")
    if not self.cfg.get("regComplete") == "True":
      return False

    _db = None
    try:
      # get full list of datasets, insert the records that don't exist yet
      _db = DB(self.cfg)
      api = ApiUtils(self.cfg.get('baseUrl'), self.cfg.get('api_key'), self.cfg.get('client_id'))
      rsp = api.post("data", {})
      dsets = [LyrReg(d) for d in rsp['datasets']]
      logging.info(f"Retrieved {len(rsp)}")
      
      _existingKeys = [d.identity for d in _db.getRecSet(LyrReg)]
      for d in dsets:
        if d.identity not in _existingKeys:
          d.sup_ver=-1 # new record gets a negative supply-id so it matches on the latest seed.
          d.sup_type=Supplies.FULL # seed is full.
          if self.cfg.get('sync_all') == "True": d.active=True
          _db.execute(*d.insSql())

      # remove items which are no longer in the metadata? (withdrawn datasets). Delete the dataset too? (mean? or prudent for accidental leaks.).
      # yes. TODO: implement this later.

      self.qaMeta = True
    
    except Exception as ex:
      logging.error(str(ex))
      self.qaMeta = False
    
    if _db: _db.close()
    self.isDbReady()
    return self.qaMeta