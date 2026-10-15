import logging
import math
import queue
import threading
import traceback
import webbrowser
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from tkinter import Canvas, IntVar, Misc, PhotoImage, StringVar, TclError, Tk, ttk
from typing import Any, Literal

from .dbTable import LyrReg, Schema, Schemas
from .setup import QA
from .sync import Supplies, Synccer
from .utils import Config, pgBinDefault
from .utils_api import ApiUtils
from .utils_db import DB

# Where tkinter puts a widgets content inside its cell.
Anchor = Literal['nw', 'n', 'ne', 'w', 'center', 'e', 'sw', 's', 'se']

IMG = Path(__file__).parent / 'img'


# The pointer to hover an editable field with. Windows and macOS draw a text cursor sized
# for their own screen, so they keep it. X11 hands back whatever the desktop cursor theme
# holds, which on a scaled display is a 48 pixel bar over a one line entry, and no cursor
# name asks for a smaller one. A bitmap of our own making is the only size a theme cannot
# override. The paths are braced because the spec is read as a tcl list.
def textCursor(win: Misc) -> str:
  global _textCursorSpec
  if _textCursorSpec is None:  # every entry wants the same one, so it is worked out once
    _textCursorSpec = _pickTextCursor(win)
  return _textCursorSpec


_textCursorSpec: str | None = None


def _pickTextCursor(win: Misc) -> str:
  if win.tk.call('tk', 'windowingsystem') != 'x11':
    return 'xterm'
  _src, _msk = IMG / 'ibeam.xbm', IMG / 'ibeam_mask.xbm'
  if not (_src.exists() and _msk.exists()):
    return 'xterm'
  _spec = f'{{@{_src}}} {{{_msk}}} black white'
  try:  # a server that will not take the bitmap keeps the one it has
    ttk.Entry(win, cursor=_spec).destroy()
  except TclError:
    logging.debug(f"X11 would not take the entry cursor bitmap, keeping xterm: {_spec}")
    return 'xterm'
  return _spec


class Ves:
  # The Vicmap Editing Service palette from ves_frontend/src/theme.css.
  ink = '#2a2440'
  muted = '#6a6577'
  line = '#e3dfea'
  navy = '#201547'
  navy2 = '#2e2063'
  purple = '#895a8b'
  purpleBg = '#f2ecf4'
  purpleLine = '#dcc9de'
  charcoal = '#3b3b3f'
  white = '#ffffff'
  ok = '#2e7d32'
  err = '#9b1c1c'
  warn = '#8a5a00'
  info = '#1565c0'
  hover = '#e6e3ee'
  picked = '#dcc9de'
  control = '#f4f1f8'

  # Which contract maintains a layer. Darker than the ok and warn they started as, so a
  # white tick reads on a filled box and the layer names carry on white as well.
  supVLAT = navy2
  supVTT = '#1b5e20'
  supMISC = '#6e4500'


