#!/usr/bin/python
# -*- coding: utf-8 -*-

# for localized messages
from . import _
from .downloader import downloadWithProgress
from .plugin import skin_path, json_downloadfile, cfg
from .xStaticText import StaticText

from Components.ActionMap import ActionMap
from Components.Sources.List import List
from Screens.MessageBox import MessageBox
from Screens.Screen import Screen
from enigma import eTimer

import json
import os
import re
import sys


class XStreamity_DownloadManager(Screen):

    def __init__(self, session):
        Screen.__init__(self, session)

        self.session = session
        skin = skin_path + 'downloadmanager.xml'

        with open(skin, 'r') as f:
            self.skin = f.read()

        self.setup_title = (_('VOD Download Manager'))
        self.onChangedEntry = []

        self.list = []
        self.drawList = []
        self.downloading = False
        self.firstrun = True

        self.progress = 0
        self.downloading = False
        self.error = ""
        self.downloadfile = None

        self.timerDisplay = eTimer()
        self.timerDisplay.start(3000, False)

        self["downloadlist"] = List(self.drawList)
        self['downloadlist'].onSelectionChanged.append(self.selectionChanged)

        self["key_red"] = StaticText(_('Back'))
        self["key_green"] = StaticText(_('Download'))
        self['key_yellow'] = StaticText(_('Download All'))
        self['key_blue'] = StaticText(_('Delete'))

        self["diskspace"] = StaticText()

        self['actions'] = ActionMap(['XStreamityActions'], {
            'red': self.keyCancel,
            'cancel': self.keyCancel,
            'green': self.download,
            'ok': self.download,
            'blue': self.delete,
            'yellow': self.downloadall
        }, -2)

        self.onFirstExecBegin.append(self.start)
        self.onLayoutFinish.append(self.__layoutFinished)

    def __layoutFinished(self):
        self.setTitle(self.setup_title)

    def start(self):
        self.readJsonFile()
        self.resetlist()
        self.diskspace()

    def readJsonFile(self):
        if os.path.isfile(json_downloadfile):
            with open(json_downloadfile, "r") as f:
                try:
                    self.downloads_all = json.load(f)
                except:
                    pass

    def resetlist(self):
        self.download_stopped()
        for item in self.downloads_all:
            item[3] = _("Not Started")
            item[4] = 0

        self['key_yellow'].setText(_('Download All'))
        self.saveJson()
        self.readJsonFile()
        self.updateList()

    def saveJson(self):
        with open(json_downloadfile, 'w') as f:
            json.dump(self.downloads_all, f)

    def updateList(self):
        if not self.downloads_all:
            self.saveJson()
            self.close()
        self.drawList = []
        self.drawList = [self.buildListEntry(x[0], x[1], x[2], x[3], x[4]) for x in self.downloads_all]
        self["downloadlist"].setList(self.drawList)

    def diskspace(self):
        stat = os.statvfs(cfg.downloadlocation.value)
        free = stat.f_bfree * stat.f_bsize
        total = stat.f_blocks * stat.f_bsize

        try:
            stat = os.statvfs(cfg.downloadlocation.value)
            free = stat.f_bfree * stat.f_bsize
            total = (stat.f_blocks * stat.f_bsize) >> 30
            if free < 10000000:
                free = "%d kB" % (free >> 10)
            else:
                free = "%d GB (%d MB)" % (free >> 30, free >> 20)
        except:
            free = "-?-"
            total = "-?-"

        self["diskspace"].setText(_('Free Space:') + " " + str(free) + " " + _("of") + " " + str(total) + " " + _("GB"))

    def selectionChanged(self):
        if self["downloadlist"].getCurrent():
            currentindex = self["downloadlist"].getIndex()

            if self.downloads_all[currentindex][3] != _("Not Started"):
                self["key_green"].setText(_('Cancel'))
            else:
                self["key_green"].setText(_('Download'))

    def keyCancel(self, answer=None):
        if self.downloading:
            if answer is None:
                self.session.openWithCallback(self.keyCancel, MessageBox, _('Cancel all downloads and exit?'))
            elif answer:
                self.download_stopped()
                self.resetlist()
                self.downloading = False
                self.close()
            else:
                return
        else:
            self.resetlist()
            self.close()

    def delete(self):
        if self["downloadlist"].getCurrent():
            currentindex = self["downloadlist"].getIndex()

            if self.downloads_all[currentindex][3] == _("Downloading"):
                self.download_stopped()

            del self.downloads_all[currentindex]
            self.saveJson()
            self.readJsonFile()
            self.updateList()

            self.timerNext = eTimer()
            try:
                self.timerNext.callback.append(self.nextDownload)
            except:
                self.timerNext_conn = self.timerNext.timeout.connect(self.nextDownload)
            self.timerNext.start(300, True)

    def downloadall(self):
        if self["downloadlist"].getCurrent():
            if self["key_yellow"].getText() == _("Download All"):
                self["downloadlist"].setIndex(0)
                for item in self.downloads_all:
                    if item[3] == _("Downloading"):
                        self["downloadlist"].setIndex(self.downloadingindex)
                    else:
                        item[3] = _("Waiting...")
                self.updateList()
                self["key_yellow"].setText(_('Reset All'))

                self.timerDownload = eTimer()
                try:
                    self.timerDownload.callback.append(self.download)
                except:
                    self.timerDownload_conn = self.timerDownload.timeout.connect(self.download)
                self.timerDownload.start(300, True)
            else:
                self.resetlist()

    def download(self):
        if self["downloadlist"].getCurrent():
            callingfunction = sys._getframe().f_back.f_code.co_name

            if self.downloading is False:
                self.progress = 0
                self.error = ""
                self.downloading = True
                self.last_recvbytes = 0
                self.lastprogress = 0

                self.url = self["downloadlist"].getCurrent()[2]
                try:
                    self.extension = str(os.path.splitext(self.url)[-1])
                except:
                    self.extension = ""
                self.filmtitle = self["downloadlist"].getCurrent()[1]

                cleanName = re.sub(r'[\<\>\:\"\/\\\|\?\*]', ' ', str(self.filmtitle))
                cleanName = re.sub(r'  ', ' ', cleanName)
                filename = str(cleanName) + str(self.extension)

                self.downloadingindex = self["downloadlist"].getIndex()
                self.downloads_all[self.downloadingindex][3] = _("Downloading")
                self.downloads_all[self.downloadingindex][4] = 0

                self.updateList()

                self.path = str(cfg.downloadlocation.getValue()) + str(filename)

                self.downloadfile = downloadWithProgress(self.url, self.path)
                self.downloadfile.addProgress(self.download_progress)
                self.downloadfile.start().addCallback(self.download_finished).addErrback(self.download_failed)
            else:

                currentindex = self["downloadlist"].getIndex()
                if self["downloadlist"].getCurrent()[3] == _("Not Started"):
                    self.downloads_all[currentindex][3] = _("Waiting...")
                    self.downloads_all[currentindex][4] = 0
                    self.updateList()

                elif self["downloadlist"].getCurrent()[3] == _("Downloading") and callingfunction != "poll":
                    self.cancelDownload()

                elif self["downloadlist"].getCurrent()[3] == _("Waiting..."):
                    self.downloads_all[currentindex][3] = _("Not Started")
                    self.downloads_all[currentindex][4] = 0
                    self.updateList()

    def download_progress(self, recvbytes, totalbytes):
        self.progress = int(100 * (float(recvbytes) / totalbytes))

        try:
            self.timerDisplay.callback.append(self.updateDisplay)
        except:
            self.timerDisplay_conn = self.timerDisplay.timeout.connect(self.updateDisplay)

    def updateDisplay(self):
        if self.progress > self.lastprogress:
            self.downloads_all[self.downloadingindex][4] = self.progress
            self.updateList()
            self.lastprogress = self.progress
            self.diskspace()

    def download_failed(self, failure_instance=None):
        self.downloading = False
        # delete current download from movie location
        if "400 Bad Request" not in str(failure_instance):
            self.session.openWithCallback(self.download_failed_error, MessageBox, _('Download Failed!\n') + str(failure_instance), MessageBox.TYPE_WARNING, timeout=5)

    def download_failed_error(self, data=None):
        self.download_stopped()
        self.timerNext = eTimer()
        try:
            self.timerNext.callback.append(self.nextDownload)
        except:
            self.timerNext_conn = self.timerNext.timeout.connect(self.nextDownload)
        self.timerNext.start(300, True)

    def download_finished(self, string=""):
        self.progress = 0
        self.downloading = False
        self.error = ""
        self.downloadfile.stop()
        del self.downloads_all[self.downloadingindex]
        self.saveJson()
        self.readJsonFile()
        self.updateList()

        self.timerNext = eTimer()
        try:
            self.timerNext.callback.append(self.nextDownload)
        except:
            self.timerNext_conn = self.timerNext.timeout.connect(self.nextDownload)
        self.timerNext.start(300, True)

    def download_stopped(self, data=None):
        if self["downloadlist"].getCurrent():
            self.progress = 0
            self.error = ""

            if self.downloading:
                if self.downloadfile:
                    self.downloadfile.stop()
                    self.downloadfile = None

                    try:
                        os.remove(self.path)
                    except:
                        pass
                self.downloads_all[self.downloadingindex][3] = _("Not Started")
                self.downloads_all[self.downloadingindex][4] = 0

                self.downloading = False

            self.updateList()

    def cancelDownload(self, answer=None):
        if answer is None:
            self.session.openWithCallback(self.cancelDownload, MessageBox, _('Cancel this download?'))
        elif answer:

            self.download_stopped()

            self.timerNext = eTimer()
            try:
                self.timerNext.callback.append(self.nextDownload)
            except:
                self.timerNext_conn = self.timerNext.timeout.connect(self.nextDownload)
            self.timerNext.start(300, True)
        else:
            return

    def buildListEntry(self, dtype, title, url, state, progress):
        progresspercent = str(progress) + "%"
        return(str(dtype), str(title), str(url), str(state), int(progress), str(progresspercent))

    def nextDownload(self):
        nextindex = 0
        waiting = False
        for item in self.downloads_all:
            if item[3] == _("Waiting..."):
                item[3] = _("Not Started")
                item[4] = 0
                self.updateList()
                waiting = True
                break

            nextindex += 1

        if waiting:
            self["downloadlist"].setIndex(nextindex)

            self.timerDownload = eTimer()
            try:
                self.timerDownload.callback.append(self.download)
            except:
                self.timerDownload_conn = self.timerDownload.timeout.connect(self.download)
            self.timerDownload.start(300, True)
