#!/usr/bin/python
# -*- coding: utf-8 -*-

from . import _
from . import xstreamity_globals as glob
from .plugin import skin_path, playlist_file, playlists_json
from .xStaticText import StaticText

from Components.ActionMap import ActionMap
from Components.ConfigList import ConfigListScreen
from Components.config import getConfigListEntry, ConfigText, ConfigSelection, ConfigYesNo, ConfigEnableDisable, NoSave, ConfigSelectionNumber
from Components.Pixmap import Pixmap
from Screens.MessageBox import MessageBox
from Screens.Screen import Screen

import os
import json

try:
    from urlparse import urlparse, parse_qs
except:
    from urllib.parse import urlparse, parse_qs


class XStreamity_Settings(ConfigListScreen, Screen):

    def __init__(self, session):
        Screen.__init__(self, session)

        self.session = session

        skin = skin_path + "settings.xml"

        if os.path.exists("/var/lib/dpkg/status"):
            skin = skin_path + "DreamOS/settings.xml"

        with open(skin, "r") as f:
            self.skin = f.read()

        self.setup_title = (_("Playlist Settings"))

        self.onChangedEntry = []

        self.list = []
        ConfigListScreen.__init__(self, self.list, session=self.session, on_change=self.changedEntry)

        self["key_red"] = StaticText(_("Back"))
        self["key_green"] = StaticText(_("Save"))

        self["VKeyIcon"] = Pixmap()
        self["VKeyIcon"].hide()
        self["HelpWindow"] = Pixmap()
        self["HelpWindow"].hide()

        self["actions"] = ActionMap(["XStreamityActions"], {
            "cancel": self.cancel,
            "red": self.cancel,
            "green": self.save,
        }, -2)

        self.onFirstExecBegin.append(self.initConfig)

        self.onLayoutFinish.append(self.__layoutFinished)

    def clear_caches(self):
        try:
            os.system("echo 1 > /proc/sys/vm/drop_caches")
            os.system("echo 2 > /proc/sys/vm/drop_caches")
            os.system("echo 3 > /proc/sys/vm/drop_caches")
        except:
            pass

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

    def initConfig(self):
        live_streamtype_choices = [("1", "DVB(1)"), ("4097", "IPTV(4097)")]
        vod_streamtype_choices = [("4097", "IPTV(4097)")]

        if os.path.exists("/usr/bin/gstplayer"):
            live_streamtype_choices.append(("5001", "GStreamer(5001)"))
            vod_streamtype_choices.append(("5001", "GStreamer(5001)"))

        if os.path.exists("/usr/bin/exteplayer3"):
            live_streamtype_choices.append(("5002", "ExtePlayer(5002)"))
            vod_streamtype_choices.append(("5002", "ExtePlayer(5002)"))

        if os.path.exists("/usr/bin/apt-get"):
            live_streamtype_choices.append(("8193", "DreamOS GStreamer(8193)"))
            vod_streamtype_choices.append(("8193", "DreamOS GStreamer(8193)"))

        self.name = str(glob.current_playlist["playlist_info"]["name"])
        self.output = str(glob.current_playlist["playlist_info"]["output"])
        self.liveType = str(glob.current_playlist["player_info"]["livetype"])
        self.vodType = str(glob.current_playlist["player_info"]["vodtype"])
        self.showlive = glob.current_playlist["player_info"]["showlive"]
        self.showvod = glob.current_playlist["player_info"]["showvod"]
        self.showseries = glob.current_playlist["player_info"]["showseries"]
        self.showcatchup = glob.current_playlist["player_info"]["showcatchup"]
        self.epgoffset = glob.current_playlist["player_info"]["epgoffset"]
        self.epgalternative = glob.current_playlist["player_info"]["epgalternative"]
        self.epgalternativeurl = glob.current_playlist["player_info"]["epgalternativeurl"]

        self.nameCfg = NoSave(ConfigText(default=self.name, fixed_size=False))
        self.outputCfg = NoSave(ConfigSelection(default=self.output, choices=[("ts", "ts"), ("m3u8", "m3u8")]))
        self.liveTypeCfg = NoSave(ConfigSelection(default=self.liveType, choices=live_streamtype_choices))
        self.vodTypeCfg = NoSave(ConfigSelection(default=self.vodType, choices=vod_streamtype_choices))
        self.showliveCfg = NoSave(ConfigYesNo(default=self.showlive))
        self.showvodCfg = NoSave(ConfigYesNo(default=self.showvod))
        self.showseriesCfg = NoSave(ConfigYesNo(default=self.showseries))
        self.showcatchupCfg = NoSave(ConfigYesNo(default=self.showcatchup))
        self.epgoffsetCfg = NoSave(ConfigSelectionNumber(-9, 9, 1, default=self.epgoffset))
        self.epgalternativeCfg = NoSave(ConfigYesNo(default=self.epgalternative))
        self.epgalternativeurlCfg = NoSave(ConfigText(default=self.epgalternativeurl, fixed_size=False))

        self.createSetup()

    def createSetup(self):
        self.list = []
        self.list.append(getConfigListEntry(_("Short name or provider name:"), self.nameCfg))
        self.list.append(getConfigListEntry(_("Output:"), self.outputCfg))

        self.list.append(getConfigListEntry(_("Show LIVE category:"), self.showliveCfg))
        self.list.append(getConfigListEntry(_("Show VOD category:"), self.showvodCfg))
        self.list.append(getConfigListEntry(_("Show SERIES category:"), self.showseriesCfg))
        self.list.append(getConfigListEntry(_("Show CATCHUP category:"), self.showcatchupCfg))
        self.list.append(getConfigListEntry(_("EPG offset:"), self.epgoffsetCfg))
        self.list.append(getConfigListEntry(_("Use alternative EPG url as instructed by provider:"), self.epgalternativeCfg))
        if self.epgalternativeCfg.value is True:
            self.list.append(getConfigListEntry(_("Enter provided alternative EPG url:"), self.epgalternativeurlCfg))
        if self.showliveCfg.value is True:
            self.list.append(getConfigListEntry(_("Stream Type LIVE:"), self.liveTypeCfg))

        if self.showvodCfg.value is True or self.showseriesCfg.value is True:
            self.list.append(getConfigListEntry(_("Stream Type VOD/SERIES:"), self.vodTypeCfg))

        self["config"].list = self.list
        self["config"].l.setList(self.list)
        self.handleInputHelpers()

    def handleInputHelpers(self):
        from enigma import ePoint
        currConfig = self["config"].getCurrent()

        if currConfig is not None:
            if isinstance(currConfig[1], ConfigText):
                if "VKeyIcon" in self:
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

                    try:
                        self["virtualKeyBoardActions"].setEnabled(False)
                    except:
                        pass
                    self["VKeyIcon"].hide()

    def changedEntry(self):
        self.item = self["config"].getCurrent()
        for x in self.onChangedEntry:
            x()

        try:
            if isinstance(self["config"].getCurrent()[1], ConfigEnableDisable) or isinstance(self["config"].getCurrent()[1], ConfigYesNo) or isinstance(self["config"].getCurrent()[1], ConfigSelection):
                self.createSetup()
        except:
            pass

    def getCurrentEntry(self):
        return self["config"].getCurrent() and self["config"].getCurrent()[0] or ""

    def getCurrentValue(self):
        return self["config"].getCurrent() and str(self["config"].getCurrent()[1].getText()) or ""

    def save(self):
        self.protocol = glob.current_playlist["playlist_info"]["protocol"]
        self.domain = glob.current_playlist["playlist_info"]["domain"]
        self.port = glob.current_playlist["playlist_info"]["port"]
        self.username = glob.current_playlist["playlist_info"]["username"]
        self.password = glob.current_playlist["playlist_info"]["password"]
        self.listtype = "m3u"
        self.host = "%s%s:%s" % (self.protocol, self.domain, self.port)

        if self["config"].isChanged():
            self.name = self.nameCfg.value.strip()
            output = self.outputCfg.value

            showlive = self.showliveCfg.value
            showvod = self.showvodCfg.value
            showseries = self.showseriesCfg.value
            showcatchup = self.showcatchupCfg.value

            livetype = self.liveTypeCfg.value
            if output == "m3u8" and livetype == "1":
                livetype = "4097"

            vodtype = self.vodTypeCfg.value
            epgoffset = self.epgoffsetCfg.value

            epgalternative = self.epgalternativeCfg.value
            epgalternativeurl = self.epgalternativeurlCfg.value

            glob.current_playlist["playlist_info"]["name"] = self.name
            glob.current_playlist["playlist_info"]["output"] = output
            glob.current_playlist["player_info"]["showlive"] = showlive
            glob.current_playlist["player_info"]["showvod"] = showvod
            glob.current_playlist["player_info"]["showseries"] = showseries
            glob.current_playlist["player_info"]["showcatchup"] = showcatchup
            glob.current_playlist["player_info"]["livetype"] = livetype
            glob.current_playlist["player_info"]["vodtype"] = vodtype
            glob.current_playlist["player_info"]["epgoffset"] = epgoffset
            glob.current_playlist["player_info"]["epgalternative"] = epgalternative
            glob.current_playlist["player_info"]["epgalternativeurl"] = epgalternativeurl

            playlistline = "%s%s:%s/get.php?username=%s&password=%s&type=%s&output=%s&timeshift=%s #%s" % (self.protocol, self.domain, self.port, self.username, self.password, self.listtype, output, epgoffset, self.name)

            self.full_url = "%s/get.php?username=%s&password=%s&type=%s&output=%s" % (self.host, self.username, self.password, self.listtype, self.output)
            glob.current_playlist["playlist_info"]["full_url"] = self.full_url
            if epgalternativeurl:
                glob.current_playlist["player_info"]["xmltv_api"] = epgalternativeurl

            # update playlists.txt file
            if not os.path.isfile(playlist_file):
                with open(playlist_file, "w+") as f:
                    f.close()

            with open(playlist_file, "r+") as f:
                lines = f.readlines()
                f.seek(0)
                exists = False
                for line in lines:
                    hastimeshift = False
                    if self.domain in line and self.username in line and self.password in line:
                        parsed_uri = urlparse(line)
                        protocol = parsed_uri.scheme + "://"
                        domain = parsed_uri.hostname
                        port = 80

                        if parsed_uri.port:
                            port = parsed_uri.port

                        query = parse_qs(parsed_uri.query, keep_blank_values=True)

                        if "username" in query:
                            username = query["username"][0].strip()
                        else:
                            continue

                        if "password" in query:
                            password = query["password"][0].strip()
                        else:
                            continue
                        if "timeshift" in query:
                            hastimeshift = True

                        if hastimeshift or int(epgoffset) != 0:
                            playlistline = "%s%s:%s/get.php?username=%s&password=%s&type=%s&output=%s&timeshift=%s #%s" % (protocol, domain, port, username, password, self.listtype, output, epgoffset, self.name)
                        else:
                            playlistline = "%s%s:%s/get.php?username=%s&password=%s&type=%s&output=%s #%s" % (protocol, domain, port, username, password, self.listtype, output, self.name)

                        line = str(playlistline) + "\n"
                        exists = True
                    f.write(line)
                if exists is False:
                    f.write("\n" + str(playlistline) + "\n")

            with open(playlist_file, "r+") as f:
                lines = f.readlines()
                f.seek(0)
                exists = False
                for line in lines:
                    if self.domain in line and self.username in line and self.password in line:
                        line = str(playlistline) + "\n"
                        exists = True
                    f.write(line)
                if exists is False:
                    f.write("\n" + str(playlistline) + "\n")

        self.getPlaylistUserFile()

    def getPlaylistUserFile(self):
        if os.path.isfile(playlists_json):
            with open(playlists_json, "r") as f:
                try:
                    self.playlists_all = json.load(f)
                except:
                    os.remove(playlists_json)

        if self.playlists_all:
            x = 0
            for playlists in self.playlists_all:
                # extra check in case playlists.txt details have been amended
                if "domain" in playlists["playlist_info"] and "username" in playlists["playlist_info"] and "password" in playlists["playlist_info"]:
                    if playlists["playlist_info"]["domain"] == self.domain and playlists["playlist_info"]["username"] == self.username and playlists["playlist_info"]["password"] == self.password:
                        self.playlists_all[x] = glob.current_playlist
                        break
                x += 1

        self.writeJsonFile()

    def writeJsonFile(self):
        with open(playlists_json, "w") as f:
            json.dump(self.playlists_all, f)
        self.clear_caches()
        self.close()
