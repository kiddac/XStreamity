#!/usr/bin/python
# -*- coding: utf-8 -*-

from . import _
from . import xstreamity_globals as glob

from .plugin import skin_directory, common_path, playlists_json, cfg
from .xStaticText import StaticText

from collections import OrderedDict
from Components.config import config
from Components.ActionMap import ActionMap
from Components.Sources.List import List
from Screens.MessageBox import MessageBox
from Screens.Screen import Screen
from Tools.LoadPixmap import LoadPixmap
from Screens.InputBox import PinInput
from Tools.BoundFunction import boundFunction

import os
import json


class ProtectedScreen:
    def __init__(self):
        if self.isProtected():
            self.onFirstExecBegin.append(boundFunction(self.session.openWithCallback, self.pinEntered, PinInput, pinList=[cfg.adultpin.value], triesEntry=cfg.retries.adultpin, title=_("Please enter the correct pin code"), windowTitle=_("Enter pin code")))

    def isProtected(self):
        return (config.plugins.XStreamity.adult.value)

    def pinEntered(self, result):
        if result is None:
            self.closeProtectedScreen()
        elif not result:
            self.session.openWithCallback(self.closeProtectedScreen, MessageBox, _("The pin code you entered is wrong."), MessageBox.TYPE_ERROR)

    def closeProtectedScreen(self, result=None):
        self.close(None)


