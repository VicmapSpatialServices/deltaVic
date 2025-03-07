import os, logging, traceback
from datetime import datetime, timedelta

from .utils_db import PGClient
from .utils_api import ApiUtils
from .dbTable import LyrReg
from .utils import FileUtils as FU, Supplies

logger = logging.getLogger(__name__)

###########################################################################

class Synccer():
  haltStates = [LyrReg.COMPLETE,LyrReg.WAIT] # ,LyrReg.OPS

  def __init__(self, config, db):
    self.config = config
    self.db = db
    # self.lyrs = []
    self.tables = []
    self.views = []
  
  def unWait(self):
    self.db.execute(LyrReg.unWaitUpSql())

  def assess(self):
    self.resolve() # updates out of date datasets to 'QUEUED'
    _layers = [ll for ll in self.db.getRecSet(LyrReg) if ll.active and not ll.err and ll.status not in self.haltStates]
    self.tables = [ll for ll in _layers if ll.relation=='table']
    # self.tables = [tt for tt in self.tables if tt.identity.startswith('vmtrans.tr_road')]#[0:1] # use to dither candidates.
    # self.tables.sort(key=lambda ll:ll.extradata.get('row_count') if 'row_count' in ll.extradata else 0, reverse=True)
    self.views = [ll for ll in _layers if ll.relation=='view']
    
    if _nmbr := len(self.tables) + len(self.views):
      logger.info(f'To Process: {len(self.tables)} table and {len(self.views)} views')
    return _nmbr
  
  def resolve(self):
    _all_local = self.db.getRecSet(LyrReg)

    _local, _errs, _remote = {}, {}, {}

    [_local.update({d.identity:d}) for d in _all_local if  not d.err]
    [_errs.update({d.identity:d}) for d in _all_local if d.err]
    [_remote.update({ll.identity:ll}) for ll in self.getVicmap()]
    logger.info(f"Layer state: {len(_all_local)} in vm_meta.data, {len([i for i in _local if _local[i].active])} active, {len(_errs)} errors. {len(_remote)} available from vicmap_master")

    # scroll thorugh the remote datasets and add any that don't exist locally
    logger.debug("checking remote layers exist locally")
    for name, dset in _remote.items():
      if not (_lyr := _local.get(name) or _errs.get(name)):
      # if name not in list(_local.keys()).extend(list(_errs.keys())):
        dset.sup_ver=-1 # new record gets a negative supply-id so it matches the latest seed.
        dset.sup_type=Supplies.FULL # seed is full.
        self.db.execute(*dset.insSql())

    # scroll through the local datasets and set to queued if versions don't match
    logger.debug("checking local layers against remote")
    for name,lyr in _local.items():
      if not (_vmLyr := _remote.get(name)):
        logger.warning(f"Dataset {name} doesn't exist in the remote vicmap_master") # auto delete? in qa at start/end?
        continue
      # Note conditions: only compare those datasets present locally as active, in a complete state and not in err.
      if lyr.active and lyr.status == LyrReg.COMPLETE:
        if lyr.sup_ver != _vmLyr.sup_ver:
          # logger.debug(f"{lyr.sup_ver}, {_vmLyr.sup_ver}")
          self.db.execute(*lyr.upStatusSql(LyrReg.QUEUED))

  def getVicmap(self):#seedDsets(self):
    # get full list of datasets
    api = ApiUtils(self.config.get('baseUrl'), self.config.get('api_key'), self.config.get('client_id'))
    rsp = api.post('data', {})
    return [LyrReg(d) for d in rsp['datasets']]
    
  def run(self):
    tracker = {}#{"queued":0,"download":0,"restore":0,"delete":0,"add":0,"reconcile":0,"clean":0}
    try:
      if self.tables: #process table based on status
        [Sync(self.db, self.config, tbl, self.haltStates,tracker).process() for tbl in self.tables]
      else:
        if self.views: # process views based on status
          [Sync(self.db, self.config, vw, self.haltStates,tracker).process() for vw in self.views]
      logger.info("--timings report--")
      [logger.info(f"{state:<10}: {secs:8.2f}") for state, secs in tracker.items()]
    except Exception as ex:
      _msg = "Something went wrong in the Synccer"
      logger.error(_msg)
      raise Exception(_msg)
  
  def restore(self, lyrQual):
    fPath = f"temp/{lyrQual}.dmp"
    PGClient(self.db, self.config.get('dbClientPath')).restore_file(fPath)

  def dump(self, lyrQual):
    fPath = f"temp/{lyrQual}.dmp"
    PGClient(self.db, self.config.get('dbClientPath')).dump_file(lyrQual, fPath)

    
