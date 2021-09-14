#!/usr/bin/python
# -*- coding: utf-8 -*-

from . import _
from . import xstreamity_globals as glob
from . import processfiles as xfiles
from .plugin import skin_path, common_path, version, downloads_json
from .xStaticText import StaticText

from Components.ActionMap import ActionMap
from Components.Sources.List import List
from enigma import eServiceReference
from os import system, chmod
from Screens.Console import Console
from Screens.Screen import Screen
from Screens.MessageBox import MessageBox
from Tools.LoadPixmap import LoadPixmap

import json
import os
import sys

try:
    pythonVer = sys.version_info.major
except:
    pythonVer = 2


class XStreamity_MainMenu(Screen):

    def __init__(self, session):
        Screen.__init__(self, session)
        self.session = session

        skin = skin_path + 'mainmenu.xml'
        with open(skin, 'r') as f:
            self.skin = f.read()

        self.list = []
        self.drawList = []
        self["list"] = List(self.drawList, enableWrapAround=True)

        self.setup_title = (_('Main Menu'))

        self['key_red'] = StaticText(_('Back'))
        self['key_green'] = StaticText(_('OK'))

        self['version'] = StaticText()

        self['actions'] = ActionMap(['XStreamityActions'], {
            'red': self.quit,
            'green': self.__next__,
            'ok': self.__next__,
            'cancel': self.quit,
            'menu': self.settings,
        }, -2)

        self.clear_caches()
        self['version'].setText(version)

        if self.session.nav.getCurrentlyPlayingServiceReference():
            glob.currentPlayingServiceRef = self.session.nav.getCurrentlyPlayingServiceReference()
            glob.currentPlayingServiceRefString = self.session.nav.getCurrentlyPlayingServiceReference().toString()
            glob.newPlayingServiceRef = self.session.nav.getCurrentlyPlayingServiceReference()
            glob.newPlayingServiceRefString = glob.newPlayingServiceRef.toString()

        self.onFirstExecBegin.append(self.check_dependencies)
        self.onLayoutFinish.append(self.__layoutFinished)

    def __layoutFinished(self):
        self.setTitle(self.setup_title)

    def check_dependencies(self):
        dependencies = True

        try:
            import requests
            from PIL import Image
        except:
            dependencies = False

        try:
            from concurrent.futures import ThreadPoolExecutor
        except:
            try:
                from multiprocessing.pool import ThreadPool
            except:
                dependencies = False

        if dependencies is False:
            chmod("/usr/lib/enigma2/python/Plugins/Extensions/XStreamity/dependencies.sh", 0o0755)
            cmd1 = ". /usr/lib/enigma2/python/Plugins/Extensions/XStreamity/dependencies.sh"
            self.session.openWithCallback(self.start, Console, title="Checking Python Dependencies", cmdlist=[cmd1], closeOnSuccess=False)
        else:
            self.start()

    def clear_caches(self):
        try:
            system("echo 1 > /proc/sys/vm/drop_caches")
            system("echo 2 > /proc/sys/vm/drop_caches")
            system("echo 3 > /proc/sys/vm/drop_caches")
        except:
            pass

    def start(self, answer=None):
        self.playlists_all = xfiles.processfiles()
        self.createSetup()

    def createSetup(self):
        self.list = []
        downloads_all = []

        if os.path.isfile(downloads_json):
            with open(downloads_json, "r") as f:
                try:
                    downloads_all = json.load(f)
                except:
                    pass

        if self.playlists_all:
            self.list.append([1, _("Playlists")])
        self.list.append([3, _("Add Playlist")])
        self.list.append([2, _("Main Settings")])
        if self.playlists_all:
            self.list.append([5, _("Manual EPG Update")])
        if downloads_all:
            self.list.append([4, _("Download Manager")])

        self.drawList = []
        self.drawList = [buildListEntry(x[0], x[1]) for x in self.list]
        self["list"].setList(self.drawList)

    def playlists(self):
        from . import playlists
        self.session.openWithCallback(self.start, playlists.XStreamity_Playlists)
        return

    def settings(self):
        from . import settings
        self.session.openWithCallback(self.start, settings.XStreamity_Settings)

    def addServer(self):
        from . import server
        self.session.openWithCallback(self.start, server.XStreamity_AddServer)
        return

    def downloadManager(self):
        from . import downloadmanager2
        self.session.openWithCallback(self.start, downloadmanager2.XStreamity_DownloadManager)
        return

    def updateEPG(self):
        self.session.openWithCallback(self.updateEPG2, MessageBox, _("EPGs downloading."), type=MessageBox.TYPE_INFO, timeout=5)

    def updateEPG2(self, data=None):
        from . import update
        epg = update.XStreamity_Update()
        
    def __next__(self):
        index = self["list"].getCurrent()[0]

        if self["list"].getCurrent():
            if index == 1:
                self.playlists()
            if index == 2:
                self.settings()
            if index == 3:
                self.addServer()
            if index == 4:
                self.downloadManager()
            if index == 5:
                self.updateEPG()

    def quit(self):
        self.playOriginalChannel()

    def playOriginalChannel(self):
        if glob.currentPlayingServiceRefString != glob.newPlayingServiceRefString:
            if glob.newPlayingServiceRefString and glob.currentPlayingServiceRefString:
                self.session.nav.playService(eServiceReference(glob.currentPlayingServiceRefString))
        self.close()


def buildListEntry(index, title):
    png = None

    if index == 1:
        png = LoadPixmap(common_path + "playlists.png")
    if index == 2:
        png = LoadPixmap(common_path + "settings.png")
    if index == 3:
        png = LoadPixmap(common_path + "addplaylist.png")
    if index == 4:
        png = LoadPixmap(common_path + "vod_download.png")
    if index == 5:
        png = LoadPixmap(common_path + "epg_download.png")

    return (index, str(title), png)
