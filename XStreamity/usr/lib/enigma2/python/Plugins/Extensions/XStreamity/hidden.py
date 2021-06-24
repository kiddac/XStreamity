#!/usr/bin/python
# -*- coding: utf-8 -*-

# for localized messages
from . import _
from . import xstreamity_globals as glob

from .plugin import skin_path, common_path, json_file
from .xStaticText import StaticText

from collections import OrderedDict
from Components.ActionMap import ActionMap
from Components.Sources.List import List
from Screens.MessageBox import MessageBox
from Screens.Screen import Screen
from Tools.LoadPixmap import LoadPixmap

import json


class XStreamity_HiddenCategories(Screen):

    def __init__(self, session, category_type, channellist, level=1):
        Screen.__init__(self, session)
        self.session = session

        skin = skin_path + 'hidden.xml'
        self.category_type = category_type
        self.channellist = channellist
        self.level = level

        with open(skin, 'r') as f:
            self.skin = f.read()

        self.setup_title = (_('Hidden Categories'))

        self.startList = []
        self.drawList = []
        self['hidden_list'] = List(self.drawList, enableWrapAround=True)
        self['hidden_list'].onSelectionChanged.append(self.getCurrentEntry)

        self.currentSelection = 0

        self["key_red"] = StaticText(_('Cancel'))
        self["key_green"] = StaticText(_('Save'))
        self['key_yellow'] = StaticText(_('Invert'))
        self['key_blue'] = StaticText(_('Clear All'))

        self.protocol = glob.current_playlist['playlist_info']['protocol']
        self.domain = glob.current_playlist['playlist_info']['domain']
        self.host = glob.current_playlist['playlist_info']['host']

        self['setupActions'] = ActionMap(['ColorActions', 'SetupActions', 'ChannelSelectEPGActions'], {
            'red': self.keyCancel,
            'green': self.keyGreen,
            'yellow': self.toggleAllSelection,
            'blue': self.clearAllSelection,
            'save': self.keyGreen,
            'cancel': self.keyCancel,
            'ok': self.toggleSelection,
        }, -2)

        self.onFirstExecBegin.append(self.loadHidden)
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
            self.hidelist = glob.current_playlist['player_info']['livehidden']

        elif self.category_type == "vod":
            self.hidelist = glob.current_playlist['player_info']['vodhidden']

        elif self.category_type == "series":
            self.hidelist = glob.current_playlist['player_info']['serieshidden']

        self.hidechannellist = glob.current_playlist['player_info']['channelshidden']

        for item in self.channellist:
            if self.level == 1:
                if item[3] not in self.hidelist:
                    self.startList.append([item[1], item[3], False])
                elif item[3] in self.hidelist:
                    self.startList.append([item[1], item[3], True])
            if self.level == 2:
                if item[2] not in self.hidechannellist:
                    self.startList.append([item[1], item[2], False])
                elif item[2] in self.hidechannellist:
                    self.startList.append([item[1], item[2], True])

        self.refresh()

    def buildListEntry(self, name, category_id, enabled):
        if enabled:
            pixmap = LoadPixmap(cached=True, path=common_path + "lock_on.png")
        else:
            pixmap = LoadPixmap(cached=True, path=common_path + "lock_off.png")
        return(pixmap, str(name), str(category_id), enabled)

    def refresh(self):
        self.drawList = []
        self.drawList = [self.buildListEntry(x[0], x[1], x[2]) for x in self.startList]
        self['hidden_list'].setList(self.drawList)
        self['hidden_list'].updateList(self.drawList)

    def toggleSelection(self):
        if len(self['hidden_list'].list) > 0:
            idx = self['hidden_list'].getIndex()
            self.startList[idx][2] = not self.startList[idx][2]
            self.refresh()

    def toggleAllSelection(self):
        for idx, item in enumerate(self['hidden_list'].list):
            self.startList[idx][2] = not self.startList[idx][2]
        self.refresh()

    def clearAllSelection(self):
        for idx, item in enumerate(self['hidden_list'].list):
            self.startList[idx][2] = False
        self.refresh()

    def getCurrentEntry(self):
        self.currentSelection = self['hidden_list'].getIndex()

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

        domain = glob.current_playlist['playlist_info']['domain']
        username = glob.current_playlist['playlist_info']['username']
        password = glob.current_playlist['playlist_info']['password']

        if self.category_type == "live":
            if self.level == 1:
                glob.current_playlist['player_info']['livehidden'] = []

                for item in self.startList:
                    if item[2] is True:
                        glob.current_playlist['player_info']['livehidden'].append(item[1])
            if self.level == 2:
                glob.current_playlist['player_info']['channelshidden'] = []

                for item in self.startList:
                    if item[2] is True:
                        glob.current_playlist['player_info']['channelshidden'].append(item[1])

        elif self.category_type == "vod":
            glob.current_playlist['player_info']['vodhidden'] = []
            for item in self.startList:
                if item[2] is True:
                    glob.current_playlist['player_info']['vodhidden'].append(item[1])

        elif self.category_type == "series":
            glob.current_playlist['player_info']['serieshidden'] = []
            for item in self.startList:
                if item[2] is True:
                    glob.current_playlist['player_info']['serieshidden'].append(item[1])

        self.playlists_all = []

        with open(json_file) as f:
            self.playlists_all = json.load(f, object_pairs_hook=OrderedDict)

        x = 0
        for playlist in self.playlists_all:
            if playlist['playlist_info']['domain'] == str(domain).strip() and playlist['playlist_info']['username'] == str(username).strip() and playlist['playlist_info']['password'] == str(password).strip():
                self.playlists_all[x] = glob.current_playlist
                break
            x += 1

        with open(json_file, 'w') as f:
            json.dump(self.playlists_all, f)

        self.close()
