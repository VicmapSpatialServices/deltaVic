from tkinter import ttk, Tk, Button, Checkbutton, Frame, Label, Entry, Text, StringVar, IntVar, END, Scrollbar, Canvas, INSERT
# import tkinter as tk
import logging, traceback
from copy import deepcopy

from .utils_db import DB, PGClient
from .setup import QA
from .sync import Synccer
from .utils import Config

from .dbTable import LyrReg

class GUI(Tk):
  def __init__(self, stg):#, cfg):
    super().__init__()
    
    self.guic = GuiControl(self, stg) # has Confg, QA and db cnxns.
    
    self.title("Vicmap Replication Service")
    self.configure(background="brown")
    self.minsize(485, 630)  # width, height
    # self.maxsize(495, 590)
    self.geometry("300x300+500+500")  # width x height + x + y

    # https://www.google.com/search?q=tkinter+colours
    self.qaClrFail = 'orange'
    self.qaClrPass = 'OliveDrab3'
    self.bgClrFail = 'brown'
    self.bgClrPass = 'skyblue'
    
    self.style = ttk.Style()
    self.style.theme_create( "MyStyle", parent="alt", settings={
      "TNotebook": {"configure": {"tabmargins": [2, 5, 2, 0] } },
      "TNotebook.Tab": {"configure": {"padding": [72, 10], "background":'skyblue', "font" : ('URW Gothic L', '11', 'bold')},},
      "bad.TNotebook.Tab": {"configure": {"padding": [72, 10], "background":'brown', "font" : ('URW Gothic L', '11', 'bold')},},
      "TFrame": {"configure": {"background":'skyblue'}},
      "bad.TFrame": {"configure": {"background":'skyblue'}}
    })
    self.style.theme_use("MyStyle")

    # self.style = ttk.Style() # Initialize style
    self.style.configure('Good', background='skyblue') # Create style used by default for all Frames
    # self.style.configure('TFrame', background='brown') # Create style for the first frame
    
    ##########
    tabs = ttk.Notebook(self)
    tSetup = ttk.Frame(tabs, style='bad.TFrame')
    tabs.add(tSetup, text='VRS Setup & QA')
    self.popSetupFrame(tSetup)

    tMeta = ttk.Frame(tabs, style='bad.TFrame')
    tabs.add(tMeta, text='MetaData')
    self.popMetaFrame(tMeta)

    tabs.grid(row=0, column=0)
    # tabs.pack(sticky='nsew')

    # tSetup.config(style='Good')
    #.config(style='Good')
    # tab1 = ttk.Frame(mainframe, style='Frame1.TFrame') # Use created style in this frame
    # mainframe.add(tab1, text="Tab1")

    # # Create separate style for the second frame
    # s.configure('Frame2.TFrame', background='blue')
    # # Use created style in this frame
    # tab2 = ttk.Frame(mainframe, style='Frame2.TFrame')
    # mainframe.add(tab2, text="Tab2")

  ###########################################################################
  ###########################################################################
  
  def _on_lyr_mousewheel(self, event):
   self.lyrCanvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

  def popMetaFrame(self, owner):
    self.currentLyrs = []
    self.currentSchBtn = None
    self.currentLyrBtn = None
    self.nrSchemas = 0
    self.nrSchHalf = 0
    rowNum, colNum = 0, 0
    
    # heading = Label(owner, text='Data Content, Status and Metadata', bg=self.bgClrPass)
    # heading.grid(row=0, column=0, columnspan=2, padx=5, pady=5, sticky="W")
    
    if self.qaDb.get():
      schs = DB(self.guic.config).getSchemas()
      self.nrSchemas = len(schs)
      self.nrSchHalf = int((self.nrSchemas-1)/2)
      print(f"{self.nrSchemas} {self.nrSchHalf}")
      for sch in schs:
        self.mkSchBtn(owner, sch, rowNum, colNum)
        if rowNum == self.nrSchHalf:
          rowNum, colNum = 0, 1
        else:
          rowNum += 1
    # self.lyrFrame = Frame(owner, borderwidth=1, relief="flat", width=250, height=400)
    # self.lyrFrame.grid(row=1, rowspan=rowNum, column=1, sticky='nsew')
    
    self.lyrCanvas = Canvas(owner, width=300)#, background='skyblue')
    self.lyrFrame = ttk.Frame(self.lyrCanvas, style='bad.TFrame')#, width=50)
    # self.lyrFrame.configure(background='skyblue')
    self.lyrFrame.bind("<Configure>", lambda e: self.lyrCanvas.configure(scrollregion=self.lyrCanvas.bbox("all")))
    self.lyrScrollbar = Scrollbar(owner, orient="vertical", command=self.lyrCanvas.yview)
    # print(f"popMetaFr: {self.lyrCanvas.bbox}")
    # print(f"popMetaFr: {self.lyrCanvas.yview}")

    owner.columnconfigure(1, weight=1)
    owner.rowconfigure(1)#, weight=1)
    self.lyrFrame.columnconfigure(0, weight=1)
    self.lyrFrame.rowconfigure(0)#, weight=1)

    # lyrScrollbar=Scrollbar(self.lyrFrame, orient="vertical")
    # lyrScrollbar.pack(side="right",fill="y")
    self.lyrCanvas.bind_all("<MouseWheel>", self._on_lyr_mousewheel)

    print(rowNum)
    self.lyrInfo = Text(owner, border=1, background='white', padx=5, pady=5, width=50, height=18)
    self.lyrInfo.grid(row=self.nrSchHalf+1, column=0, columnspan=4, padx=10, pady=10, sticky="nsew")

  def mkSchBtn(self, owner, sch, row, col):
    # self.syncBtn = Button(fr, text='SYNC', font=(72), padx=30, relief="solid", background="salmon", command=self.guic.sync)
    setattr(self, f"sch{sch}", StringVar(value=sch))
    setattr(self, f"btn{sch}", Button(owner, textvariable=getattr(self, f"sch{sch}"), width=8, height=1, padx=1, relief="solid", background=self.qaClrFail))
    getattr(self, f"btn{sch}").config(command=lambda:self.showSch(owner, getattr(self, f"sch{sch}").get()))
    # self.syncBtn.
    getattr(self, f"btn{sch}").grid(row=row, column=col, sticky="W", padx=5)#, pady=(2,0))

  def showSch(self, owner, sch):
    # print(f"showSch1: {self.lyrCanvas.bbox}")
    # change the schema button colours and remove the currentl lyrs
    if self.currentSchBtn:
      self.currentSchBtn.config(background=self.qaClrFail)
    self.currentSchBtn = getattr(self, f"btn{sch}")
    self.currentSchBtn.config(background=self.qaClrPass)
    for item in self.currentLyrs:
       item.destroy()

    # print("CANVAS CHILDREN:")
    print(self.lyrFrame.children)
    # print(self.lyrCanvas.configure(height=10))

    # TODO: Redo this, reset the height or something else instead.
    # Re-instantiate layer frame to reset height
    self.lyrCanvas = Canvas(owner, width=300)#, background='skyblue')
    self.lyrFrame = ttk.Frame(self.lyrCanvas, style='bad.TFrame')#, width=50)
    self.lyrFrame.bind("<Configure>", lambda e: self.lyrCanvas.configure(scrollregion=self.lyrCanvas.bbox("all")))

    # self.lyrScrollbar = Scrollbar(owner, orient="vertical", command=self.lyrCanvas.yview)
    # self.lyrCanvas.bind_all("<MouseWheel>", self._on_lyr_mousewheel)   
    
    
    print(f"showSch({owner}, {sch})")
    lyrs = DB(self.guic.config).getTables(sch)
    # print(lyrs)
    # label = ttk.Label(self.lyrFrame, text="Layer List")
    # label.grid(row=0, column=0, pady=10)
    rowNum = 1
    self.lyrCanvas.create_window((0, 0), window=self.lyrFrame, anchor="nw")
    self.lyrCanvas.grid(row=0, column=2, rowspan=self.nrSchHalf+1, sticky="nsew")
    for lyr in lyrs:
      self.showLyrBtn(self.lyrFrame, lyr, rowNum, 0)
      rowNum += 1

    #print(self.lyrFrame.children)
    
    self.lyrScrollbar.grid(row=0, column=3, rowspan=self.nrSchHalf+1, sticky="ns")
    self.lyrCanvas.configure(yscrollcommand=self.lyrScrollbar.set, background='skyblue')
    # print(f"showSch2: {self.lyrCanvas.bbox}")
    
  def showLyrBtn(self, fr, lyr, rowNum, col):
    # print(f"showLyr({fr}, {lyr})")
    print(f"lyrBtn{lyr}")

    setattr(self, f"lyrBtn{lyr}", Button(fr, text=lyr, padx=10, background=self.qaClrFail, command=lambda:self.showLyrDetails(lyr))) #, command=lambda:self.showLyr(owner, getattr(self, f"lyrBtn{lyr}").get())
    #setattr(self, f"lyrBtn{lyr}", Button(None, textvariable="test", width=8, height=1, padx=1, relief="solid", background=self.qaClrFail))
    getattr(self, f"lyrBtn{lyr}").grid(row=rowNum, column=col, sticky="W", padx=5, pady=1)
    self.currentLyrs.append(getattr(self, f"lyrBtn{lyr}"))
  ###########################################################################
  ###########################################################################

  def showLyrDetails(self, lyr):
    print(lyr)

    # change the layer button colours and remove the current layer details
    if self.currentLyrBtn:
      self.currentLyrBtn.config(background=self.qaClrFail)
    self.currentLyrBtn = getattr(self, f"lyrBtn{lyr}")
    self.currentLyrBtn.config(background=self.qaClrPass)

    self.lyrInfo.insert(INSERT, lyr)


  
  def popSetupFrame(self, owner):
    # Label(tSetup, text='Vicmap Replication Service', font=(32)).grid(row=0, column=0, columnspan=2, padx=5, pady=5)
    ##
    # qaReg
    Label(owner, text='profile:', bg=self.bgClrPass).grid(row=0, column=0, sticky="E")
    self.profiles = self.guic.config.cp.sections()
    # self.profiles.append("Add New...")
    self.proBox = ttk.Combobox(owner, values=self.profiles)
    self.proBox.current(0)
    self.proBox.grid(row=0, column=1, sticky="W")
    self.proBox.bind("<<ComboboxSelected>>", self.profileChanged)
    self.proBox.bind("<Return>",self.profileChanged)
    
    Label(owner, text='API URL:', bg=self.bgClrPass).grid(row=1, column=0, sticky="E")
    self.strurl = StringVar(value=self.guic.config.get('baseUrl'))
    Label(owner, textvariable=self.strurl, bg=self.bgClrPass).grid(row=1, column=1, sticky="W")
    
    # self.cntrlFrmBg = StringVar(value=self.qaClrFail)
    self.cntrlFrame = Frame(owner, borderwidth=5, relief="raised")#, width=150, height=100)#, width=300, height=300)
    self.cntrlFrame.grid(row=2, column=0, columnspan=2, padx=5, pady=5, sticky='nsew')
    self.cntrlFrm(self.cntrlFrame)#self.cntrlFrmBg)
    ##
    self.dbFrmBg = StringVar(value=self.qaClrFail)
    self.dbFrm = Frame(owner, bg=self.qaClrFail, borderwidth=5, padx=10, pady=10, relief="sunken")
    self.dbFrm.grid(row=3, column=0, columnspan=2, padx=5, pady=(0,5), sticky='nsew')#.pack(side='top',  fill='none',  padx=10,  pady=10,  expand=False)
    self.dbLbls = self.mkDbFrm(self.dbFrm, self.dbFrmBg)
    ##
    self.cltFrmBg = StringVar(value=self.qaClrFail)
    self.cltFrm = Frame(owner, bg=self.qaClrFail, borderwidth=5, padx=10, pady=10, relief="sunken")
    self.cltFrm.grid(row=4, column=0, padx=5, columnspan=2, pady=(0,5), sticky='nsew')#.pack(side='top',  fill='none',  padx=30,  pady=10,  expand=False)
    self.cltLbls = self.mkCltFrm(self.cltFrm, self.cltFrmBg)
    ##
    self.regFrmBg = StringVar(value=self.qaClrFail)
    self.regFrm = Frame(owner, bg=self.qaClrFail, borderwidth=5, padx=5, pady=5, relief="sunken")
    self.regFrm.grid(row=5, column=0, columnspan=2, padx=5, pady=(0,5), sticky='nsew')#.pack(side='top',  fill='none',  padx=30,  pady=10,  expand=False)
    # self.regFrm.grid_propagate(0)
    self.regLbls = self.mkRegFrm(self.regFrm, self.regFrmBg)
    
    self.getCfgVars()
    # self.endp.delete(0,END)
    # self.endp.insert(0, 'xxxxxx')
    # print(f"{self.strendp.get()}")
    # self.strendp.set('xxxxx')
    # print(f"{self.strendp.get()}")
    
  ###########################################################################
  
  def cntrlFrm(self, fr):
    self.syncBtn = Button(fr, text='SYNC', font=(72), padx=30, relief="solid", background="OliveDrab3", command=self.guic.sync)
    self.syncBtn.grid(row=2, column=3)#, padx=5, pady=5)#.pack(side='top', fill='none', padx=5, pady=(15,0))
    # Button(tSetup, text='SYNC', font=(288), command=self.sync).grid(row=1, column=0)
    self.openCloseBtn = Button(fr, text="Close", font=(288), command=self.dbOpenClose)
    self.openCloseBtn.grid(row=0, column=6, sticky='E', padx=5, pady=5)
    
    qaFr = Frame(fr, borderwidth=1, relief="solid")
    Label(qaFr, text='QA', font=(32)).grid(row=0, column=0, columnspan=2, pady=2)
    self.qaVars = []
    qaArr = [("Db", "DB cnxn", 1, 0), ("Spat", "PostGis", 2, 0), ("Clt", "DB PG_Client", 3, 0),
             ("Reg", "Registered", 1, 2), ("Val", "Validated", 2, 2), ("Meta", "Metadata", 3, 2), ("DbSch", "DB Schemas", 4, 2)]
    [self.qaVars.append(self.qaChk(qaFr, *qat)) for qat in qaArr]
    qaFr.grid(row=0, column=0, rowspan=5, sticky='E', padx=5, pady=5)

    Label(fr, text='datasets:').grid(row=1, column=4, sticky="E")
    # self.dsetCnt = IntVar(); self.dsetCnt.set(0)
    self.dsetCnt = Label(fr, text='0')
    self.dsetCnt.grid(row=1, column=5, sticky="W")
    
    Label(fr, text='active:').grid(row=2, column=4, sticky="E")
    # self.activeCnt = IntVar(); self.dsetCnt.set(0)
    self.activeCnt = Label(fr, text='0')
    self.activeCnt.grid(row=2, column=5, sticky="W")
    
    Label(fr, text='errors:').grid(row=3, column=4, sticky="E")
    # self.errCnt = IntVar(value=0)
    # Label(fr, text=self.errCnt.get()).grid(row=3, column=5, sticky="W")
    self.errCnt = Label(fr, text='0')
    self.errCnt.grid(row=3, column=5, sticky="W")
    self.fixBtn = Button(fr, text="Fix", command=self.guic.fix)
    self.fixBtn.grid(row=3, column=6, sticky='E', padx=5, pady=5)
    
  ###########################################################################
  
  def mkDbFrm(self, frm, bgClr):
    self.lblDbHdr = Label(frm, text='Database Connection Details', background=bgClr.get())
    self.lblDbHdr.grid(row=0, column=0, columnspan=2, sticky='W', pady=(0,5))
    Button(frm, text='Test Connection', command=self.guic.testDb).grid(row=0, column=2, sticky="W", pady=(0,5))
    Button(frm, text='Test Spatial', command=self.guic.testSpat).grid(row=0, column=3, sticky="E", pady=(0,5))
    ##
    self.lblEnt(frm, bgClr, 'endp', 'endpoint', 'localhost', 60, 1, 0, 3)
    self.lblEnt(frm, bgClr, 'inst', 'instance', 'vicmap', None, 2, 0)
    self.lblEnt(frm, bgClr, 'port', 'port', '5432', 10, 3, 0)
    self.lblEnt(frm, bgClr, 'user', 'username', 'vicmap', None, 2, 2)
    self.lblEnt(frm, bgClr, 'pswd', 'password', 'vicmap', None, 3, 2)
    return (frm, self.lblDbHdr, self.lblendp, self.lblinst, self.lblport, self.lbluser, self.lblpswd)
  
  def mkCltFrm(self, frm, bgClr):
    title = 'Database Client path -> home folder for pg_dump & pg_restore.'
    self.lblCltHdr = Label(frm, text=title, background=bgClr.get())
    self.lblCltHdr.grid(row=0, column=0, columnspan=3, sticky='W', pady=(0,5))
    Button(frm, text='Test Restore', command=self.guic.testPgc).grid(row=0, column=1, sticky="E", pady=(0,5))
    self.lblEnt(frm, bgClr, 'binPath', 'Bin Path', 'C:\Program Files\PostgreSQL\\17\\bin', 60, 1, 0)
    return (frm, self.lblCltHdr, self.lblbinPath)
  
  def mkRegFrm(self, frm, bgClr):
    self.lblRegHdr = Label(frm, text='Registration', background=bgClr.get())
    self.lblRegHdr.grid(row=0, column=0, columnspan=3, pady=(0,5), sticky="W")
    # self.lblRegHdr.config(text='')
    ##
    self.lblemail = self.lblEnt(frm, bgClr, 'email', 'email', 'somebody@example.org', 60, 1, 0, 3)
    self.lblClientId = self.lblEnt(frm, bgClr, 'clientId', 'Client ID', '', 40, 2, 0)
    self.clientId.config(state='disabled')
    # Button(frm, text='Get Client ID', command=lambda:self.guic.register('reg')).grid(row=2, column=2, sticky="W", pady=(5,5))
    self.lblApik = self.lblEnt(frm, bgClr, 'apik', 'API Key', '', 40, 3, 0)
    self.apik.config(state='disabled')
    # Button(frm, text='Get ApiKey', command=lambda:self.guic.register('apik')).grid(row=3, column=2, sticky="W", pady=(0,5))
    Button(frm, text='Refresh', command=lambda:self.guic.register('')).grid(row=2, rowspan=2, column=2, sticky="nsew", padx=20, pady=20)#(5,5))
    return [frm, self.lblRegHdr, self.lblemail, self.lblclientId, self.lblapik]
  
  ###########################################################################
  
  def qaChk(self, fr, var, desc, row, col): #(self.cntrlFrame, "DB", "DB", 1, 0)
    setattr(self, f"qa{var}", IntVar(value=0)) # IntVar())#self.qaDb = IntVar()
    # getattr(self, f"qa{var}").set('blog') #2)# self.qaDb.set(0)
    setattr(self, f"chk{var}", Checkbutton(fr, text=desc, variable=getattr(self, f"qa{var}"), onvalue=1, offvalue=0))#, tristatevalue=2))#o)) # self.dbChk = Checkbutton(self.cntrlFrame, text='DB', variable=self.qaDb, onvalue=1, offvalue=0)#, command=print_selection)
    # print(getattr(self, f"qa{var}").get())
    # getattr(self, f"qa{var}").state(['alternate'])
    getattr(self, f"chk{var}").config(state="disabled")
    getattr(self, f"chk{var}").grid(row=row, column=col, sticky='W')
    return getattr(self, f"qa{var}")
  
  def lblEnt(self, fr, bgClr, var, name, val, wid, row, col, colspan=1):
    # set label as lbl{var}
    setattr(self, f"lbl{var}", Label(fr, text=f"{name}:", background=bgClr.get(), width=8))
    getattr(self, f"lbl{var}").grid(row=row, column=col, sticky="E")
    # set entry as var, value as str{var}
    setattr(self, f"str{var}", StringVar(value=val))
    setattr(self, var, Entry(fr, textvariable=getattr(self, f"str{var}"), width=wid if wid else 20, bd=3))
    # getattr(self, var).insert(0, val)
    getattr(self, var).grid(row=row, column=col+1, columnspan=colspan, sticky="W", padx=5, pady=2)
    return getattr(self, f"lbl{var}")

  ###########################################################################
  ###########################################################################
  
  def profileChanged(self, event):
    _profile = self.proBox.get()
    print(f"{_profile} {event}")
    if _profile not in self.guic.config.cp.sections():
      print("Making new section")
      self.guic.config.setStage(_profile)
      self.profiles.append(_profile)
      self.getCfgVars()
    else:
      print("updating existing section")
      self.guic.config.setStage(_profile)
      self.getCfgVars()
  
  def getCfgVars(self):
    #meta
    self.strurl.set(self.guic.config.get("baseUrl"))
    qaChks = ['Db','Spat','Clt','Reg','Val','Meta','DbSch']
    [getattr(self, f"qa{qaChk}").set(0) for qaChk in qaChks]
    # db
    self.strendp.set(self.guic.config.get("dbHost") or 'localhost')
    self.strinst.set(self.guic.config.get("dbName"))
    self.strport.set(self.guic.config.get("dbPort") or '5432')
    self.struser.set(self.guic.config.get("dbUser"))
    self.strpswd.set(self.guic.config.get("dbPswd"))
    self.guic.testDb()
    self.guic.testSpat()
    # dbCli
    self.strbinPath.set(self.guic.config.get("dbClientPath") or 'C:\\Program Files\\PostgreSQL\\17\\bin')
    self.guic.testPgc()
    # Reg
    self.stremail.set(self.guic.config.get("email"))
    self.strclientId.set('xxxxx-xxxxx-xxxxx')#self.guic.config.get("client_id"))
    self.strapik.set('xxxxx-xxxxx-xxxxx')#self.guic.config.get("api_key"))
    self.guic.register('')

    self.qaAssess()

  def qaInit(self):
    self.syncReady = False

  def qaAssess(self):
    # print("qaAssess()")
    _qaDb = ["dbLbls", (self.qaDb.get(), self.qaSpat.get())]
    _qaClt = ["cltLbls", [self.qaClt.get()]]
    _qaReg = ["regLbls", (self.qaReg.get(), self.qaVal.get())]
    for qat in [_qaDb, _qaClt, _qaReg]:
      [lbl.config(bg=self.qaClrPass if all(qat[1]) else self.qaClrFail) for lbl in getattr(self, qat[0])]
    
    # check if all qa has passed
    # print(f"verifyQa: {all([qa.get() for qa in self.qaVars])} {[qa.get() for qa in self.qaVars]}")
    self.syncReady = all([qa.get() for qa in self.qaVars])
    _bgCol = self.qaClrPass if self.syncReady else self.qaClrFail
    self.style.configure('TFrame', background=_bgCol)
    self.syncBtn.config(background='OliveDrab3')
    
  ###########################################################################

  def dbOpenClose(self):#, event):
    print(self.qaDb.get())
    self.openCloseBtn.configure(text='Open' if not self.qaDb.get() else 'Close')
    self.qaDb.set(1) if not self.qaDb.get() else self.qaDb.set(0)
    # self.regFrmBg.set('OliveDrab3')
    # self.dbFrm.config(background='OliveDrab3')
    self.style.configure('TFrame', background='brown')

    self.guic.updateDBCounts()
    
    self.update_idletasks()
    # print(self.regFrmBg.get())
    #self.destroy()
  
