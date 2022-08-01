import sys
import traceback
from functools import partial
from threading import Thread

import wx
from pubsub import pub

from . import operations, process_files
from .model import File, Status
from .operations import msg


class CustomDropTarget(wx.FileDropTarget):
    def __init__(self, callbacks):
        super().__init__()
        self.callbacks = callbacks
        self.enable()

    def OnDropFiles(self, x, y, files):
        if self.enabled:
            self.callbacks.DropCallbackFiles(files)
        return self.enabled

    def OnEnter(self, *args):
        if self.enabled:
            self.callbacks.DropCallbackEnter()
        return super().OnEnter(*args)

    def OnLeave(self, *args):
        if self.enabled:
            self.callbacks.DropCallbackLeave()
        return super().OnLeave(*args)

    def disable(self):
        self.enabled = False
        self.DefaultAction = wx.DragResult.DragError

    def enable(self):
        self.enabled = True
        self.DefaultAction = wx.DragResult.DragCopy


class CustomThread(Thread):
    def __init__(self, *args):
        super().__init__(daemon=True)
        self.args = args
        self.start()

    def run(self, *args):
        try:
            self._run(*args)
        except Exception:
            msg(
                "fatalError",
                e=traceback.format_exception(*sys.exc_info()),
                ctx=(self.__class__.__name__, self.args),
            )
            raise


class DiscoverThread(CustomThread):
    def _run(self):
        (iterator,) = self.args
        for file, outfile in iterator:
            msg("discoverFile", file=file, outfile=outfile)
        msg("discoverDone")


class LoadSessionThread(CustomThread):
    def _run(self):
        msg("sessionLoaded", session=operations.load_session())


