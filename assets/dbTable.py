import json, logging
from datetime import datetime

# from .utils import Supplies
from .utils_api import ApiUtils
from .utils_db import DB

class DBTable():
  QUIESCENT="QUIESCENT"
  QUEUED="QUEUED"
  DOWNLOAD="DOWNLOAD"
  RESTORE="RESTORE"
  OPS = "OPS"
  ANALYZE="ANALYZE"
  VACUUM="VACUUM"
  RECONCILE="RECONCILE"
  CLEAN="CLEAN"
  COMPLETE="COMPLETE"
  WAIT="WAIT"

  def __init__(self, row):
    [setattr(self, col,val) for col,val in zip(self.cols, row)]
    if hasattr(self, 'extradata'):
      self.extradata = self.extradata or {}
  
  def insSql(self):
    _upDict = {}
    [_upDict.update({col:val}) for col,val in zip(self.cols, self.asList()) if col not in ('edit_date')]
    _cols = _upDict.keys()
    sqlStr =  f"INSERT into {self.name} ({','.join(_cols)}) VALUES ({('%s,'*len(_cols))[0:-1]})"
    sqlParams = list(_upDict.values())
    # logging.info(f"sqlStr:{sqlStr}")
    # logging.info(f"sqlParams:{sqlParams}")
    return sqlStr, sqlParams

  def setErr(self, errState=True):
    # if self.status == self.RECONCILE: # queue the full supply as we have a misrec. -> can get stuck in a loop when the misrec is due to bad metadata.
    #   self.sup_ver = -1
    #   self.status = self.QUEUED
    #   return self.upSupSql(self.sup_ver, Supplies.FULL, self.sup_date)
    
    # default behaviour is to log the error.
    self.err = errState
    sqlStr = f"update {self.name} set err=%s where identity=%s"
    sqlParams = (self.err, self.identity)
    return sqlStr, sqlParams
  
  def setActive(self, active):
    self.active = active
    sqlStr = f"update {self.name} set active=%s where identity=%s"
    sqlParams = (self.active, self.identity)
    return sqlStr, sqlParams

  def asList(self):
    # return [getattr(self, col) for col in self.cols]
    listy = [getattr(self, col) for col in self.cols]
    listy = [json.dumps(ll) if isinstance(ll, dict) else ll for ll in listy] #json columns need to be strings on pg insert.
    return listy
  
  def enQueue(self, supVer, supType):
    sqlStr = "update {} set status=%s, sup_ver=%s, sup_type=%s, err=%s where identity=%s".format(self.name)
    sqlParams = (self.QUEUED, supVer, supType, False, self.identity)
    return sqlStr, sqlParams

  def upStatsSql(self, maxUfiDate, maxUfi, tblCount, tblChkSum):
    sqlStr = "update {} set max_create=%s, max_ufi=%s, row_count=%s, check_sum=%s where identity=%s".format(self.name)
    sqlParams = (maxUfiDate, maxUfi, tblCount, tblChkSum, self.identity)
    return sqlStr, sqlParams

  def upSupSql(self, supVer, supType, supDate):
    """ update supply info """
    self.sup_ver, self.sup_type, self.sup_date  = supVer, supType, supDate
    sqlStr = "UPDATE {} SET sup_ver=%s, sup_type=%s, sup_date=%s WHERE identity=%s".format(self.name)
    sqlParams = (supVer, supType, supDate, self.identity)
    return sqlStr, sqlParams
  
  def upStatusSql(self, status):
    self.status = status
    sqlStr = "UPDATE {} SET status=%s WHERE identity=%s".format(self.name)
    sqlParams = (status, self.identity)
    return sqlStr, sqlParams

  def upExtraSql(self, dicty=None):
    self.extradata = self.extradata or {} # set as empty dict if None
    if isinstance(self.extradata, str): # dodgy fix?
      logging.warn("Extradata was a string, fixing")
      self.extradata = json.loads(self.extradata)
    # update with the new values or clear the field if None was supplied.
    self.extradata.update(dicty) if dicty else self.extradata.clear()
    
    sqlStr = "UPDATE {} SET extradata=%s where identity=%s".format(self.name)
    sqlParams = (json.dumps(self.extradata), self.identity)
    return sqlStr, sqlParams
  
  def delExtraKey(self, key):
    if self.extradata and self.extradata.get(key):
      self.extradata.pop(key)
    
    sqlStr = "UPDATE {} SET extradata=%s where identity=%s".format(self.name)
    sqlParams = (json.dumps(self.extradata), self.identity)
    return sqlStr, sqlParams
  
  @classmethod
  def unWaitUpSql(cls):
    return f"update {cls.name} set status='QUEUED' where status = 'WAIT'"

  @classmethod
  def listmaker(cls):
    return f"select {','.join(cls.cols)} from {cls.name} order by identity"

