from tkinter import (
  Tk,
  Button,
  Checkbutton,
  Frame,
  Label,
  Entry,
  StringVar,
  IntVar,
  END,
  Scrollbar,
  Canvas,
  Misc,
)
from tkinter import ttk

# import tkinter as tk
import logging
import math
from datetime import datetime
import webbrowser
import queue
import threading
import traceback
from collections.abc import Callable
from typing import Any, Literal

from .utils_db import DB
from .setup import QA
from .sync import Synccer, Supplies
from .utils import Config

from .utils_api import ApiUtils

from .dbTable import LyrReg, Schemas

# Where tkinter puts a widget's content inside its cell.
Anchor = Literal['nw', 'n', 'ne', 'w', 'center', 'e', 'sw', 's', 'se']


class StyMan:
  # Sizes rather than bare numbers in the widgets. font=(72) was not a tuple, so tk read
  # 72 as a family name, found none and fell back, which is why every one of these has
  # been rendering at 12 whatever the number said.
  fontHeading = ("TkDefaultFont", 14)
  # Use headings, written as that rather than as a number of its own so
  # the pair cannot drift apart.
  fontBigBtn = ("TkDefaultFont", fontHeading[1])

  qaClrFail = 'orange'
  qaClrPass = 'OliveDrab3'
  bgClrFail = 'brown'
  bgClrPass = 'skyblue'
  bgClrData = 'white'

  supVLAT = 'midnight blue'
  supVTT = 'dark green'
  supMISC = 'saddle brown'

  def __init__(self):
    # https://www.google.com/search?q=tkinter+colours

    self.style = ttk.Style()
    # self.style.configure("TButton", padding=6, font=("Arial", 12))
    # self.style.configure("Active.TButton", background="green", foreground=StyMan.bgClrData, font=("Arial", 12, "bold"))
    self.style.theme_create(
      "VlrsStyle",
      parent="default",
      settings={
        "TNotebook": {"configure": {"tabmargins": [2, 5, 2, 0]}},
        "TNotebook.Tab": {
          "configure": {
            "padding": [60, 10],
            "background": self.bgClrPass,
            "font": ('URW Gothic L', '11', 'bold'),
          },
        },
        "bad.TNotebook.Tab": {
          "configure": {
            "padding": [60, 10],
            "background": self.bgClrFail,
            "font": ('URW Gothic L', '11', 'bold'),
          },
        },
        "TFrame": {"configure": {"background": self.bgClrPass}},
        "bad.TFrame": {"configure": {"background": self.bgClrPass}},
        "lyrInfo.TFrame": {"configure": {"background": StyMan.bgClrData}},
        "metaLink.TLabel": {
          "configure": {"background": StyMan.bgClrData, "font": ('Sans', '10', 'bold', 'underline')}
        },
        "treeHeading.TLabel": {
          "configure": {"background": StyMan.bgClrData, "font": ('Sans', '9', 'bold')}
        },
        "Bold.TLabel": {"configure": {"font": ('Helvetica', 12, 'bold')}},
      },
    )
    self.style.theme_use("VlrsStyle")
    # self.style.configure('Good', background=self.bgClrPass) # Create style used by default for all Frames
    # self.style.configure('TFrame', background=self.bgClrFail) # Create style for the first frame


class GuiControl(Tk):
  def __init__(self, stg: str):
    super().__init__()
    # self.overrideredirect(1) # removes window, but loses max/min/close & screen positioning.

    self.cfg = Config('config.ini', stg)
    self.qa = QA(self.cfg)
    self.rights: dict[str, Any] = {}
    self.styleMgr = StyMan()

    # Work handed back from worker threads, run one batch per drain. Tkinter is only
    # safe to call from the thread that made the window, so this is the way back in.
    self._uiQueue: queue.Queue[Callable[[], None]] = queue.Queue()
    self._closing = False
    # Set while a job that changes data is running, so a second one cannot start.
    self.busy = False

    ###########################################################################
    # self.overrideredirect(1) # removes window, loses max/min/close & positioning.

    self.title("Vicmap Load & Replication Service")
    self.configure(background=StyMan.bgClrFail)
    # The minimum is measured from the built tabs further down, not set to a number
    # here that goes stale the next time a widget is added to one of them.
    # self.maxsize(495, 590)

    self.tabs = ttk.Notebook(self)
    self.tabs.grid(row=0, column=0, sticky='nsew')
    # tabs.pack(sticky='nsew')
    self.columnconfigure(0, weight=1)
    self.rowconfigure(0, weight=1)

    self.frSetup = FrSetup(self.tabs, self)
    self.tabs.add(self.frSetup, text='VRS Setup & QA')
    # self.frSetup.test()

    self.frMeta = FrMetaData(self.tabs, self, 'Meta')
    self.tabs.add(self.frMeta, text='Meta')

    self.frData = FrMetaData(self.tabs, self, 'Data')
    self.tabs.add(self.frData, text='Data')

    # What the tabs actually need, now that they exist. Without this the window opened
    # narrower than the setup tab and clipped it, and taller than any tab wanted.
    self.fitToContent()

    self._drainUi()

  # Grows the window into whatever a tab has come to need. The minimum only ever goes
  # up, so a pane that shrinks again cannot make the window jump about.
  def fitToContent(self) -> None:
    self.update_idletasks()
    _w, _h = self.minsize()
    self.minsize(max(_w, self.winfo_reqwidth()), max(_h, self.winfo_reqheight()))

  # Runs work on a worker thread, then hands its result, or the exception it raised,
  # to done back on the ui thread. Nothing in work may touch a widget.
  def runAsync(
    self, work: Callable[[], Any], done: Callable[[Any, Exception | None], None]
  ) -> None:
    def wrapper() -> None:
      result: Any = None
      err: Exception | None = None
      try:
        result = work()
      except Exception as ex:
        err = ex
        logging.error(traceback.format_exc())
      self.uiCall(lambda: done(result, err))

    threading.Thread(target=wrapper, daemon=True).start()

  # Queue a callable to run on the ui thread. Safe to call from any thread.
  def uiCall(self, fn: Callable[[], None]) -> None:
    self._uiQueue.put(fn)

  def _drainUi(self) -> None:
    while True:
      try:
        fn = self._uiQueue.get_nowait()
      except queue.Empty:
        break
      try:
        fn()
      except Exception:
        logging.error(traceback.format_exc())
    if not self._closing:
      self.after(100, self._drainUi)

  def destroy(self) -> None:
    # Stops the drain rescheduling itself onto a window that is going away.
    self._closing = True
    super().destroy()

    # self.tabs.add(FrAdmin(self.tabs, self), text='Admin')

  #   self.tabs.bind("<<NotebookTabChanged>>", self.refresh_tab_content)

  # def refresh_tab_content(self, event): # works, but.
  #   print(event)
  #   selected_tab = self.tabs.index(self.tabs.select())
  #   print(selected_tab)
  #   if selected_tab == 1:
  #       self.frMeta.setData() # 5 second pause waiting for full list from APIs
  #   elif selected_tab == 2:
  #       self.frData.setData() # quick, but doesn't remark the newly inactive checks.

  def uploadAllowed(
    self, lyr: LyrReg, upldType: str | None = None
  ) -> bool:  # upldType prevents overlogging whent he buttons havn't been pressed.
    # NB: checking these right here is just for display purposes, they are rechecked on submission on the server side of the API.
    if not self.rights:
      if upldType:
        print("GUI's got no rights. You need to refresh the registration form.")
      return False
    if lyr.sup in ('VLAT', 'VTT'):  # only MISC allowed
      if upldType:
        print(
          "Only MISC datasets (brown) can be updated. VLAT (green) and VTT (blue) are external maintanance contracts."
        )
      return False

    if (
      any(lyr.identity.startswith(s) for s in self.rights['schemas']['allow']['write'])
      and lyr.identity not in self.rights['datasets']['deny']['write']
    ):
      # print(f"validated: schema and not dataset.")
      return True
    if lyr.identity in self.rights['datasets']['allow']['write']:
      # print(f"validated: dataset. {lyr.identity in self.rights['datasets']['allow']['write']}")
      return True

    if upldType:
      print("default no rights")
    return False  # default.