class MainFrame(wx.Frame):
    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)

        self.count = 0
        self.files = []
        self.files_seen = set()
        self.task_queue = []
        self.dialog = None
        self.session = None

        self.DropTarget = CustomDropTarget(self)
        self.makeMenuBar()
        self.CreateStatusBar()
        self.update_status()

        self.sizer = wx.BoxSizer(wx.VERTICAL)
        self.makePanel()
        self.makeDragPanel()
        self.DropCallbackLeave()
        self.SetSizerAndFit(self.sizer)

        self.update_files()
        self.done_iterator()

        pub.subscribe(self.discoverFile, "discoverFile")
        pub.subscribe(self.done_iterator, "discoverDone")
        pub.subscribe(self.fatalError, "fatalError")
        pub.subscribe(self.update_files, "update_files")
        pub.subscribe(self.sessionLoaded, "sessionLoaded")

        self.Bind(wx.EVT_CHAR_HOOK, self.OnKeyUP)

        wx.CallAfter(LoadSessionThread)

    def makePanel(self):
        self.pnl = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)

        btn_files = wx.Button(self.pnl, label="Open Files")
        btn_dirs = wx.Button(self.pnl, label="Open Folder")
        self.Bind(wx.EVT_BUTTON, self.OnBtnFiles, btn_files)
        self.Bind(wx.EVT_BUTTON, self.OnBtnDirs, btn_dirs)

        sizer2 = wx.BoxSizer(wx.HORIZONTAL)
        sizer2.Add(btn_files, wx.SizerFlags().Border(wx.ALL, 15))
        sizer2.Add(btn_dirs, wx.SizerFlags().Border(wx.ALL, 15))
        sizer.Add(sizer2, 0)

        st = wx.StaticText(self.pnl, label="Drag and drop files and folders here")
        sizer.Add(st, 0, wx.ALL, 15)

        self.queue = wx.ListCtrl(self.pnl, style=wx.LC_REPORT | wx.LC_VIRTUAL)
        self.queue.AppendColumn("File", width=300)
        self.queue.AppendColumn("Output", width=150)
        self.queue.AppendColumn("Status", width=70)
        self.queue.OnGetItemText = self.getItemText
        self.queue.SetItemCount(10)
        sizer.Add(self.queue, 1, wx.EXPAND | wx.ALL, 20)

        self.pnl.Sizer = sizer
        self.sizer.Add(self.pnl, 1, wx.EXPAND)

    def getItemText(self, item, column):
        if item > len(self.files):
            return ""

        item = self.files[item]
        return str((item.file, item.outfile, item.status.name)[column])

    def fatalError(self, e, ctx):
        wx.MessageBox(
            f"Fatal Error\n\n{ctx}\n\n" + "".join(e),
            "Fatal Error",
            wx.OK | wx.ICON_ERROR,
        )
        self.OnExit()

    def update_files(self):
        self.files.sort(key=lambda x: (x.status.value, x.file))
        self.queue.SetItemCount(len(self.files))
        if self.files:
            self.queue.RefreshItems(0, len(self.files) - 1)
        self.update_status()

    def update_status(self):
        if self.dialog:
            text = "Discovering files..."
        elif not self.session:
            text = "Loading model..."
        elif any(file.status not in {Status.Done, Status.Error} for file in self.files):
            text = "Processing files..."
        else:
            text = "Idle"

        self.SetStatusText(text)

    def makeDragPanel(self):
        self.drag_pnl = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)

        sizer.AddStretchSpacer()
        st = wx.StaticText(
            self.drag_pnl,
            label="Accepting dragged files",
            style=wx.ALIGN_CENTER_HORIZONTAL,
        )
        sizer.Add(st, 0, wx.ALIGN_CENTER)
        sizer.AddStretchSpacer()

        self.drag_pnl.Sizer = sizer
        self.sizer.Add(self.drag_pnl, 1, wx.EXPAND)

    def makeMenuBar(self):
        fileMenu = wx.Menu()

        openFileItem = fileMenu.Append(-1, "&Open File...\tCtrl-O")
        self.Bind(wx.EVT_MENU, self.OnBtnFiles, openFileItem)

        openFileItem = fileMenu.Append(-1, "Open Fol&der...\tCtrl-D")
        self.Bind(wx.EVT_MENU, self.OnBtnDirs, openFileItem)

        fileMenu.AppendSeparator()

        exitItem = fileMenu.Append(wx.ID_EXIT)
        self.Bind(wx.EVT_MENU, self.OnExit, exitItem)

        menuBar = wx.MenuBar()
        menuBar.Append(fileMenu, "&File")

        self.MenuBar = menuBar

    def OnExit(self, *args):
        self.Close(True)

    def OnBtnFiles(self, event):
        with wx.FileDialog(
            self,
            message="Select files",
            style=wx.FD_OPEN | wx.FD_MULTIPLE | wx.FD_FILE_MUST_EXIST,
            wildcard="Image files (*.jpg,*.png)|*.jpg;*.jpeg;*.png|All files|*",
        ) as dialog:
            if dialog.ShowModal() == wx.ID_CANCEL:
                return
            self.process_iterator(process_files.open_files(dialog.Paths))

    def OnBtnDirs(self, event):
        with wx.DirDialog(
            self,
            message="Select folder",
        ) as dialog:
            if dialog.ShowModal() == wx.ID_CANCEL:
                return
            self.process_iterator(process_files.open_folder(dialog.Path))

    def DropCallbackFiles(self, files):
        self.DropCallbackLeave()
        self.process_iterator(process_files.open_mixed(files))

    def process_iterator(self, iterator):
        if self.dialog:
            print("cannot process files while busy")
            return

        self.DropTarget.disable()
        self.dialog = wx.ProgressDialog("Busy", "Discovering files")
        self.dialog.Pulse()
        self.update_status()

        wx.CallAfter(DiscoverThread, iterator)

    def done_iterator(self):
        self.DropTarget.enable()

        if self.dialog:
            self.dialog.Destroy()

        self.dialog = None
        self.update_status()

    def sessionLoaded(self, session):
        assert session
        self.session = session
        self.update_status()
        wx.CallAfter(self.check_task_queue)

    def discoverFile(self, file, outfile):
        if file in self.files_seen:
            return

        self.files_seen.add(file)

        file = File(file=file, outfile=outfile, status=Status.Pending)
        self.files.append(file)
        self.update_files()

        self.task_queue.append(file)
        wx.CallAfter(self.check_task_queue)

    def check_task_queue(self):
        if self.session is None:
            return

        for file in self.task_queue:
            operations.queue_file(self.session, file)
        self.task_queue.clear()

    def DropCallbackEnter(self):
        self.pnl.Hide()
        self.drag_pnl.Show()
        self.sizer.Layout()

    def DropCallbackLeave(self):
        self.pnl.Show()
        self.drag_pnl.Hide()
        self.sizer.Layout()

    def OnKeyUP(self, event):
        keyCode = event.GetKeyCode()
        if keyCode == wx.WXK_ESCAPE:
            self.OnExit()
        event.Skip()


def main():
    app = wx.App()
    frm = MainFrame(None, title="Background Remover")
    frm.Show()
    app.MainLoop()
