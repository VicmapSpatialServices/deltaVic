from tkinter import Tk, Button, Checkbutton, Frame, Label, Entry, StringVar, IntVar, END, Scrollbar, Canvas
from tkinter import ttk
# import tkinter as tk
import logging, traceback, math
from datetime import datetime
import webbrowser

from .utils_db import DB
from .setup import QA
from .sync import Synccer, Supplies
from .utils import Config

from .utils_api import ApiUtils

from .dbTable import LyrReg, Schemas

class StyMan():
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
    self.style.theme_create( "VlrsStyle", parent="default", settings={
      "TNotebook": {"configure": {"tabmargins": [2, 5, 2, 0] } },
      "TNotebook.Tab": {"configure": {"padding": [60, 10], "background":self.bgClrPass, "font" : ('URW Gothic L', '11', 'bold')},},
      "bad.TNotebook.Tab": {"configure": {"padding": [60, 10], "background":self.bgClrFail, "font" : ('URW Gothic L', '11', 'bold')},},
      "TFrame": {"configure": {"background":self.bgClrPass}},
      "bad.TFrame": {"configure": {"background":self.bgClrPass}},
      "lyrInfo.TFrame": {"configure": {"background": StyMan.bgClrData}},
      "metaLink.TLabel": {"configure": {"background": StyMan.bgClrData, "font" : ('Sans','10','bold', 'underline')}},
      "treeHeading.TLabel": {"configure": {"background": StyMan.bgClrData, "font" : ('Sans','9','bold')}},
      "Bold.TLabel": {"configure": {"font":('Helvetica', 12, 'bold')}}
    })
    self.style.theme_use("VlrsStyle")
    # self.style.configure('Good', background=self.bgClrPass) # Create style used by default for all Frames
    # self.style.configure('TFrame', background=self.bgClrFail) # Create style for the first frame

class GuiControl(Tk):
  def __init__(self, stg):
    super().__init__()
    # self.overrideredirect(1) # removes window, but loses max/min/close & screen positioning.

    self.cfg = Config('config.ini', stg)
    self.qa = QA(self.cfg)
    self.rights = {} # this is populated by a successful call to API-registration.
    self.styleMgr = StyMan()
    
    ###########################################################################
    # self.overrideredirect(1) # removes window, loses max/min/close & positioning.

    self.title("Vicmap Load & Replication Service")
    self.configure(background=StyMan.bgClrFail)
    self.minsize(630, 855)  # width, height
    # self.maxsize(495, 590)
    self.geometry("300x300")  # width x height + x + y

    self.tabs = ttk.Notebook(self)
    self.tabs.grid(row=0, column=0, sticky='nsew')
    # tabs.pack(sticky='nsew')
    self.columnconfigure(0,weight=1)
    self.rowconfigure(0,weight=1)

    self.frSetup = FrSetup(self.tabs, self)
    self.tabs.add(self.frSetup, text='VRS Setup & QA')
    # self.frSetup.test()
    
    self.frMeta = FrMetaData(self.tabs, self, 'Meta')
    self.tabs.add(self.frMeta, text='Meta')
    
    self.frData = FrMetaData(self.tabs, self, 'Data')
    self.tabs.add(self.frData, text='Data')

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

  def uploadAllowed(self, lyr, upldType=None): # upldType prevents overlogging whent he buttons havn't been pressed.
    # NB: checking these right here is just for display purposes, they are rechecked on submission on the server side of the API.
    if not self.rights:
      if upldType: print("GUI's got no rights. You need to refresh the registration form.")
      return False
    elif lyr.sup in ('VLAT','VTT'): # only MISC allowed
      if upldType: print("Only MISC datasets (brown) can be updated. VLAT (green) and VTT (blue) are external maintanance contracts.")
      return False
    
    if any(lyr.identity.startswith(s) for s in self.rights['schemas']['allow']['write']) and not lyr.identity in self.rights['datasets']['deny']['write']:
      # print(f"validated: schema and not dataset.")
      return True
    if lyr.identity in self.rights['datasets']['allow']['write']:
      # print(f"validated: dataset. {lyr.identity in self.rights['datasets']['allow']['write']}")
      return True
    
    if upldType: print("default no rights")
    return False # default.