###########################################################################
###########################################################################
class FrMetaData(ttk.Frame):
  def __init__(self, container: Misc, guic: GuiControl, type: str):
    super().__init__(container, style="bad.TFrame")  # "bad.TFrame")#
    self.guic = guic
    self.type = type  # is it remote ('Meta') or local ('Data')
    self.schDepth = 0
    self.data = Schemas(self.type, self.guic.cfg, load=False)

    self.schFr = SubFrMetaSchs(self, guic, self.data)  # self.mkSchFr() #
    self.schFr.grid(row=1, column=0, padx=5, pady=5, sticky='nw')  # columnspan=2,

    self.lyrFr = SubFrMetaLyrs(self, guic, self.data)  # self.mkLyrFr() #
    self.lyrFr.grid(row=1, column=1, padx=5, pady=5, sticky='nsew')  # columnspan=2,
    self.grid_columnconfigure(1, weight=1)

    self.lyrInfoFr = SubFrMetaLyrInfo(self, guic)
    self.lyrInfoFr.grid(row=2, column=0, columnspan=4, padx=10, pady=10, sticky="nsew")
    self.rowconfigure(1, weight=1)
    self.rowconfigure(2, weight=1)

    self.setData()

  def setData(self) -> None:
    self.guic.runAsync(lambda: Schemas(self.type, self.guic.cfg), self._setDataDone)

  def _setDataDone(self, data: Schemas | None, err: Exception | None) -> None:
    if err or not data:
      logging.error(f"Could not read the {self.type} layer list: {err}")
      return
    print([sch.name for sch in data.schs])
    self.data = data
    self.schFr.setData(data)
    self.lyrFr.setData(data)
    print(len(data.schs))

  ###########################################################################
  ###########################################################################
  def mkLyrFr(self) -> Frame:
    _fr = Frame(self, borderwidth=1, relief="raised", bg=StyMan.bgClrPass)
    _schHdr = Label(_fr, text="Layers", bg=StyMan.bgClrPass, font='bold')
    _schHdr.grid(row=0, column=0, sticky='nsew')
    return _fr

  ###########################################################################
  ###########################################################################


class SubFrMeta(Frame):
  def __init__(self, owner: Misc, guic: GuiControl):
    if self.__class__.__name__ == 'SubFrMetaLyrInfo':
      super().__init__(owner, borderwidth=5, padx=5, pady=5, relief="sunken", bg=StyMan.bgClrData)
    else:
      super().__init__(owner, borderwidth=1, padx=5, pady=5, relief="raised", bg=StyMan.bgClrPass)
    self.bgClr = StringVar(value=StyMan.bgClrPass)
    self.guic = guic


class SubFrMetaSchs(SubFrMeta):
  def __init__(self, owner: FrMetaData, guic: GuiControl, data: Schemas):
    super().__init__(owner, guic)

    self.owner = owner
    self.selected: Button | None = None  # currently selected schema
    self.schBtns: list[Button] = []

    """ HEADER """
    _schHdr = Label(self, text="Schemas", bg=StyMan.bgClrPass, font='bold')
    _schHdr.grid(row=0, column=0, columnspan=2, sticky='nsew')
    """ SCHEMAS """
    self.setData(data)

  def setData(self, data: Schemas) -> None:
    [btn.destroy() for btn in self.schBtns]
    self.schBtns = []
    self.selected = None
    self.schs = data.schs

    _schCnt = len(self.schs)
    _nrCols = 2
    _nrItems = math.ceil(_schCnt / _nrCols)
    for ii in range(_schCnt):
      _row = 1 + (ii % _nrItems)
      _col = int(ii / _nrItems)
      self.mkSchBtn(self.schs[ii].name, _row, _col)
    self.schDepth = _nrItems

  def mkSchBtn(self, sch: str, row: int, col: int) -> None:
    setattr(
      self,
      f"btn{sch}",
      Button(
        self,
        textvariable=StringVar(value=sch),
        width=8,
        height=1,
        padx=1,
        relief="solid",
        background=StyMan.qaClrFail,
      ),
    )
    _btn: Button = getattr(self, f"btn{sch}")
    _btn.config(command=lambda: self.showSch(f"{sch}"))
    _btn.grid(row=row, column=col, sticky="W", padx=5)  # , pady=(2,0))
    self.schBtns.append(_btn)

  def selectedName(self) -> str | None:
    return str(self.selected["text"]) if self.selected else None

  def showSch(self, sch: str) -> None:
    # change the schema button colours
    if self.selected:
      self.selected.config(background=StyMan.qaClrFail)
    _btn: Button = getattr(self, f"btn{sch}")
    self.selected = _btn
    _btn.config(background=StyMan.qaClrPass)

    self.owner.lyrFr.redrawCanvas(sch)