class StyMan:
  # Fonts, using defaults.
  fontBase = ('TkDefaultFont', 10)
  fontBold = ('TkDefaultFont', 10, 'bold')
  fontSmall = ('TkDefaultFont', 9)
  fontHeading = ('TkDefaultFont', 11, 'bold')
  fontTitle = ('TkDefaultFont', 13, 'bold')

  def __init__(self) -> None:
    self.style = ttk.Style()
    # Style: clam is the one theme here that draws a flat widget.
    self.style.theme_create("vlrsVes", parent="clam")
    self.style.theme_use("vlrsVes")
    self._frames()
    self._labels()
    self._buttons()
    self._inputs()
    self._notebook()
    self._table()

  def _frames(self) -> None:
    st = self.style
    st.configure('TFrame', background=Ves.purpleBg)
    st.configure('Logo.TFrame', background=Ves.white)
    st.configure('Banner.TFrame', background=Ves.navy)
    st.configure('Rule.TFrame', background=Ves.purple)
    st.configure('Status.TFrame', background=Ves.white)
    st.configure(
      'Qa.TFrame', background=Ves.white, borderwidth=1, relief='solid', bordercolor=Ves.line
    )
    st.configure('Plain.TFrame', background=Ves.white, borderwidth=0)
    st.configure(
      'Key.TFrame',
      background=Ves.purpleBg,
      borderwidth=1,
      relief='solid',
      bordercolor=Ves.purpleLine,
    )
    st.configure(
      'Card.TFrame', background=Ves.white, borderwidth=1, relief='solid', bordercolor=Ves.line
    )

  def _labels(self) -> None:
    st = self.style
    st.configure('TLabel', background=Ves.purpleBg, foreground=Ves.charcoal, font=self.fontBase)
    st.configure('Card.TLabel', background=Ves.white, foreground=Ves.charcoal, font=self.fontBase)
    st.configure('Head.TLabel', background=Ves.white, foreground=Ves.ink, font=self.fontHeading)
    st.configure('Muted.TLabel', background=Ves.white, foreground=Ves.muted, font=self.fontSmall)
    st.configure('KeyText.TLabel', background=Ves.purpleBg, foreground=Ves.ink, font=self.fontSmall)
    st.configure('Title.TLabel', background=Ves.navy, foreground=Ves.white, font=self.fontTitle)
    st.configure('Sub.TLabel', background=Ves.navy, foreground=Ves.purpleLine, font=self.fontSmall)
    for name, clr in (('Ok', Ves.ok), ('Err', Ves.err), ('Warn', Ves.warn), ('Info', Ves.info)):
      st.configure(f'{name}.TLabel', background=Ves.white, foreground=clr, font=self.fontBase)
    for sup in ('VLAT', 'VTT', 'MISC'):
      st.configure(
        f'{sup}.Key.TLabel',
        background=Ves.purpleBg,
        foreground=getattr(Ves, f'sup{sup}'),
        font=self.fontSmall,
      )

  def _buttons(self) -> None:
    st = self.style
    st.configure(
      'TButton',
      background=Ves.control,
      foreground=Ves.ink,
      bordercolor=Ves.purple,
      lightcolor=Ves.control,
      darkcolor=Ves.control,
      focuscolor=Ves.purple,
      relief='solid',
      borderwidth=1,
      anchor='center',
      font=self.fontBase,
      padding=(12, 6),
    )
    st.map(
      'TButton',
      background=[('disabled', Ves.white), ('pressed', Ves.picked), ('active', Ves.hover)],
      lightcolor=[('disabled', Ves.white), ('pressed', Ves.picked), ('active', Ves.hover)],
      darkcolor=[('disabled', Ves.white), ('pressed', Ves.picked), ('active', Ves.hover)],
      bordercolor=[('disabled', Ves.line)],
      foreground=[('disabled', Ves.muted)],
    )
    # The one action on the window that starts work, so it is the one filled button.
    st.configure(
      'Accent.TButton',
      background=Ves.purple,
      foreground=Ves.white,
      bordercolor=Ves.purple,
      lightcolor=Ves.purple,
      darkcolor=Ves.purple,
      padding=(24, 9),
    )
    st.map(
      'Accent.TButton',
      background=[('disabled', Ves.purpleBg), ('pressed', Ves.navy), ('active', Ves.navy2)],
      lightcolor=[('disabled', Ves.purpleBg), ('active', Ves.navy2)],
      darkcolor=[('disabled', Ves.purpleBg), ('active', Ves.navy2)],
      bordercolor=[('disabled', Ves.purpleLine)],
      foreground=[('disabled', Ves.muted)],
    )
    st.configure('Hdr.TButton', padding=(10, 3), anchor='center', font=self.fontSmall)
    st.configure('Key.TButton', padding=(10, 3), width=4, anchor='center', font=self.fontSmall)
    # Schema and layer buttons carry their picked state as a widget state, so choosing
    # one is a state change rather than a colour written over the widget.
    st.configure(
      'Sch.TButton',
      background=Ves.white,
      lightcolor=Ves.white,
      darkcolor=Ves.white,
      bordercolor=Ves.white,
      relief='flat',
      borderwidth=0,
      padding=(8, 5),
      anchor='w',
    )
    st.map(
      'Sch.TButton',
      background=[('selected', Ves.purple), ('active', Ves.hover)],
      foreground=[('selected', Ves.white)],
    )
    # A schema whose layers all come from the one contract is named and picked in that
    # contract's colour. Mixed schemas keep the plain style above.
    for sup in ('VLAT', 'VTT', 'MISC'):
      _clr = getattr(Ves, f'sup{sup}')
      st.configure(
        f'{sup}.Sch.TButton',
        background=Ves.white,
        lightcolor=Ves.white,
        darkcolor=Ves.white,
        bordercolor=Ves.white,
        foreground=_clr,
        relief='flat',
        borderwidth=0,
        padding=(8, 5),
        anchor='w',
      )
      st.map(
        f'{sup}.Sch.TButton',
        background=[('selected', _clr), ('active', Ves.hover)],
        lightcolor=[('selected', _clr)],
        darkcolor=[('selected', _clr)],
        foreground=[('selected', Ves.white)],
      )
    for sup in ('VLAT', 'VTT', 'MISC'):
      st.configure(
        f'{sup}.Lyr.TButton',
        background=Ves.white,
        lightcolor=Ves.white,
        darkcolor=Ves.white,
        bordercolor=Ves.white,
        relief='flat',
        borderwidth=0,
        foreground=getattr(Ves, f'sup{sup}'),
        padding=(8, 4),
        anchor='w',
        font=self.fontSmall,
      )
      # Picking a layer fills it with the contract colour it is named in, so the
      # selection says the same thing as the key rather than a purple of its own.
      st.map(
        f'{sup}.Lyr.TButton',
        background=[('selected', getattr(Ves, f'sup{sup}')), ('active', Ves.hover)],
        lightcolor=[('selected', getattr(Ves, f'sup{sup}'))],
        darkcolor=[('selected', getattr(Ves, f'sup{sup}'))],
        foreground=[('selected', Ves.white)],
      )

  def _inputs(self) -> None:
    st = self.style
    st.configure(
      'TEntry',
      fieldbackground=Ves.white,
      bordercolor=Ves.purpleLine,
      lightcolor=Ves.purpleLine,
      darkcolor=Ves.purpleLine,
      foreground=Ves.ink,
      padding=4,
    )
    st.map(
      'TEntry', fieldbackground=[('disabled', Ves.purpleBg)], foreground=[('disabled', Ves.muted)]
    )
    st.configure(
      'TCombobox', fieldbackground=Ves.white, background=Ves.white, bordercolor=Ves.purpleLine
    )
    st.configure(
      'TCheckbutton',
      background=Ves.white,
      foreground=Ves.charcoal,
      indicatorbackground=Ves.white,
      indicatorforeground=Ves.purple,
      indicatormargin=(0, 0, 6, 0),
      upperbordercolor=Ves.purpleLine,
      lowerbordercolor=Ves.purpleLine,
      focuscolor=Ves.white,
    )
    st.map(
      'TCheckbutton',
      indicatorbackground=[
        ('disabled', Ves.purpleBg),
        ('selected', Ves.purple),
        ('!selected', Ves.white),
      ],
      upperbordercolor=[('disabled', Ves.line), ('selected', Ves.purple)],
      lowerbordercolor=[('disabled', Ves.line), ('selected', Ves.purple)],
      background=[('active', Ves.white)],
      foreground=[('disabled', Ves.muted)],
    )
    st.configure('Lyr.TCheckbutton', background=Ves.white, padding=0)
    st.map('Lyr.TCheckbutton', background=[('active', Ves.hover)])
    # A ticked layer fills its box with the contract colour, so the tick reads against
    # the key the same way the layer name beside it does.
    for sup in ('VLAT', 'VTT', 'MISC'):
      _clr = getattr(Ves, f'sup{sup}')
      st.configure(f'{sup}.Lyr.TCheckbutton', background=Ves.white, padding=0)
      st.map(
        f'{sup}.Lyr.TCheckbutton',
        background=[('active', Ves.hover)],
        indicatorbackground=[
          ('disabled', Ves.purpleBg),
          ('selected', _clr),
          ('!selected', Ves.white),
        ],
        # The tick is drawn on the filled box, so it is white rather than the mauve it
        # would inherit, which was near invisible on the two lighter contracts.
        indicatorforeground=[('selected', Ves.white)],
        upperbordercolor=[('disabled', Ves.line), ('selected', _clr)],
        lowerbordercolor=[('disabled', Ves.line), ('selected', _clr)],
      )
    st.configure(
      'TScrollbar',
      background=Ves.purpleBg,
      troughcolor=Ves.white,
      bordercolor=Ves.line,
      arrowcolor=Ves.muted,
    )
    st.configure('TProgressbar', background=Ves.purple, troughcolor=Ves.line, bordercolor=Ves.line)

  def _notebook(self) -> None:
    st = self.style
    st.configure('TNotebook', background=Ves.navy, borderwidth=0, tabmargins=(0, 0, 0, 0))
    st.configure(
      'TNotebook.Tab',
      background=Ves.navy,
      foreground=Ves.purpleLine,
      padding=(28, 10),
      borderwidth=0,
      font=self.fontBase,
    )
    st.map(
      'TNotebook.Tab',
      background=[('selected', Ves.purple), ('active', Ves.navy2)],
      foreground=[('selected', Ves.white)],
      font=[('selected', self.fontBold)],
    )

  def _table(self) -> None:
    st = self.style
    st.configure(
      'Treeview',
      background=Ves.white,
      fieldbackground=Ves.white,
      foreground=Ves.charcoal,
      bordercolor=Ves.line,
      rowheight=22,
      font=self.fontSmall,
    )
    st.map('Treeview', background=[('selected', Ves.purpleBg)], foreground=[('selected', Ves.ink)])
    st.configure(
      'Treeview.Heading',
      background=Ves.purpleBg,
      foreground=Ves.ink,
      font=self.fontSmall,
      relief='flat',
      padding=4,
    )
    st.map('Treeview.Heading', background=[('active', Ves.purpleLine)])


class StatusBar(ttk.Frame):
  # Where the messages go that used to be printed to a terminal the user of a window
  # never sees.
  def __init__(self, container: Misc):
    super().__init__(container, style='Status.TFrame', padding=(12, 6))
    self.msg = ttk.Label(self, text="Ready", style='Card.TLabel')
    self.msg.grid(row=0, column=0, sticky='w')
    self.bar = ttk.Progressbar(self, mode='indeterminate', length=140)
    self.columnconfigure(0, weight=1)

  def say(self, text: str, kind: str = '') -> None:
    self.msg.configure(text=text, style=f'{kind}.TLabel' if kind else 'Card.TLabel')

  def busy(self, text: str) -> None:
    self.say(text, 'Info')
    self.bar.grid(row=0, column=1, sticky='e', padx=(12, 0))
    self.bar.start(12)

  def idle(self, text: str, kind: str = '') -> None:
    self.bar.stop()
    self.bar.grid_remove()
    self.say(text, kind)


