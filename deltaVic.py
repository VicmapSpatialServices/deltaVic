import sys, os, logging, traceback
from datetime import datetime, timedelta

from assets import DB, FU, Logger, Config, LyrReg
from assets import Setup, Synccer, GUI

rootLog = Logger().get()
# rootLog.level = logging.DEBUG
# NOTSET=0, DEBUG=10, INFO=20, WARN=30, ERROR=40, CRITICAL=50

class vmdelta():
  STAGE='default'

  def __init__(self, vargs):
    self.action=vargs[0] if len(vargs) > 0 else "gui"#"sync" # default
    self.task  =vargs[1] if len(vargs) > 1 else False
    self.thing =vargs[2] if len(vargs) > 2 else False
    logging.debug("running deltaVic...")

    self.config = Config("config.ini", self.STAGE)
    logging.getLogger().setLevel(int(self.config.get('log_level')))
    
  def run(self):
    print(self.action)
    match self.action:
      case "gui":
        print("running gui")
        gui = GUI(self.STAGE)
        gui.mainloop()
      case "setup":
        Setup(self.STAGE).run()
      case "sync":
        _db = self.getDb()
        synccer = Synccer(self.config, _db)
        synccer.unWait() # queue any leftover jobs from last time.
        while(synccer.assess()):
          synccer.run()
          # break
      case "status":
        Setup(self.STAGE).status()
      case "core":
        # set only core vicmap layers
        Setup(self.STAGE).core()
      # case "upload":
      #   self.upload(self.thing)
      case "clean":
        if self.task == "db": # analyse and vaccuume the tables
          _db = self.getDb()
          logging.info("Analysing and Vaccuuming...")
          for dset in _db.getRecSet(LyrReg):
            if _db.table_exists(dset.identity):
              # logging.info(f"...{dset.identity}")
              _db.analVac(dset.identity)
        elif self.task == "files": # remove any leftover files in temp
          for dir, subdir, files in os.walk('temp'):
            [FU.remove(f"{dir}{os.sep}{ff}") for ff in files]
        else:
          logging.info("task was not specified")
      case "scorch":
        # remove all datasets and empty the data table
        _db = self.getDb()
        for dset in _db.getRecSet(LyrReg):
          if dset.relation == 'table': _db.dropTable(dset.identity)
          # if dset.relation == 'view': _db.dropView(dset.identity)
        _db.truncate("vm_meta.data")
      case 'test':
        _db = self.getDb()
        synccer = Synccer(self.config, _db)
        # synccer.restore()
        synccer.dump()
      case "_":
        gui = GUI(None, None)
        gui.mainloop()
        # print("print: action was not specified") # default to sync?
        # logging.info("action was not specified") # default to sync?
  
  def getDb(self):
    return DB(self.config.get('dbHost'), 
              self.config.get('dbPort'), 
              self.config.get('dbName'), 
              self.config.get('dbUser'), 
              self.config.get('dbPswd'))
  
  # def upload(self):
  #   pass

def main():
  startTime = datetime.now()
  # logging.info(f"Start Time: {startTime}")
  
  try:
    vmd = vmdelta(sys.argv[1:])
    vmd.run()
  except Exception as ex:
    logging.info(f"Exception: {str(ex)}")
    logging.info(traceback.format_exc())
  
  endTime = datetime.now()
  # logging.info(f"End Time: {endTime}")
  duration = (endTime - startTime).total_seconds()
  logging.info(f"Duration: {str(timedelta(seconds=duration)).split('.')[0]}")

if __name__ == "__main__":
  main()