class SubFrMetaLyrs(SubFrMeta):
  def __init__(self, owner: FrMetaData, guic: GuiControl, data: Schemas):
    super().__init__(owner, guic)
    self.data = data
    self.owner = owner

    # super().__init__(owner, width=400, height=300, background='red')
    self.lyrHdrStr = StringVar(self, "Layers")
    self.lyrHdr = Label(
      self, text="Layers", bg=StyMan.bgClrPass, font='bold', textvariable=self.lyrHdrStr
    )
    self.lyrHdr.grid(row=0, column=0, sticky='ew')
    if self.owner.type == "Meta":
      self.btnSchOn = Button(
        self,
        text="All ON",
        padx=10,
        background=StyMan.qaClrPass,
        anchor='e',
        command=lambda: self.toggleActive(sch=self.owner.schFr.selectedName(), active=True),
      )
      self.btnSchOn.grid(row=0, column=1, sticky='e')
      self.btnSchOff = Button(
        self,
        text="All OFF",
        padx=10,
        background=StyMan.qaClrFail,
        anchor='e',
        command=lambda: self.toggleActive(sch=self.owner.schFr.selectedName(), active=False),
      )
      self.btnSchOff.grid(row=0, column=2, sticky='e')

    self.grid_columnconfigure(0, weight=1)
    self.grid_rowconfigure(1, weight=1)

    self.canvas = Canvas(self, width=415, background=StyMan.bgClrPass)
    self.canvas.bind(
      '<Enter>', lambda e: self.canvas.bind_all("<MouseWheel>", self._on_lyr_mousewheel)
    )
    self.canvas.bind('<Leave>', lambda e: self.canvas.unbind_all("<MouseWheel>"))

    self.lyrFrame = ttk.Frame(self.canvas, padding=(5, 5), style='bad.TFrame')  # , width=50)
    self.lyrFrame.bind(
      "<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
    )
    self.canvasWin = self.canvas.create_window((0, 0), window=self.lyrFrame, anchor="nw")
    self.canvas.bind(
      '<Configure>', lambda e: self.canvas.itemconfigure(self.canvasWin, width=e.width)
    )
    self.canvas.grid(row=1, column=0, columnspan=3, sticky="nsew")  # rowspan=self.schDepth+1,

    self.lyrScrollbar = Scrollbar(
      self,
      orient="vertical",
      command=self.canvas.yview,  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]
    )
    self.lyrScrollbar.grid(row=1, column=4, sticky="ns")
    # Wired here as well as on every redraw, because until the canvas has reported a
    # position the scrollbar answers with the four value protocol, and the wheel over
    # one of those calls yview with a bare number, which is not a thing yview takes.
    self.canvas.configure(yscrollcommand=self.lyrScrollbar.set)
    self.lyrScrollbar.set(0.0, 1.0)

    # self.guic = guic
    self.lyrBtns: list[Button] = []
    self.lyrChks: list[Checkbutton] = []
    self.lyrVars: list[IntVar] = []
    self.selected: Button | None = None  # currently selected schema

    self.redrawCanvas()

    # self.columnconfigure(1, weight=1)
    # self.rowconfigure(1)#, weight=1)
    # self.columnconfigure(0, weight=1)
    # self.rowconfigure(0)#, weight=1)

  def _on_lyr_mousewheel(self, event: Any) -> None:
    self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

  def setData(self, data: Schemas) -> None:
    self.data = data

  def redrawCanvas(self, newSch: str | None = None) -> None:
    # print("reDraw")
    if not newSch:
      return

      # clear current controls
    [lyrBtn.destroy() for lyrBtn in self.lyrBtns]
    [lyrChk.destroy() for lyrChk in self.lyrChks]
    # [lyrVar.destroy() for lyrVar in self.lyrVars]

    self.lyrBtns, self.lyrChks = [], []

    if not (_sch := self.data.get(newSch)):
      return
    self.nrLyrs = len(_sch.lyrs)
    self.lyrHdrStr.set(f"Layers ({self.nrLyrs})")
    # _lyrs = [d.tbl for d in _sch.lyrs]
    _sch.lyrs.sort(key=lambda lyr: lyr.identity)
    self.setLyrs(_sch.lyrs)
    # self.update_idletasks()
    self.canvas.configure(yscrollcommand=self.lyrScrollbar.set)

  def setLyrs(self, lyrs: list[LyrReg]) -> None:
    self.selected: Button | None = None
    [self.mkLyrBtn(lyr, lyrs.index(lyr)) for lyr in lyrs]  # , 0
    # self.columnconfigure((0,2), 1)
    [
      self.lyrFrame.columnconfigure(ii, uniform='equal_columns', weight=1) for ii in (0, 2)
    ]  # range(2)]

  def mkLyrBtn(self, lyr: LyrReg, idx: int) -> None:  # , col):
    # print(f"mkLyrBtn({self}, {lyr}, {rowNum}, {col})")
    _cols = 2
    rowNum, colNum = int(idx / _cols) % self.nrLyrs, idx % _cols
    # print(f"({rowNum}, {colNum*_cols}) ({rowNum}, {(colNum*_cols)+1})")

    fgCol = getattr(StyMan, f"sup{lyr.sup}")
    setattr(
      self,
      f"lyrBtn{lyr.identity}",
      Button(
        self.lyrFrame,
        text=lyr.tbl,
        padx=10,
        background="snow3",
        anchor='w',
        fg=fgCol,
        command=lambda: self.showLyrDetails(lyr),
      ),
    )
    getattr(self, f"lyrBtn{lyr.identity}").grid(
      row=rowNum, column=(colNum * _cols) + 1, sticky="nsew", padx=(0, 3), pady=1
    )
    self.lyrBtns.append(getattr(self, f"lyrBtn{lyr.identity}"))

    if self.owner.type == "Meta":
      setattr(self, f"lyrAct{lyr.identity}", IntVar(value=1 if lyr.active else 0))
      setattr(
        self,
        f"lyrChk{lyr.identity}",
        Checkbutton(
          self.lyrFrame,
          variable=getattr(self, f"lyrAct{lyr.identity}"),
          onvalue=1,
          offvalue=0,
          bg=fgCol,
          command=lambda: self.toggleActive(lyr=lyr),
        ),
      )
      getattr(self, f"lyrChk{lyr.identity}").grid(
        row=rowNum, column=colNum * _cols, sticky="E", padx=(3, 0), pady=1
      )
      if self.guic.cfg.get('dbComplete') != "True":
        getattr(self, f"lyrChk{lyr.identity}").config(state="disabled")
      self.lyrChks.append(getattr(self, f"lyrChk{lyr.identity}"))
      self.lyrVars.append(getattr(self, f"lyrAct{lyr.identity}"))

  def showLyrDetails(self, lyr: LyrReg) -> None:
    if self.selected:
      self.selected.config(background="snow3")
    _btn: Button = getattr(self, f"lyrBtn{lyr.identity}")
    self.selected = _btn
    _btn.config(background=StyMan.bgClrData)

    self.owner.lyrInfoFr.showLyrDetails(lyr)

  def toggleActive(
    self, lyr: LyrReg | None = None, sch: str | None = None, active: bool | None = None
  ) -> None:
    _db = DB(self.guic.cfg)
    if lyr:
      active = bool(getattr(self, f"lyrAct{lyr.identity}").get())
      _db.execute(*lyr.setActive(active))
    if sch:
      sqlStr = f"update vm_meta.data set active={str(active).lower()} where identity like '{sch}%'"
      _db.execute(sqlStr)
      [lyrVar.set(bool(active)) for lyrVar in self.lyrVars]