class GuiControl(Tk):
  def __init__(self, stg: str):
    super().__init__()

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

    self.title("deltaVic")
    self.configure(background=Ves.purpleBg)

    self._logoBar()
    self._banner()

    self.tabs = ttk.Notebook(self)
    self.tabs.grid(row=3, column=0, sticky='nsew')
    self.columnconfigure(0, weight=1)
    self.rowconfigure(3, weight=1)

    self.status = StatusBar(self)
    self.status.grid(row=4, column=0, sticky='ew')

    self.frSetup = FrSetup(self.tabs, self)
    self.tabs.add(self.frSetup, text=f"{'Setup & QA':^14}")

    self.frMeta = FrMetaData(self.tabs, self, 'Meta')
    self.tabs.add(self.frMeta, text=f"{'Meta':^14}")

    self.frData = FrMetaData(self.tabs, self, 'Data')
    self.tabs.add(self.frData, text=f"{'Data':^14}")

    # What the tabs actually need, now that they exist, rather than a fixed size that
    # goes stale the next time a widget is added to one of them.
    self.fitToContent()

    self._drainUi()
    self.frSetup.regFrm.refreshRights()

  def _logoBar(self) -> None:
    bar = ttk.Frame(self, style='Logo.TFrame', padding=(20, 6))
    bar.grid(row=0, column=0, sticky='ew')
    bar.columnconfigure(1, weight=1)
    # Held on the instance because tkinter keeps no reference of its own and a
    # collected image leaves an empty box behind.
    self.imgVicmap = self._logo('vicmap-logo.png')
    self.imgVicgov = self._logo('vicgov-logo.png')
    if self.imgVicmap:
      ttk.Label(bar, image=self.imgVicmap, style='Card.TLabel').grid(row=0, column=0, sticky='w')
    if self.imgVicgov:
      ttk.Label(bar, image=self.imgVicgov, style='Card.TLabel').grid(row=0, column=2, sticky='e')
    ttk.Frame(self, style='Rule.TFrame', height=3).grid(row=1, column=0, sticky='ew')

  # Stored at the size they are drawn, so tkinter never has to scale them. Sources are
  # ves_frontend/src/assets in the VES repository.
  def _logo(self, name: str) -> PhotoImage | None:
    try:
      return PhotoImage(file=IMG / name)
    except Exception as ex:
      logging.warning(f"Could not load {name}: {ex}")
      return None

  def _banner(self) -> None:
    ban = ttk.Frame(self, style='Banner.TFrame', padding=(20, 10))
    ban.grid(row=2, column=0, sticky='ew')
    ban.columnconfigure(0, weight=1)
    ttk.Label(ban, text="deltaVic", style='Title.TLabel').grid(row=0, column=0, sticky='w')
    ttk.Label(ban, text="Vicmap layers replicated to your local database", style='Sub.TLabel').grid(
      row=1, column=0, sticky='w', pady=(2, 0)
    )

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

  # The reason there is no write on this layer, or None when there is.
  def uploadBlocked(self, lyr: LyrReg) -> str | None:
    if not self.rights:
      return "No rights held. Refresh the registration on the setup tab."
    if lyr.sup in ('VLAT', 'VTT'):
      return f"{lyr.sup} is an external maintenance contract, so only MISC can be uploaded."
    if (
      any(lyr.identity.startswith(s) for s in self.rights['schemas']['allow']['write'])
      and lyr.identity not in self.rights['datasets']['deny']['write']
    ) or lyr.identity in self.rights['datasets']['allow']['write']:
      return None
    return f"Your registration carries no write rights on {lyr.sch}."

  def uploadAllowed(self, lyr: LyrReg, upldType: str | None = None) -> bool:
    # Checked here for display only. The server checks all of it again on submission.
    if not self.rights:
      if upldType:
        self.status.idle("No rights held. Refresh the registration on the setup tab.", 'Warn')
      return False
    if lyr.sup in ('VLAT', 'VTT'):  # only MISC allowed
      if upldType:
        self.status.idle(
          "Only MISC datasets can be updated. VLAT and VTT are external contracts.", 'Warn'
        )
      return False

    if (
      any(lyr.identity.startswith(s) for s in self.rights['schemas']['allow']['write'])
      and lyr.identity not in self.rights['datasets']['deny']['write']
    ):
      return True
    if lyr.identity in self.rights['datasets']['allow']['write']:
      return True

    if upldType:
      self.status.idle(f"No rights to write {lyr.identity}.", 'Warn')
    return False


class FrMetaData(ttk.Frame):
  def __init__(self, container: Misc, guic: GuiControl, type: str):
    super().__init__(container, padding=12)
    self.guic = guic
    self.type = type  # is it remote ('Meta') or local ('Data')
    self.data = Schemas(self.type, self.guic.cfg, load=False)
    self.inflight = False  # a layer list is already on its way

    self.schFr = SubFrMetaSchs(self, guic, self.data)
    self.schFr.grid(row=0, column=0, padx=(0, 10), sticky='nsew')

    self.lyrFr = SubFrMetaLyrs(self, guic, self.data)
    self.lyrFr.grid(row=0, column=1, sticky='nsew')

    self.lyrInfoFr = SubFrMetaLyrInfo(self, guic)
    self.lyrInfoFr.grid(row=1, column=0, columnspan=2, pady=(10, 0), sticky='nsew')

    self.columnconfigure(1, weight=1)
    self.rowconfigure(0, weight=1)
    self.rowconfigure(1, weight=1)

    self.setData()

  def setData(self) -> None:
    # The tab asks for its list when it is built, and the registration check asks
    # again when rights come back. One request in flight is enough.
    if self.inflight:
      return
    self.inflight = True
    # The meta list is an api call and takes a few seconds, so the tab says what it is
    # waiting on rather than sitting empty and looking broken.
    self.schFr.waiting("Loading ...")
    self.guic.runAsync(lambda: Schemas(self.type, self.guic.cfg), self._setDataDone)

  def _setDataDone(self, data: Schemas | None, err: Exception | None) -> None:
    self.inflight = False
    if err or not data:
      self.schFr.waiting("Unavailable")
      self.guic.status.idle(f"Could not read the {self.type} layer list: {err}", 'Err')
      return
    self.data = data
    _open = self.schFr.selectedName()
    self.schFr.setData(data)
    self.lyrFr.setData(data)
    if _open and _open in self.schFr.schBtns:
      self.schFr.showSch(_open)


class Card(ttk.Frame):
  # A titled white panel. Every block of content on the window is one of these.
  def __init__(self, owner: Misc, title: str = ''):
    super().__init__(owner, style='Card.TFrame', padding=12)
    self.row = 0
    if title:
      ttk.Label(self, text=title, style='Head.TLabel').grid(
        row=0, column=0, columnspan=6, sticky='w', pady=(0, 8)
      )
      self.row = 1


