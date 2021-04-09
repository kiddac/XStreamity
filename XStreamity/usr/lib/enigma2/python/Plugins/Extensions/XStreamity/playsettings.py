#!/usr/bin/python
# -*- coding: utf-8 -*-

# for localized messages
from . import _
from . import xstreamity_globals as glob
from .plugin import skin_path, cfg, playlist_path, json_file
from .xStaticText import StaticText

from Components.ActionMap import ActionMap
from Components.ConfigList import ConfigListScreen
from Components.config import getConfigListEntry, ConfigText, ConfigSelection, ConfigSelectionNumber, ConfigNumber, ConfigYesNo, ConfigEnableDisable, NoSave
from Components.Pixmap import Pixmap
from Screens.MessageBox import MessageBox
from Screens.ParentalControlSetup import ProtectedScreen
from Screens.Screen import Screen

import os
import json


class XStreamity_Settings(ConfigListScreen, Screen):

    def __init__(self, session):
        Screen.__init__(self, session)

        self.session = session

        skin = skin_path + 'settings.xml'

        if os.path.exists('/var/lib/dpkg/status'):
            skin = skin_path + 'DreamOS/settings.xml'

        with open(skin, 'r') as f:
            self.skin = f.read()

        self.setup_title = (_('Playlist Settings'))

        self.onChangedEntry = []

        self.list = []
        ConfigListScreen.__init__(self, self.list, session=self.session, on_change=self.changedEntry)

        self['key_red'] = StaticText(_('Back'))
        self['key_green'] = StaticText(_('Save'))

        self['VirtualKB'].setEnabled(False)
        self['VKeyIcon'] = Pixmap()
        self['VKeyIcon'].hide()
        self['HelpWindow'] = Pixmap()
        self['HelpWindow'].hide()

        self['actions'] = ActionMap(['XStreamityActions'], {
            'cancel': self.cancel,
            'red': self.cancel,
            'green': self.save,
        }, -2)

        self.onFirstExecBegin.append(self.initConfig)

        self.onLayoutFinish.append(self.__layoutFinished)

    def __layoutFinished(self):
        self.setTitle(self.setup_title)

    def cancel(self, answer=None):
        if answer is None:
            if self['config'].isChanged():
                self.session.openWithCallback(self.cancel, MessageBox, _('Really close without saving settings?'))
            else:
                self.close()
        elif answer:
            for x in self['config'].list:
                x[1].cancel()

            self.close()
        return

    def initConfig(self):
        streamtypechoices = [('1', 'DVB(1)'), ('4097', 'IPTV(4097)')]

        if os.path.exists("/usr/bin/gstplayer"):
            streamtypechoices.append(('5001', 'GStreamer(5001)'))

        if os.path.exists("/usr/bin/exteplayer3"):
            streamtypechoices.append(('5002', 'ExtePlayer(5002)'))

        if os.path.exists("/usr/bin/apt-get"):
            streamtypechoices.append(('8193', 'DreamOS GStreamer(8193)'))

        self.name = str(glob.current_playlist['playlist_info']['name'])
        self.output = str(glob.current_playlist['playlist_info']['output'])
        self.liveType = str(glob.current_playlist['player_info']['livetype'])
        self.vodType = str(glob.current_playlist['player_info']['vodtype'])
        self.catchupType = str(glob.current_playlist['player_info']['catchuptype'])
        # self.epgType = str(glob.current_playlist['player_info']['epgtype'])
        self.epgUrl = str(glob.current_playlist['playlist_info']['xmltv_api'])
        self.epgshift = str(glob.current_playlist['player_info']['epgshift'])
        self.catchupshift = str(glob.current_playlist['player_info']['catchupshift'])
        # self.epgquickshift = str(glob.current_playlist['player_info']['epgquickshift'])
        self.showlive = glob.current_playlist['player_info']['showlive']
        self.showvod = glob.current_playlist['player_info']['showvod']
        self.showseries = glob.current_playlist['player_info']['showseries']
        self.showcatchup = glob.current_playlist['player_info']['showcatchup']

        self.nameCfg = NoSave(ConfigText(default=self.name, fixed_size=False))
        self.outputCfg = NoSave(ConfigSelection(default=self.output, choices=[('ts', 'ts'), ('m3u8', 'm3u8')]))
        self.liveTypeCfg = NoSave(ConfigSelection(default=self.liveType, choices=streamtypechoices))
        self.vodTypeCfg = NoSave(ConfigSelection(default=self.vodType, choices=streamtypechoices))
        self.catchupTypeCfg = NoSave(ConfigSelection(default=self.catchupType, choices=streamtypechoices))
        # self.epgTypeCfg = NoSave(ConfigSelection(default=self.epgType, choices=[('0', _('Off')), ('1', _('Quick')), ('2', _('XMLTV EPG (EPG Importer)'))]))

        self.epgUrlCfg = NoSave(ConfigText(default=self.epgUrl))

        self.epgShiftCfg = NoSave(ConfigSelectionNumber(min=-9, max=9, stepwidth=1, default=self.epgshift))
        self.catchupShiftCfg = NoSave(ConfigSelectionNumber(min=-9, max=9, stepwidth=1, default=self.catchupshift))
        # self.epgQuickShiftCfg = NoSave(ConfigSelectionNumber(min=-12, max=12, stepwidth=1, default=self.epgquickshift))
        self.showliveCfg = NoSave(ConfigYesNo(default=self.showlive))
        self.showvodCfg = NoSave(ConfigYesNo(default=self.showvod))
        self.showseriesCfg = NoSave(ConfigYesNo(default=self.showseries))
        self.showcatchupCfg = NoSave(ConfigYesNo(default=self.showcatchup))

        self.createSetup()

    def createSetup(self):
        self.list = []
        self.list.append(getConfigListEntry(_('Short name or provider name:'), self.nameCfg))
        self.list.append(getConfigListEntry(_('Output:'), self.outputCfg))

        self.list.append(getConfigListEntry(_('Show LIVE category:'), self.showliveCfg))
        self.list.append(getConfigListEntry(_('Show VOD category:'), self.showvodCfg))
        self.list.append(getConfigListEntry(_('Show SERIES category:'), self.showseriesCfg))
        self.list.append(getConfigListEntry(_('Show CATCHUP category:'), self.showcatchupCfg))

        if self.showliveCfg.value is True:
            self.list.append(getConfigListEntry(_('Stream Type LIVE:'), self.liveTypeCfg))

        if self.showvodCfg.value is True or self.showseriesCfg.value is True:
            self.list.append(getConfigListEntry(_('Stream Type VOD/SERIES:'), self.vodTypeCfg))

        if self.showcatchupCfg.value is True:
            self.list.append(getConfigListEntry(_('Stream Type CATCHUP:'), self.catchupTypeCfg))

        if self.showliveCfg.value is True:
            """
            self.list.append(getConfigListEntry(_('EPG Type:'), self.epgTypeCfg))

            if self.epgTypeCfg.value == '2':
                self.list.append(getConfigListEntry(_('XMLTV EPG Url:'), self.epgUrlCfg))
                """

            self.list.append(getConfigListEntry(_('Full EPG Timeshift:'), self.epgShiftCfg))
            self.list.append(getConfigListEntry(_('Catchup Timeshift:'), self.catchupShiftCfg))

            self.list.append(getConfigListEntry(_('XMLTV EPG Url:'), self.epgUrlCfg))

            """
            if self.epgTypeCfg.value == '1':
                # self.list.append(getConfigListEntry(_('Quick EPG Timeshift:'), self.epgQuickShiftCfg))
                """
            # self.list.append(getConfigListEntry(_('Quick EPG Timeshift:'), self.epgQuickShiftCfg))

        self['config'].list = self.list
        self['config'].l.setList(self.list)
        self.handleInputHelpers()

    def handleInputHelpers(self):
        from enigma import ePoint
        currConfig = self["config"].getCurrent()

        if currConfig is not None:
            if isinstance(currConfig[1], ConfigText):
                if 'VKeyIcon' in self:
                    if isinstance(currConfig[1], ConfigNumber):
                        self['VirtualKB'].setEnabled(False)
                        self['VKeyIcon'].hide()
                    else:
                        self['VirtualKB'].setEnabled(True)
                        self['VKeyIcon'].show()

                if "HelpWindow" in self and currConfig[1].help_window and currConfig[1].help_window.instance is not None:
                    helpwindowpos = self["HelpWindow"].getPosition()
                    currConfig[1].help_window.instance.move(ePoint(helpwindowpos[0], helpwindowpos[1]))
            else:
                if 'VKeyIcon' in self:
                    self['VirtualKB'].setEnabled(False)
                    self['VKeyIcon'].hide()

    def changedEntry(self):
        self.item = self['config'].getCurrent()
        for x in self.onChangedEntry:
            x()

        try:
            if isinstance(self['config'].getCurrent()[1], ConfigEnableDisable) or isinstance(self['config'].getCurrent()[1], ConfigYesNo) or isinstance(self['config'].getCurrent()[1], ConfigSelection):
                self.createSetup()
        except:
            pass

    def getCurrentEntry(self):
        return self['config'].getCurrent() and self['config'].getCurrent()[0] or ''

    def getCurrentValue(self):
        return self['config'].getCurrent() and str(self['config'].getCurrent()[1].getText()) or ''

    def save(self):
        self.protocol = glob.current_playlist['playlist_info']['protocol']
        self.domain = glob.current_playlist['playlist_info']['domain']
        self.port = glob.current_playlist['playlist_info']['port']
        self.username = glob.current_playlist['playlist_info']['username']
        self.password = glob.current_playlist['playlist_info']['password']
        self.listtype = "m3u"
        self.host = "%s%s:%s" % (self.protocol, self.domain, self.port)

        if self['config'].isChanged():
            self.name = self.nameCfg.value.strip()
            output = self.outputCfg.value

            showlive = self.showliveCfg.value
            showvod = self.showvodCfg.value
            showseries = self.showseriesCfg.value
            showcatchup = self.showcatchupCfg.value

            livetype = self.liveTypeCfg.value
            vodtype = self.vodTypeCfg.value
            catchuptype = self.catchupTypeCfg.value

            epgshift = self.epgShiftCfg.value
            catchupshift = self.catchupShiftCfg.value
            # epgtype = self.epgTypeCfg.value
            epgurl = self.epgUrlCfg.value
            # epgquickshift = self.epgQuickShiftCfg.value

            glob.current_playlist['playlist_info']['name'] = self.name
            glob.current_playlist['playlist_info']['output'] = output
            glob.current_playlist['player_info']['showlive'] = showlive
            glob.current_playlist['player_info']['showvod'] = showvod
            glob.current_playlist['player_info']['showseries'] = showseries
            glob.current_playlist['player_info']['showcatchup'] = showcatchup
            glob.current_playlist['player_info']['livetype'] = livetype
            glob.current_playlist['player_info']['vodtype'] = vodtype
            glob.current_playlist['player_info']['catchuptype'] = catchuptype
            # glob.current_playlist['player_info']['epgtype'] = epgtype

            glob.current_playlist['player_info']['xmltv_api'] = epgurl

            glob.current_playlist['player_info']['epgshift'] = epgshift
            glob.current_playlist['player_info']['catchupshift'] = catchupshift
            # glob.current_playlist['player_info']['epgquickshift'] = epgquickshift

            playlistline = '%s%s:%s/get.php?username=%s&password=%s&type=%s&output=%s&timeshift=%s #%s' % (self.protocol, self.domain, self.port, self.username, self.password, self.listtype, output, epgshift, self.name)
            self.full_url = "%s/get.php?username=%s&password=%s&type=%s&output=%s" % (self.host, self.username, self.password, self.listtype, self.output)
            glob.current_playlist["playlist_info"]["full_url"] = self.full_url

            # update playlists.txt file
            if not os.path.isfile(playlist_path):
                with open(playlist_path, 'w+') as f:
                    f.close()

            with open(playlist_path, 'r+') as f:
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
        if os.path.isfile(json_file):
            with open(json_file, "r") as f:
                try:
                    self.playlists_all = json.load(f)
                except:
                    os.remove(json_file)

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
        with open(json_file, 'w') as f:
            json.dump(self.playlists_all, f)
        self.close()