class XStreamity_HiddenCategories(Screen, ProtectedScreen):
    ALLOW_SUSPEND = True

    def __init__(self, session, category_type, channellist, level=1):

        Screen.__init__(self, session)

        if cfg.adult.getValue() is True:
            ProtectedScreen.__init__(self)

        self.session = session

        skin_path = os.path.join(skin_directory, cfg.skin.getValue())
        skin = os.path.join(skin_path, "hidden.xml")
        self.category_type = category_type
        self.channellist = channellist
        self.level = level

        with open(skin, "r") as f:
            self.skin = f.read()

        self.setup_title = (_("Hidden Categories"))

        self.startList = []
        self.drawList = []
        self["hidden_list"] = List(self.drawList, enableWrapAround=True)
        self["hidden_list"].onSelectionChanged.append(self.getCurrentEntry)

        self.currentSelection = 0

        self["key_red"] = StaticText(_("Cancel"))
        self["key_green"] = StaticText(_("Save"))
        self["key_yellow"] = StaticText(_("Invert"))
        self["key_blue"] = StaticText(_("Reset"))

        self.protocol = glob.current_playlist["playlist_info"]["protocol"]
        self.domain = glob.current_playlist["playlist_info"]["domain"]
        self.host = glob.current_playlist["playlist_info"]["host"]

        self["actions"] = ActionMap(["XStreamityActions"], {
            "red": self.keyCancel,
            "green": self.keyGreen,
            "yellow": self.toggleAllSelection,
            "blue": self.clearAllSelection,
            "save": self.keyGreen,
            "cancel": self.keyCancel,
            "ok": self.toggleSelection,
        }, -2)

        self.loadHidden()
        self.onLayoutFinish.append(self.__layoutFinished)

    def __layoutFinished(self):
        self.setTitle(self.setup_title)
        self.getCurrentEntry()

    def loadHidden(self):
        self.playlists_all = []
        self.hidelist = []
        self.hidechannellist = []
        self.startList = []

        if self.category_type == "live":
            if self.level == 1:
                self.hidelist = glob.current_playlist["player_info"]["livehidden"]
            else:
                self.hidelist = glob.current_playlist["player_info"]["channelshidden"]

        elif self.category_type == "vod":
            if self.level == 1:
                self.hidelist = glob.current_playlist["player_info"]["vodhidden"]
            else:
                self.hidelist = glob.current_playlist["player_info"]["vodstreamshidden"]

        elif self.category_type == "series":
            if self.level == 1:
                self.hidelist = glob.current_playlist["player_info"]["serieshidden"]
            elif self.level == 2:
                self.hidelist = glob.current_playlist["player_info"]["seriestitleshidden"]

            elif self.level == 3:
                self.hidelist = glob.current_playlist["player_info"]["seriesseasonshidden"]

            elif self.level == 4:
                self.hidelist = glob.current_playlist["player_info"]["seriesepisodeshidden"]

        elif self.category_type == "catchup":
            if self.level == 1:
                self.hidelist = glob.current_playlist["player_info"]["catchuphidden"]
            else:
                self.hidelist = glob.current_playlist["player_info"]["catchupchannelshidden"]

        for item in self.channellist:
            if item[2] not in self.hidelist:
                self.startList.append([item[1], item[2], False])
            elif item[2] in self.hidelist:
                self.startList.append([item[1], item[2], True])

        self.drawList = []
        self.drawList = [self.buildListEntry(x[0], x[1], x[2]) for x in self.startList]
        self["hidden_list"].setList(self.drawList)

    def buildListEntry(self, name, category_id, enabled):
        if enabled:
            pixmap = LoadPixmap(cached=True, path=os.path.join(common_path, "lock_on.png"))
        else:
            pixmap = LoadPixmap(cached=True, path=os.path.join(common_path, "lock_off.png"))
        return (pixmap, str(name), str(category_id), enabled)

    def refresh(self):
        self.drawList = []
        self.drawList = [self.buildListEntry(x[0], x[1], x[2]) for x in self.startList]
        self["hidden_list"].updateList(self.drawList)

    def toggleSelection(self):
        if len(self["hidden_list"].list) > 0:
            idx = self["hidden_list"].getIndex()
            self.startList[idx][2] = not self.startList[idx][2]
            self.refresh()

    def toggleAllSelection(self):
        for idx, item in enumerate(self["hidden_list"].list):
            self.startList[idx][2] = not self.startList[idx][2]
        self.refresh()

    def clearAllSelection(self):
        for idx, item in enumerate(self["hidden_list"].list):
            self.startList[idx][2] = False
        self.refresh()

    def getCurrentEntry(self):
        self.currentSelection = self["hidden_list"].getIndex()

    def keyCancel(self):
        self.close()

    def keyGreen(self):
        count = 0
        for item in self.startList:
            if item[2] is True:
                count += 1

        if count == len(self.channellist):
            self.session.open(MessageBox, _("Error: All categories hidden. Please amend your selection."), MessageBox.TYPE_ERROR)
            return

        domain = glob.current_playlist["playlist_info"]["domain"]
        username = glob.current_playlist["playlist_info"]["username"]
        password = glob.current_playlist["playlist_info"]["password"]

        for item in self.startList:

            if self.category_type == "live":
                if self.level == 1:
                    if item[2] is True and item[1] not in glob.current_playlist["player_info"]["livehidden"]:
                        glob.current_playlist["player_info"]["livehidden"].append(item[1])
                    elif item[2] is False and item[1] in glob.current_playlist["player_info"]["livehidden"]:
                        glob.current_playlist["player_info"]["livehidden"].remove(item[1])

                elif self.level == 2:
                    if item[2] is True and item[1] not in glob.current_playlist["player_info"]["channelshidden"]:
                        glob.current_playlist["player_info"]["channelshidden"].append(item[1])
                    elif item[2] is False and item[1] in glob.current_playlist["player_info"]["channelshidden"]:
                        glob.current_playlist["player_info"]["channelshidden"].remove(item[1])

            elif self.category_type == "vod":
                if self.level == 1:
                    if item[2] is True and item[1] not in glob.current_playlist["player_info"]["vodhidden"]:
                        glob.current_playlist["player_info"]["vodhidden"].append(item[1])
                    elif item[2] is False and item[1] in glob.current_playlist["player_info"]["vodhidden"]:
                        glob.current_playlist["player_info"]["vodhidden"].remove(item[1])

                elif self.level == 2:
                    if item[2] is True and item[1] not in glob.current_playlist["player_info"]["vodstreamshidden"]:
                        glob.current_playlist["player_info"]["vodstreamshidden"].append(item[1])
                    elif item[2] is False and item[1] in glob.current_playlist["player_info"]["vodstreamshidden"]:
                        glob.current_playlist["player_info"]["vodstreamshidden"].remove(item[1])

            elif self.category_type == "series":
                if self.level == 1:
                    if item[2] is True and item[1] not in glob.current_playlist["player_info"]["serieshidden"]:
                        glob.current_playlist["player_info"]["serieshidden"].append(item[1])
                    elif item[2] is False and item[1] in glob.current_playlist["player_info"]["serieshidden"]:
                        glob.current_playlist["player_info"]["serieshidden"].remove(item[1])
                if self.level == 2:
                    if item[2] is True and item[1] not in glob.current_playlist["player_info"]["seriestitleshidden"]:
                        glob.current_playlist["player_info"]["seriestitleshidden"].append(item[1])
                    elif item[2] is False and item[1] in glob.current_playlist["player_info"]["seriestitleshidden"]:
                        glob.current_playlist["player_info"]["seriestitleshidden"].remove(item[1])

                if self.level == 3:
                    if item[2] is True and item[1] not in glob.current_playlist["player_info"]["seriesseasonshidden"]:
                        glob.current_playlist["player_info"]["seriesseasonshidden"].append(item[1])
                    elif item[2] is False and item[1] in glob.current_playlist["player_info"]["seriesseasonshidden"]:
                        glob.current_playlist["player_info"]["seriesseasonshidden"].remove(item[1])

                if self.level == 4:
                    if item[2] is True and item[1] not in glob.current_playlist["player_info"]["seriesepisodeshidden"]:
                        glob.current_playlist["player_info"]["seriesepisodeshidden"].append(item[1])
                    elif item[2] is False and item[1] in glob.current_playlist["player_info"]["seriesepisodeshidden"]:
                        glob.current_playlist["player_info"]["seriesepisodeshidden"].remove(item[1])

            elif self.category_type == "catchup":
                if self.level == 1:
                    if item[2] is True and item[1] not in glob.current_playlist["player_info"]["catchuphidden"]:
                        glob.current_playlist["player_info"]["catchuphidden"].append(item[1])
                    elif item[2] is False and item[1] in glob.current_playlist["player_info"]["catchuphidden"]:
                        glob.current_playlist["player_info"]["catchuphidden"].remove(item[1])

                elif self.level == 2:
                    if item[2] is True and item[1] not in glob.current_playlist["player_info"]["catchupchannelshidden"]:
                        glob.current_playlist["player_info"]["catchupchannelshidden"].append(item[1])
                    elif item[2] is False and item[1] in glob.current_playlist["player_info"]["catchupchannelshidden"]:
                        glob.current_playlist["player_info"]["catchupchannelshidden"].remove(item[1])

        self.playlists_all = []

        with open(playlists_json) as f:
            self.playlists_all = json.load(f, object_pairs_hook=OrderedDict)

        x = 0
        for playlist in self.playlists_all:
            if playlist["playlist_info"]["domain"] == str(domain).strip() and playlist["playlist_info"]["username"] == str(username).strip() and playlist["playlist_info"]["password"] == str(password).strip():
                self.playlists_all[x] = glob.current_playlist
                break
            x += 1

        with open(playlists_json, "w") as f:
            json.dump(self.playlists_all, f)

        self.close()