###########################################################################
###########################################################################
class FrMetaData(ttk.Frame):
  def __init__(self, container, guic, type):
    super().__init__(container, style="bad.TFrame")#"bad.TFrame")#
    self.guic = guic
    self.type = type # is it remote ('Meta') or local ('Data')
    self.schDepth = 0
    self.data = Schemas(self.type, self.guic.cfg)
    
    # heading = Label(self, text='Data Content, Status and Metadata', bg=StyMan.bgClrPass)
    # heading.grid(row=0, column=0, columnspan=2, padx=5, pady=5, sticky="W")
    # self.ctrlFr = self.mkCtrlFr()
    # self.ctrlFr.grid(row=0, column=0, columnspan=2, padx=5, pady=5, sticky='nsew') #
    
    self.schFr = SubFrMetaSchs(self, guic, self.data) # self.mkSchFr() # 
    self.schFr.grid(row=1, column=0, padx=5, pady=5, sticky='W')#columnspan=2, 
    
    self.lyrFr = SubFrMetaLyrs(self, guic, self.data) # self.mkLyrFr() # 
    self.lyrFr.grid(row=1, column=1, padx=5, pady=5, sticky='nsew')#columnspan=2, 
    self.grid_columnconfigure(1, weight=1)

    self.lyrInfoFr = SubFrMetaLyrInfo(self, guic)
    self.lyrInfoFr.grid(row=2, column=0, columnspan=4, padx=10, pady=10, sticky="nsew")
    self.rowconfigure(2, weight=1)

    # self.columnconfigure(1, weight=1)
    # self.rowconfigure(1)#, weight=1)
    # self.columnconfigure(0, weight=1)
    # self.rowconfigure(0)#, weight=1)

  def setData(self):
    data = Schemas(self.type, self.guic.cfg)
    self.schFr.setData(data)
    self.lyrFr.setData(data)
    print(len(data.schs))
  
  ###########################################################################
  def mkCtrlFr(self):
    _fr = Frame(self, borderwidth=1, relief="raised", bg=StyMan.bgClrPass)
    self.remoteBtn = Button(_fr, text='REMOTE', font=(72), padx=30, relief="solid", background=StyMan.qaClrFail, command=self.showLocal)
    self.remoteBtn.grid(row=0, column=1, padx=5, pady=5, sticky="E")
    # self.remoteBtn.place(relx=0.5, rely=0.5, anchor=tk.CENTER)
    self.localBtn = Button(_fr, text='LOCAL', font=(72), padx=30, relief="solid", background=StyMan.qaClrFail, command=self.showRemote)
    self.localBtn.grid(row=0, column=2, padx=5, pady=5, sticky="W")
    # [_fr.columnconfigure(ii, uniform='equal_columns', weight=0) for ii in range(2)]
    _fr.columnconfigure((0,4), weight=1)
    return _fr
    
  ###########################################################################
  ###########################################################################
  def mkLyrFr(self):
    _fr = Frame(self, borderwidth=1, relief="raised", bg=StyMan.bgClrPass)
    _schHdr = Label(_fr, text="Layers", bg=StyMan.bgClrPass, font='bold')
    _schHdr.grid(row=0, column=0, sticky='nsew')
    return _fr

  ###########################################################################
  ###########################################################################
  
class SubFrMeta(Frame):
  def __init__(self, owner, guic):
    if self.__class__.__name__ == 'SubFrMetaLyrInfo':
      super().__init__(owner, borderwidth=5, padx=5, pady=5, relief="sunken", bg=StyMan.bgClrData)
    else:
      super().__init__(owner, borderwidth=1, padx=5, pady=5, relief="raised", bg=StyMan.bgClrPass)
    self.bgClr = StringVar(value=StyMan.bgClrPass)
    self.guic = guic
    
class SubFrMetaSchs(SubFrMeta):
  def __init__(self, owner, guic, data):
    super().__init__(owner, guic)
    
    self.owner = owner
    self.selected = None # currently selected schema

    """ HEADER """
    _schHdr = Label(self, text="Schemas", bg=StyMan.bgClrPass, font='bold')
    _schHdr.grid(row=0, column=0, columnspan=2, sticky='nsew')
    """ SCHEMAS """
    self.setData(data)

  def setData(self, data):
    self.schs = data.schs
    
    _schCnt = len(self.schs)
    _nrCols = 2; _nrItems = math.ceil(_schCnt/_nrCols)
    for ii in range(_schCnt):
      _row = 1+(ii%_nrItems); _col = int(ii/_nrItems)
      self.mkSchBtn(self.schs[ii].name, _row, _col)
    self.schDepth = _nrItems
  
  def mkSchBtn(self, sch, row, col):
    setattr(self, f"btn{sch}", Button(self, textvariable=StringVar(value=sch), width=8, height=1, padx=1, relief="solid", background=StyMan.qaClrFail))
    getattr(self, f"btn{sch}").config(command=lambda:self.showSch(f"{sch}"))
    getattr(self, f"btn{sch}").grid(row=row, column=col, sticky="W", padx=5)#, pady=(2,0))
  
  def showSch(self, sch):
    # change the schema button colours
    if self.selected:
      self.selected.config(background=StyMan.qaClrFail)
    self.selected = getattr(self, f"btn{sch}")
    self.selected.config(background=StyMan.qaClrPass)

    self.owner.lyrFr.redrawCanvas(sch)

