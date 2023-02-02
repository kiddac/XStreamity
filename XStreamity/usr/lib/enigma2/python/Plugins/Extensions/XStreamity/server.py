#!/usr/bin/python
# -*- coding: utf-8 -*-

from . import _
from .plugin import skin_directory, playlist_file, hdr, cfg
from .xStaticText import StaticText

from Components.ActionMap import ActionMap
from Components.ConfigList import ConfigListScreen
from Components.config import getConfigListEntry, NoSave, ConfigText, ConfigSelection, ConfigNumber, ConfigYesNo, ConfigEnableDisable
from Components.Pixmap import Pixmap
from Screens.MessageBox import MessageBox
from Screens.Screen import Screen

import os
import shutil


class XStreamity_AddServer(ConfigListScreen, Screen):
    def __init__(self, session):
        Screen.__init__(self, session)
        self.session = session

        skin_path = os.path.join(skin_directory, cfg.skin.getValue())
        skin = os.path.join(skin_path, "settings.xml")

        if os.path.exists("/var/lib/dpkg/status"):
            skin = os.path.join(skin_path, "DreamOS/settings.xml")

        with open(skin, "r") as f:
            self.skin = f.read()

        self.setup_title = (_("Add Xtream Codes Playlist"))

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
        self.server = "domain.xyz"
        self.port = ""
        self.username = "username"
        self.password = "password"
        self.listType = "m3u"
        self.output = "ts"

        self["actions"] = ActionMap(["XStreamityActions"], {
            "cancel": self.cancel,
            "red": self.cancel,
            "green": self.save,
            "ok": self.void,
        }, -2)

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
        return

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

    def save(self):
        if self["config"].isChanged():

            self.name = self.nameCfg.value.strip()
            protocol = self.protocolCfg.value
            domain = self.serverCfg.value.strip().lower()
            port = self.portCfg.value

            if port:
                host = "%s%s:%s" % (protocol, domain, port)
            else:
                host = "%s%s" % (protocol, domain)

            username = self.usernameCfg.value.strip()
            password = self.passwordCfg.value.strip()
            listtype = "m3u"
            output = self.outputCfg.value

            playlistline = "%s/get.php?username=%s&password=%s&type=%s&output=%s #%s" % (host, username, password, listtype, output, self.name)
            self.apiline = "%s/player_api.php?username=%s&password=%s" % (host, username, password)

            valid = self.checkline()

            if not valid:
                self.session.open(MessageBox, _("Details are not valid or unauthorised"), type=MessageBox.TYPE_INFO, timeout=5)
                return

            # update playlists.txt file
            if not os.path.isfile(playlist_file):
                with open(playlist_file, "w+") as f:
                    f.close()

            """
            with open(playlist_file, "r") as f:
                lines = f.readlines()
                exists = False
                for line in lines:
                    if domain in line and username in line and password in line:
                        exists = True
                        """

            with open(playlist_file, "a") as f:
                f.write("\n" + str(playlistline) + "\n")

            try:
                shutil.copyfile(playlist_file, '/home/playlists.txt')
            except:
                pass

            self.session.open(MessageBox, _("Playlist added successfully."), type=MessageBox.TYPE_INFO, timeout=5)
            self.close()

    def changedEntry(self):
        self.item = self["config"].getCurrent()
        for x in self.onChangedEntry:
            x()
        try:
            if isinstance(self["config"].getCurrent()[1], ConfigEnableDisable) or isinstance(self["config"].getCurrent()[1], ConfigYesNo) or isinstance(self["config"].getCurrent()[1], ConfigSelection):
                self.createSetup()
        except:
            pass

    def checkline(self):
        import requests
        from requests.adapters import HTTPAdapter

        valid = False

        r = ""
        adapter = HTTPAdapter(max_retries=0)
        http = requests.Session()
        http.mount("http://", adapter)
        http.mount("https://", adapter)
        response = ""
        try:
            with http.get(self.apiline, headers=hdr, timeout=15, verify=False, stream=True) as r:
                r.raise_for_status()
                if r.status_code == requests.codes.ok:
                    try:
                        response = r.json()
                        if "user_info" in response:
                            if "auth" in response["user_info"]:
                                if response["user_info"]["auth"] == 1:
                                    valid = True
                    except Exception as e:
                        print(e)

        except Exception as e:
            print(("Error Connecting: %s" % e))

        return valid
