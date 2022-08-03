import sys
import traceback
from copy import copy
from functools import partial

import wx
import wx.lib.sized_controls
from pubsub import pub

from . import operations, process_files
from .model import *
from .operations import msg

try:
    from os import startfile
except ImportError:

    def startfile(*args, **kwargs):
        pass


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


class MainFrame(wx.Frame):
    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)

        self.count = 0
        self.files = []
        self.files_seen = set()
        self.task_queue = []
        self.discover_threads = 0
        self.settings = Settings()

        self.session = operations.new_session()
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
        pub.subscribe(self.model_sessions_loaded, "model_sessions_loaded")

        self.Bind(wx.EVT_CHAR_HOOK, self.OnKeyUP)

        wx.CallAfter(operations.load_model_sessions)

    def makePanel(self):
        self.pnl = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)

        flags = wx.UP | wx.LEFT
        border = 15
        sizer_flags = wx.SizerFlags().Border(flags, border)

        sizer2 = wx.BoxSizer(wx.HORIZONTAL)

        btn = wx.Button(self.pnl, label="Open Files")
        self.Bind(wx.EVT_BUTTON, self.OnBtnFiles, btn)
        sizer2.Add(btn, sizer_flags)

        btn = wx.Button(self.pnl, label="Open Folder")
        self.Bind(wx.EVT_BUTTON, self.OnBtnDirs, btn)
        sizer2.Add(btn, sizer_flags)

        sizer.Add(sizer2, 0)
        sizer2 = wx.BoxSizer(wx.HORIZONTAL)

        btn = wx.Button(self.pnl, label="Set Model")
        self.Bind(wx.EVT_BUTTON, self.OnBtnSetModel, btn)
        sizer2.Add(btn, sizer_flags)

        btn = wx.Button(self.pnl, label="Set Background")
        self.Bind(wx.EVT_BUTTON, self.OnBtnSetBackground, btn)
        sizer2.Add(btn, sizer_flags)

        btn = wx.Button(self.pnl, label="Clear Completed")
        self.Bind(wx.EVT_BUTTON, self.OnBtnClear, btn)
        sizer2.Add(btn, sizer_flags)

        sizer.Add(sizer2, 0)

        st = wx.StaticText(self.pnl, label="Drag and drop files and folders here")
        sizer.Add(st, sizer_flags)

        self.queue = wx.ListCtrl(self.pnl, style=wx.LC_REPORT | wx.LC_VIRTUAL)
        self.queue.AppendColumn("File", width=300)
        self.queue.AppendColumn("Output", width=150)
        self.queue.AppendColumn("Status", width=70)
        self.queue.OnGetItemText = self.getItemText
        self.queue.SetItemCount(10)
        self.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self.itemClicked, self.queue)
        sizer.Add(self.queue, 1, wx.EXPAND | wx.RIGHT | flags, border)

        self.pnl.Sizer = sizer
        self.sizer.Add(self.pnl, 1, wx.EXPAND)

    def getItemText(self, item, column):
        if item > len(self.files):
            return ""

        item = self.files[item]
        return str((item.file, item.outfile, item.status.name)[column])

    def itemClicked(self, event):
        try:
            file = self.files[event.Index]
        except IndexError:
            return

        if file.status == Status.Done:
            startfile(file.outfile.parent)

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
        if self.discover_threads > 0:
            text = "Discovering files..."
        elif not self.session.model_sessions:
            text = "Loading models..."
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

        fileMenu.Append(-1, "Version: 2").Enabled = False
        fileMenu.AppendSeparator()

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

    def OnBtnSetModel(self, event):
        with wx.SingleChoiceDialog(self, "", "Select model", ModelTypeList) as dialog:
            dialog.SetSelection(ModelTypeList.index(self.settings.model.name))
            if dialog.ShowModal() == wx.ID_CANCEL:
                return
            self.settings.model = ModelType[ModelTypeList[dialog.GetSelection()]]

    def OnBtnSetBackground(self, event):
        with wx.SingleChoiceDialog(
            self, "", "Select background", BGColorList
        ) as dialog:
            dialog.SetSelection(BGColorList.index(self.settings.bgcolor.name))
            if dialog.ShowModal() == wx.ID_CANCEL:
                return
            self.settings.bgcolor = BGColor[BGColorList[dialog.GetSelection()]]

    def OnBtnClear(self, event):
        to_keep = []
        for file in self.files:
            if file.status == Status.Done:
                self.files_seen.discard(file.file)
            else:
                to_keep.append(file)

        self.files = to_keep
        self.update_files()

    def DropCallbackFiles(self, files):
        self.DropCallbackLeave()
        self.process_iterator(process_files.open_mixed(files))

    def process_iterator(self, iterator):
        self.discover_threads += 1
        self.update_status()

        wx.CallAfter(operations.queue_discover, self.session, iterator)

    def done_iterator(self):
        self.discover_threads -= 1

        self.update_status()

    def model_sessions_loaded(self, model_sessions):
        assert model_sessions
        self.session.model_sessions = model_sessions
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
        if self.session.model_sessions is None:
            return

        for file in self.task_queue:
            operations.queue_file(self.session, file, self.settings)
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