class SubFrMetaLyrs(SubFrMeta):
  def __init__(self, owner, guic, data):
    super().__init__(owner, guic)
    self.data = data
    self.owner = owner

    # super().__init__(owner, width=400, height=300, background='red')
    self.lyrHdrStr = StringVar(self, "Layers")
    self.lyrHdr = Label(self, text="Layers", bg=StyMan.bgClrPass, font='bold', textvariable=self.lyrHdrStr)
    self.lyrHdr.grid(row=0, column=0, sticky='ew')
    if self.owner.type == "Meta":
      self.btnSchOn = Button(self, text="All ON", padx=10, background=StyMan.qaClrPass, anchor='e', command=lambda:self.toggleActive(sch=self.owner.schFr.selected["text"], active=True))
      self.btnSchOn.grid(row=0, column=1, sticky='e')
      self.btnSchOff = Button(self, text="All OFF", padx=10, background=StyMan.qaClrFail, anchor='e', command=lambda:self.toggleActive(sch=self.owner.schFr.selected["text"], active=False))
      self.btnSchOff.grid(row=0, column=2, sticky='e')
      self.grid_columnconfigure(0, weight=1)

    self.canvas = Canvas(self, width=415, background=StyMan.bgClrPass)
    self.canvas.bind('<Enter>', lambda e: self.canvas.bind_all("<MouseWheel>", self._on_lyr_mousewheel))
    self.canvas.bind('<Leave>', lambda e: self.canvas.unbind_all("<MouseWheel>"))
    
    self.lyrFrame = ttk.Frame(self.canvas, padding=(5,5), style='bad.TFrame')#, width=50)
    self.lyrFrame.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
    self.canvas.create_window((0,0), window=self.lyrFrame, anchor="nw")
    self.canvas.grid(row=1, column=0, columnspan=3, sticky="nsew")#rowspan=self.schDepth+1, 
    
    self.lyrScrollbar = Scrollbar(self, orient="vertical", command=self.canvas.yview)
    self.lyrScrollbar.grid(row=1, column=4, sticky="ns")
    
    # self.guic = guic 
    self.lyrBtns, self.lyrChks , self.lyrVars = [], [], []
    self.selected = None # currently selected schema

    self.redrawCanvas()
    
    # self.columnconfigure(1, weight=1)
    # self.rowconfigure(1)#, weight=1)
    # self.columnconfigure(0, weight=1)
    # self.rowconfigure(0)#, weight=1)
    
  def _on_lyr_mousewheel(self, event):
    self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

  def setData(self, data):
    self.data = data

  def redrawCanvas(self, newSch=None):
    # print("reDraw")
    if not newSch: return
    
     # clear current controls
    [lyrBtn.destroy() for lyrBtn in self.lyrBtns]
    [lyrChk.destroy() for lyrChk in self.lyrChks]
    # [lyrVar.destroy() for lyrVar in self.lyrVars]
    
    self.lyrBtns, self.lyrChks = [], []

    _sch = self.data.get(newSch)
    self.nrLyrs = len(_sch.lyrs)
    self.lyrHdrStr.set(f"Layers ({self.nrLyrs})")
    # _lyrs = [d.tbl for d in _sch.lyrs]
    _sch.lyrs.sort(key = lambda lyr:lyr.identity)
    self.setLyrs(_sch.lyrs)
    # self.update_idletasks()
    self.canvas.configure(yscrollcommand=self.lyrScrollbar.set)
    
  def setLyrs(self, lyrs):
    self.selected = None
    [self.mkLyrBtn(lyr, lyrs.index(lyr)) for lyr in lyrs]#, 0
    # self.columnconfigure((0,2), 1)
    [self.lyrFrame.columnconfigure(ii, uniform='equal_columns', weight=1) for ii in (0,2)]#range(2)]
    
  def mkLyrBtn(self, lyr, idx):#, col):
    # print(f"mkLyrBtn({self}, {lyr}, {rowNum}, {col})")
    _cols=2
    rowNum, colNum = int(idx/_cols)%self.nrLyrs, idx%_cols
    # print(f"({rowNum}, {colNum*_cols}) ({rowNum}, {(colNum*_cols)+1})")
    
    fgCol = getattr(StyMan, f"sup{lyr.sup}")
    setattr(self, f"lyrBtn{lyr.identity}", Button(self.lyrFrame, text=lyr.tbl, padx=10, background="snow3", anchor='w', fg=fgCol, command=lambda:self.showLyrDetails(lyr)))
    getattr(self, f"lyrBtn{lyr.identity}").grid(row=rowNum, column=(colNum*_cols)+1, sticky="nsew", padx=(0,3), pady=1)
    self.lyrBtns.append(getattr(self, f"lyrBtn{lyr.identity}"))

    if self.owner.type == "Meta":
      setattr(self, f"lyrAct{lyr.identity}", IntVar(value=1 if lyr.active else 0))
      setattr(self, f"lyrChk{lyr.identity}", Checkbutton(self.lyrFrame, variable=getattr(self, f"lyrAct{lyr.identity}"), onvalue=1, offvalue=0, bg=fgCol, command=lambda:self.toggleActive(lyr=lyr)))
      getattr(self, f"lyrChk{lyr.identity}").grid(row=rowNum, column=colNum*_cols, sticky="E", padx=(3,0), pady=1)
      if self.guic.cfg.get('dbComplete')!="True":
        getattr(self, f"lyrChk{lyr.identity}").config(state="disabled")
      self.lyrChks.append(getattr(self, f"lyrChk{lyr.identity}"))
      self.lyrVars.append(getattr(self, f"lyrAct{lyr.identity}"))
      
  def showLyrDetails(self, lyr):
    if self.selected:
      self.selected.config(background="snow3")
    self.selected = getattr(self, f"lyrBtn{lyr.identity}")
    self.selected.config(background=StyMan.bgClrData)
    
    self.owner.lyrInfoFr.showLyrDetails(lyr)
  
  def toggleActive(self, lyr=None, sch=None, active=None):
    _db = DB(self.guic.cfg)
    if lyr:
      active = bool(getattr(self, f"lyrAct{lyr.identity}").get())
      _db.execute(*lyr.setActive(active))
    if sch:
      sqlStr = f"update vm_meta.data set active={str(active).lower()} where identity like '{sch}%'"
      _db.execute(sqlStr)
      [lyrVar.set(active) for lyrVar in self.lyrVars]

