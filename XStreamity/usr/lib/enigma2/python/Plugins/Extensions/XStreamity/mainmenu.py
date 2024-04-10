#!/usr/bin/python
# -*- coding: utf-8 -*-

from . import _
from . import xstreamity_globals as glob
from . import processfiles as loadfiles
from .plugin import skin_directory, common_path, version, downloads_json, pythonFull, playlists_json, playlist_file, cfg
from .xStaticText import StaticText

from Components.ActionMap import ActionMap
from Components.Sources.List import List
from enigma import eServiceReference
from Screens.Console import Console
from Screens.MessageBox import MessageBox
from Screens.Screen import Screen
# from time import time
from Tools.LoadPixmap import LoadPixmap

import json
import os
import shutil


class XStreamity_MainMenu(Screen):
    ALLOW_SUSPEND = True

    def __init__(self, session):
        Screen.__init__(self, session)
        self.session = session

        skin_path = os.path.join(skin_directory, cfg.skin.getValue())

        skin = os.path.join(skin_path, "mainmenu.xml")
        with open(skin, "r") as f:
            self.skin = f.read()

        self.list = []
        self.drawList = []
        self.playlists_all = []
        self["list"] = List(self.drawList, enableWrapAround=True)

        self.setup_title = (_("Main Menu"))

        self["key_red"] = StaticText(_("Back"))
        self["key_green"] = StaticText(_("OK"))
        self["key_blue"] = StaticText(_("Reset JSON"))

        self["version"] = StaticText()

        self["actions"] = ActionMap(["XStreamityActions"], {
            "red": self.quit,
            "green": self.__next__,
            "ok": self.__next__,
            "cancel": self.quit,
            "menu": self.settings,
            "help": self.resetData,
            "blue": self.resetData
        }, -2)

        self["version"].setText(version)

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

        try:
            if cfg.locationvalid.getValue() is False:
                self.session.open(MessageBox, _("Playlists.txt location is invalid and has been reset."), type=MessageBox.TYPE_INFO, timeout=5)
                cfg.locationvalid.setValue(True)
                cfg.save()
        except:
            pass

        dependencies = True

        try:
            import requests
            from PIL import Image
            print("***** python version *** %s" % pythonFull)
            if pythonFull < 3.9:
                print("*** checking multiprocessing ***")
                from multiprocessing.pool import ThreadPool
        except Exception as e:
            print("**** missing dependencies ***")
            print(e)
            dependencies = False

        if dependencies is False:
            os.chmod("/usr/lib/enigma2/python/Plugins/Extensions/XStreamity/dependencies.sh", 0o0755)
            cmd1 = ". /usr/lib/enigma2/python/Plugins/Extensions/XStreamity/dependencies.sh"
            self.session.openWithCallback(self.start, Console, title="Checking Python Dependencies", cmdlist=[cmd1], closeOnSuccess=False)
        else:
            self.start()

    def start(self, answer=None):
        self.playlists_all = loadfiles.processfiles()
        self.createSetup()

    def createSetup(self):
        self.list = []
        downloads_all = []

        if os.path.isfile(downloads_json) and os.stat(downloads_json).st_size > 0:
            with open(downloads_json, "r") as f:
                try:
                    downloads_all = json.load(f)
                except Exception as e:
                    print(e)

        if self.playlists_all:
            self.list.append([1, _("Playlists")])
            self.list.append([3, _("Add Playlist")])
            self.list.append([2, _("Main Settings")])
            # self.list.append([5, _("Manual EPG Update")])

        else:
            self.list.append([3, _("Add Playlist")])
            self.list.append([2, _("Main Settings")])

        if downloads_all:
            self.list.append([4, _("Download Manager")])

        self.drawList = []
        self.drawList = [buildListEntry(x[0], x[1]) for x in self.list]
        self["list"].setList(self.drawList)

    def playlists(self):
        from . import playlists
        self.session.openWithCallback(self.start, playlists.XStreamity_Playlists)

    def settings(self):
        from . import settings
        self.session.openWithCallback(self.start, settings.XStreamity_Settings)

    def addServer(self):
        from . import server
        self.session.openWithCallback(self.start, server.XStreamity_AddServer)

    def downloadManager(self):
        from . import downloadmanager
        self.session.openWithCallback(self.start, downloadmanager.XStreamity_DownloadManager)

    """
    def updateEPG(self):

        recordings = ""
        next_rec_time = -1

        try:
            recordings = self.session.nav.getRecordings()
            if not recordings:
                next_rec_time = self.session.nav.RecordTimer.getNextRecordingTime()
        except:
            pass

        if recordings or (next_rec_time > 0 and (next_rec_time - time()) < 360):
            self.session.open(MessageBox, _("Recordings in progress. EPG not downloaded."), type=MessageBox.TYPE_INFO, timeout=5)
        else:
            self.session.openWithCallback(self.updateEPG2, MessageBox, _("EPGs downloading."), type=MessageBox.TYPE_INFO, timeout=5)
            """

    """
    def updateEPG2(self, data=None):
        from . import update
        update.XStreamity_Update()
        """

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
            """
            if index == 5:
                self.updateEPG()
                """

    def quit(self, data=None):
        try:
            shutil.copyfile(playlist_file, '/home/playlists.txt')
        except:
            pass

        self.playOriginalChannel()

    def playOriginalChannel(self):
        if glob.currentPlayingServiceRefString != glob.newPlayingServiceRefString:
            if glob.newPlayingServiceRefString and glob.currentPlayingServiceRefString:
                self.session.nav.playService(eServiceReference(glob.currentPlayingServiceRefString))
        self.close()

    def resetData(self, answer=None):
        if answer is None:
            self.session.openWithCallback(self.resetData, MessageBox, _("Warning: delete stored json data for all playlists... Settings, favourites etc. \nPlaylists will not be deleted.\nDo you wish to continue?"))
        elif answer:
            os.remove(playlists_json)
            if not os.path.isfile(playlists_json):
                with open(playlists_json, "a") as f:
                    f.close()
            self.quit()


def buildListEntry(index, title):
    png = None

    if index == 1:
        png = LoadPixmap(os.path.join(common_path, "playlists.png"))
    if index == 2:
        png = LoadPixmap(os.path.join(common_path, "settings.png"))
    if index == 3:
        png = LoadPixmap(os.path.join(common_path, "addplaylist.png"))
    if index == 4:
        png = LoadPixmap(os.path.join(common_path, "vod_download.png"))
    """
    if index == 5:
        png = LoadPixmap(os.path.join(common_path, "epg_download.png"))
        """

    return (index, str(title), png)