class SubFrMetaSchs(Card):
  def __init__(self, owner: FrMetaData, guic: GuiControl, data: Schemas):
    super().__init__(owner, 'Schemas')
    self.owner = owner
    self.guic = guic
    self.selected: ttk.Button | None = None
    self.schBtns: dict[str, ttk.Button] = {}
    self.schs: list[Schema] = []
    self.note: ttk.Label | None = None
    self.setData(data)

  # Stands in for the schema buttons until there are some to draw.
  def waiting(self, text: str) -> None:
    if not self.note:
      self.note = ttk.Label(self, style='Muted.TLabel')
      self.note.grid(row=self.row, column=0, columnspan=2, sticky='w', padx=2, pady=2)
    self.note.configure(text=text)

  def setData(self, data: Schemas) -> None:
    if self.note:
      self.note.destroy()
      self.note = None
    [btn.destroy() for btn in self.schBtns.values()]
    self.schBtns = {}
    self.selected = None
    self.schs = data.schs

    _nrCols = 2
    _nrItems = math.ceil(len(self.schs) / _nrCols) or 1
    for ii, sch in enumerate(self.schs):
      self.mkSchBtn(sch.name, self.row + (ii % _nrItems), int(ii / _nrItems), self.supOf(sch))

  # The contract most of the schema's layers belong to. Only about half of them are pure,
  # so the majority names the schema and the layer names inside carry the exceptions.
  # A tie goes to the contract listed first in the key.
  @staticmethod
  def supOf(sch: Schema) -> str | None:
    _sups = [lyr.sup for lyr in sch.lyrs if lyr.sup in ('VLAT', 'VTT', 'MISC')]
    return max(('VLAT', 'VTT', 'MISC'), key=_sups.count) if _sups else None

  def mkSchBtn(self, sch: str, row: int, col: int, sup: str | None = None) -> None:
    _style = f'{sup}.Sch.TButton' if sup in ('VLAT', 'VTT', 'MISC') else 'Sch.TButton'
    btn = ttk.Button(self, text=sch, style=_style, command=lambda: self.showSch(sch))
    btn.grid(row=row, column=col, sticky='ew', padx=2, pady=1)
    self.schBtns[sch] = btn

  def selectedName(self) -> str | None:
    return str(self.selected['text']) if self.selected else None

  def showSch(self, sch: str) -> None:
    if self.selected:
      self.selected.state(['!selected'])
    self.selected = self.schBtns[sch]
    self.selected.state(['selected'])
    self.owner.lyrFr.redrawCanvas(sch)


class SubFrMetaLyrs(Card):
  def __init__(self, owner: FrMetaData, guic: GuiControl, data: Schemas):
    super().__init__(owner)
    self.data = data
    self.owner = owner
    self.guic = guic
    self.nrLyrs = 0

    self.lyrHdrStr = StringVar(self, "Layers")
    ttk.Label(self, textvariable=self.lyrHdrStr, style='Head.TLabel').grid(
      row=0, column=0, sticky='w', pady=(0, 8)
    )
    ttk.Button(self, text="Key", style='Key.TButton', command=self.toggleKey).grid(
      row=0, column=1, sticky='w', padx=(10, 0), pady=(0, 8)
    )
    if self.owner.type == "Meta":
      ttk.Button(
        self,
        text="All on",
        style='Hdr.TButton',
        command=lambda: self.toggleActive(sch=self.owner.schFr.selectedName(), active=True),
      ).grid(row=0, column=3, sticky='e', padx=(6, 0), pady=(0, 8))
      ttk.Button(
        self,
        text="All off",
        style='Hdr.TButton',
        command=lambda: self.toggleActive(sch=self.owner.schFr.selectedName(), active=False),
      ).grid(row=0, column=4, sticky='e', padx=(6, 0), pady=(0, 8))

    # The colours a layer name is drawn in, which mean nothing until they are named.
    self.key = ttk.Frame(self, style='Key.TFrame', padding=8)
    for ii, (sup, what) in enumerate(
      (
        ('VLAT', 'VLAT, address and property contract'),
        ('VTT', 'VTT, topographic contract'),
        ('MISC', 'MISC, maintained in house and uploadable'),
      )
    ):
      ttk.Label(self.key, text='\u25a0', style=f'{sup}.Key.TLabel').grid(row=ii, column=0)
      ttk.Label(self.key, text=what, style='KeyText.TLabel').grid(
        row=ii, column=1, sticky='w', padx=(6, 0)
      )

    self.columnconfigure(2, weight=1)  # the gap that holds the actions out to the right
    self.rowconfigure(2, weight=1)

    self.canvas = Canvas(self, width=415, background=Ves.white, highlightthickness=0, bd=0)
    # X11 reports the wheel as buttons 4 and 5, everywhere else as <MouseWheel>. The
    # bindings are global because the pointer is over a layer button rather than the
    # canvas for most of the list, and the handler works out whether this list is under it.
    for _seq in ('<MouseWheel>', '<Button-4>', '<Button-5>'):
      self.canvas.bind_all(_seq, self._onWheel, add='+')

    self.lyrFrame = ttk.Frame(self.canvas, style='Card.TFrame', padding=2)
    self.lyrFrame.bind(
      "<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
    )
    self.canvasWin = self.canvas.create_window((0, 0), window=self.lyrFrame, anchor="nw")
    # A canvas item keeps its own width, so widening the window has to widen it too.
    self.canvas.bind(
      '<Configure>', lambda e: self.canvas.itemconfigure(self.canvasWin, width=e.width)
    )
    self.canvas.grid(row=2, column=0, columnspan=5, sticky="nsew")

    self.lyrScrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]
    self.lyrScrollbar.grid(row=2, column=5, sticky="ns")
    # Until the canvas has reported a position the scrollbar answers with the four
    # value protocol, and the wheel over one of those calls yview with a bare number.
    self.canvas.configure(yscrollcommand=self.lyrScrollbar.set)
    self.lyrScrollbar.set(0.0, 1.0)

    self.lyrBtns: dict[str, ttk.Button] = {}
    self.lyrChks: dict[str, ttk.Checkbutton] = {}
    self.lyrVars: dict[str, IntVar] = {}
    self.selected: ttk.Button | None = None

  def toggleKey(self) -> None:
    if self.key.winfo_ismapped():
      self.key.grid_remove()
    else:
      self.key.grid(row=1, column=0, columnspan=6, sticky='w', pady=(2, 8))

  # Scrolls this layer list, but only while the pointer is somewhere inside it. Both
  # tabs build one of these and both are bound, so each asks before it acts.
  def _onWheel(self, event: Any) -> None:
    _under = self.winfo_containing(event.x_root, event.y_root)
    if not _under or not str(_under).startswith(str(self.canvas)):
      return
    if event.num in (4, 5):  # x11
      _step = -1 if event.num == 4 else 1
    else:
      _step = int(-event.delta / 120) or (-1 if event.delta > 0 else 1)
    self.canvas.yview_scroll(_step, "units")

  def setData(self, data: Schemas) -> None:
    self.data = data
    self.clearCanvas()

  def clearCanvas(self) -> None:
    [w.destroy() for w in self.lyrBtns.values()]
    [w.destroy() for w in self.lyrChks.values()]
    self.lyrBtns, self.lyrChks, self.lyrVars = {}, {}, {}
    self.selected = None
    self.lyrHdrStr.set("Layers")

  def redrawCanvas(self, newSch: str | None = None) -> None:
    if not newSch:
      return
    self.clearCanvas()

    if not (_sch := self.data.get(newSch)):
      return
    self.nrLyrs = len(_sch.lyrs)
    self.lyrHdrStr.set(f"Layers ({self.nrLyrs})")
    _sch.lyrs.sort(key=lambda lyr: lyr.identity)
    self.setLyrs(_sch.lyrs)

  def setLyrs(self, lyrs: list[LyrReg]) -> None:
    [self.mkLyrBtn(lyr, idx) for idx, lyr in enumerate(lyrs)]
    [self.lyrFrame.columnconfigure(ii, uniform='equal_columns', weight=1) for ii in (1, 3)]

  def mkLyrBtn(self, lyr: LyrReg, idx: int) -> None:
    _cols = 2
    rowNum, colNum = int(idx / _cols), idx % _cols

    btn = ttk.Button(
      self.lyrFrame,
      text=lyr.tbl,
      style=f'{lyr.sup}.Lyr.TButton',
      command=lambda: self.showLyrDetails(lyr),
    )
    btn.grid(row=rowNum, column=(colNum * _cols) + 1, sticky="ew", padx=(0, 4), pady=1)
    self.lyrBtns[lyr.identity] = btn

    if self.owner.type == "Meta":
      var = IntVar(value=1 if lyr.active else 0)
      chk = ttk.Checkbutton(
        self.lyrFrame,
        variable=var,
        onvalue=1,
        offvalue=0,
        style=f'{lyr.sup}.Lyr.TCheckbutton',
        command=lambda: self.toggleActive(lyr=lyr),
      )
      chk.grid(row=rowNum, column=colNum * _cols, sticky="e", padx=(4, 0), pady=1)
      if self.guic.cfg.get('dbComplete') != "True":
        chk.configure(state="disabled")
      self.lyrChks[lyr.identity] = chk
      self.lyrVars[lyr.identity] = var

  def showLyrDetails(self, lyr: LyrReg) -> None:
    if self.selected:
      self.selected.state(['!selected'])
    self.selected = self.lyrBtns[lyr.identity]
    self.selected.state(['selected'])
    self.owner.lyrInfoFr.showLyrDetails(lyr)

  def toggleActive(
    self, lyr: LyrReg | None = None, sch: str | None = None, active: bool | None = None
  ) -> None:
    _db = DB(self.guic.cfg)
    try:
      if lyr:
        active = bool(self.lyrVars[lyr.identity].get())
        _db.execute(*lyr.setActive(active))
      if sch and (_sch := self.data.get(sch)):
        _db.execute(
          "update vm_meta.data set active=%s where split_part(identity, '.', 1)=%s",
          (bool(active), sch),
        )
        for _lyr in _sch.lyrs:
          _lyr.active = bool(active)
        [var.set(bool(active)) for var in self.lyrVars.values()]
        self.guic.status.idle(f"{sch}: all layers {'on' if active else 'off'}", 'Ok')
    finally:
      _db.close()


