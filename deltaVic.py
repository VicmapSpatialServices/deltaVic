import sys
import os
import logging
import traceback
from datetime import datetime, timedelta

from assets import DB, FU, Logger, Config, LyrReg
from assets import Setup, Synccer, GuiControl, Supplies

rootLog = Logger().get()
# rootLog.level = logging.DEBUG
# NOTSET=0, DEBUG=10, INFO=20, WARN=30, ERROR=40, CRITICAL=50


class vmdelta:
  # An absent argument is an empty string, so the comparisons below and the stage
  # name in upload all get the type they expect.
  def __init__(self, vargs: list[str], cfgStg: str = 'default'):
    self.action = vargs[0] if len(vargs) > 0 else "gui"  # "sync" # default
    self.task = vargs[1] if len(vargs) > 1 else ""
    self.thing = vargs[2] if len(vargs) > 2 else ""
    logging.debug("running deltaVic...")

    self.cfgStg = cfgStg
    self.config = Config("config.ini", cfgStg)
    logging.getLogger().setLevel(int(self.config.get('log_level')))

  def run(self):
    print(self.action)
    match self.action:
      case "gui":
        print("running gui")
        gui = GuiControl(self.cfgStg)
        gui.mainloop()
      case "setup":
        Setup(self.cfgStg).run()
      case "sync":
        _db = DB(self.config)
        synccer = Synccer(self.config, _db)
        synccer.unWait()  # queue any leftover jobs from last time.
        while synccer.assess():
          synccer.run()
          # break
        _db.close()
      case "status":
        Setup(self.cfgStg).status()
      case "core":
        # set only core vicmap layers
        Setup(self.cfgStg).core()
      case "upload":
        # Fall back to the stage this instance was opened with when none is named.
        _cfg = Config('config.ini', self.task or self.cfgStg)  # task is stage "default"
        _ident = self.thing  # thing is the layer name, qualified.
        _dbExp = DB(_cfg)
        return Synccer(self.config, _dbExp).upload(_ident, Supplies.DIFF)
      case 'fixErrs':
        print("fix all error datasets by Q'ing them for reseeding")
        _db = DB(self.config)
        _db.fixErrs()
        _db.close()

      case "clean":
        if self.task == "db":  # analyse and vaccuume the tables
          _db = DB(self.config)
          logging.info("Analysing and Vaccuuming...")
          for dset in _db.getRecSet(LyrReg):
            if _db.table_exists(dset.identity):
              # logging.info(f"...{dset.identity}")
              _db.analVac(dset.identity)
        elif self.task == "files":  # remove any leftover files in temp
          for dir, _subdir, files in os.walk('temp'):
            [FU.remove(f"{dir}{os.sep}{ff}") for ff in files]
        else:
          logging.info("task was not specified")
      case "scorch":
        # remove all datasets and empty the data table
        _db = DB(self.config)
        for dset in _db.getRecSet(LyrReg):
          if dset.relation == 'table':
            _db.dropTable(dset.identity)
          # if dset.relation == 'view': _db.dropView(dset.identity)
        _db.truncate("vm_meta.data")
      case 'test':
        # _db = DB(self.config)
        # synccer = Synccer(self.config, _db)
        # # synccer.restore()
        # synccer.dump()
        print(sys.path)
        # for key, value in os.environ.items():
        #   print(f'{key}: {value}')
      case _:
        gui = GuiControl(self.cfgStg)
        gui.mainloop()
        # print("print: action was not specified") # default to sync?
        # logging.info("action was not specified") # default to sync?
    # Only upload answers with anything. Said out loud so the actions that finish by
    # doing rather than returning are not read as having forgotten to.
    return None


def main() -> int:
  startTime = datetime.now()
  # logging.info(f"Start Time: {startTime}")

  failed = False
  try:
    vmd = vmdelta(sys.argv[1:], 'default')
    vmd.run()
  except Exception as ex:
    # Logged at error, and the exit status says so too. Swallowing this and returning 0
    # told Step Functions the sync had worked: post-sync then rebuilt indexes and tiles
    # over data that had never moved, and the run reported success.
    logging.error(f"Exception: {str(ex)}")
    logging.error(traceback.format_exc())
    failed = True

  endTime = datetime.now()
  # logging.info(f"End Time: {endTime}")
  duration = (endTime - startTime).total_seconds()
  logging.info(f"Duration: {str(timedelta(seconds=duration)).split('.')[0]}")
  return 1 if failed else 0


if __name__ == "__main__":
  sys.exit(main())