class SubFrMetaLyrInfo(SubFrMeta):
  def __init__(self, owner, guic):
    super().__init__(owner, guic)
    self.owner = owner
    self.lyrMeta = None

  def showLyrDetails(self, lyr):
    # print(f"{lyr}")
    
    # clear frame
    for widget in self.winfo_children():
      widget.destroy()

    self.lyrMeta = self.getLyrMetadata(lyr.identity)

    _frIdent = Frame(self, borderwidth=2, relief="raised", bg=StyMan.bgClrPass)
    Label(_frIdent, text=lyr.identity, background=StyMan.bgClrPass, font='bold').grid(row=0, column=0, padx=10, pady=5)#, textvariable=self.lyrNameStr)
    _frIdent.grid(row=0, column=0, columnspan=2, sticky='W')
    # ttk.Label(self, text=lyr.identity, border=0).grid(row=0, column=0, padx=10)

    if self.owner.type == "Meta": # all records here should have vicmap metadata from the APIs.
      _frActions = Frame(self, borderwidth=2, bg=StyMan.bgClrData)
      layerReseed = Button(_frActions, text="Reseed", padx=5, pady=2, background="snow3", bg=StyMan.qaClrPass, command=lambda:self.reseed(lyr.identity)) #anchor='e', 
      layerReseed.grid(row=0, column=0, padx=(0.10), sticky='W')
      layerMetaLink = Button(_frActions, text="Metadata weblink (GeoNetwork ISO 19115)", padx=5, pady=2, background="snow3", anchor='e', bg=StyMan.qaClrPass, command=lambda:webbrowser.open_new(self.lyrMeta['metadata']))#self.geonet(self.lyrMeta)) 
      layerMetaLink.grid(row=0, column=1, padx=(10.0), sticky='E') #padx=(5.5), 
      _frActions.grid(row=0, column=3, columnspan=4)#, sticky='EW')
    if self.owner.type == "Data":
      print(lyr)
      _frUpload = self.mkFrUpload(lyr)
      _frUpload.grid(row=0, column=3, columnspan=4, sticky='e')
    
    if self.lyrMeta: # existing layer
      ## Table Columns
      _colData = [(col,type) for col,type in self.lyrMeta['columns'].items()] if self.lyrMeta['columns'] else []
      _colcols = [('Column',120,'e'),('Type',120,'w')]
      _cols = TView(self, 'Columns', _colcols, 1, 0, _colData)
      ## Table Indexes
      _idxData = [(idx[1],idx[0],idx[2]) for idx in self.lyrMeta['indexes']] if self.lyrMeta['indexes'] else []
      _idxCols = [('Column',120,'w'),('idx_Name',120,'w'),('Type',50,'w')]
      _idxs = TView(self, 'Indexes', _idxCols, 1, 3, _idxData)
      ## Dump History Tree
      _ldData = [(dump[2], dump[1], datetime.fromisoformat(dump[3]).strftime('%d/%m/%Y %H:%M'),dump[4],dump[5],dump[6]) for dump in self.lyrMeta['pgDumps']] if self.lyrMeta['pgDumps'] else []
      _ldData.sort(key = lambda x:datetime.strptime(x[2], "%d/%m/%Y %H:%M"), reverse=True)
      _ldCols = [('Supply Version',50,'w'),('Type',50,'w'),('Date',100,'w'),('Adds',80,'e'),('Dels',80,'e'),('Count',80,'e')]
      _loads = TView(self, 'Update History', _ldCols, 3, 0, _ldData, 7) #'Type':75,
    else: # new layer
      self.mkNewUplFrm()
      
  def mkNewUplFrm(self):
    Label(self, text='Upload New Dataset', border=3).grid(row=1, column=0, padx=10, sticky='EW')
    # (self, fr, bgClr, var, name, val, wid, row, col, colspan=1, private=False):
    # (self, self.bgClr, 'email', 'email', _valEmail, 60, 1, 0, 3)

    self.relation = StringVar()
    _lbl = Label(self, text='Relation:', background = StyMan.bgClrData)
    _lbl.grid(row=2, column=0, sticky="E")
    # Label(self, text='datasets:').grid(row=1, column=4, sticky="E")
    self.relBox = ttk.Combobox(self, values=['table','view'])
    self.relBox.current(0)
    self.relBox.grid(row=2, column=1, sticky="W")
    # self.relBox.bind("<<ComboboxSelected>>", self.profileChanged)
    # self.relBox.bind("<Return>",self.profileChanged)
    
    self.mdUUID = StringVar()
    Label(self, text='GeoNetwork UUID:', background = StyMan.bgClrData).grid(row=3, column=0, sticky='E')
    self.uuidEnt = Entry(self, textvariable=self.mdUUID, width=40, bd=3).grid(row=3, column=1, sticky='W')

    self.geomtype = StringVar()
    Label(self, text='Geometry Type:', background = StyMan.bgClrData).grid(row=4, column=0, sticky='E')
    self.gtBox = ttk.Combobox(self, values=['polygon','multipolygon','linestring','multilinestring','point','multipoint','none'])
    self.gtBox.current(0)
    self.gtBox.grid(row=4, column=1, sticky="W")
    
    self.vdp = IntVar(value=0)
    Label(self, text='VDP:', background = StyMan.bgClrData).grid(row=5, column=0, sticky='E')
    self.vdpChk = Checkbutton(self, variable=self.vdp, onvalue=1, offvalue=0)
    self.vdpChk.grid(row=5, column=1, sticky="W")

    testBtn = Button(self, text="test", padx=5, pady=2, background="snow3", bg=StyMan.qaClrPass, command=lambda:self.testVars())
    testBtn.grid(row=6, column=1, padx=5, pady=5)
    
  def testVars(self):
    print(f"{self.mdUUID.get()} {self.relBox.get()} {self.gtBox.get()} {"true" if self.vdp.get() else "false"}")

  def mkFrUpload(self, lyr):
    _fr = Frame(self, borderwidth=1, relief="raised", bg=StyMan.bgClrPass)
    ttk.Label(_fr, text='Upload', border=3).grid(row=0, column=0, padx=10)
    lyrUploadInc = Button(_fr, text="INC", padx=5, pady=2, background="snow3", bg=StyMan.qaClrPass, command=lambda:self.upload(lyr, Supplies.INC))
    lyrUploadInc.grid(row=0, column=1, pady=5)
    
    lyrUploadDiff = Button(_fr, text="DIFF", padx=5, pady=2, background="snow3", bg=StyMan.qaClrPass, command=lambda:self.upload(lyr, Supplies.DIFF))
    lyrUploadDiff.grid(row=0, column=2, padx=5, pady=5)
    lyrUploadFull = Button(_fr, text="FULL", padx=5, pady=2, background="snow3", bg=StyMan.qaClrPass, command=lambda:self.upload(lyr, Supplies.FULL))
    lyrUploadFull.grid(row=0, column=3, padx=5, pady=5)
    
    if not self.lyrMeta: # new dataset, full upload only
      lyrUploadInc.configure(fg='white', state="disabled", bg=StyMan.bgClrFail)
      lyrUploadDiff.configure(fg='white', state="disabled", bg=StyMan.bgClrFail)
    if not self.guic.uploadAllowed(lyr):
      lyrUploadInc.configure(fg='white', state="disabled", bg=StyMan.bgClrFail)
      lyrUploadDiff.configure(fg='white', state="disabled", bg=StyMan.bgClrFail)
      lyrUploadFull.configure(fg='white', state="disabled", bg=StyMan.bgClrFail)
    return _fr
    
  def getLyrMetadata(self, ident):
    api = ApiUtils(self.guic.cfg.get('baseUrl'), self.guic.cfg.get('api_key'), self.guic.cfg.get('client_id'))
    response = None
    try:
      response = api.post("data", {"dset": f"{ident}"})
    except Exception as ex:
      logging.warning(ex)
    return response

  
  # def geonet(self, layerMeta):
  #   webbrowser.open_new(layerMeta['metadata'])

  def upload(self, lyr, upldType):
    print(f"{lyr}, {upldType}")
    if not self.guic.uploadAllowed(lyr, upldType):
      print(f"You have no rights to update {lyr.identity} data. If you think you should, try refreshing the registration")
      return
    elif upldType==Supplies.INC:
      print("INCREMENTAL supplies have not yet been implemented from the client")
    # do the upload ...
    sync = Synccer(self.guic.cfg, DB(self.guic.cfg))
    if self.lyrMeta: # existing dset
      sync.upload(lyr.identity, upldType)
    else:
      _uuid = self.mdUUID.get()
      _rel = self.relBox.get()
      _gType = self.gtBox.get()
      _vdp = "true" if self.vdp.get() else "false"
      print(f"{_uuid} {_rel} {_gType} {_vdp}")
      sync.upload(lyr.identity, upldType, relation=_rel, md_uuid=_uuid, geomType=_gType, vdp=_vdp)

  def reseed(self, ident):
    print(f"Reseeding {ident}")
    _db = DB(self.guic.cfg)
    _db.fixErrs(ident)
    _db.close()
    # Should we auto mark teh records as active and update the GUI ticklist?
    # Should we kick off an immediate sync? (may get hung up on other unsyncced layers for awhile.)

