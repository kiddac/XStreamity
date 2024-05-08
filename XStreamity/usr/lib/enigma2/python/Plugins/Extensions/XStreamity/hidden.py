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

    def pinEntered(self, result=None):
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

        if cfg.adult.value:
            ProtectedScreen.__init__(self)

        self.session = session

        skin_path = os.path.join(skin_directory, cfg.skin.value)
        skin = os.path.join(skin_path, "hidden.xml")
        with open(skin, "r") as f:
            self.skin = f.read()

        self.category_type = category_type
        self.channellist = channellist
        self.level = level

        self.setup_title = _("Hidden Categories")
        self.startList = []
        self.drawList = []
        self["hidden_list"] = List(self.drawList, enableWrapAround=True)
        self["hidden_list"].onSelectionChanged.append(self.getCurrentEntry)
        self.currentSelection = 0

        self["key_red"] = StaticText(_("Cancel"))
        self["key_green"] = StaticText(_("Save"))
        self["key_yellow"] = StaticText(_("Invert"))
        self["key_blue"] = StaticText(_("Reset"))

        playlist_info = glob.active_playlist["playlist_info"]
        self.protocol = playlist_info["protocol"]
        self.domain = playlist_info["domain"]
        self.host = playlist_info["host"]

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
        self.startList = []
        player_info = glob.active_playlist["player_info"]

        # Define dictionary to map category types to keys in player_info
        category_keys = {
            "live": ["livehidden", "channelshidden"],
            "vod": ["vodhidden", "vodstreamshidden"],
            "series": ["serieshidden", "seriestitleshidden", "seriesseasonshidden", "seriesepisodeshidden"],
            "catchup": ["catchuphidden", "catchupchannelshidden"]
        }

        # Get the corresponding key based on category_type and level
        list_key = category_keys.get(self.category_type, [])[self.level - 1]

        # Retrieve hidelist based on list_key
        self.hidelist = player_info.get(list_key, [])

        # Populate startList based on hidelist
        for item in self.channellist:
            hidden = item[2] in self.hidelist
            self.startList.append([item[1], item[2], hidden])

        self.drawList = []
        self.drawList = [self.buildListEntry(x[0], x[1], x[2]) for x in self.startList]
        self["hidden_list"].setList(self.drawList)

    def buildListEntry(self, name, category_id, enabled):
        image_path = "lock_hidden.png" if enabled else "lock_off.png"
        full_path = os.path.join(common_path, image_path)
        pixmap = LoadPixmap(cached=True, path=full_path)
        return (pixmap, str(name), str(category_id), enabled)

    def refresh(self):
        self.drawList = []
        self.drawList = [self.buildListEntry(x[0], x[1], x[2]) for x in self.startList]
        self["hidden_list"].updateList(self.drawList)

    def toggleSelection(self):
        if self["hidden_list"].list:
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
        count = sum(1 for item in self.startList if item[2])

        if count == len(self.channellist):
            self.session.open(MessageBox, _("Error: All categories hidden. Please amend your selection."), MessageBox.TYPE_ERROR)
            return

        playlist_info = glob.active_playlist["playlist_info"]
        player_info = glob.active_playlist["player_info"]
        domain = playlist_info["domain"]
        username = playlist_info["username"]
        password = playlist_info["password"]

        # Define dictionary to map category types to keys in player_info
        category_keys = {
            "live": ["livehidden", "channelshidden"],
            "vod": ["vodhidden", "vodstreamshidden"],
            "series": ["serieshidden", "seriestitleshidden", "seriesseasonshidden", "seriesepisodeshidden"],
            "catchup": ["catchuphidden", "catchupchannelshidden"]
        }

        # Get the list key based on category type and level
        list_key = category_keys.get(self.category_type, [])[self.level - 1]

        # Ensure list_key exists before proceeding
        if list_key:
            selected_list = player_info.get(list_key, [])

            for item in self.startList:
                item_id = item[1]
                hidden = item[2]

                if hidden and item_id not in selected_list:
                    selected_list.append(item_id)
                elif not hidden and item_id in selected_list:
                    selected_list.remove(item_id)

            # Update player_info with the modified list
            player_info[list_key] = selected_list

        with open(playlists_json) as f:
            self.playlists_all = json.load(f, object_pairs_hook=OrderedDict)

        for idx, playlist in enumerate(self.playlists_all):
            if (
                playlist["playlist_info"]["domain"].strip() == str(domain).strip() and
                playlist["playlist_info"]["username"].strip() == str(username).strip() and
                playlist["playlist_info"]["password"].strip() == str(password).strip()
            ):
                self.playlists_all[idx] = glob.active_playlist
                break

        with open(playlists_json, "w") as f:
            json.dump(self.playlists_all, f)

        self.close()
