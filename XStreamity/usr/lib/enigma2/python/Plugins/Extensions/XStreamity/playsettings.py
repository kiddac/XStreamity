#!/usr/bin/python
# -*- coding: utf-8 -*-

from . import _
from . import xstreamity_globals as glob
from .plugin import skin_directory, playlist_file, playlists_json, cfg
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
except ImportError:
    from urllib.parse import urlparse, parse_qs


class XStreamity_Settings(ConfigListScreen, Screen):
    ALLOW_SUSPEND = True

    def __init__(self, session):
        Screen.__init__(self, session)
        self.session = session

        skin_path = os.path.join(skin_directory, cfg.skin.getValue())
        skin = os.path.join(skin_path, "settings.xml")

        if os.path.exists("/var/lib/dpkg/status"):
            skin = os.path.join(skin_path, "DreamOS/settings.xml")

        with open(skin, "r") as f:
            self.skin = f.read()

        self.setup_title = _("Playlist Settings")

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
            with open("/proc/sys/vm/drop_caches", "w") as drop_caches:
                drop_caches.write("1\n2\n3\n")
        except IOError:
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

        playlist_info = glob.current_playlist.get("playlist_info", {})
        player_info = glob.current_playlist.get("player_info", {})

        self.name = str(playlist_info.get("name", ""))
        self.output = str(playlist_info.get("output", ""))
        self.liveType = str(player_info.get("livetype", ""))
        self.vodType = str(player_info.get("vodtype", ""))
        self.showlive = player_info.get("showlive", False)
        self.showvod = player_info.get("showvod", False)
        self.showseries = player_info.get("showseries", False)
        self.showcatchup = player_info.get("showcatchup", False)
        self.epgoffset = player_info.get("epgoffset", 0)
        self.epgalternative = player_info.get("epgalternative", False)
        self.epgalternativeurl = player_info.get("epgalternativeurl", "")
        self.directsource = player_info.get("directsource", "Standard")

        self.nameCfg = NoSave(ConfigText(default=self.name, fixed_size=False))
        self.outputCfg = NoSave(ConfigSelection(default=self.output, choices=[("ts", "ts"), ("m3u8", "m3u8")]))
        self.liveTypeCfg = NoSave(ConfigSelection(default=self.liveType, choices=live_streamtype_choices))
        self.vodTypeCfg = NoSave(ConfigSelection(default=self.vodType, choices=vod_streamtype_choices))
        self.showliveCfg = NoSave(ConfigYesNo(default=self.showlive))
        self.showvodCfg = NoSave(ConfigYesNo(default=self.showvod))
        self.showseriesCfg = NoSave(ConfigYesNo(default=self.showseries))
        self.showcatchupCfg = NoSave(ConfigYesNo(default=self.showcatchup))
        self.epgoffsetCfg = NoSave(ConfigSelectionNumber(-9, 9, 1, default=self.epgoffset, wraparound=True))
        self.epgalternativeCfg = NoSave(ConfigYesNo(default=self.epgalternative))
        self.epgalternativeurlCfg = NoSave(ConfigText(default=self.epgalternativeurl, fixed_size=False))
        self.directsourceCfg = NoSave(ConfigSelection(default=self.directsource, choices=[("Standard", "Standard"), ("Direct Source", "Direct Source")]))

        self.createSetup()

    def createSetup(self):
        self.list = [
            getConfigListEntry(_("Short name or provider name:"), self.nameCfg),
            getConfigListEntry(_("Show LIVE category:"), self.showliveCfg),
            getConfigListEntry(_("Show VOD category:"), self.showvodCfg),
            getConfigListEntry(_("Show SERIES category:"), self.showseriesCfg),
            getConfigListEntry(_("Show CATCHUP category:"), self.showcatchupCfg),
            getConfigListEntry(_("Output:"), self.outputCfg)
        ]

        if self.showliveCfg.value:
            self.list.append(getConfigListEntry(_("Stream Type LIVE:"), self.liveTypeCfg))

        if self.showvodCfg.value or self.showseriesCfg.value:
            self.list.append(getConfigListEntry(_("Stream Type VOD/SERIES:"), self.vodTypeCfg))

        self.list.extend([
            getConfigListEntry(_("Stream Source URL:"), self.directsourceCfg),
            getConfigListEntry(_("EPG offset:"), self.epgoffsetCfg),
            getConfigListEntry(_("Use alternative EPG url:"), self.epgalternativeCfg)
        ])

        if self.epgalternativeCfg.value:
            self.list.append(getConfigListEntry(_("Alternative EPG url:"), self.epgalternativeurlCfg))

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
        self.playlists_all = self.getPlaylistJson()

        playlist_info = glob.current_playlist.get("playlist_info", {})
        player_info = glob.current_playlist.get("player_info", {})

        self.protocol = playlist_info.get("protocol", "")
        self.domain = playlist_info.get("domain", "")
        self.port = playlist_info.get("port", "")
        self.username = playlist_info.get("username", "")
        self.password = playlist_info.get("password", "")
        self.listtype = "m3u"

        self.host = "{}{}:{}".format(self.protocol, self.domain, self.port) if self.port else "{}{}".format(self.protocol, self.domain)

        if self["config"].isChanged():
            self.name = self.nameCfg.value.strip()
            self.full_url = playlist_info.get("full_url", "")

            if not self.name or len(self.name) < 3:
                self.session.open(MessageBox, _("Bouquet name cannot be blank. Please enter a unique bouquet name. Minimum 3 characters."), MessageBox.TYPE_ERROR, timeout=10)
                return

            if self.playlists_all:
                for playlist in self.playlists_all:
                    if playlist["playlist_info"]["name"] == self.name and str(playlist["playlist_info"]["full_url"]) != str(playlist_info.get("full_url", "")):
                        self.session.open(MessageBox, _("Name already used. Please enter a unique name."), MessageBox.TYPE_ERROR, timeout=10)
                        return

            output = self.outputCfg.value
            showlive = self.showliveCfg.value
            showvod = self.showvodCfg.value
            showseries = self.showseriesCfg.value
            showcatchup = self.showcatchupCfg.value
            livetype = self.liveTypeCfg.value
            if output == "m3u8" and livetype == "1":
                livetype = "4097"

            vodtype = self.vodTypeCfg.value
            epgoffset = int(self.epgoffsetCfg.value)
            epgalternative = self.epgalternativeCfg.value
            epgalternativeurl = self.epgalternativeurlCfg.value
            directsource = self.directsourceCfg.value

            playlist_info["name"] = self.name
            playlist_info["output"] = output
            player_info["showlive"] = showlive
            player_info["showvod"] = showvod
            player_info["showseries"] = showseries
            player_info["showcatchup"] = showcatchup
            player_info["livetype"] = livetype
            player_info["vodtype"] = vodtype
            player_info["epgoffset"] = epgoffset
            player_info["epgalternative"] = epgalternative
            player_info["epgalternativeurl"] = epgalternativeurl
            player_info["directsource"] = directsource

            playlistline = "{}/get.php?username={}&password={}&type={}&output={}&timeshift={} #{}".format(
                self.host, self.username, self.password, self.listtype, output, epgoffset, self.name)
            self.full_url = "{}/get.php?username={}&password={}&type={}&output={}".format(
                self.host, self.username, self.password, self.listtype, output)

            playlist_info["full_url"] = self.full_url
            if epgalternativeurl:
                player_info["xmltv_api"] = epgalternativeurl

            # Update playlists.txt file
            if not os.path.isfile(playlist_file):
                with open(playlist_file, "w+") as f:
                    f.close()

            with open(playlist_file, "r+") as f:
                lines = f.readlines()
                f.seek(0)
                exists = False
                for line in lines:
                    hastimeshift = False
                    if all(x in line for x in [self.domain, self.username, self.password]):
                        parsed_uri = urlparse(line)
                        protocol = parsed_uri.scheme + "://"
                        domain = parsed_uri.hostname
                        port = parsed_uri.port or ""
                        host = "{}{}".format(protocol, domain + (":" + str(port) if port else ""))

                        query = parse_qs(parsed_uri.query, keep_blank_values=True)

                        username = query.get("username", [None])[0]
                        password = query.get("password", [None])[0]

                        if username is None or password is None:
                            continue

                        hastimeshift = "timeshift" in query

                        if hastimeshift or int(epgoffset) != 0:
                            playlistline = "{}/get.php?username={}&password={}&type={}&output={}&timeshift={} #{}".format(
                                host, username.strip(), password.strip(), self.listtype, output, epgoffset, self.name)
                        else:
                            playlistline = "{}/get.php?username={}&password={}&type={}&output={} #{}".format(
                                host, username.strip(), password.strip(), self.listtype, output, self.name)

                        line = str(playlistline) + "\n"
                        exists = True
                    f.write(line)
                if not exists:
                    f.write("\n{}\n".format(playlistline))

        self.getPlaylistUserFile()

    def load_playlists(self):
        playlists_all = []
        if os.path.exists(playlists_json) and os.stat(playlists_json).st_size > 0:
            try:
                with open(playlists_json) as f:
                    playlists_all = json.load(f)
            except json.JSONDecodeError as e:
                print(f"Error loading playlists from {playlists_json}: {e}")
                os.remove(playlists_json)
        return playlists_all

    def getPlaylistUserFile(self):
        for index, playlist in enumerate(self.playlists_all):
            playlist_info = playlist.get("playlist_info", {})
            if all(key in playlist_info for key in ["domain", "username", "password"]):
                if (playlist_info["domain"], playlist_info["username"], playlist_info["password"]) == (self.domain, self.username, self.password):
                    self.playlists_all[index] = glob.current_playlist
                    break

        self.writeJsonFile()

    def writeJsonFile(self):
        with open(playlists_json, "w") as f:
            json.dump(self.playlists_all, f)
        self.clear_caches()
        self.close()