class SubFrMetaLyrInfo(Card):
  def __init__(self, owner: FrMetaData, guic: GuiControl):
    super().__init__(owner)
    self.owner = owner
    self.guic = guic
    self.lyrMeta: dict[str, Any] | None = None
    # The layer whose details were last asked for, used to drop stale answers.
    self.pendingLyr: LyrReg | None = None
    self.relBox: ttk.Combobox
    self.gtBox: ttk.Combobox
    self.mdUUID: StringVar
    self.vdp: IntVar
    ttk.Label(self, text="Pick a layer to see its details", style='Muted.TLabel').grid(
      row=0, column=0, padx=4, pady=4
    )

  def showLyrDetails(self, lyr: LyrReg) -> None:
    # The metadata is an api call, so it is fetched off the ui thread and the frame is
    # drawn when it lands. The layer asked for is remembered so a slow answer for an
    # earlier click cannot draw over a later one.
    self.pendingLyr = lyr
    for widget in self.winfo_children():
      widget.destroy()
    ttk.Label(self, text=f"Loading {lyr.identity} ...", style='Muted.TLabel').grid(
      row=0, column=0, padx=4, pady=4
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

    ttk.Label(self, text=lyr.identity, style='Head.TLabel').grid(
      row=0, column=0, columnspan=3, sticky='w', pady=(0, 8)
    )
    _bar = ttk.Frame(self, style='Plain.TFrame')
    _bar.grid(row=0, column=4, sticky='e')
    self.columnconfigure(3, weight=1)  # the gap that holds the bar out to the right

    if self.owner.type == "Data":
      self.mkFrUpload(_bar, lyr)
      self.mkUploadPane(lyr)
      self.guic.fitToContent()
      return

    self.columnconfigure(0, weight=1, uniform='panes')
    self.columnconfigure(3, weight=1, uniform='panes')
    ttk.Button(_bar, text="Reseed", command=lambda: self.reseed(lyr.identity)).grid(
      row=0, column=0, padx=(0, 6)
    )
    ttk.Button(
      _bar, text="Metadata weblink (GeoNetwork ISO 19115)", command=self.openMetaLink
    ).grid(row=0, column=1)

    if self.lyrMeta:  # existing layer
      _colData = (
        [(col, type) for col, type in self.lyrMeta['columns'].items()]
        if self.lyrMeta['columns']
        else []
      )
      _colcols: list[tuple[str, int, Anchor]] = [('Column', 140, 'w'), ('Type', 200, 'w')]
      TView(self, 'Columns', _colcols, 1, 0, _colData, self.rowsFor(_colData))

      _idxData = (
        [(idx[1], idx[0], idx[2]) for idx in self.lyrMeta['indexes']]
        if self.lyrMeta['indexes']
        else []
      )
      _idxCols: list[tuple[str, int, Anchor]] = [
        ('Column', 110, 'w'),
        ('idx_Name', 180, 'w'),
        ('Type', 50, 'w'),
      ]
      TView(self, 'Indexes', _idxCols, 1, 3, _idxData, self.rowsFor(_idxData))

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
        ('Supply Version', 110, 'w'),
        ('Type', 60, 'w'),
        ('Date', 110, 'w'),
        ('Adds', 70, 'e'),
        ('Dels', 70, 'e'),
        ('Count', 80, 'e'),
      ]
      TView(self, 'Update History', _ldCols, 3, 0, _ldData, self.rowsFor(_ldData))
    else:
      ttk.Label(self, text="No metadata held for this layer.", style='Muted.TLabel').grid(
        row=1, column=0, columnspan=4, sticky='w', pady=(10, 0)
      )

    # How wide this pane needs to be depends on the layer that was clicked, so the
    # window is given the chance to grow into it.
    self.guic.fitToContent()

  # What the data tab shows below the upload buttons. A table already registered with
  # VLRS needs no form, so it gets the local state that decides what an upload does.
  def mkUploadPane(self, lyr: LyrReg) -> None:
    _known = bool(self.lyrMeta)
    if _why := self.guic.uploadBlocked(lyr):
      _text, _style = _why, 'Warn.TLabel'
    elif _known:
      _text, _style = "Held by VLRS. Choose a supply type above.", 'Muted.TLabel'
    else:
      _text, _style = (
        "Not registered with VLRS. Describe it below, then upload FULL.",
        'Warn.TLabel',
      )
    ttk.Label(self, text=_text, style=_style).grid(
      row=1, column=0, columnspan=5, sticky='w', pady=(10, 0)
    )
    self.mkNewUplFrm(lyr, _known)

    ttk.Label(self, text='Local state', style='Head.TLabel').grid(
      row=2, column=2, columnspan=2, sticky='w', padx=(30, 0), pady=(10, 6)
    )
    _rows: list[tuple[str, str]] = [
      ('Status', f"{lyr.status}{' (in error)' if lyr.err else ''}"),
      ('Supply', f"{lyr.sup} {lyr.sup_type or ''}".strip()),
      ('Version', str(lyr.sup_ver)),
      ('Rows', str(lyr.extradata.get('row_count', 'unknown'))),
      ('Active', 'yes' if lyr.active else 'no'),
    ]
    for ii, (name, val) in enumerate(_rows):
      ttk.Label(self, text=f"{name}:", width=10, anchor='e', style='Card.TLabel').grid(
        row=3 + ii, column=2, sticky='e', padx=(30, 8), pady=2
      )
      ttk.Label(
        self, text=val, style='Err.TLabel' if name == 'Status' and lyr.err else 'Card.TLabel'
      ).grid(row=3 + ii, column=3, sticky='w', pady=2)

  # Known is a table VLRS already holds, whose answers come from the server and are
  # shown filled in rather than hidden, so the tab reads the same for either.
  # Tall enough to be worth scrolling, short enough not to leave a blank pane under
  # two rows of content.
  @staticmethod
  def rowsFor(data: list[tuple[Any, ...]]) -> int:
    return max(4, min(len(data), 10))

  def mkNewUplFrm(self, lyr: LyrReg, known: bool) -> None:
    _state = 'disabled' if known else 'readonly'
    ttk.Label(self, text='Dataset' if known else 'Register and upload', style='Head.TLabel').grid(
      row=2, column=0, columnspan=2, sticky='w', pady=(10, 6)
    )

    ttk.Label(self, text='Relation:', width=16, anchor='e', style='Card.TLabel').grid(
      row=3, column=0, sticky="e", padx=(0, 8)
    )
    self.relBox = ttk.Combobox(self, values=['table', 'view'], state=_state, width=22)
    self.relBox.set((lyr.relation or '') if known else 'table')
    self.relBox.grid(row=3, column=1, sticky="w", pady=2)

    self.mdUUID = StringVar(value=(lyr.md_uuid or '') if known else '')
    ttk.Label(self, text='GeoNetwork UUID:', width=16, anchor='e', style='Card.TLabel').grid(
      row=4, column=0, sticky='e', padx=(0, 8)
    )
    ttk.Entry(
      self,
      textvariable=self.mdUUID,
      width=40,
      state='disabled' if known else 'normal',
      cursor=textCursor(self),
    ).grid(row=4, column=1, sticky='w', pady=2)

    ttk.Label(self, text='Geometry type:', width=16, anchor='e', style='Card.TLabel').grid(
      row=5, column=0, sticky='e', padx=(0, 8)
    )
    self.gtBox = ttk.Combobox(
      self,
      state=_state,
      width=22,
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
    self.gtBox.set((lyr.geom_type or '') if known else 'polygon')
    self.gtBox.grid(row=5, column=1, sticky="w", pady=2)

    self.vdp = IntVar(value=0)
    ttk.Label(self, text='VDP:', width=16, anchor='e', style='Card.TLabel').grid(
      row=6, column=0, sticky='e', padx=(0, 8)
    )
    ttk.Checkbutton(
      self, variable=self.vdp, onvalue=1, offvalue=0, state='disabled' if known else 'normal'
    ).grid(row=6, column=1, sticky="w", pady=2)

  def mkFrUpload(self, bar: ttk.Frame, lyr: LyrReg) -> None:
    ttk.Label(bar, text='Upload', style='Card.TLabel').grid(row=0, column=0, padx=(0, 10))
    _btns = {
      sup: ttk.Button(bar, text=sup.upper(), command=lambda s=sup: self.upload(lyr, s))
      for sup in (Supplies.INC, Supplies.DIFF, Supplies.FULL)
    }
    for ii, btn in enumerate(_btns.values()):
      btn.grid(row=0, column=ii + 1, padx=(0, 6))

    if not self.lyrMeta:  # new dataset, full upload only
      _btns[Supplies.INC].configure(state="disabled")
      _btns[Supplies.DIFF].configure(state="disabled")
    if self.guic.uploadBlocked(lyr):
      [btn.configure(state="disabled") for btn in _btns.values()]

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

  def upload(self, lyr: LyrReg, upldType: str) -> None:
    if not self.guic.uploadAllowed(lyr, upldType):
      return
    if upldType == Supplies.INC:
      self.guic.status.idle("Incremental supplies are not implemented from the client.", 'Warn')
      return
    if self.guic.busy:
      self.guic.status.idle("Another job is still running.", 'Warn')
      return

    # The form is read here, on the ui thread. The worker only gets plain values.
    _new = (
      None
      if self.lyrMeta
      else {
        'relation': self.relBox.get(),
        'md_uuid': self.mdUUID.get(),
        'geomType': self.gtBox.get(),
        'vdp': bool(self.vdp.get()),
      }
    )

    self.guic.busy = True
    self.guic.status.busy(f"Uploading {lyr.identity} ...")
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
      self.guic.status.idle(f"Upload of {lyr.identity} failed: {err}", 'Err')
    else:
      self.guic.status.idle(
        f"Upload of {lyr.identity} {'succeeded' if ok else 'did not succeed'}",
        'Ok' if ok else 'Err',
      )
    self.guic.frSetup.ctrlFrm.refresh()

  def openMetaLink(self) -> None:
    if link := (self.lyrMeta or {}).get('metadata'):
      webbrowser.open_new(link)
    else:
      self.guic.status.idle("This layer has no metadata link to open.", 'Warn')

  def reseed(self, ident: str) -> None:
    _db = DB(self.guic.cfg)
    try:
      _db.fixErrs(ident)
    finally:
      _db.close()
    self.guic.status.idle(f"{ident} queued for reseeding.", 'Ok')


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

    self.colHdr = ttk.Label(owner, text=name, style='Head.TLabel')
    self.colHdr.grid(row=row, column=col, columnspan=len(colTupl) + 1, sticky='w', pady=(10, 4))
    [self.mkCol(tupl) for tupl in colTupl]
    [self.insert('', 'end', values=rowData) for rowData in data]
    self.grid(row=row + 1, column=col, columnspan=len(colTupl), sticky='nsew')

    self.scrollbar = ttk.Scrollbar(owner, orient='vertical', command=self.yview)  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]
    self.scrollbar.grid(row=row + 1, column=col + len(colTupl), sticky='ns', padx=(0, 8))
    self.configure(yscrollcommand=self.scrollbar.set)
    self.scrollbar.set(0.0, 1.0)  # a table with no rows never reports a position

  def mkCol(self, colTupl: tuple[str, int, Anchor]) -> None:
    name, wid, anc = colTupl
    self.heading(name, text=name)
    self.column(name, minwidth=0, width=wid, anchor=anc, stretch=True)


