from __future__ import annotations
import json
import logging
from datetime import datetime
from typing import Any
from collections.abc import Sequence

from .utils import Config

# from .utils import Supplies
from .utils_api import ApiUtils
from .utils_db import DB

# What every statement builder here hands back, the sql and the parameters for it,
# ready to go into execute as its two arguments.
Stmt = tuple[str, Sequence[object]]


class DBTable:
  # Declared, not assigned. Every subclass supplies both, and naming them here lets the
  # base read them and makes a subclass that forgets one a type error rather than an
  # AttributeError at the first call.
  name: str
  cols: list[str]
  # Read by every statement this class builds, and supplied by the subclass through cols.
  identity: str
  # Read here too, by upExtraSql and delExtraKey. Only the subclasses that carry an
  # extradata column ever have one, which is what the hasattr below is asking.
  extradata: dict[str, Any]

  QUIESCENT = "QUIESCENT"
  QUEUED = "QUEUED"
  DOWNLOAD = "DOWNLOAD"
  RESTORE = "RESTORE"
  OPS = "OPS"
  ANALYZE = "ANALYZE"
  VACUUM = "VACUUM"
  RECONCILE = "RECONCILE"
  CLEAN = "CLEAN"
  COMPLETE = "COMPLETE"
  WAIT = "WAIT"

  def __init__(self, row: Sequence[object]):
    [setattr(self, col, val) for col, val in zip(self.cols, row, strict=True)]
    if hasattr(self, 'extradata'):
      self.extradata = self.extradata or {}

  def insSql(self) -> Stmt:
    _upDict: dict[str, Any] = {}
    [
      _upDict.update({col: val})
      for col, val in zip(self.cols, self.asList(), strict=True)
      if col not in ('edit_date')
    ]
    _cols = _upDict.keys()
    sqlStr = f"INSERT into {self.name} ({','.join(_cols)}) VALUES ({('%s,' * len(_cols))[0:-1]})"
    sqlParams = list(_upDict.values())
    # logging.info(f"sqlStr:{sqlStr}")
    # logging.info(f"sqlParams:{sqlParams}")
    return sqlStr, sqlParams

  def setErr(self, errState: bool = True) -> Stmt:
    # if self.status == self.RECONCILE: # queue the full supply as we have a misrec. -> can get stuck in a loop when the misrec is due to bad metadata.
    #   self.sup_ver = -1
    #   self.status = self.QUEUED
    #   return self.upSupSql(self.sup_ver, Supplies.FULL, self.sup_date)

    # default behaviour is to log the error.
    self.err = errState
    sqlStr = f"update {self.name} set err=%s where identity=%s"
    sqlParams = (self.err, self.identity)
    return sqlStr, sqlParams

  def setActive(self, active: bool) -> Stmt:
    self.active = active
    sqlStr = f"update {self.name} set active=%s where identity=%s"
    sqlParams = (self.active, self.identity)
    return sqlStr, sqlParams

  def asList(self) -> list[object]:
    # return [getattr(self, col) for col in self.cols]
    listy: list[object] = [getattr(self, col) for col in self.cols]
    listy = [
      json.dumps(ll) if isinstance(ll, dict) else ll for ll in listy
    ]  # json columns need to be strings on pg insert.
    return listy

  def enQueue(self, supVer: int, supType: str) -> Stmt:
    sqlStr = f"update {self.name} set status=%s, sup_ver=%s, sup_type=%s, err=%s where identity=%s"
    sqlParams = (self.QUEUED, supVer, supType, False, self.identity)
    return sqlStr, sqlParams

  def upStatsSql(
    self, maxUfiDate: datetime | None, maxUfi: int | None, tblCount: int, tblChkSum: int
  ) -> Stmt:
    sqlStr = f"update {self.name} set max_create=%s, max_ufi=%s, row_count=%s, check_sum=%s where identity=%s"
    sqlParams = (maxUfiDate, maxUfi, tblCount, tblChkSum, self.identity)
    return sqlStr, sqlParams

  def upSupSql(self, supVer: int, supType: str, supDate: datetime | None) -> Stmt:
    """update supply info"""
    self.sup_ver, self.sup_type, self.sup_date = supVer, supType, supDate
    sqlStr = f"UPDATE {self.name} SET sup_ver=%s, sup_type=%s, sup_date=%s WHERE identity=%s"
    sqlParams = (supVer, supType, supDate, self.identity)
    return sqlStr, sqlParams

  def upStatusSql(self, status: str) -> Stmt:
    self.status = status
    sqlStr = f"UPDATE {self.name} SET status=%s WHERE identity=%s"
    sqlParams = (status, self.identity)
    return sqlStr, sqlParams

  def upExtraSql(self, dicty: dict[str, Any] | None = None) -> Stmt:
    self.extradata = self.extradata or {}  # set as empty dict if None
    if isinstance(self.extradata, str):  # dodgy fix?
      logging.warning("Extradata was a string, fixing")
      self.extradata = json.loads(self.extradata)
    # update with the new values or clear the field if None was supplied.
    self.extradata.update(dicty) if dicty else self.extradata.clear()

    sqlStr = f"UPDATE {self.name} SET extradata=%s where identity=%s"
    sqlParams = (json.dumps(self.extradata), self.identity)
    return sqlStr, sqlParams

  def delExtraKey(self, key: str) -> Stmt:
    if self.extradata and self.extradata.get(key):
      self.extradata.pop(key)

    sqlStr = f"UPDATE {self.name} SET extradata=%s where identity=%s"
    sqlParams = (json.dumps(self.extradata), self.identity)
    return sqlStr, sqlParams

  @classmethod
  def unWaitUpSql(cls) -> str:
    return f"update {cls.name} set status='QUEUED' where status = 'WAIT'"

  @classmethod
  def listmaker(cls) -> str:
    return f"select {','.join(cls.cols)} from {cls.name} order by identity"