class TView(ttk.Treeview):
  def __init__(self, owner, name, colTupl, row, col, data, height=10):
    super().__init__(owner, columns=[c[0] for c in colTupl], height=height, show='headings')

    self.colHdr = ttk.Label(owner, text=name, style='treeHeading.TLabel')
    self.colHdr.grid(row=row, column=col, columnspan=len(colTupl)+1, sticky='w')
    [self.mkCol(tupl) for tupl in colTupl]
    [self.insert('', END, value=rowData) for rowData in data]
    self.grid(row=row+1, column=col, columnspan=len(colTupl), sticky='nsew')

    self.scrollbar = Scrollbar(owner, orient='vertical', command=self.yview)
    self.scrollbar.grid(row=row+1, column=col+len(colTupl), sticky='ns', padx=(0,3))
    self.configure(yscrollcommand=self.scrollbar.set)

  def mkCol(self, colTupl):
    name, wid, anc = colTupl
    self.heading(name, text=name)
    self.column(name, minwidth=0, width=wid, anchor=anc, stretch=True)

class FrSetup(ttk.Frame):
  def __init__(self, container, guic):
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
    self.proBox.bind("<Return>",self.profileChanged)
    
    Label(self, text='API URL:', bg=StyMan.bgClrPass).grid(row=1, column=0, sticky="E")
    self.strurl = StringVar(value=self.guic.cfg.get('baseUrl'))
    Label(self, textvariable=self.strurl, bg=StyMan.bgClrPass).grid(row=1, column=1, sticky="W")
    
    self.ctrlFrm = SubFrCtrl(self, self.guic)
    self.ctrlFrm.grid(row=4, column=0, columnspan=2, padx=5, pady=(0,5), sticky='E')
    self.regFrm = SubFrReg(self, self.guic)
    self.regFrm.grid(row=2, column=0, columnspan=2, padx=5, pady=(0,5), sticky='nsew')
    self.dbFrm = SubFrDb(self, self.guic)
    self.dbFrm.grid(row=3, column=0, columnspan=2, padx=5, pady=(0,5), sticky='nsew')
    
  ###########################################################################
  
  def profileChanged(self, event):
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
  
  def test(self):
    self.regFrm.test()
    self.dbFrm.test()
    
  def refresh(self):
    # meta
    self.strurl.set(self.guic.cfg.get('baseUrl'))
    self.regFrm.refresh()
    self.dbFrm.refresh()
    self.ctrlFrm.refresh()

