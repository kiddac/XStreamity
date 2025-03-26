#!/usr/bin/python
# -*- coding: utf-8 -*-

# Standard library imports
import os
import json

try:
    from http.client import HTTPConnection
    HTTPConnection.debuglevel = 0
except ImportError:
    from httplib import HTTPConnection
    HTTPConnection.debuglevel = 0

# Third-party imports
import requests
from requests.adapters import HTTPAdapter, Retry

# Enigma2 components
from Components.ActionMap import ActionMap
from Components.ConfigList import ConfigListScreen
from Components.config import getConfigListEntry, NoSave, ConfigText, ConfigSelection, ConfigNumber, ConfigYesNo, ConfigEnableDisable
from Components.Pixmap import Pixmap
from Screens.MessageBox import MessageBox
from Screens.Screen import Screen

# Local application/library-specific imports
from . import _
from .plugin import skin_directory, cfg
from .xStaticText import StaticText


hdr = {
    'User-Agent': str(cfg.useragent.value),
    'Accept-Encoding': 'gzip, deflate'
}

playlist_file = cfg.playlist_file.value
playlists_json = cfg.playlists_json.value


class XStreamity_AddServer(ConfigListScreen, Screen):

    def __init__(self, session):
        Screen.__init__(self, session)
        self.session = session

        skin_path = os.path.join(skin_directory, cfg.skin.value)
        skin = os.path.join(skin_path, "settings.xml")

        if os.path.exists("/var/lib/dpkg/status"):
            skin = os.path.join(skin_path, "DreamOS/settings.xml")

        with open(skin, "r") as f:
            self.skin = f.read()

        self.setup_title = _("Add Xtream Codes Playlist")

        self.onChangedEntry = []

        self.list = []

        ConfigListScreen.__init__(self, self.list, session=self.session, on_change=self.changedEntry)

        self["key_red"] = StaticText(_("Back"))
        self["key_green"] = StaticText(_("Save"))

        self["VKeyIcon"] = Pixmap()
        self["VKeyIcon"].hide()

        self["HelpWindow"] = Pixmap()
        self["HelpWindow"].hide()

        self.protocol = "http://"
        self.output = "ts"

        self["actions"] = ActionMap(["XStreamityActions"], {
            "cancel": self.cancel,
            "red": self.cancel,
            "green": self.save,
            "ok": self.void,
        }, -2)

        self.playlists_all = self.getPlaylistJson()

        self.onFirstExecBegin.append(self.initConfig)
        self.onLayoutFinish.append(self.__layoutFinished)

    def __layoutFinished(self):
        self.setTitle(self.setup_title)

    def cancel(self, answer=None):
        if answer is None:
            if self["config"].isChanged():
                self.session.openWithCallback(self.cancel, MessageBox, _("Really close without saving settings?"))
            else:
                self.close()
        elif answer:
            for x in self["config"].list:
                x[1].cancel()

            self.close()

    def void(self):
        currConfig = self["config"].getCurrent()
        if isinstance(currConfig[1], ConfigNumber):
            pass

    def initConfig(self):
        self.nameCfg = NoSave(ConfigText(default="IPTV", fixed_size=False))
        self.protocolCfg = NoSave(ConfigSelection(default=self.protocol, choices=[("http://", "http://"), ("https://", "https://")]))
        self.serverCfg = NoSave(ConfigText(fixed_size=False))
        self.portCfg = NoSave(ConfigText(fixed_size=False))
        self.usernameCfg = NoSave(ConfigText(fixed_size=False))
        self.passwordCfg = NoSave(ConfigText(fixed_size=False))
        self.outputCfg = NoSave(ConfigSelection(default=self.output, choices=[("ts", "ts"), ("m3u8", "m3u8")]))
        self.createSetup()

    def createSetup(self):
        self.list = []

        self.list.append(getConfigListEntry(_("Short name or provider name:"), self.nameCfg))
        self.list.append(getConfigListEntry(_("Protocol:"), self.protocolCfg))
        self.list.append(getConfigListEntry(_("Server URL: i.e. domain.xyz"), self.serverCfg))
        self.list.append(getConfigListEntry(_("Port:"), self.portCfg))
        self.list.append(getConfigListEntry(_("Username:"), self.usernameCfg))
        self.list.append(getConfigListEntry(_("Password:"), self.passwordCfg))
        self.list.append(getConfigListEntry(_("Output:"), self.outputCfg))

        self["config"].list = self.list
        self["config"].l.setList(self.list)
        self.handleInputHelpers()

    def handleInputHelpers(self):
        from enigma import ePoint
        currConfig = self["config"].getCurrent()

        if currConfig is not None:
            if isinstance(currConfig[1], ConfigText):
                if "VKeyIcon" in self:
                    if isinstance(currConfig[1], ConfigNumber):
                        try:
                            self["VirtualKB"].setEnabled(False)
                        except:
                            pass

                        try:
                            self["virtualKeyBoardActions"].setEnabled(False)
                        except:
                            pass

                        self["VKeyIcon"].hide()
                    else:
                        try:
                            self["VirtualKB"].setEnabled(True)
                        except:
                            pass

                        try:
                            self["virtualKeyBoardActions"].setEnabled(True)
                        except:
                            pass
                        self["VKeyIcon"].show()

                if "HelpWindow" in self and currConfig[1].help_window and currConfig[1].help_window.instance is not None:
                    helpwindowpos = self["HelpWindow"].getPosition()
                    currConfig[1].help_window.instance.move(ePoint(helpwindowpos[0], helpwindowpos[1]))

            else:
                if "VKeyIcon" in self:
                    try:
                        self["VirtualKB"].setEnabled(False)
                    except:
                        pass
                    self["VKeyIcon"].hide()

    def getPlaylistJson(self):
        playlists_all = []

        # Check if the playlist file exists and is not empty
        if os.path.exists(playlists_json) and os.path.getsize(playlists_json) > 0:
            try:
                with open(playlists_json) as f:
                    playlists_all = json.load(f)
            except Exception as e:
                print("Error loading playlist JSON:", e)
                os.remove(playlists_json)

        return playlists_all

    def save(self):
        if not self["config"].isChanged():
            return

        self.name = self.nameCfg.value.strip()
        protocol = self.protocolCfg.value
        domain = self.serverCfg.value.strip().lower()
        port = self.portCfg.value

        host = "{}{}:{}".format(protocol, domain, port) if port else "{}{}".format(protocol, domain)

        username = self.usernameCfg.value.strip()
        password = self.passwordCfg.value.strip()
        media_type = "m3u"
        output = self.outputCfg.value

        playlistline = "{}/get.php?username={}&password={}&type={}&output={} #{}".format(host, username, password, media_type, output, self.name)
        self.apiline = "{}/player_api.php?username={}&password={}".format(host, username, password)

        valid = self.checkline()

        # check url has response
        if not valid:
            self.session.open(MessageBox, _("Details are not valid or unauthorised"), type=MessageBox.TYPE_INFO, timeout=5)
            return

        # check name is not blank
        if not self.name or len(self.name) < 3:
            self.session.open(MessageBox, _("Bouquet name cannot be blank. Please enter a unique bouquet name. Minimum 2 characters."), MessageBox.TYPE_ERROR, timeout=10)
            self.createSetup()
            return

        # check if name exists
        if any(playlists["playlist_info"]["name"] == self.name for playlists in self.playlists_all):
            self.session.open(MessageBox, _("Name already used. Please enter a unique name."), MessageBox.TYPE_ERROR, timeout=10)
            return

        if not os.path.exists(playlist_file):
            with open(playlist_file, "a") as f:
                pass

        with open(playlist_file, "a") as f:
            f.write("\n{}\n".format(playlistline))

        self.session.open(MessageBox, _("Playlist added successfully."), type=MessageBox.TYPE_INFO, timeout=5)
        self.close()

    def changedEntry(self):
        self.item = self["config"].getCurrent()
        for x in self.onChangedEntry:
            x()
        try:
            if isinstance(self["config"].getCurrent()[1], ConfigEnableDisable) or isinstance(self["config"].getCurrent()[1], ConfigYesNo) or isinstance(self["config"].getCurrent()[1], ConfigSelection):
                self.createSetup()
        except Exception as e:
            print("Error in changedEntry:", e)

    def checkline(self):
        valid = False

        retries = Retry(total=2, backoff_factor=1)
        adapter = HTTPAdapter(max_retries=retries)

        with requests.Session() as http:
            http.mount("http://", adapter)
            http.mount("https://", adapter)

            try:
                response = http.get(self.apiline, headers=hdr, timeout=30, verify=False)
                response.raise_for_status()
                if response.status_code == requests.codes.ok:
                    try:
                        json_response = response.json()
                        if "user_info" in json_response and "auth" in json_response["user_info"]:
                            valid = str(json_response["user_info"]["auth"]) == "1"
                    except ValueError:
                        pass
            except Exception as e:
                print("Error connecting:", e)

        return valid