class FrSetup(ttk.Frame):
  def __init__(self, container: Misc, guic: GuiControl):
    super().__init__(container, padding=12)
    self.guic = guic

    _top = ttk.Frame(self)
    _top.grid(row=0, column=0, sticky='ew', pady=(0, 10))
    ttk.Label(_top, text='Profile:').grid(row=0, column=0, sticky="e", padx=(0, 6))
    self.profiles = self.guic.cfg.cp.sections()
    self.proBox = ttk.Combobox(_top, values=self.profiles, state='readonly', width=20)
    self.proBox.current(0)
    self.proBox.grid(row=0, column=1, sticky="w")
    self.proBox.bind("<<ComboboxSelected>>", self.profileChanged)

    ttk.Label(_top, text='API:').grid(row=0, column=2, sticky="e", padx=(20, 6))
    self.strurl = StringVar(value=self.guic.cfg.get('baseUrl'))
    ttk.Label(_top, textvariable=self.strurl).grid(row=0, column=3, sticky="w")

    self.regFrm = SubFrReg(self, self.guic)
    self.regFrm.grid(row=1, column=0, sticky='nsew', pady=(0, 10))
    self.dbFrm = SubFrDb(self, self.guic)
    self.dbFrm.grid(row=2, column=0, sticky='nsew', pady=(0, 10))
    self.ctrlFrm = SubFrCtrl(self, self.guic)
    self.ctrlFrm.grid(row=3, column=0, sticky='nsew')

    self.columnconfigure(0, weight=1)
    self.rowconfigure(3, weight=1)

  def profileChanged(self, event: Any) -> None:
    _profile = self.proBox.get()
    if _profile not in self.guic.cfg.cp.sections():
      self.profiles.append(_profile)
    self.guic.cfg.setStage(_profile)
    self.refresh()

  def test(self) -> None:
    self.regFrm.test()
    self.dbFrm.test()

  def refresh(self) -> None:
    self.strurl.set(self.guic.cfg.get('baseUrl'))
    self.regFrm.refresh()
    self.dbFrm.refresh()
    self.ctrlFrm.refresh()