class SubFr(Frame):
  def __init__(self, owner, guic):
    # print(self.__class__.__name__)
    if self.__class__.__name__ != 'SubFrCtrl':
      super().__init__(owner, bg=StyMan.qaClrFail, borderwidth=5, padx=5, pady=5, relief="sunken")
    else:
      super().__init__(owner, borderwidth=5, padx=5, pady=5, relief="raised")
    self.bgClr = StringVar(value=StyMan.qaClrFail)
    self.guic = guic
    self.bgElements = [self]

  def paint(self, passed):
    for ele in self.bgElements:
      [ele.config(bg=StyMan.qaClrPass if passed else StyMan.qaClrFail) for ele in self.bgElements]

  def lblEnt(self, fr, bgClr, var, name, val, wid, row, col, colspan=1, private=False):
    # set label as lbl{var}
    setattr(self, f"lbl{var}", Label(fr, text=f"{name}:", background=bgClr.get(), width=8))
    getattr(self, f"lbl{var}").grid(row=row, column=col, sticky="E")
    self.bgElements.append(getattr(self, f"lbl{var}"))
    # set entry as var, value as str{var}
    _displayVal = val if not private else '' if not val else 'xxxxx-xxxxx-xxxxx'
    setattr(self, f"str{var}", StringVar(value=_displayVal))#'xxxxx-xxxxx-xxxxx' if private else val))
    setattr(self, var, Entry(fr, textvariable=getattr(self, f"str{var}"), width=wid if wid else 20, bd=3))
    # getattr(self, var).insert(0, val)
    getattr(self, var).grid(row=row, column=col+1, columnspan=colspan, sticky="W", padx=5, pady=2)
    return getattr(self, f"lbl{var}")

  def qaChk(self, fr, var, desc, row, col): #(self.cntrlFrame, "DB", "DB", 1, 0)
    setattr(self, f"qa{var}", IntVar(value=0)) # IntVar())#self.qaDb = IntVar()
    setattr(self, f"chk{var}", Checkbutton(fr, text=desc, variable=getattr(self, f"qa{var}"), onvalue=1, offvalue=0))#, tristatevalue=2))#o)) # self.dbChk = Checkbutton(self.cntrlFrame, text='DB', variable=self.qaDb, onvalue=1, offvalue=0)#, command=print_selection)
    getattr(self, f"chk{var}").config(state="disabled")
    getattr(self, f"chk{var}").grid(row=row, column=col, sticky='W')
    return getattr(self, f"qa{var}")
  
