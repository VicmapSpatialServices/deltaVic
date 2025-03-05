import logging

from .utils_db import DB
from .utils_api import ApiUtils
from .dbTable import LyrReg
from .utils import Supplies, Config

logger = logging.getLogger(__name__)

class Setup():
  def __init__(self, stg):
    self.config = Config('config.ini', stg)
    self.db = None
    self.dbSchemas = None

  def run(self):
    qa = QA() # each event will throw an Exception unless it passes
    
    # TODO: allow input of cofig vars prior to each module of setup being executed.
    cfgVars = ['dbHost','dbPort','dbPort','dbName','dbUser','dbPswd', 'dbClientPath','baseUrl','email']
    self.config.keysExist(cfgVars)
    
    # test connection - exception will be thrown if it is bad
    self.db = DB(self.config)
    
    qa.checkPostGis(self.db)
    qa.mkDbControl(self.db)
    qaCode, qaMsg = qa.checkApiClient(self.config)
    if qaCode < 2:
      self.logger.error(qaMsg)
      raise Exception(qaMsg)
    
    qa.seedMetaData(self.db, self.config)
    qa.createVicmapSchemas(self.db)

  def status(self):
    logger.info(f"testing config file has all required keys for '{self.config.getStage()}' instance: {self.config}")
    logger.info(f"dbCnxn: {self.config.stg['dbUser']}:{self.config.stg['dbPswd']}@{self.config.stg['dbHost']}:{self.config.stg['dbPort']}/{self.config.stg['dbName']}")
    logger.info(f"Email: {self.config.stg['email']}")
    logger.info(f"ClientId: {self.config.stg['client_id']}")
    logger.info(f"ApiKey: {self.config.stg['api_key']}")
    logger.info(f"deltaVic endpoint: {self.config.stg['baseUrl']}")

    # for key, val in self.config.items():
    #   logger.info(f"{key}: {val}")#, self.cfg['key'])
  
  def core(self):
    self.db = DB(self.config)
    sqlUnretired = "update vm_meta.data set active=false where identity like 'vlat%' or identity like 'vtt%'"
    self.db.execute(sqlUnretired)
    sqlNotMisc = "update vm_meta.data set active=false where sup='MISC' and not "
    sqlNotMisc += "(" + ' or '.join(f"identity like '{sch}%'" for sch in ['vmadmin','vmreftab','vmfeat']) + ")"
    logger.info(sqlNotMisc)
    # self.db.execute(sqlNotMisc)
    
class QA():
  def __init__(self):
    pass

  # @staticmethod
  # def preReqs(cfg, cfgVars):
  #   for var in cfgVars:
  #     if not (val := cfg.get(var)):
  #       raise Exception(f"No {var} in config.ini")
  #     if not val:
  #       raise Exception(f"No value for {var} in config.ini")
  #   return True
  
  @staticmethod
  def checkPostGis(db):
    # check db is spatial
    try:
      db.execute("SELECT PostGIS_version()")
    except Exception as ex:
      logger.warning(f"PostGis has not been installed in the {db.dbname} schema. Please install it as the database superuser.")
      # try: # issue, you have to be the superuser (postgres) to install postgis.
      #   self.db.execute("CREATE EXTENSION PostGIS")
      # except Exception as ex:
      #   logger.error("Could not install PostGis on DB")
      #   raise ex
    
  @staticmethod
  def mkDbControl(db):
    # check db has vm_meta/vm_delta schemas. If not create and add data
    metaSch = ['vm_meta', 'vm_delta']
    [db.createSch(sch) for sch in metaSch if sch not in db.getSchemas()]
    
    if 'data' not in db.getTables('vm_meta'):
      with open('data.sql', 'r') as file:
        createStmt = file.read()
        db.execute(createStmt)
  
  @staticmethod
  def checkApiClient(cfg):
    if not (_email := cfg.get('email')):
      return 0, "Email not set in config"
    elif _email == 'somebody@example.org':
      return 0, "You cannot register the default email address"
    
    # if the client_id is null, we need to create it
    if not (_clientId := cfg.get('client_id')):
      logger.debug("Submitting email address to obtain a client_id")
      api = ApiUtils(cfg.get('baseUrl'), None, None) # No client-id passed
      rsp = api.post("register", {"email":_email})
      logger.debug("Updating config file with client_id...")
      _clientId = rsp['client_id']
      cfg.set({'client_id':_clientId})
      # cfg['client_id'] = rsp['client_id']
      # cfg.write()
      errStr = f"Client_id not yet verified, please check your inbox for {_email}"
      # raise Exception(errStr)
      return 1, errStr # unverified
    
    if not (_apiKey := cfg.get("api_key")):
      logger.info("Submitting client_id to obtain an api-key")
      api = ApiUtils(cfg.get('baseUrl'), None, _clientId)
      rsp = api.post("register", {"email":_email})
      logger.info("Updating config file with api_key...")
      # cfg['api_key'] = rsp['api_key']
      _apiKey = rsp['api_key']
      cfg.set({'api_key':_apiKey})
      # cfg.write()
      # return 2 

    # if all 3 registration attrs are present in config, then return 0?
    # try and avoind this registration call every time the gui is opened.
    # return 2, "Registration"
    logger.debug(f"Submitting register call to obtain rights.")# {cfg.keys()} {cfg.get('baseUrl')}")
    api = ApiUtils(cfg.get('baseUrl'), _apiKey, _clientId)
    rsp = api.post("register", {"email":_email})
    return 2, rsp['rights'] if 'rights' in rsp else "Registration"# "No rights" # all good to go
      
  @staticmethod
  def seedMetaData(db, cfg):
    # get full list of datasets
    api = ApiUtils(cfg.get('baseUrl'), cfg.get('api_key'), cfg.get('client_id'))
    rsp = api.post("data", {})
    dsets = [LyrReg(d) for d in rsp['datasets']]
    logger.info(f"Retrieved {len(rsp)}")
    
    # insert the records that don't exist yet
    _existingKeys = [d.identity for d in db.getRecSet(LyrReg)]
    for d in dsets:
      if d.identity not in _existingKeys:
        d.sup_ver=-1 # new record gets a negative supply-id so it matches on the latest seed.
        d.sup_type=Supplies.FULL # seed is full.
        db.execute(*d.insSql())

  @staticmethod
  def createVicmapSchemas(db):
    # check db has all vicmap schemas
    _dsets = db.getRecSet(LyrReg)
    _schemas = set([d.identity.split('.')[0] for d in _dsets])
    logger.info(_schemas)
    [db.createSch(sch) for sch in _schemas if sch not in db.getSchemas()]
 