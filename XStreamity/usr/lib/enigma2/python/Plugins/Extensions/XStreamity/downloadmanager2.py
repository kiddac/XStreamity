#!/usr/bin/python
# -*- coding: utf-8 -*-

from . import _
from .plugin import skin_path, downloads_json, cfg, pythonVer
from .xStaticText import StaticText

from Components.ActionMap import ActionMap
from Components.Sources.List import List
from Screens.MessageBox import MessageBox
from Screens.Screen import Screen
from enigma import eTimer

from twisted.web.client import downloadPage

try:
    from urlparse import urlparse
except:
    from urllib.parse import urlparse

import json
import math
import os
import re
import requests
import sys
import time


# https twisted client hack #
try:
    from twisted.internet import ssl
    from twisted.internet._sslverify import ClientTLSOptions
    sslverify = True
except:
    sslverify = False

if sslverify:
    class SNIFactory(ssl.ClientContextFactory):
        def __init__(self, hostname=None):
            self.hostname = hostname

        def getContext(self):
            ctx = self._contextFactory(self.method)
            if self.hostname:
                ClientTLSOptions(self.hostname, ctx)
            return ctx


def convert_size(size_bytes):
    if size_bytes == 0:
        return "0B"
    size_name = ("B", "KB", "MB", "GB", "TB")
    i = int(math.floor(math.log(size_bytes, 1024)))
    p = math.pow(1024, i)
    s = round(size_bytes / p, 2)
    return "%s %s" % (s, size_name[i])


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
        self.downloadfile = None

        self.timerDisplay = eTimer()

        self["downloadlist"] = List(self.drawList)
        self['downloadlist'].onSelectionChanged.append(self.selectionChanged)

        self["key_red"] = StaticText(_('Back'))
        self["key_green"] = StaticText(_('Download'))
        self['key_blue'] = StaticText(_('Delete'))

        self["diskspace"] = StaticText()

        self['actions'] = ActionMap(['XStreamityActions'], {
            'red': self.keyCancel,
            'cancel': self.keyCancel,
            'green': self.download,
            'ok': self.download,
            'blue': self.delete,
        }, -2)

        self.onFirstExecBegin.append(self.start)
        self.onLayoutFinish.append(self.__layoutFinished)

    def __layoutFinished(self):
        self.setTitle(self.setup_title)

    def start(self):
        self.readJsonFile()
        self.diskspace()
        self.getDownloadSize()
        self.checkactivedownloads()
        self.buildList()
        self.saveJson()

        try:
            self.timerDisplay.callback.append(self.updatescreen)
        except:
            self.timerDisplay_conn = self.timerDisplay.timeout.connect(self.updatescreen)

        self.timerDisplay.start(3000, False)

    def readJsonFile(self):
        if os.path.isfile(downloads_json):
            with open(downloads_json, "r") as f:
                try:
                    self.downloads_all = json.load(f)
                except:
                    pass

    def diskspace(self):
        try:
            stat = os.statvfs(cfg.downloadlocation.value)
            free = convert_size(float(stat.f_bfree * stat.f_bsize))
            total = convert_size(float(stat.f_blocks * stat.f_bsize))
        except:
            free = "-?-"
            total = "-?-"

        self["diskspace"].setText(_('Free Space:') + " " + str(free) + " " + _("of") + " " + str(total))

    def getDownloadSize(self):
        x = 0
        for video in self.downloads_all:
            url = video[2]
            length = video[5]
            if length == 0:
                r = requests.get(url, timeout=10, verify=False, stream=True).headers['Content-length']
                video[5] = float(r)
                x += 1
                if x == 3:
                    x = 0
                    time.sleep(1)
        self.saveJson()

    def checkactivedownloads(self):
        self.downloading = False
        x = 0
        for video in self.downloads_all:
            if video[3] == _("Downloading"):
                self.downloading = True

                try:
                    self.extension = str(os.path.splitext(video[2])[-1])
                except:
                    self.extension = ""

                self.filmtitle = video[1]

                cleanName = re.sub(r'[\<\>\:\"\/\\\|\?\*]', ' ', str(self.filmtitle))
                cleanName = re.sub(r'  ', ' ', cleanName)

                filename = str(cleanName) + str(self.extension)

                self.path = str(cfg.downloadlocation.getValue()) + str(filename)
                self.downloadingindex = x

                totalbytes = self.downloads_all[self.downloadingindex][5]
                recbytes = os.path.getsize(self.path)
                if totalbytes == recbytes:
                    self.downloads_all[self.downloadingindex][3] = _("Finished")
                    self.downloads_all[self.downloadingindex][4] = 100
                    self.downloading = False
                break

            x += 1

    def buildList(self):
        self.drawList = []
        self.drawList = [self.buildListEntry(x[0], x[1], x[2], x[3], x[4], x[5]) for x in self.downloads_all]
        self["downloadlist"].setList(self.drawList)

    def updatescreen(self):
        if self.downloading:
            self.diskspace()
            self.getprogress()

    def getprogress(self):
        if os.path.exists(self.path):
            totalbytes = self.downloads_all[self.downloadingindex][5]
            recbytes = os.path.getsize(self.path)
            self.progress = int(100 * (float(recbytes) / totalbytes))
            self.downloads_all[self.downloadingindex][4] = self.progress
            self.buildList()

    def saveJson(self):
        with open(downloads_json, 'w') as f:
            json.dump(self.downloads_all, f)

    def selectionChanged(self):
        if self["downloadlist"].getCurrent():
            currentindex = self["downloadlist"].getIndex()

            if self.downloads_all[currentindex][3] != _("Not Started"):
                self["key_green"].setText(_('Cancel'))
            else:
                self["key_green"].setText(_('Download'))

    def keyCancel(self, answer=None):
        self.saveJson()
        self.close()

    def cancelDownload(self, answer=None):
        if answer is None:
            self.session.openWithCallback(self.cancelDownload, MessageBox, _('Cancel this download?'))
        elif answer:
            self.download_cancelled()
        else:
            return

    def delete(self):
        if self["downloadlist"].getCurrent():
            currentindex = self["downloadlist"].getIndex()

            if self.downloads_all[currentindex][3] == _("Downloading"):
                self.download_cancelled()

            del self.downloads_all[currentindex]
            self.saveJson()

    def download_cancelled(self, data=None):
        self.progress = 0
        if self.downloading:
            if self.downloadfile:
                try:
                    self.downloadfile = None
                except Exception as e:
                    print(e)

        try:
            os.remove(self.path)
        except:
            pass

        self.downloads_all[self.downloadingindex][3] = _("Not Started")
        self.downloads_all[self.downloadingindex][4] = 0
        self.downloading = False
        self.saveJson()
        self.buildList()

    def download(self):
        if self["downloadlist"].getCurrent():
            self.url = self["downloadlist"].getCurrent()[2]

            currentindex = self["downloadlist"].getIndex()

            if self.downloads_all[currentindex][3] == _("Finished"):
                self.session.open(MessageBox, _('File already downloaded.'), type=MessageBox.TYPE_INFO)
                return

            parsed_uri = urlparse(self.url)
            video_domain = parsed_uri.hostname

            if self.session.nav.getCurrentlyPlayingServiceReference():
                playingstream = self.session.nav.getCurrentlyPlayingServiceReference().toString()

                if str(video_domain) in playingstream:
                    # stop iptv
                    if self.session.nav.getCurrentlyPlayingServiceReference():
                        self.session.nav.stopService()

            if self.downloading is False:
                if self.downloads_all[currentindex][3] == _("Not Started"):
                    self.downloads_all[currentindex][3] = _("Downloading")
                    self.downloads_all[currentindex][4] = 0

                    self.downloadingindex = currentindex

                    self.progress = 0
                    self.downloading = True

                    try:
                        self.extension = str(os.path.splitext(self.url)[-1])
                    except:
                        self.extension = ""

                    self.filmtitle = self["downloadlist"].getCurrent()[1]

                    cleanName = re.sub(r'[\<\>\:\"\/\\\|\?\*]', ' ', str(self.filmtitle))
                    cleanName = re.sub(r'  ', ' ', cleanName)
                    filename = str(cleanName) + str(self.extension)
                    self.path = str(cfg.downloadlocation.getValue()) + str(filename)

                    self.buildList()

                    try:
                        parsed = urlparse(self.url)
                        domain = parsed.hostname
                        scheme = parsed.scheme

                        if pythonVer == 3:
                            self.url = self.url.encode()

                        if scheme == "https" and sslverify:
                            sniFactory = SNIFactory(domain)
                            self.downloadfile = downloadPage(self.url, self.path, sniFactory)
                            self.downloadfile.addCallback(self.download_finished)
                            self.downloadfile.addErrback(self.download_failed)
                        else:
                            self.downloadfile = downloadPage(self.url, self.path)
                            self.downloadfile.addCallback(self.download_finished)
                            self.downloadfile.addErrback(self.download_failed)
                    except Exception as e:
                        self.downloading = False
                        print(e)

            elif self.downloading is True:
                if self.downloads_all[currentindex][3] == _("Downloading"):
                    self.cancelDownload()
                elif self.downloads_all[currentindex][3] == _("Not Started"):
                    self.session.open(MessageBox, _('Multiple downloads not allowed. Please wait or cancel download.'), type=MessageBox.TYPE_INFO)
                    return

    def download_failed(self, data=None):
        self.downloading = False
        if "400 Bad Request" not in str(data):
            self.session.openWithCallback(self.download_failed_error, MessageBox, _('Download Failed!\n') + str(data), MessageBox.TYPE_WARNING, timeout=5)

    def download_failed_error(self, data=None):
        print("**** download_failed_error %s" % data)
        self.download_cancelled()

    def download_finished(self, string=""):
        self.downloads_all[self.downloadingindex][3] = _("Finished")
        self.downloads_all[self.downloadingindex][4] = 100
        self.downloading = False
        self.saveJson()
        self.buildList()

    def buildListEntry(self, dtype, title, url, state, progress, length):
        progresspercent = str(progress) + "%"
        length = convert_size(length)
        return(str(dtype), str(title), str(url), str(state), int(progress), str(progresspercent), str(length))