class SubFrMetaLyrInfo(SubFrMeta):
  def __init__(self, owner: FrMetaData, guic: GuiControl):
    super().__init__(owner, guic)
    self.owner = owner
    self.lyrMeta: dict[str, Any] | None = None
    # The layer whose details were last asked for, used to drop stale answers.
    self.pendingLyr: LyrReg | None = None

  def showLyrDetails(self, lyr: LyrReg) -> None:
    # The metadata is an api call, so it is fetched off the ui thread and the frame is
    # drawn when it lands. The layer asked for is remembered so a slow answer for an
    # earlier click cannot draw over a later one.
    self.pendingLyr = lyr
    for widget in self.winfo_children():
      widget.destroy()
    Label(self, text=f"Loading {lyr.identity} ...", bg=StyMan.bgClrData).grid(
      row=0, column=0, padx=10, pady=10
    )
    self.guic.runAsync(
      lambda: self.getLyrMetadata(lyr.identity),
      lambda meta, err: self._lyrMetaDone(lyr, meta, err),
    )

  def _lyrMetaDone(self, lyr: LyrReg, meta: dict[str, Any] | None, err: Exception | None) -> None:
    if self.pendingLyr is not lyr:  # a later click has already asked for something else
      return
    if err:
      logging.warning(err)
    self.lyrMeta = meta
    self.renderLyrDetails(lyr)

  def renderLyrDetails(self, lyr: LyrReg) -> None:
    for widget in self.winfo_children():
      widget.destroy()

    _frIdent = Frame(self, borderwidth=2, relief="raised", bg=StyMan.bgClrPass)
    Label(_frIdent, text=lyr.identity, background=StyMan.bgClrPass, font='bold').grid(
      row=0, column=0, padx=10, pady=5
    )  # , textvariable=self.lyrNameStr)
    _frIdent.grid(row=0, column=0, columnspan=2, sticky='W')
    # ttk.Label(self, text=lyr.identity, border=0).grid(row=0, column=0, padx=10)

    if self.owner.type == "Meta":  # all records here should have vicmap metadata from the APIs.
      _frActions = Frame(self, borderwidth=2, bg=StyMan.bgClrData)
      layerReseed = Button(
        _frActions,
        text="Reseed",
        padx=5,
        pady=2,
        background="snow3",
        bg=StyMan.qaClrPass,
        command=lambda: self.reseed(lyr.identity),
      )  # anchor='e',
      layerReseed.grid(row=0, column=0, padx=(0.10), sticky='W')
      layerMetaLink = Button(
        _frActions,
        text="Metadata weblink (GeoNetwork ISO 19115)",
        padx=5,
        pady=2,
        background="snow3",
        anchor='e',
        bg=StyMan.qaClrPass,
        command=self.openMetaLink,
      )  # self.geonet(self.lyrMeta))
      layerMetaLink.grid(row=0, column=1, padx=(10.0), sticky='E')  # padx=(5.5),
      _frActions.grid(row=0, column=3, columnspan=4)  # , sticky='EW')
    if self.owner.type == "Data":
      print(lyr)
      _frUpload = self.mkFrUpload(lyr)
      _frUpload.grid(row=0, column=3, columnspan=4, sticky='e')

    if self.lyrMeta:  # existing layer
      ## Table Columns
      _colData = (
        [(col, type) for col, type in self.lyrMeta['columns'].items()]
        if self.lyrMeta['columns']
        else []
      )
      _colcols: list[tuple[str, int, Anchor]] = [('Column', 120, 'e'), ('Type', 120, 'w')]
      _cols = TView(self, 'Columns', _colcols, 1, 0, _colData)
      ## Table Indexes
      _idxData = (
        [(idx[1], idx[0], idx[2]) for idx in self.lyrMeta['indexes']]
        if self.lyrMeta['indexes']
        else []
      )
      _idxCols: list[tuple[str, int, Anchor]] = [
        ('Column', 120, 'w'),
        ('idx_Name', 120, 'w'),
        ('Type', 50, 'w'),
      ]
      _idxs = TView(self, 'Indexes', _idxCols, 1, 3, _idxData)
      ## Dump History Tree
      _ldData = (
        [
          (
            dump[2],
            dump[1],
            datetime.fromisoformat(dump[3]).strftime('%d/%m/%Y %H:%M'),
            dump[4],
            dump[5],
            dump[6],
          )
          for dump in self.lyrMeta['pgDumps']
        ]
        if self.lyrMeta['pgDumps']
        else []
      )
      _ldData.sort(key=lambda x: datetime.strptime(x[2], "%d/%m/%Y %H:%M"), reverse=True)
      _ldCols: list[tuple[str, int, Anchor]] = [
        ('Supply Version', 50, 'w'),
        ('Type', 50, 'w'),
        ('Date', 100, 'w'),
        ('Adds', 80, 'e'),
        ('Dels', 80, 'e'),
        ('Count', 80, 'e'),
      ]
      _loads = TView(self, 'Update History', _ldCols, 3, 0, _ldData, 7)  #'Type':75,
    else:  # new layer
      self.mkNewUplFrm()

    # How wide this pane needs to be depends on the layer that was clicked, so the
    # window is given the chance to grow into it.
    self.guic.fitToContent()

  def mkNewUplFrm(self) -> None:
    Label(self, text='Upload New Dataset', border=3).grid(row=1, column=0, padx=10, sticky='EW')
    # (self, fr, bgClr, var, name, val, wid, row, col, colspan=1, private=False):
    # (self, self.bgClr, 'email', 'email', _valEmail, 60, 1, 0, 3)

    self.relation = StringVar()
    _lbl = Label(self, text='Relation:', background=StyMan.bgClrData)
    _lbl.grid(row=2, column=0, sticky="E")
    # Label(self, text='datasets:').grid(row=1, column=4, sticky="E")
    self.relBox = ttk.Combobox(self, values=['table', 'view'])
    self.relBox.current(0)
    self.relBox.grid(row=2, column=1, sticky="W")
    # self.relBox.bind("<<ComboboxSelected>>", self.profileChanged)
    # self.relBox.bind("<Return>",self.profileChanged)

    self.mdUUID = StringVar()
    Label(self, text='GeoNetwork UUID:', background=StyMan.bgClrData).grid(
      row=3, column=0, sticky='E'
    )
    self.uuidEnt = Entry(self, textvariable=self.mdUUID, width=40, bd=3).grid(
      row=3, column=1, sticky='W'
    )

    self.geomtype = StringVar()
    Label(self, text='Geometry Type:', background=StyMan.bgClrData).grid(
      row=4, column=0, sticky='E'
    )
    self.gtBox = ttk.Combobox(
      self,
      values=[
        'polygon',
        'multipolygon',
        'linestring',
        'multilinestring',
        'point',
        'multipoint',
        'none',
      ],
    )
    self.gtBox.current(0)
    self.gtBox.grid(row=4, column=1, sticky="W")

    self.vdp = IntVar(value=0)
    Label(self, text='VDP:', background=StyMan.bgClrData).grid(row=5, column=0, sticky='E')
    self.vdpChk = Checkbutton(self, variable=self.vdp, onvalue=1, offvalue=0)
    self.vdpChk.grid(row=5, column=1, sticky="W")

    testBtn = Button(
      self,
      text="test",
      padx=5,
      pady=2,
      background="snow3",
      bg=StyMan.qaClrPass,
      command=lambda: self.testVars(),
    )
    testBtn.grid(row=6, column=1, padx=5, pady=5)

  def testVars(self) -> None:
    print(
      f"{self.mdUUID.get()} {self.relBox.get()} {self.gtBox.get()} {"true" if self.vdp.get() else "false"}"
    )

  def mkFrUpload(self, lyr: LyrReg) -> Frame:
    _fr = Frame(self, borderwidth=1, relief="raised", bg=StyMan.bgClrPass)
    ttk.Label(_fr, text='Upload', border=3).grid(row=0, column=0, padx=10)
    lyrUploadInc = Button(
      _fr,
      text="INC",
      padx=5,
      pady=2,
      background="snow3",
      bg=StyMan.qaClrPass,
      command=lambda: self.upload(lyr, Supplies.INC),
    )
    lyrUploadInc.grid(row=0, column=1, pady=5)

    lyrUploadDiff = Button(
      _fr,
      text="DIFF",
      padx=5,
      pady=2,
      background="snow3",
      bg=StyMan.qaClrPass,
      command=lambda: self.upload(lyr, Supplies.DIFF),
    )
    lyrUploadDiff.grid(row=0, column=2, padx=5, pady=5)
    lyrUploadFull = Button(
      _fr,
      text="FULL",
      padx=5,
      pady=2,
      background="snow3",
      bg=StyMan.qaClrPass,
      command=lambda: self.upload(lyr, Supplies.FULL),
    )
    lyrUploadFull.grid(row=0, column=3, padx=5, pady=5)

    if not self.lyrMeta:  # new dataset, full upload only
      lyrUploadInc.configure(fg='white', state="disabled", bg=StyMan.bgClrFail)
      lyrUploadDiff.configure(fg='white', state="disabled", bg=StyMan.bgClrFail)
    if not self.guic.uploadAllowed(lyr):
      lyrUploadInc.configure(fg='white', state="disabled", bg=StyMan.bgClrFail)
      lyrUploadDiff.configure(fg='white', state="disabled", bg=StyMan.bgClrFail)
      lyrUploadFull.configure(fg='white', state="disabled", bg=StyMan.bgClrFail)
    return _fr

  def getLyrMetadata(self, ident: str) -> dict[str, Any] | None:
    api = ApiUtils(
      self.guic.cfg.get('baseUrl'), self.guic.cfg.get('api_key'), self.guic.cfg.get('client_id')
    )
    response = None
    try:
      response = api.post("data", {"dset": f"{ident}"})
    except Exception as ex:
      logging.warning(ex)
    return response

  # def geonet(self, layerMeta):
  #   webbrowser.open_new(layerMeta['metadata'])

  def upload(self, lyr: LyrReg, upldType: str) -> None:
    print(f"{lyr}, {upldType}")
    if not self.guic.uploadAllowed(lyr, upldType):
      print(
        f"You have no rights to update {lyr.identity} data. If you think you should, try refreshing the registration"
      )
      return
    if upldType == Supplies.INC:
      print("INCREMENTAL supplies have not yet been implemented from the client")
    if self.guic.busy:
      print("Another job is still running, wait for it to finish")
      return

    # The form is read here, on the ui thread. The worker only gets plain values.
    if self.lyrMeta:  # existing dset
      _new = None
    else:
      _new = {
        'relation': self.relBox.get(),
        'md_uuid': self.mdUUID.get(),
        'geomType': self.gtBox.get(),
        'vdp': bool(self.vdp.get()),
      }
      print(_new)

    self.guic.busy = True
    print(f"uploading {lyr.identity} ...")
    self.guic.runAsync(
      lambda: self._runUpload(lyr.identity, upldType, _new),
      lambda ok, err: self._uploadDone(lyr, ok, err),
    )

  # Off the ui thread, so it opens its own connection and touches no widget.
  def _runUpload(self, ident: str, upldType: str, new: dict[str, Any] | None) -> bool:
    _db = DB(self.guic.cfg)
    try:
      sync = Synccer(self.guic.cfg, _db)
      if new is None:  # existing dset
        return sync.upload(ident, upldType)
      return sync.upload(ident, upldType, **new)
    finally:
      _db.close()

  def _uploadDone(self, lyr: LyrReg, ok: bool, err: Exception | None) -> None:
    self.guic.busy = False
    if err:
      print(f"upload of {lyr.identity} failed: {err}")
    else:
      print(f"upload of {lyr.identity} {'succeeded' if ok else 'did not succeed'}")
    self.guic.frSetup.ctrlFrm.refresh()

  def openMetaLink(self) -> None:
    if link := (self.lyrMeta or {}).get('metadata'):
      webbrowser.open_new(link)
    else:
      logging.warning("This layer has no metadata link to open")

  def reseed(self, ident: str) -> None:
    print(f"Reseeding {ident}")
    _db = DB(self.guic.cfg)
    _db.fixErrs(ident)
    _db.close()
    # Should we kick off an immediate sync? (may get hung up on other unsyncced layers for awhile.)