class SubFr(Card):
  def __init__(self, owner: Misc, guic: GuiControl, title: str):
    super().__init__(owner, title)
    self.guic = guic
    self.entries: dict[str, ttk.Entry] = {}
    self.vars: dict[str, StringVar] = {}
    self.qaMarks: dict[str, ttk.Label] = {}
    self.columnconfigure(3, weight=1)  # pushes the checks panel to the right edge

  def lblEnt(
    self,
    var: str,
    name: str,
    val: str,
    wid: int,
    row: int,
    col: int,
    colspan: int = 1,
    private: bool = False,
  ) -> None:
    ttk.Label(self, text=f"{name}:", width=11, anchor='e', style='Card.TLabel').grid(
      row=row, column=col, sticky="e", padx=(0, 8), pady=2
    )
    _displayVal = val if not private else '' if not val else 'xxxxx-xxxxx-xxxxx'
    self.vars[var] = StringVar(value=_displayVal)
    ent = ttk.Entry(self, textvariable=self.vars[var], width=wid, cursor=textCursor(self))
    ent.grid(row=row, column=col + 1, columnspan=colspan, sticky="w", pady=2)
    self.entries[var] = ent

  QA_WIDTH = 14

  def qaRow(self, fr: Misc, var: str, desc: str, row: int) -> None:
    mark = ttk.Label(fr, text='–', width=2, anchor='center', style='Muted.TLabel')
    mark.grid(row=row, column=0, sticky='w')
    ttk.Label(fr, text=desc, width=self.QA_WIDTH, style='Card.TLabel').grid(
      row=row, column=1, sticky='w', padx=(4, 0)
    )
    self.qaMarks[var] = mark

  # None means it has not been run, which is neither a pass nor a failure.
  def setQa(self, var: str, state: bool | None) -> None:
    _look = {None: ('–', 'Muted'), True: ('\u2713', 'Ok'), False: ('\u2717', 'Err')}
    txt, sty = _look[state]
    self.qaMarks[var].configure(text=txt, style=f'{sty}.TLabel')

  # The state in words as well as in a mark, because a mark alone is a colour to
  # anyone who cannot pick it out.
  def qaSay(self, lbl: ttk.Label, passed: bool, okMsg: str, failMsg: str) -> None:
    lbl.configure(text=okMsg if passed else failMsg, style='Ok.TLabel' if passed else 'Err.TLabel')


class SubFrReg(SubFr):
  def __init__(self, owner: FrSetup, guic: GuiControl):
    super().__init__(owner, guic, 'Registration')

    qaFr = ttk.Frame(self, style='Qa.TFrame', padding=10)
    qaFr.grid(row=self.row, column=5, rowspan=4, sticky='ne', padx=(20, 0))
    self.qaRow(qaFr, 'Reg', 'Registered', 0)
    self.qaRow(qaFr, 'Val', 'Validated', 1)
    ttk.Button(qaFr, text='Refresh', command=self.test).grid(
      row=2, column=0, columnspan=2, sticky='ew', pady=(10, 0)
    )

    _valEmail = self.guic.cfg.get("email") or ""
    self.lblEnt('email', 'Email', _valEmail, 50, self.row, 0, 3)
    _valClient = self.guic.cfg.get("client_id") or ''
    self.lblEnt('clientId', 'Client ID', _valClient, 34, self.row + 1, 0, private=True)
    self.entries['clientId'].configure(state='disabled')
    _valApik = self.guic.cfg.get("api_key") or ''
    self.lblEnt('apik', 'API key', _valApik, 34, self.row + 2, 0, private=True)
    self.entries['apik'].configure(state='disabled')

    self.regMsg = ttk.Label(self, text='', style='Muted.TLabel')
    self.regMsg.grid(row=self.row + 3, column=0, columnspan=5, sticky="w", pady=(8, 0))

    self.setQa('Reg', True if self.guic.cfg.get("client_id") else None)
    self.setQa('Val', True if self.guic.cfg.get("api_key") else None)
    if self.guic.cfg.get('regComplete') == "True":
      self.qaSay(self.regMsg, True, "Registered and validated.", "")

  # Only worth doing unprompted when there is a registration to check. An incomplete
  # one is the setup flow, which posts a new registration and sends a verification
  # email, and that is the user's to start.
  def refreshRights(self) -> None:
    if self.guic.cfg.get('client_id') and self.guic.cfg.get('api_key'):
      self.test()

  def test(self) -> None:
    self.guic.cfg.set({"email": self.entries['email'].get()})
    self.regMsg.configure(text="Checking ...", style='Muted.TLabel')
    self.guic.runAsync(self.guic.qa.checkApiClient, self._testDone)

  def _testDone(self, result: tuple[int, Any] | None, err: Exception | None) -> None:
    if err or not result:
      self.qaSay(self.regMsg, False, "", f"Registration check failed: {err}")
      return
    qaCode, qaMsg = result
    if qaCode == 0:
      self.qaSay(self.regMsg, False, "", str(qaMsg))
    elif qaCode == 1:  # still need to verify the email
      self.setQa('Reg', True)
      self.setQa('Val', False)
      self.regMsg.configure(text=str(qaMsg), style='Warn.TLabel')
    elif qaCode == 2:  # verified
      self.setQa('Reg', True)
      self.setQa('Val', True)
      self.qaSay(self.regMsg, True, "Read and upload rights have been set.", "")
      self.guic.rights = qaMsg  # dict returned when success here
      self.guic.frMeta.setData()

    self.refresh()
    self.guic.frSetup.ctrlFrm.refresh()

  def refresh(self) -> None:
    self.vars['email'].set(self.guic.cfg.get("email"))
    self.vars['clientId'].set('xxxxx-xxxxx-xxxxx' if self.guic.cfg.get("client_id") else '')
    self.vars['apik'].set('xxxxx-xxxxx-xxxxx' if self.guic.cfg.get("api_key") else '')
    self.setQa('Reg', True if self.guic.cfg.get("client_id") else None)
    self.setQa('Val', True if self.guic.cfg.get("api_key") else None)