class SubFrReg(SubFr):
  def __init__(self, owner, guic):
    super().__init__(owner, guic)

    """ HEADER """
    self.lblRegHdr = Label(self, text='Registration', background=self.bgClr.get())
    self.lblRegHdr.grid(row=0, column=0, columnspan=3, pady=(0,5), sticky="W")
    self.bgElements.append(self.lblRegHdr)
    """ QA """
    qaFr = Frame(self, borderwidth=1, relief="solid")
    Label(qaFr, text='QA', font=(32), width=12).grid(row=0, column=0, pady=2)
    self.qaVars = []
    qaArr = [("Reg", "Registered", 1, 0), ("Val", "Validated", 2, 0)]
    [self.qaVars.append(self.qaChk(qaFr, *qat)) for qat in qaArr]
    Button(qaFr, text='Refresh', relief="solid", command=lambda:self.test()).grid(row=3, rowspan=1, column=0, sticky="nsew", padx=5, pady=5)#(5,5))
    qaFr.grid(row=0, column=4, rowspan=5, columnspan=1, sticky='E', padx=20, pady=5)
    
    """ EMAIL """
    _valEmail = self.guic.cfg.get("email") or ""
    self.lblemail = self.lblEnt(self, self.bgClr, 'email', 'email', _valEmail, 60, 1, 0, 3)
    """ CLIENT_ID """
    _valClient = self.guic.cfg.get("client_id") or ''
    self.lblClientId = self.lblEnt(self, self.bgClr, 'clientId', 'Client ID', _valClient, 40, 2, 0, private=True)
    self.clientId.config(state='disabled')
    """ API_KEY """
    _valApik = self.guic.cfg.get("api_key") or ''
    self.lblApik = self.lblEnt(self, self.bgClr, 'apik', 'API Key', _valApik, 40, 3, 0, private=True)
    self.apik.config(state='disabled')
    """ MESSAGE """
    self.regMsg = Label(self, text='', background=self.bgClr.get())
    self.regMsg.grid(row=5, column=0, columnspan=4, pady=(0,5), sticky="E")
    self.bgElements.append(self.regMsg)
    
    if self.guic.cfg.get('regComplete')=="True": self.paint(True)
    
  def test(self):
    self.guic.cfg.set({"email":self.email.get()}) # client_id and api_key are non editable.
    
    qaCode, qaMsg = self.guic.qa.checkApiClient()
    print(f"{qaCode}, {qaMsg}")
    if qaCode == 0: #possible?
      self.regMsg.config(text=qaMsg)
      # self.paint(False)
    elif qaCode == 1: # still need to verify the email
      self.qaReg.set(1)
      self.regMsg.config(text=qaMsg)
      # self.paint(False)
    elif qaCode == 2: # verified
      self.qaReg.set(1)
      self.qaVal.set(1)
      self.regMsg.config(text="Read and Upload rights have been set.")#str(qaMsg))
      self.guic.rights = qaMsg # dict returned when success here.
      # self.paint(True)
      self.guic.frMeta.setData()

    self.refresh()
    self.guic.frSetup.ctrlFrm.refresh()
    # self.regMsg.config(text=qaMsg)
  
  def refresh(self):
    # repopulate the values from config as values/profile may have changed.
    self.stremail.set(self.guic.cfg.get("email"))
    self.strclientId.set('xxxxx-xxxxx-xxxxx' if self.guic.cfg.get("client_id") else '')
    self.strapik.set('xxxxx-xxxxx-xxxxx' if self.guic.cfg.get("api_key") else '')
    self.qaReg.set(1 if self.guic.cfg.get("client_id") else 0)
    self.qaVal.set(1 if self.guic.cfg.get("api_key") else 0)

    self.paint(self.guic.cfg.get("regComplete")=="True")

