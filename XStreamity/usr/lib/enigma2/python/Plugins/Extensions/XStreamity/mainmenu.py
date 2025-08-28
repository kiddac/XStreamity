#!/usr/bin/python
# -*- coding: utf-8 -*-

# Standard library imports
import json
import os
import sys
import datetime

# Enigma2 components
from Components.ActionMap import ActionMap
from Components.Sources.List import List
from enigma import eServiceReference
from Screens.Console import Console
from Screens.MessageBox import MessageBox
from Screens.Screen import Screen
from Tools.LoadPixmap import LoadPixmap
from Components.config import configfile

# Local application/library-specific imports
from . import _
from . import xstreamity_globals as glob
from . import processfiles as loadfiles
from .plugin import skin_directory, common_path, version, downloads_json, cfg
from .xStaticText import StaticText


class XStreamity_MainMenu(Screen):
    ALLOW_SUSPEND = True

    def __init__(self, session):
        Screen.__init__(self, session)
        self.session = session

        skin_path = os.path.join(skin_directory, cfg.skin.value)
        skin = os.path.join(skin_path, "mainmenu.xml")
        with open(skin, "r") as f:
            self.skin = f.read()

        self.list = []
        self.drawList = []
        self.playlists_all = []
        self["list"] = List(self.drawList, enableWrapAround=True)

        self.playlists_json = cfg.playlists_json.value
        self.setup_title = _("Main Menu")
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
            "blue": self.resetData,
            "0": lambda: self.keyPressed('0'),
            "1": lambda: self.keyPressed('1'),
            "2": lambda: self.keyPressed('2'),
            "3": lambda: self.keyPressed('3'),
            "4": lambda: self.keyPressed('4'),
            "5": lambda: self.keyPressed('5'),
            "6": lambda: self.keyPressed('6'),
            "7": lambda: self.keyPressed('7'),
            "8": lambda: self.keyPressed('8'),
            "9": lambda: self.keyPressed('9'),
        }, -2)

        self["version"].setText(version)

        self.key_sequence = []
        self.hackavision_added = False

        if self.session.nav.getCurrentlyPlayingServiceReference():
            glob.currentPlayingServiceRef = self.session.nav.getCurrentlyPlayingServiceReference()
            glob.currentPlayingServiceRefString = self.session.nav.getCurrentlyPlayingServiceReference().toString()
            glob.newPlayingServiceRef = self.session.nav.getCurrentlyPlayingServiceReference()
            glob.newPlayingServiceRefString = glob.newPlayingServiceRef.toString()

        self.onShow.append(self.createSetup)
        self.onFirstExecBegin.append(self.check_dependencies)
        self.onLayoutFinish.append(self.__layoutFinished)

    def __layoutFinished(self):
        self.setTitle(self.setup_title)

    def getDynamicKeyCombo(self):
        today = datetime.date.today()
        day = str(today.day).zfill(2)
        year = str(today.month).zfill(2)
        return day + year

    def keyPressed(self, key):
        self.key_sequence.append(key)
        if ''.join(self.key_sequence[-4:]) == self.getDynamicKeyCombo():
            self.showHackAVision()

    def showHackAVision(self):
        if not self.hackavision_added:
            self.hackavision_added = True
            self.createSetup()

    def check_python_dependencies(self):
        try:
            import requests
            from PIL import Image
            if sys.version_info < (3, 9):
                from multiprocessing.pool import ThreadPool
            return True
        except Exception as e:
            print("Failed to import dependencies:", e)
            return False

    def check_dependencies(self):
        try:
            if not cfg.location_valid.value:
                print("Playlists.txt location is invalid and has been reset.")
                self.session.open(MessageBox, _("Playlists.txt location is invalid and has been reset."), type=MessageBox.TYPE_INFO, timeout=5)
                cfg.location_valid.setValue(True)
                cfg.save()
                configfile.save()
        except Exception as e:
            print("Error checking location validity:", e)

        dependencies = True
        dependencies = self.check_python_dependencies()

        if not dependencies:
            script_file = os.path.join(os.path.dirname(__file__), "dependencies.sh")
            try:
                os.chmod(script_file, 0o755)
            except Exception as e:
                print(e)

            cmd = ". {}".format(script_file)
            self.session.openWithCallback(self.retry_check_dependencies, Console, title="Checking Python Dependencies", cmdlist=[cmd], closeOnSuccess=True)
        else:
            self.start()

    def retry_check_dependencies(self):
        dependencies = self.check_python_dependencies()

        if not dependencies:
            self.session.openWithCallback(self.close, MessageBox, _("Dependencies not installed.\n\nTrying installing older version from feeds first..."), type=MessageBox.TYPE_INFO, timeout=10)
        else:
            self.start()

    def start(self):
        self.playlists_all = loadfiles.process_files()
        self.createSetup()

    def createSetup(self):
        self.list = []
        downloads_all = []

        if os.path.isfile(downloads_json) and os.stat(downloads_json).st_size > 0:
            try:
                with open(downloads_json, "r") as f:
                    downloads_all = json.load(f)
            except Exception as e:
                print(e)

        if self.playlists_all:
            self.list.extend([[1, _("Playlists")], [3, _("Add Playlist")], [2, _("Main Settings")]])
        else:
            self.list.extend([[3, _("Add Playlist")], [2, _("Main Settings")]])

        if downloads_all:
            self.list.append([4, _("Download Manager")])

        if self.hackavision_added:
            self.list.append([5, _("Hack-A-Vision")])

        self.drawList = [buildListEntry(x[0], x[1]) for x in self.list]
        self["list"].setList(self.drawList)

    def playlists(self):
        from . import playlists
        self.session.openWithCallback(lambda: self.start, playlists.XStreamity_Playlists)

    def settings(self):
        from . import settings
        self.session.openWithCallback(lambda: self.start, settings.XStreamity_Settings)

    def addServer(self):
        from . import server
        self.session.openWithCallback(lambda: self.start, server.XStreamity_AddServer)

    def downloadManager(self):
        from . import downloadmanager
        self.session.openWithCallback(lambda: self.start, downloadmanager.XStreamity_DownloadManager)

    def hackavision(self):
        from . import scanner
        self.session.openWithCallback(lambda: self.start, scanner.XStreamity_Scanner)

    def __next__(self):
        current_entry = self["list"].getCurrent()

        if current_entry:
            index = current_entry[0]
            if index == 1:
                self.playlists()
            elif index == 2:
                self.settings()
            elif index == 3:
                self.addServer()
            elif index == 4:
                self.downloadManager()
            elif index == 5:
                self.hackavision()

    def quit(self, data=None):
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
            try:
                os.remove(self.playlists_json)
                with open(self.playlists_json, "a"):
                    pass
            except OSError as e:
                print("Error deleting or recreating JSON file:", e)
            self.quit()


def buildListEntry(index, title):
    image_mapping = {
        1: "playlists.png",
        2: "settings.png",
        3: "addplaylist.png",
        4: "vod_download.png",
        5: "playlists.png"
    }

    png = None
    if index in image_mapping:
        png = LoadPixmap(os.path.join(common_path, image_mapping[index]))

    return index, str(title), png