class SubFrDb(SubFr):
  def __init__(self, owner: FrSetup, guic: GuiControl):
    super().__init__(owner, guic, 'Database connection')

    qaFr = ttk.Frame(self, style='Qa.TFrame', padding=10)
    qaFr.grid(row=self.row, column=5, rowspan=6, sticky='ne', padx=(20, 0))
    for ii, (var, desc) in enumerate(
      [("Db", "Connection"), ("Clt", "PG client"), ("Spat", "PostGIS"), ("Meta", "Metadata")]
    ):
      self.qaRow(qaFr, var, desc, ii)
    ttk.Button(qaFr, text='Test database', command=self.test).grid(
      row=4, column=0, columnspan=2, sticky='ew', pady=(10, 0)
    )

    self.lblEnt('endp', 'Endpoint', self.guic.cfg.get("dbHost") or "localhost", 50, self.row, 0, 3)
    self.lblEnt('inst', 'Instance', self.guic.cfg.get("dbName") or "vicmap", 18, self.row + 1, 0)
    self.lblEnt('user', 'Username', self.guic.cfg.get("dbUser") or "vicmap", 18, self.row + 1, 2)
    self.lblEnt('port', 'Port', self.guic.cfg.get("dbPort") or '5432', 18, self.row + 2, 0)
    self.lblEnt('pswd', 'Password', self.guic.cfg.get("dbPswd") or "vicmap", 18, self.row + 2, 2)
    ttk.Label(self, text='Home folder for pg_dump and pg_restore', style='Muted.TLabel').grid(
      row=self.row + 3, column=1, columnspan=3, sticky='w', pady=(6, 0)
    )
    self.lblEnt(
      'binPath',
      'Bin path',
      self.guic.cfg.get("dbClientPath") or pgBinDefault(),
      50,
      self.row + 4,
      0,
      3,
    )

    self.dbMsg = ttk.Label(self, text='', style='Muted.TLabel')
    self.dbMsg.grid(row=self.row + 5, column=0, columnspan=5, sticky='w', pady=(8, 0))

    if self.guic.cfg.get("dbComplete") == "True":
      [self.setQa(nm, True) for nm in ('Db', 'Clt', 'Spat', 'Meta')]
      self.qaSay(self.dbMsg, True, "Database is ready.", "")

  def test(self) -> None:
    self.guic.cfg.set(
      {
        'dbHost': self.entries['endp'].get(),
        'dbPort': self.entries['port'].get(),
        'dbName': self.entries['inst'].get(),
        'dbUser': self.entries['user'].get(),
        'dbPswd': self.entries['pswd'].get(),
        'dbClientPath': self.entries['binPath'].get(),
      }
    )
    self.dbMsg.configure(text="Checking ...", style='Muted.TLabel')
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
      self.qaSay(self.dbMsg, False, "", f"Database checks failed: {err}")
    # A failed check stops the ones after it, so results is short and every box is
    # cleared first rather than leaving a tick from the previous run standing.
    _names = ['Db', 'Clt', 'Spat', 'Meta']
    _got = results or []
    # A check the run never reached is unknown, not failed.
    for ii, nm in enumerate(_names):
      self.setQa(nm, bool(_got[ii]) if ii < len(_got) else None)

    # Read from the results just computed rather than from the config flag, which is
    # written by the checks themselves and still holds the last run's answer.
    if len(results or []) == len(_names) and all(results or []):
      self.qaSay(self.dbMsg, True, "Database is ready.", "")
      self.guic.frData.setData()
    elif not err:
      _failed = [nm for ii, nm in enumerate(_names) if ii >= len(_got) or not _got[ii]]
      self.qaSay(self.dbMsg, False, "", f"Not ready. Outstanding: {', '.join(_failed)}")

    self.guic.frSetup.ctrlFrm.refresh()

  def refresh(self) -> None:
    self.vars['endp'].set(self.guic.cfg.get("dbHost") or "localhost")
    self.vars['inst'].set(self.guic.cfg.get("dbName") or "vicmap")
    self.vars['port'].set(self.guic.cfg.get("dbPort") or "5432")
    self.vars['user'].set(self.guic.cfg.get("dbUser") or "vicmap")
    self.vars['pswd'].set(self.guic.cfg.get("dbPswd") or "vicmap")
    self.vars['binPath'].set(self.guic.cfg.get("dbClientPath") or pgBinDefault())
    [self.setQa(nm, None) for nm in ('Db', 'Clt', 'Spat', 'Meta')]
    self.dbMsg.configure(text='', style='Muted.TLabel')


class SubFrCtrl(SubFr):
  def __init__(self, owner: FrSetup, guic: GuiControl):
    super().__init__(owner, guic, 'Replication')

    self.counts: dict[str, ttk.Label] = {}
    for ii, (key, name) in enumerate(
      [('dsets', 'Datasets'), ('active', 'Active'), ('errs', 'Errors')]
    ):
      ttk.Label(self, text=f"{name}:", width=11, anchor='e', style='Card.TLabel').grid(
        row=self.row + ii, column=0, sticky='e', padx=(0, 8), pady=2
      )
      lbl = ttk.Label(self, text='N/A', width=8, style='Card.TLabel')
      lbl.grid(row=self.row + ii, column=1, sticky='w', pady=2)
      self.counts[key] = lbl

    self.fixBtn = ttk.Button(self, text="Fix errors", command=self.fix)
    self.fixBtn.grid(row=self.row, column=4, rowspan=3, sticky='e', padx=(20, 12), pady=4)

    self.syncBtn = ttk.Button(self, text='SYNC', style='Accent.TButton', command=self.sync)
    self.syncBtn.grid(row=self.row, column=5, rowspan=3, sticky='e', padx=(0, 8), pady=4)
    self.syncBtn.configure(state="disabled")

    self.refresh()

  def refresh(self) -> None:
    # Getting metadata depends on cfg.regComplete, so this covers both.
    if self.guic.cfg.get("dbComplete") == "True":
      _db = DB(self.guic.cfg)
      try:
        _dsets = _db.getRecSet(LyrReg)
      finally:
        _db.close()
      _errs = len([d for d in _dsets if d.err])
      self.counts['dsets'].configure(text=str(len(_dsets)))
      self.counts['active'].configure(text=str(len([d for d in _dsets if d.active])))
      self.counts['errs'].configure(text=str(_errs), style='Err.TLabel' if _errs else 'Card.TLabel')
      self.syncBtn.configure(state='normal')
    else:
      [lbl.configure(text="N/A", style='Card.TLabel') for lbl in self.counts.values()]
      self.syncBtn.configure(state='disabled')

  def fix(self) -> None:
    _db = DB(self.guic.cfg)
    try:
      _db.fixErrs()
    finally:
      _db.close()
    self.guic.status.idle("Error datasets queued for reseeding.", 'Ok')
    self.refresh()

  def sync(self) -> None:
    if self.guic.busy:
      self.guic.status.idle("Another job is still running.", 'Warn')
      return
    self.guic.busy = True
    self.syncBtn.configure(state="disabled", text="SYNCING")
    self.guic.status.busy("Syncing ...")
    self.guic.runAsync(self._runSync, self._syncDone)

  # Off the ui thread, so it opens its own connection and touches no widget.
  def _runSync(self) -> None:
    _db = DB(self.guic.cfg)
    try:
      synccer = Synccer(self.guic.cfg, _db)
      synccer.unWait()  # queue any leftover jobs from last time
      while synccer.assess():
        synccer.run()
    finally:
      _db.close()

  def _syncDone(self, _result: Any, err: Exception | None) -> None:
    self.guic.busy = False
    self.syncBtn.configure(text="SYNC")
    self.guic.status.idle(
      f"Sync failed: {err}" if err else "Sync complete.", 'Err' if err else 'Ok'
    )
    self.refresh()  # puts the button back to enabled


if __name__ == '__main__':
  logging.basicConfig(level=logging.INFO)
  GuiControl('default').mainloop()