class LyrReg(DBTable):
  # One per entry in columns below, since __init__ sets them with setattr and nothing else
  # says they exist. This is the shape of a vm_meta.data row as the rest of the code
  # reads it.
  identity: str
  active: bool
  relation: str
  geom_type: str | None
  pkey: str | None
  status: str
  err: bool
  sup: str
  sup_ver: int
  sup_date: datetime | None
  sup_type: str | None
  md_uuid: str | None
  extradata: dict[str, Any]
  edit_date: datetime | None

  name = 'vm_meta.data'
  cols = [
    'identity',
    'active',
    'relation',
    'geom_type',
    'pkey',
    'status',
    'err',
    'sup',
    'sup_ver',
    'sup_date',
    'sup_type',
    'md_uuid',
    'extradata',
    'edit_date',
  ]

  def __init__(self, lyrObj: Sequence[Any] | dict[str, Any]):
    if isinstance(lyrObj, tuple):
      super().__init__(lyrObj)
    elif isinstance(lyrObj, dict):
      sup_date = datetime.fromisoformat(lyrObj['sup_date']) if lyrObj['sup_date'] else None
      newRow = [
        lyrObj['identity'],
        False,
        lyrObj['relation'],
        lyrObj['geom_type'],
        lyrObj['pkey'],
        self.QUIESCENT,
        False,
        lyrObj['sup'],
        lyrObj['sup_ver'],
        sup_date,
        None,
        None,
        None,
        None,
      ]
      # logging.debug(f"initting new row: {newRow}")
      super().__init__(newRow)
      # logging.debug(self.sup_ver)
    else:
      raise Exception("Layer Object was not in an expected format")

    self.sch, self.tbl = self.identity.split('.')

  def __str__(self) -> str:
    return f"{self.identity}-{self.sup}-{self.sup_ver}-{self.status}"

  def merge(self, dbDsets: list[LyrReg]) -> None:
    if others := [d for d in dbDsets if d.identity == self.identity]:
      [setattr(self, col, getattr(others[0], col)) for col in self.cols]
    else:  # dirty hack for new datasets to be default MISC.
      self.sup = 'MISC'

  def delSql(self) -> Stmt:
    sqlStr = f"delete from {self.name} where identity=%s"
    sqlParams = (self.identity,)
    return sqlStr, sqlParams


class Schemas:  # list
  def __init__(self, type: str, cfg: Config, load: bool = True):
    # super().__init__(self)
    # print(f"Schema({type})")
    self.schs: list[Schema] = []
    self.type = type
    self.cfg = cfg

    # populate reads the api and the database, so a caller that cannot block builds
    # this empty and calls it itself.
    if load:
      self.populate()

  def populate(self) -> None:
    match self.type:
      case 'Meta':
        if self.cfg.get("regComplete") != "True":
          return

        api = ApiUtils(self.cfg.get('baseUrl'), self.cfg.get('api_key'), self.cfg.get('client_id'))
        rsp = api.post("data", {})  # get full list of permitted datasets
        _dsets = [LyrReg(d) for d in rsp['datasets']]

        # Merge in the existing table data for display and manipulation of active and status
        if self.cfg.get("dbComplete") == "True":
          _db = DB(self.cfg)
          _dbDsets = list(_db.getRecSet(LyrReg))
          [d.merge(_dbDsets) for d in _dsets]

        _schs = list({lyr.sch for lyr in _dsets})
        _schs.sort(key=lambda s: s)
        for sch in _schs:
          _lyrs = [d for d in _dsets if d.sch == sch]
          _newSch = Schema(sch)
          [_newSch.add(d) for d in _lyrs]
          self.schs.append(_newSch)
      case 'Data':
        if self.cfg.get("dbComplete") != "True":
          return

        _db = DB(self.cfg)
        _dbDsets = list(_db.getRecSet(LyrReg))
        _schs = _db.getSchemas()
        for sch in _schs:
          _newSch = Schema(sch)
          # combine the below with the available vm_meta.data info
          _dsets = [
            LyrReg(
              (
                f"{sch}.{tbl}",
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
              )
            )
            for tbl in _db.getTables(sch)
          ]
          [
            d.merge(_dbDsets) for d in _dsets
          ]  # merge in the existing metadata from the local tracking table
          [_newSch.add(d) for d in _dsets]
          self.schs.append(_newSch)
      case _:
        logging.warning(f"Metadata type {self.type} not known")

  def get(self, sch: str) -> Schema | None:
    if schs := [s for s in self.schs if s.name == sch]:
      return schs[0]
    logging.warning(f"No schema named {sch} in this metadata")
    return None
    # newSch = Schema(sch)
    # self.append(newSch)
    # return newSch


class Schema:  # list
  def __init__(self, sch: str):
    # super().__init__(self)
    self.name = sch
    self.lyrs: list[LyrReg] = []
    # print(f"*** {sch} ***")

  def add(self, lyr: LyrReg) -> None:
    # print(lyr)
    self.lyrs.append(lyr)