class TView(ttk.Treeview):
  def __init__(
    self,
    owner: Misc,
    name: str,
    colTupl: list[tuple[str, int, Anchor]],
    row: int,
    col: int,
    data: list[tuple[Any, ...]],
    height: int = 10,
  ):
    super().__init__(owner, columns=[c[0] for c in colTupl], height=height, show='headings')

    self.colHdr = ttk.Label(owner, text=name, style='treeHeading.TLabel')
    self.colHdr.grid(row=row, column=col, columnspan=len(colTupl) + 1, sticky='w')
    [self.mkCol(tupl) for tupl in colTupl]
    [self.insert('', END, values=rowData) for rowData in data]
    self.grid(row=row + 1, column=col, columnspan=len(colTupl), sticky='nsew')

    self.scrollbar = Scrollbar(
      owner,
      orient='vertical',
      command=self.yview,  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]
    )
    self.scrollbar.grid(row=row + 1, column=col + len(colTupl), sticky='ns', padx=(0, 3))
    self.configure(yscrollcommand=self.scrollbar.set)
    self.scrollbar.set(0.0, 1.0)  # same as the layer canvas, for a table with no rows

  def mkCol(self, colTupl: tuple[str, int, Anchor]) -> None:
    name, wid, anc = colTupl
    self.heading(name, text=name)
    self.column(name, minwidth=0, width=wid, anchor=anc, stretch=True)