class SubFrDb(SubFr):
  def __init__(self, owner, guic):
    super().__init__(owner, guic)
  
    """ HEADER """
    self.lblDbHdr = Label(self, text='Database Connection Details', background=self.bgClr.get())
    self.lblDbHdr.grid(row=0, column=0, columnspan=2, sticky='W', pady=(0,5))
    self.bgElements.append(self.lblDbHdr)
    """ QA """
    qaFr = Frame(self, borderwidth=1, relief="solid")
    Label(qaFr, text='QA', font=(32), width=12).grid(row=0, column=0, pady=2)
    self.qaVars = []
    qaArr = [("Db", "DB cnxn", 1, 0), ("Clt", "DB PG_Client", 2, 0), ("Spat", "PostGis", 3, 0), ("Meta", "Metadata", 4, 0)]
    [self.qaVars.append(self.qaChk(qaFr, *qat)) for qat in qaArr]
    Button(qaFr, text='Test DB', relief="solid", command=self.test).grid(row=5, column=0, rowspan=1, sticky="nsew", padx=5, pady=5)#row=4, column=0, sticky="W", pady=(0,5))
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
    self.lblDbHdr = Label(self, text='Database Connection Details', background=self.bgClr.get())#, style="Bold.TLabel"
    # self.lblDbHdr.configure(font=('Helvetica',18,'bold'))
    title = 'Database Client path -> home folder for pg_dump & pg_restore.'
    self.lblCltHdr = Label(self, text=title, background=self.bgClr.get())
    self.lblCltHdr.grid(row=4, column=0, columnspan=4, sticky='W', pady=(0,5))
    self.bgElements.append(self.lblCltHdr)
    _binPath = self.guic.cfg.get("dbClientPath") or r"C:\Program Files\PostgreSQL\17\bin"
    self.lblEnt(self, self.bgClr, 'binPath', 'Bin Path', _binPath, 60, 5, 0, 4)
    
    if self.guic.cfg.get('dbComplete')=="True": self.paint(True)

  def test(self):
    # update config
    self.guic.cfg.set({'dbHost':self.endp.get(), 'dbPort':self.port.get(), 'dbName':self.inst.get(), 
      'dbUser':self.user.get(), 'dbPswd':self.pswd.get(), 'dbClientPath':self.binPath.get()})
    
    # nested if's below, becuase don't waste your time if one fails.
    if self.guic.qa.checkDbControl():
      self.qaDb.set(True)
      if self.guic.qa.checkPGClient():
        self.qaClt.set(True)
        if self.guic.qa.checkPostGis(): 
          self.qaSpat.set(True)
          if self.guic.qa.checkMetaData(): 
            self.qaMeta.set(True)

    if self.guic.cfg.get("dbComplete")=="True":
      self.paint(True)
      self.guic.frData.setData()
      
    self.guic.frSetup.ctrlFrm.refresh()

  def refresh(self):
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
  def __init__(self, owner, guic):
    super().__init__(owner, guic)#style="lyrInfo.TFrame"#"bad.TFrame")#
    self.guic = guic
    # self.columnconfigure(1, weight=1)
    
    self.syncBtn = Button(self, text='SYNC', font=(72), padx=30, relief="solid", background=StyMan.qaClrFail, command=self.sync)
    self.syncBtn.grid(row=2, column=3, sticky='E')#, padx=5, pady=5)#.pack(side='top', fill='none', padx=5, pady=(15,0))
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

  def refresh(self):
    if self.guic.cfg.get("dbComplete")=="True": # getting metadata has a dependancy on cfg.regComplete, so this covers both
      _dsets = DB(self.guic.cfg).getRecSet(LyrReg)
      # _total, _active, _errs = []
      self.dsetCnt.config(text=len(_dsets))#str(len(_dsets)))
      self.activeCnt.config(text=f'{str(len([d  for d in _dsets if d.active]))}')# and not d.err
      self.errCnt.config(text=str(len([d for d in _dsets if d.err])))
      self.syncBtn.config(state='active', bg=StyMan.qaClrPass)
    else:
      self.dsetCnt.config(text="N/A")
      self.activeCnt.config(text="N/A")
      self.errCnt.config(text="N/A")
      self.syncBtn.config(state='disabled', bg=StyMan.qaClrFail)
    self.update_idletasks()

  def fix(self):
    print("fix all error datasets by Q'ing them for reseeding")
    _db = DB(self.guic.cfg)
    _db.fixErrs()
    _db.close()

  def sync(self):
    print("sync - app will lose focus and hang while this occurs") # make it threaded? possible in tkinter?
    _db = DB(self.guic.cfg)
    synccer = Synccer(self.guic.cfg, _db)
    synccer.unWait() # queue any leftover jobs from last time.
    while(synccer.assess()):
      synccer.run()
    _db.close()
    print("sync complete")

    self.refresh()

###########################################################################
###########################################################################
class SubFrAdmin(SubFr):
  def __init__(self, container, guic):
    super().__init__(container, style="lyrInfo.TFrame")#"bad.TFrame")#
    self.guic = guic
    self.label = ttk.Label(self, text="Hello, Tkinter!")
    self.label.pack(pady=20)
    self.button = ttk.Button(self, text="Click Me", command=self.on_click)
    self.button.pack()
    # self.configure('lyrInfo.TFrame')

  def on_click(self):
    self.label.config(text="Button Clicked!")
  
  def test(self):
    pass
  def refresh(self):
    pass
###########################################################################
###########################################################################

if __name__ == "__main__":
  gui = GuiControl(None, None)
  gui.mainloop()