###########################################################################
                     ### y   y N    N CCCCC
                     #   y   y NN   N C
                     ###  y y  N N  N C
                       #   y   N  N N C
                     ###   y   N   NN CCCCC
###########################################################################

class Sync():
  def __init__(self, db, config, lyr, haltStates, tracker):
    self.db = db
    self.config = config
    self.lyr = lyr
    self.halt = haltStates
    self.tracker = tracker

  def process(self):
    while self.lyr.status not in self.halt and not self.lyr.err:
      try:
        startTime = datetime.now() 
        _status = self.lyr.status.lower() # store this here before it is updated by the process.
        
        getattr(self, _status)()
        
        self.upTrack(_status, (datetime.now()-startTime).total_seconds(), self.lyr)
      except Exception as ex:
        logger.error(str(ex))
        logger.debug(traceback.format_exc())
        self.db.execute(*self.lyr.upExtraSql({"error":str(ex)}))
        self.db.execute(*self.lyr.setErr())

  def queued(self):
    logger.debug(F"q-ing {self.lyr.identity} -- current({self.lyr.sup}:{self.lyr.sup_ver}:{self.lyr.sup_type})")
    self.db.execute(*self.lyr.delExtraKey('error')) # clear the err for a new run
    
    # get the next dump file from data endpoint
    api = ApiUtils(self.config.get('baseUrl'), self.config.get('api_key'), self.config.get('client_id'))
    _rsp = api.post("data", {"dset":self.lyr.identity,"sup_ver":self.lyr.sup_ver})
    if not (_next := _rsp.get("next")):
      if self.lyr.sup_ver == _rsp.get("sup_ver"): # have the latest already
        logger.warn("Requested data load but endpoint says max(sup_ver) is current")
        self.db.execute(*self.lyr.upStatusSql(LyrReg.COMPLETE))
      else:
        logger.warn("Requested data load but endpoint says next ready only half ready yet")
        self.db.execute(*self.lyr.upStatusSql(LyrReg.WAIT))
      return
    
    self.db.execute(*self.lyr.upExtraSql(_next))

    _supDate = datetime.fromisoformat(_next['sup_date']) if _next['sup_date'] else None # always there? Is there an edge case it may still be missing?
    logger.info(F"q-ing {self.lyr.identity} ({self.lyr.sup}:{self.lyr.sup_ver}:{self.lyr.sup_type})-->({_next['sup_ver']}:{_next['sup_type']})")#:{_supDate}
    self.db.execute(*self.lyr.upSupSql(_next['sup_ver'], _next['sup_type'], _supDate))
    self.db.execute(*self.lyr.upStatusSql(LyrReg.DOWNLOAD))

  def download(self):
    logger.debug(F" -> download-ing {self.lyr.identity}")
    if not os.path.exists("temp"): os.makedirs("temp")
    fPath = f"temp/{self.lyr.extradata['filename']}"
    ApiUtils.download_file(self.lyr.extradata['s3_url'], fPath)
    
    self.db.execute(*self.lyr.delExtraKey('s3_url')) # remove s3_url from extradata as we are done with it now.
    self.db.execute(*self.lyr.upStatusSql(LyrReg.RESTORE))

  def restore(self):
    # restore the file - full loads go straight to each vicmap schema, incs go to the vm_delta schema.
    # logger.debug(f"restore version: {PGClient(self.db, self.config.get('dbClientPath')).get_restore_version()}") # test pg connection.
    fPath = f"temp/{self.lyr.extradata['filename']}"
    PGClient(self.db, self.config.get('dbClientPath')).restore_file(fPath)
    
    if self.lyr.sup_type == Supplies.FULL:
      self.db.execute(*self.lyr.upStatusSql(LyrReg.RECONCILE))
    else:
      self.db.execute(*self.lyr.upStatusSql(LyrReg.OPS))#DELETE
  
  def ops(self): # maintains idempotency if you are doing reRunFromState.
    logger.debug(f" -> Deleting rows for {self.lyr.identity}")
    _delta = self.lyr.extradata['filename'].replace('.dmp','')
    self.db.execute(f"delete from {self.lyr.identity} where {self.lyr.pkey} in (select {self.lyr.pkey} from {_delta})")

    logger.debug(f" -> Adding rows for {self.lyr.identity}")
    colsCsv = ",".join(self.db.getAllCols(self.lyr.identity)) # Get Column names as csv for sql.
    self.db.execute(f"insert into {self.lyr.identity} (select {colsCsv} from {_delta} where operation='INSERT')")
    
    self.db.execute(*self.lyr.upStatusSql(LyrReg.VACUUM)) # LyrReg.RECONCILE# LyrReg.ANALYZE ?

  
  def vacuum(self):
    self.db.execute(f"vacuum {self.lyr.identity}")
    self.db.execute(*self.lyr.upStatusSql(LyrReg.ANALYZE))

  def analyze(self):
    self.db.execute(f"analyze {self.lyr.identity}")
    self.db.execute(*self.lyr.upStatusSql(LyrReg.RECONCILE))

  def reconcile(self): # reconcile the row count and check sum -> signOff()?
    # warning: if table is malformed and missing ufi_created col, it will fail here and not insert stats, which will throw errs when assembling datasets.
    # warning 2, if a datasets does not have a pkey specified it will also failed - need to update the control schema prior to anyone seeding.
    logger.debug(F" -> reconcile-ing {self.lyr.identity}")
    recStr = ""
    
    try: 
      supCount, supChkSum = self.lyr.extradata['row_count'], self.lyr.extradata['check_sum']
      logger.debug(f"{supCount} {supChkSum}")
      maxUfiDate, maxUfi, tblCount, tblChkSum = self.db.getTblStats(self.lyr.identity, Supplies.meta(self.lyr.sup).ufiCreateCol, self.lyr.pkey) # , state_query=self.obj.pidUpSql()
      logger.debug(f"{tblCount} {tblChkSum}")
      
    except Exception as ex:
      logger.warning(f"{self.lyr.identity} did not return stats: {str(ex)}")
      raise Exception(f"Problem getting stats: {str(ex)}")
    
    recStr += f" count(remote:{supCount}!=local:{tblCount})-diff({supCount-tblCount})" if tblCount!=supCount else ""
    recStr += f" chkSum(remote:{supChkSum}!=local:{tblChkSum})-diff({supChkSum-tblChkSum})" if tblChkSum!=supChkSum else ""
    if recStr:
      raise Exception(f"Supply misreconciled: {recStr}")
    # self.db.execute(*self.lyr.upStatsSql(maxUfiDate, maxUfi, tblCount, tblChkSum))
    
    # self.db.execute(*self.lyr.upSupSql(self.lyr.extradata['sup_ver'], self.lyr.extradata['sup_type'], self.lyr.extradata['sup_date']))
    self.db.execute(*self.lyr.upStatusSql(LyrReg.CLEAN))
   
  def clean(self):
    # clean up the temp file and the temp view
    logger.debug(F" -> clean-ing {self.lyr.identity}")
    if self.lyr.sup_type == Supplies.INC:
      self.db.dropTable(self.lyr.extradata['filename'].replace('.dmp',''))
    FU.remove(f"temp/{self.lyr.extradata['filename']}")
    # status->COMPLETE or err=true
    self.db.execute(*self.lyr.upStatusSql(LyrReg.COMPLETE))

  def upTrack(self, status, duration, lyr):
    # whole of run stats
    if status not in self.tracker:
      self.tracker.update({status:duration})
    else:
      self.tracker[status] = self.tracker[status] + duration
    
    # individual layer stats
    tms = 'timings-full' if lyr.sup_type==Supplies.FULL else f'timings-inc-{lyr.sup_ver}' 
    _tms = lyr.extradata[tms] if tms in lyr.extradata else {}
    _tms.update({status:duration}) # overwrite
    self.db.execute(*lyr.upExtraSql({tms:_tms}))
    