class FrSetup(ttk.Frame):
  def __init__(self, container: Misc, guic: GuiControl):
    super().__init__(container, style="bad.TFrame")
    self.guic = guic

    # Label(tSetup, text='Vicmap Replication Service', font=(32)).grid(row=0, column=0, columnspan=2, padx=5, pady=5)
    ##
    # qaReg
    Label(self, text='profile:', bg=StyMan.bgClrPass).grid(row=0, column=0, sticky="E")
    self.profiles = self.guic.cfg.cp.sections()
    # self.profiles.append("Add New...")
    self.proBox = ttk.Combobox(self, values=self.profiles)
    self.proBox.current(0)
    self.proBox.grid(row=0, column=1, sticky="W")
    self.proBox.bind("<<ComboboxSelected>>", self.profileChanged)
    self.proBox.bind("<Return>", self.profileChanged)

    Label(self, text='API URL:', bg=StyMan.bgClrPass).grid(row=1, column=0, sticky="E")
    self.strurl = StringVar(value=self.guic.cfg.get('baseUrl'))
    Label(self, textvariable=self.strurl, bg=StyMan.bgClrPass).grid(row=1, column=1, sticky="W")

    self.ctrlFrm = SubFrCtrl(self, self.guic)
    self.ctrlFrm.grid(row=4, column=0, columnspan=2, padx=5, pady=(0, 5), sticky='E')
    self.regFrm = SubFrReg(self, self.guic)
    self.regFrm.grid(row=2, column=0, columnspan=2, padx=5, pady=(0, 5), sticky='nsew')
    self.dbFrm = SubFrDb(self, self.guic)
    self.dbFrm.grid(row=3, column=0, columnspan=2, padx=5, pady=(0, 5), sticky='nsew')

  ###########################################################################

  def profileChanged(self, event: Any) -> None:
    _profile = self.proBox.get()
    # print(f"{_profile} {event}")
    if _profile not in self.guic.cfg.cp.sections():
      print("Making new section")
      self.guic.cfg.setStage(_profile)
      self.profiles.append(_profile)
      self.refresh()
    else:
      print("updating with existing section")
      self.guic.cfg.setStage(_profile)
      self.refresh()

  def test(self) -> None:
    self.regFrm.test()
    self.dbFrm.test()

  def refresh(self) -> None:
    # meta
    self.strurl.set(self.guic.cfg.get('baseUrl'))
    self.regFrm.refresh()
    self.dbFrm.refresh()
    self.ctrlFrm.refresh()


class SubFr(Frame):
  def __init__(self, owner: Misc, guic: GuiControl):
    # print(self.__class__.__name__)
    if self.__class__.__name__ != 'SubFrCtrl':
      super().__init__(owner, bg=StyMan.qaClrFail, borderwidth=5, padx=5, pady=5, relief="sunken")
    else:
      super().__init__(owner, borderwidth=5, padx=5, pady=5, relief="raised")
    self.bgClr = StringVar(value=StyMan.qaClrFail)
    self.guic = guic
    self.bgElements: list[Frame | Label] = [self]

  def paint(self, passed: bool) -> None:
    for ele in self.bgElements:
      ele.config(bg=StyMan.qaClrPass if passed else StyMan.qaClrFail)

  def lblEnt(
    self,
    fr: Misc,
    bgClr: StringVar,
    var: str,
    name: str,
    val: str,
    wid: int | None,
    row: int,
    col: int,
    colspan: int = 1,
    private: bool = False,
  ) -> Label:
    # set label as lbl{var}
    setattr(self, f"lbl{var}", Label(fr, text=f"{name}:", background=bgClr.get(), width=8))
    getattr(self, f"lbl{var}").grid(row=row, column=col, sticky="E")
    self.bgElements.append(getattr(self, f"lbl{var}"))
    # set entry as var, value as str{var}
    _displayVal = val if not private else '' if not val else 'xxxxx-xxxxx-xxxxx'
    setattr(
      self, f"str{var}", StringVar(value=_displayVal)
    )  #'xxxxx-xxxxx-xxxxx' if private else val))
    setattr(
      self, var, Entry(fr, textvariable=getattr(self, f"str{var}"), width=wid if wid else 20, bd=3)
    )
    # getattr(self, var).insert(0, val)
    getattr(self, var).grid(row=row, column=col + 1, columnspan=colspan, sticky="W", padx=5, pady=2)
    return getattr(self, f"lbl{var}")

  def qaChk(
    self, fr: Misc, var: str, desc: str, row: int, col: int
  ) -> IntVar:  # (self.cntrlFrame, "DB", "DB", 1, 0)
    setattr(self, f"qa{var}", IntVar(value=0))  # IntVar())#self.qaDb = IntVar()
    setattr(
      self,
      f"chk{var}",
      Checkbutton(fr, text=desc, variable=getattr(self, f"qa{var}"), onvalue=1, offvalue=0),
    )  # , tristatevalue=2))#o)) # self.dbChk = Checkbutton(self.cntrlFrame, text='DB', variable=self.qaDb, onvalue=1, offvalue=0)#, command=print_selection)
    getattr(self, f"chk{var}").config(state="disabled")
    getattr(self, f"chk{var}").grid(row=row, column=col, sticky='W')
    return getattr(self, f"qa{var}")