class LyrReg(DBTable):
  name='vm_meta.data'
  cols=['identity','active','relation','geom_type','pkey','status','err','sup','sup_ver','sup_date','sup_type','md_uuid','extradata','edit_date']
  
  def __init__(self, lyrObj):
    if type(lyrObj) == tuple:
      super().__init__(lyrObj)
    elif type(lyrObj) == dict:
      sup_date = datetime.fromisoformat(lyrObj['sup_date']) if lyrObj['sup_date'] else None
      newRow = [lyrObj['identity'],False,lyrObj['relation'],lyrObj['geom_type'],lyrObj['pkey'],self.QUIESCENT,False,lyrObj['sup'],lyrObj['sup_ver'],sup_date,None,None,None,None]
      # logging.debug(f"initting new row: {newRow}")
      super().__init__(newRow)
      # logging.debug(self.sup_ver)
    else:
      raise Exception(f"Layer Object was not in an expected format")
    
    self.sch, self.tbl = self.identity.split('.')
  
  def __str__(self):
    return f"{self.identity}-{self.sup}-{self.sup_ver}-{self.status}"

  def merge(self, dbDsets):
    if others := [d for d in dbDsets if d.identity==self.identity]:
      [setattr(self, col, getattr(others[0], col)) for col in self.cols]

class Schemas():#list
  def __init__(self, type, cfg):
    # super().__init__(self)
    # print(f"Schema({type})")
    self.schs = []
    self.type = type
    self.cfg = cfg

    self.populate()
    
  def populate(self):
    match self.type:
      case 'Meta':
        if not self.cfg.get("regComplete") == "True": return

        api = ApiUtils(self.cfg.get('baseUrl'), self.cfg.get('api_key'), self.cfg.get('client_id'))
        rsp = api.post("data", {})
        _dsets = [LyrReg(d) for d in rsp['datasets']]

        # Merge in the existing table data for display and manipulation of active and status
        if self.cfg.get("dbComplete") == "True": 
          _db = DB(self.cfg)
          _dbDsets = [d for d in _db.getRecSet(LyrReg)]
          [d.merge(_dbDsets) for d in _dsets]

        _schs = list(set([lyr.sch for lyr in _dsets]))
        _schs.sort(key=lambda s:s)
        for sch in _schs:
          _lyrs = [d for d in _dsets if d.sch==sch]
          _newSch = Schema(sch)
          [_newSch.add(d) for d in _lyrs]
          self.schs.append(_newSch)
      case 'Data':
        if not self.cfg.get("dbComplete") == "True": return

        _db = DB(self.cfg)
        _dbDsets = [d for d in _db.getRecSet(LyrReg)]
        _schs = _db.getSchemas()
        for sch in _schs:
          _newSch = Schema(sch)
          # combine the below with the available vm_meta.data info
          _dsets = [LyrReg((f"{sch}.{tbl}",None,None,None,None,None,None,None,None,None,None,None,None,None)) for tbl in _db.getTables(sch)]
          [d.merge(_dbDsets) for d in _dsets] # merge in the existing metadata from the local tracking table
          [_newSch.add(d) for d in _dsets]
          self.schs.append(_newSch)
      case '_':
        logging.warning(f"Metadata type {self.type} not known") 
    
  def get(self, sch):
    if schs := [s for s in self.schs if s.name==sch]:
      return schs[0]
    else:
      print("Nope")
      # newSch = Schema(sch)
      # self.append(newSch)
      # return newSch

class Schema():#list
  def __init__(self, sch):
    # super().__init__(self)
    self.name = sch
    self.lyrs = []
    # print(f"*** {sch} ***")
  def add(self, lyr):
    # print(lyr)
    self.lyrs.append(lyr)
