#!/usr/bin/python
# -*- coding: utf-8 -*-

# Standard library imports
import os
import json
from time import time

try:
    from http.client import HTTPConnection
    HTTPConnection.debuglevel = 0
except:
    from httplib import HTTPConnection
    HTTPConnection.debuglevel = 0

# Enigma2 components
from Components.ActionMap import ActionMap
from Components.Sources.List import List
from Screens.Screen import Screen
from Screens.MessageBox import MessageBox

# Local application/library-specific imports
from . import _
from . import xstreamity_globals as glob
from .plugin import skin_directory, cfg, version, downloads_json
from .xStaticText import StaticText
from . import processfiles as loadfiles


class XStreamity_ChannelMenu(Screen):
    ALLOW_SUSPEND = True

    instance = None

    def __init__(self, session, callfunc):
        Screen.__init__(self, session)
        self.session = session
        self.callfunc = callfunc

        skin_path = os.path.join(
            skin_directory,
            cfg.interface.value,
            cfg.skin.value
        )

        if not os.path.exists(skin_path):
            skin_path = os.path.join(
                skin_directory,
                cfg.interface.value,
                "default"
            )

        skin = os.path.join(skin_path, "channelmenu.xml")

        with open(skin, "r") as f:
            self.skin = f.read()

        self.list = []
        self.drawList = []
        self.playlists_all = self.playlists_all = loadfiles.process_files()
        self["list"] = List(self.drawList, enableWrapAround=True)

        self.setup_title = _("Menu")

        self.provider = glob.active_playlist["playlist_info"]["name"]
        self["provider"] = StaticText(self.provider)

        self["key_red"] = StaticText(_("Back"))
        self["key_green"] = StaticText(_("OK"))

        self['dialogactions'] = ActionMap(['XStreamityActions'], {
            "green": self.__next__,
            "ok": self.__next__,
            "up": self.goUp,
            "down": self.goDown,
            "left": self.pageUp,
            "right": self.pageDown,
            "0": self.reset,
        }, -1)

        self["version"] = StaticText()
        self["version"].setText(version)

        self.createSetup()

        self.onLayoutFinish.append(self.__layoutFinished)

    def __layoutFinished(self):
        self.setTitle(self.setup_title)

    def goUp(self):
        instance = self["list"].master.master.instance
        instance.moveSelection(instance.moveUp)

    def goDown(self):
        instance = self["list"].master.master.instance
        instance.moveSelection(instance.moveDown)

    def pageUp(self):
        instance = self["list"].master.master.instance
        instance.moveSelection(instance.pageUp)

    def pageDown(self):
        instance = self["list"].master.master.instance
        instance.moveSelection(instance.pageDown)

    # button 0
    def reset(self):
        self["list"].setIndex(0)

    def createSetup(self):
        # print("*** createsetup **")
        self.provider = str(glob.active_playlist["playlist_info"]["name"])

        self["provider"].setText(self.provider)

        self.list = []

        if glob.active_playlist["player_info"]["showlive"] and self.callfunc == "live":
            self.list.append([5, _("Manual EPG Update")])
        self.list.append([6, _("Playlist Settings")])
        if glob.current_list:
            self.list.append([7, _("Show/Hide Channels")])
        if cfg.sidemenuaccountinfo.value:
            self.list.append([8, _("Account Info")])
        if len(self.playlists_all) > 1 and cfg.sidemenumanageplaylists.value:
            self.list.append([10, _("Manage Playlists")])
        self.list.append([11, _("Add New Playlist")])

        downloads_all = []
        if os.path.isfile(downloads_json) and os.stat(downloads_json).st_size > 0:
            try:
                with open(downloads_json, "r") as f:
                    downloads_all = json.load(f)
            except Exception as e:
                print(e)

        if downloads_all:
            self.list.append([12, _("Download Manager")])
        self.list.append([13, _("Global Settings")])

        self.drawList = []
        self.drawList = [buildListEntry(x[0], x[1]) for x in self.list]
        self["list"].setList(self.drawList)

    def __next__(self):
        choice = self["list"].getCurrent()[1]

        if self["list"].getCurrent():
            if choice == "":
                pass

            if choice == _("Manual EPG Update"):
                self.manualEPGUpdate()
            if choice == _("Playlist Settings"):
                self.playlistSettings()
            if choice == _("Show/Hide Channels"):
                self.showHidden()
            if choice == _("Account Info"):
                self.userInfo()
            if choice == _("Manage Playlists"):
                self.showPlaylists()
            if choice == _("Add New Playlist"):
                self.addPlaylist()
            if choice == _("Download Manager"):
                self.downloadManager()
            if choice == _("Global Settings"):
                self.mainSettings()

    def manualEPGUpdate(self):
        self.closeDialog()

        recordings = ""
        next_rec_time = -1

        try:
            recordings = self.session.nav.getRecordings()
            if not recordings:
                next_rec_time = self.session.nav.RecordTimer.getNextRecordingTime()
        except Exception as e:
            print(e)

        if recordings or (next_rec_time > 0 and (next_rec_time - time()) < 360):
            self.session.open(MessageBox, _("Recordings in progress. EPG not downloaded."), type=MessageBox.TYPE_INFO, timeout=5)
        else:
            self.session.openWithCallback(self.manualEPGUpdate2, MessageBox, _("EPGs downloading."), type=MessageBox.TYPE_INFO, timeout=5)

    def manualEPGUpdate2(self, data=None):
        from . import update
        update.XStreamity_Update(self.session, "manual")
        self.callback()

    def playlistSettings(self):
        self.closeDialog()
        from . import playsettings
        self.session.openWithCallback(self.callback, playsettings.XStreamity_Settings)

    def showHidden(self):
        self.closeDialog()
        from . import hidden
        self.session.openWithCallback(self.callback, hidden.XStreamity_HiddenCategories, glob.current_screen, glob.current_list, glob.current_level)

    def userInfo(self):
        self.closeDialog()
        from . import serverinfo
        if "user_info" in glob.active_playlist:
            if "auth" in glob.active_playlist["user_info"]:
                if str(glob.active_playlist["user_info"]["auth"]) == "1":
                    self.session.openWithCallback(self.callback, serverinfo.XStreamity_UserInfo)

    def showPlaylists(self):
        self.closeDialog()
        from . import playlists
        self.session.openWithCallback(self.callback, playlists.XStreamity_Playlists)

    def addPlaylist(self):
        self.closeDialog()
        from . import server
        self.session.openWithCallback(self.callback, server.XStreamity_AddServer)

    def downloadManager(self):
        self.closeDialog()
        from . import downloadmanager
        self.session.openWithCallback(self.callback, downloadmanager.XStreamity_DownloadManager)

    def mainSettings(self):
        self.closeDialog()
        from . import settings
        self.session.openWithCallback(self.callback, settings.XStreamity_Settings)

    def callback(self, answer=None):
        if glob.ChoiceBoxDialog:
            glob.ChoiceBoxDialog['dialogactions'].execBegin()
            glob.ChoiceBoxDialog.show()
            self.createSetup()

    def closeDialog(self):
        if glob.ChoiceBoxDialog:
            glob.ChoiceBoxDialog.hide()
            glob.ChoiceBoxDialog['dialogactions'].execEnd()

    def exitDialog(self):
        if glob.ChoiceBoxDialog:
            glob.ChoiceBoxDialog.hide()
            glob.ChoiceBoxDialog['dialogactions'].execEnd()
            self.session.deleteDialog(glob.ChoiceBoxDialog)


def buildListEntry(index, choice):
    icon = None

    if choice == _("Live"):
        icon = ""
    if choice == _("Vod"):
        icon = ""
    if choice == _("Series"):
        icon = ""
    if choice == _("Catchup"):
        icon = ""
    if choice == _("Manual EPG Update"):
        icon = ""
    if choice == _("Playlist Settings"):
        icon = ""
    if choice == _("Show/Hide Channels"):
        icon = ""
    if choice == _("Account Info"):
        icon = ""
    if choice == ("Set As Default Playlist"):
        icon = ""
    if choice == _("Manage Playlists"):
        icon = ""
    if choice == _("Add New Playlist"):
        icon = ""
    if choice == _("Download Manager"):
        icon = ""
    if choice == _("Global Settings"):
        icon = ""

    return (index, str(choice), icon)