class SubFrReg(SubFr):
  # Built by lblEnt and qaChk, which make the attribute names out of the var passed in.
  clientId: Entry
  strclientId: StringVar
  apik: Entry
  strapik: StringVar
  email: Entry
  stremail: StringVar
  qaReg: IntVar
  qaVal: IntVar

  def __init__(self, owner: FrSetup, guic: GuiControl):
    super().__init__(owner, guic)

    """ HEADER """
    self.lblRegHdr = Label(self, text='Registration', background=self.bgClr.get())
    self.lblRegHdr.grid(row=0, column=0, columnspan=3, pady=(0, 5), sticky="W")
    self.bgElements.append(self.lblRegHdr)
    """ QA """
    qaFr = Frame(self, borderwidth=1, relief="solid")
    Label(qaFr, text='QA', font=StyMan.fontHeading, width=12).grid(row=0, column=0, pady=2)
    self.qaVars: list[IntVar] = []
    qaArr = [("Reg", "Registered", 1, 0), ("Val", "Validated", 2, 0)]
    [self.qaVars.append(self.qaChk(qaFr, *qat)) for qat in qaArr]
    Button(qaFr, text='Refresh', relief="solid", command=lambda: self.test()).grid(
      row=3, rowspan=1, column=0, sticky="nsew", padx=5, pady=5
    )  # (5,5))
    qaFr.grid(row=0, column=4, rowspan=5, columnspan=1, sticky='E', padx=20, pady=5)

    """ EMAIL """
    _valEmail = self.guic.cfg.get("email") or ""
    self.lblemail = self.lblEnt(self, self.bgClr, 'email', 'email', _valEmail, 60, 1, 0, 3)
    """ CLIENT_ID """
    _valClient = self.guic.cfg.get("client_id") or ''
    self.lblClientId = self.lblEnt(
      self, self.bgClr, 'clientId', 'Client ID', _valClient, 40, 2, 0, private=True
    )
    self.clientId.config(state='disabled')
    """ API_KEY """
    _valApik = self.guic.cfg.get("api_key") or ''
    self.lblApik = self.lblEnt(
      self, self.bgClr, 'apik', 'API Key', _valApik, 40, 3, 0, private=True
    )
    self.apik.config(state='disabled')
    """ MESSAGE """
    self.regMsg = Label(self, text='', background=self.bgClr.get())
    self.regMsg.grid(row=5, column=0, columnspan=4, pady=(0, 5), sticky="E")
    self.bgElements.append(self.regMsg)

    if self.guic.cfg.get('regComplete') == "True":
      self.paint(True)

  def test(self) -> None:
    self.guic.cfg.set({"email": self.email.get()})  # client_id and api_key are non editable.
    self.regMsg.config(text="checking ...")
    self.guic.runAsync(self.guic.qa.checkApiClient, self._testDone)

  def _testDone(self, result: tuple[int, Any] | None, err: Exception | None) -> None:
    if err or not result:
      self.regMsg.config(text=f"Registration check failed: {err}")
      return
    qaCode, qaMsg = result
    print(f"{qaCode}, {qaMsg}")
    if qaCode == 0:  # possible?
      self.regMsg.config(text=qaMsg)
      # self.paint(False)
    elif qaCode == 1:  # still need to verify the email
      self.qaReg.set(1)
      self.regMsg.config(text=qaMsg)
      # self.paint(False)
    elif qaCode == 2:  # verified
      self.qaReg.set(1)
      self.qaVal.set(1)
      self.regMsg.config(text="Read and Upload rights have been set.")  # str(qaMsg))
      self.guic.rights = qaMsg  # dict returned when success here.
      # self.paint(True)
      self.guic.frMeta.setData()

    self.refresh()
    self.guic.frSetup.ctrlFrm.refresh()
    # self.guic.frMeta.setData()
    # self.regMsg.config(text=qaMsg)

  def refresh(self) -> None:
    # repopulate the values from config as values/profile may have changed.
    self.stremail.set(self.guic.cfg.get("email"))
    self.strclientId.set('xxxxx-xxxxx-xxxxx' if self.guic.cfg.get("client_id") else '')
    self.strapik.set('xxxxx-xxxxx-xxxxx' if self.guic.cfg.get("api_key") else '')
    self.qaReg.set(1 if self.guic.cfg.get("client_id") else 0)
    self.qaVal.set(1 if self.guic.cfg.get("api_key") else 0)

    self.paint(self.guic.cfg.get("regComplete") == "True")


class SubFrDb(SubFr):
  # As SubFrReg: qaChk builds these from the var it is given.
  qaDb: IntVar
  qaClt: IntVar
  qaSpat: IntVar
  qaMeta: IntVar
  endp: Entry
  strendp: StringVar
  inst: Entry
  strinst: StringVar
  port: Entry
  strport: StringVar
  user: Entry
  struser: StringVar
  pswd: Entry
  strpswd: StringVar
  binPath: Entry
  strbinPath: StringVar

  def __init__(self, owner: FrSetup, guic: GuiControl):
    super().__init__(owner, guic)

    """ HEADER """
    self.lblDbHdr = Label(self, text='Database Connection Details', background=self.bgClr.get())
    self.lblDbHdr.grid(row=0, column=0, columnspan=2, sticky='W', pady=(0, 5))
    self.bgElements.append(self.lblDbHdr)
    """ QA """
    qaFr = Frame(self, borderwidth=1, relief="solid")
    Label(qaFr, text='QA', font=StyMan.fontHeading, width=12).grid(row=0, column=0, pady=2)
    self.qaVars: list[IntVar] = []
    qaArr = [
      ("Db", "DB cnxn", 1, 0),
      ("Clt", "DB PG_Client", 2, 0),
      ("Spat", "PostGis", 3, 0),
      ("Meta", "Metadata", 4, 0),
    ]
    [self.qaVars.append(self.qaChk(qaFr, *qat)) for qat in qaArr]
    Button(qaFr, text='Test DB', relief="solid", command=self.test).grid(
      row=5, column=0, rowspan=1, sticky="nsew", padx=5, pady=5
    )  # row=4, column=0, sticky="W", pady=(0,5))
    # Button(qaFr, text='Test Spatial', command=self.test('spat')).grid(row=0, column=3, sticky="E", pady=(0,5))
    qaFr.grid(row=0, column=4, rowspan=6, columnspan=1, sticky='E', padx=20, pady=5)

    """ DATABASE PARAMETERS - set defaults if not present in config """
    _valEndp = self.guic.cfg.get("dbHost") or "localhost"
    self.lblEnt(self, self.bgClr, 'endp', 'endpoint', _valEndp, 60, 1, 0, 3)
    _valInst = self.guic.cfg.get("dbName") or "vicmap"
    self.lblEnt(self, self.bgClr, 'inst', 'instance', _valInst, None, 2, 0)
    _valPort = self.guic.cfg.get("dbPort") or '5432'
    self.lblEnt(self, self.bgClr, 'port', 'port', _valPort, 10, 3, 0)
    _valUser = self.guic.cfg.get("dbUser") or "vicmap"
    self.lblEnt(self, self.bgClr, 'user', 'username', _valUser, None, 2, 2)
    _valPswd = self.guic.cfg.get("dbPswd") or "vicmap"
    self.lblEnt(self, self.bgClr, 'pswd', 'password', _valPswd, None, 3, 2)

    """ DATABASE CLIENT """
    self.lblDbHdr = Label(
      self, text='Database Connection Details', background=self.bgClr.get()
    )  # , style="Bold.TLabel"
    # self.lblDbHdr.configure(font=('Helvetica',18,'bold'))
    title = 'Database Client path -> home folder for pg_dump & pg_restore.'
    self.lblCltHdr = Label(self, text=title, background=self.bgClr.get())
    self.lblCltHdr.grid(row=4, column=0, columnspan=4, sticky='W', pady=(0, 5))
    self.bgElements.append(self.lblCltHdr)
    _binPath = self.guic.cfg.get("dbClientPath") or r"C:\Program Files\PostgreSQL\17\bin"
    self.lblEnt(self, self.bgClr, 'binPath', 'Bin Path', _binPath, 60, 5, 0, 4)

    if self.guic.cfg.get('dbComplete') == "True":
      self.paint(True)

  def test(self) -> None:
    # update config
    self.guic.cfg.set(
      {
        'dbHost': self.endp.get(),
        'dbPort': self.port.get(),
        'dbName': self.inst.get(),
        'dbUser': self.user.get(),
        'dbPswd': self.pswd.get(),
        'dbClientPath': self.binPath.get(),
      }
    )

    self.guic.runAsync(self._runChecks, self._testDone)

  # Off the ui thread. Nested, becuase don't waste your time if one fails.
  def _runChecks(self) -> list[bool]:
    _results = [self.guic.qa.checkDbControl()]
    if _results[-1]:
      _results.append(self.guic.qa.checkPGClient())
      if _results[-1]:
        _results.append(self.guic.qa.checkPostGis())
        if _results[-1]:
          _results.append(self.guic.qa.checkMetaData())
    return _results

  def _testDone(self, results: list[bool] | None, err: Exception | None) -> None:
    if err:
      logging.error(f"Database checks failed: {err}")
    # A failed check stops the ones after it, so results is short and every box is
    # cleared first rather than leaving a tick from the previous run standing.
    _vars = [self.qaDb, self.qaClt, self.qaSpat, self.qaMeta]
    [var.set(0) for var in _vars]
    for var, passed in zip(_vars, results or [], strict=False):
      var.set(passed)

    if self.guic.cfg.get("dbComplete") == "True":
      self.paint(True)
      self.guic.frData.setData()

    self.guic.frSetup.ctrlFrm.refresh()

  def refresh(self) -> None:
    # repopulate the values from config as profile has changed.
    self.strendp.set(self.guic.cfg.get("dbHost") or "localhost")
    self.strinst.set(self.guic.cfg.get("dbName") or "vicmap")
    self.strport.set(self.guic.cfg.get("dbPort") or "5432")
    self.struser.set(self.guic.cfg.get("dbUser") or "vicmap")
    self.strpswd.set(self.guic.cfg.get("dbPswd") or "vicmap")
    self.strbinPath.set(self.guic.cfg.get("dbClientPath") or r"C:\Program Files\PostgreSQL\17\bin")

    self.qaDb.set(0)
    self.qaClt.set(0)
    self.qaSpat.set(0)
    self.qaMeta.set(0)

    self.paint(False)
    # self.test()