class GuiControl():
  def __init__(self, gui, stg):
    self.gui = gui
    # self.db = None
    self.config = Config('config.ini', stg)
    print(f"stage: {self.config.getStage()}")
    # print(self.config.stg['email'])
    # print(self.config.get('email'))
    # self.setup = Setup(self.config, 'default')
    self.qa = QA() # each event will throw an Exception unless it passes?
    
  ## funtionality ##
  def register(self, action):
    print(f"register {self.config.get('email')}")
    # print(action)
    # self.gui.qaDb.set(1) if self.gui.qaDb else self.qaDb.gui.set(0)
    # if self.gui.email.get() == 'somebody@example.org':
    #   raise Exception("You cannot register the default email address")
    
    # update config
    self.config.set({'email':self.gui.email.get()})
    qaCode, qaMsg = self.qa.checkApiClient(self.config)
    # if qaCode < 2:
    #   logging.error(qaMsg)
    #   raise Exception(qaMsg)
    if qaCode == 0: #possible?
      # raise Exception("email not found")
      self.gui.lblRegHdr.config(text=qaMsg)
    elif qaCode == 1: # need to verify
      self.gui.strclientId.set(self.config.get('client_id'))
      self.gui.qaReg.set(1)
    elif qaCode == 2: # verified
      self.gui.qaReg.set(1)
      self.gui.qaVal.set(1)
      self.gui.strapik.set('xxxxx')#self.config.get('api_key'))
    
    self.gui.lblRegHdr.config(text=qaMsg)
    
    # if action == 'apik':
    #   # send the email and the client ID to attain the apik.
    #   pass
    self.gui.qaAssess()
  
  def testDb(self):
    # print("testDb")
    # update config
    self.config.set({'dbHost':self.gui.endp.get(),'dbPort':self.gui.port.get(),'dbName':self.gui.inst.get(), 'dbUser':self.gui.user.get(), 'dbPswd':self.gui.pswd.get()})
    
    try:
      DB(self.config).connect()
      # print(self.db.execute("select count(*) from vmadd.address"))
      self.gui.qaDb.set(1)
      print("db test successful")
      self.updateDBCounts()
    except Exception as ex:
      self.gui.qaDb.set(0)
      print(f"db cnxn test failed. Error:{ex}")
    self.gui.qaAssess()
    
  def testSpat(self):
    # print("testSpat")
    # update config
    # self.config.set({'dbHost':self.gui.endp.get(),'dbPort':self.gui.port.get(),'dbName':self.gui.inst.get(), 'dbUser':self.gui.user.get(), 'dbPswd':self.gui.pswd.get()})
    
    try:
      result = DB(self.config).execute("SELECT PostGIS_full_version()")
      print(result)
      if not result: raise Exception("No PostGis Version detected.")
      self.gui.qaSpat.set(1)
      print("db test successful")
    except Exception as ex:
      self.gui.qaSpat.set(0)
      print(f"db cnxn test failed. Error:{ex}")
    self.gui.qaAssess()
    
  def testPgc(self):
    # print("testPgc")
    # update config
    self.config.set({'dbClientPath':self.gui.binPath.get()})

    try:
      # print(self.binPath.get())
      ver = PGClient(None, self.gui.binPath.get()).get_restore_version()
      # print(f"PG Client version: {ver}")
      self.gui.qaClt.set(1)
      # self.chkDb.config(back)
      print("db client test successful")
    except Exception as ex:
      self.gui.qaClt.set(0)
      # print(f"Exception: {str(ex)}")
      # print(traceback.format_exc())
      print(f"db client test failed. Error:{ex}")
    self.gui.qaAssess()

  def sync(self):
    print("sync")
    _db = DB(self.config)
    synccer = Synccer(self.config, _db)
    synccer.unWait() # queue any leftover jobs from last time.
    while(synccer.assess()):
      synccer.run()
      # break

    self.updateDBCounts()

  def fix(self):
    print("fix")
    # TODO: set the layers in error to seed loads.

  def updateDBCounts(self):
    if self.gui.qaDb.get():
      _db = DB(self.config)
      _local = _db.getRecSet(LyrReg)

      self.gui.dsetCnt.config(text=f'{str(len([d for d in _local]))}')
      self.gui.activeCnt.config(text=f'{str(len([d  for d in _local if d.active and not d.err]))}')
      self.gui.errCnt.config(text=str(len([d for d in _local if d.err])))
    else:
      self.gui.dsetCnt.config(text="   ")
      self.gui.activeCnt.config(text="   ")
      self.gui.errCnt.config(text="   ")

if __name__ == "__main__":
  gui = GUI(None, None)
  gui.mainloop()