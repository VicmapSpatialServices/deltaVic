import json, logging
from datetime import datetime

logger = logging.getLogger(__name__)

class DBTable():
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
  
  def insSql(self):
    _upDict = {}
    [_upDict.update({col:val}) for col,val in zip(self.cols, self.asList()) if col not in ('edit_date')]
    _cols = _upDict.keys()
    sqlStr =  f"INSERT into {self.name} ({','.join(_cols)}) VALUES ({('%s,'*len(_cols))[0:-1]})"
    sqlParams = list(_upDict.values())
    # logger.info(f"sqlStr:{sqlStr}")
    # logger.info(f"sqlParams:{sqlParams}")
    return sqlStr, sqlParams

  def setErr(self, errState=True):
    self.err = errState
    sqlStr = "update {} set err=%s where identity=%s".format(self.name)
    sqlParams = (self.err, self.identity)
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
      logger.warning("Extradata was a string, fixing")
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
      newRow = [lyrObj['identity'],True,lyrObj['relation'],lyrObj['geom_type'],lyrObj['pkey'],LyrReg.QUEUED,False,lyrObj['sup'],lyrObj['sup_ver'],sup_date,None,None,None,None]
      # logger.debug(f"initting new row: {newRow}")
      super().__init__(newRow)
      # logger.debug(self.sup_ver)
    else:
      raise Exception(f"Layer Object was not in an expected format")
  
  def __str__(self):
    return f"{self.identity}-{self.sup}-{self.sup_ver}-{self.status}"

# class Datasets():
#   def __init__(self, db):
#     _dsets = db.getRecSet(LyrReg.listmaker())
#   def __str__(self):
#     return f"{self.sch}.{self.tbl} {self.status}"