class SubFrCtrl(SubFr):
  def __init__(self, owner: FrSetup, guic: GuiControl):
    super().__init__(owner, guic)  # style="lyrInfo.TFrame"#"bad.TFrame")#
    self.guic = guic
    # self.columnconfigure(1, weight=1)

    self.syncBtn = Button(
      self,
      text='SYNC',
      font=StyMan.fontBigBtn,
      padx=30,
      relief="solid",
      background=StyMan.qaClrFail,
      command=self.sync,
    )
    self.syncBtn.grid(
      row=2, column=3, sticky='E'
    )  # , padx=5, pady=5)#.pack(side='top', fill='none', padx=5, pady=(15,0))
    self.syncBtn.config(state="disabled")

    Label(self, text='datasets:').grid(row=1, column=4, sticky="E")
    self.dsetCnt = Label(self, text='N/A')
    self.dsetCnt.grid(row=1, column=5, sticky="W")

    Label(self, text='active:').grid(row=2, column=4, sticky="E")
    self.activeCnt = Label(self, text='N/A')
    self.activeCnt.grid(row=2, column=5, sticky="W")

    Label(self, text='errors:').grid(row=3, column=4, sticky="E")
    self.errCnt = Label(self, text='N/A')
    self.errCnt.grid(row=3, column=5, sticky="W")

    self.fixBtn = Button(self, text="Fix", command=self.fix)
    self.fixBtn.grid(row=3, column=6, sticky='E', padx=5, pady=5)

    self.refresh()

  def refresh(self) -> None:
    if (
      self.guic.cfg.get("dbComplete") == "True"
    ):  # getting metadata has a dependancy on cfg.regComplete, so this covers both
      _dsets = DB(self.guic.cfg).getRecSet(LyrReg)
      # _total, _active, _errs = []
      self.dsetCnt.config(text=len(_dsets))  # str(len(_dsets)))
      self.activeCnt.config(text=f'{str(len([d for d in _dsets if d.active]))}')  # and not d.err
      self.errCnt.config(text=str(len([d for d in _dsets if d.err])))
      self.syncBtn.config(state='active', bg=StyMan.qaClrPass)
    else:
      self.dsetCnt.config(text="N/A")
      self.activeCnt.config(text="N/A")
      self.errCnt.config(text="N/A")
      self.syncBtn.config(state='disabled', bg=StyMan.qaClrFail)
    self.update_idletasks()

  def fix(self) -> None:
    print("fix all error datasets by Q'ing them for reseeding")
    _db = DB(self.guic.cfg)
    _db.fixErrs()
    _db.close()

  def sync(self) -> None:
    if self.guic.busy:
      print("Another job is still running, wait for it to finish")
      return
    self.guic.busy = True
    self.syncBtn.config(state="disabled", text="SYNCING", bg=StyMan.qaClrFail)
    self.guic.runAsync(self._runSync, self._syncDone)

  # Off the ui thread, so it opens its own connection and touches no widget.
  def _runSync(self) -> None:
    _db = DB(self.guic.cfg)
    try:
      synccer = Synccer(self.guic.cfg, _db)
      synccer.unWait()  # queue any leftover jobs from last time.
      while synccer.assess():
        synccer.run()
    finally:
      _db.close()

  def _syncDone(self, _result: Any, err: Exception | None) -> None:
    self.guic.busy = False
    self.syncBtn.config(text="SYNC")
    print(f"sync failed: {err}" if err else "sync complete")
    self.refresh()  # puts the button back to its enabled colour


###########################################################################
###########################################################################
class SubFrAdmin(SubFr):
  def __init__(self, container: FrSetup, guic: GuiControl):
    super().__init__(container, guic)
    self.guic = guic
    self.label = ttk.Label(self, text="Hello, Tkinter!")
    self.label.pack(pady=20)
    self.button = ttk.Button(self, text="Click Me", command=self.on_click)
    self.button.pack()
    # self.configure('lyrInfo.TFrame')

  def on_click(self) -> None:
    self.label.config(text="Button Clicked!")

  def test(self) -> None:
    pass

  def refresh(self) -> None:
    pass


###########################################################################
###########################################################################

if __name__ == "__main__":
  gui = GuiControl('default')
  gui.mainloop()
