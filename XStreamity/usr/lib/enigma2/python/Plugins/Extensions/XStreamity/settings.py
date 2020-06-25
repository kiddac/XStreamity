#!/usr/bin/python
# -*- coding: utf-8 -*-

# for localized messages
from . import _

from Components.ActionMap import ActionMap
from Components.ConfigList import ConfigListScreen
from Components.config import config, configfile, getConfigListEntry, ConfigText, ConfigSelection, ConfigNumber, ConfigPassword, ConfigYesNo, ConfigEnableDisable
from Components.Pixmap import Pixmap
from plugin import skin_path, cfg
from Screens.LocationBox import LocationBox
from Screens.MessageBox import MessageBox
from Screens.ParentalControlSetup import ProtectedScreen
from Screens.Screen import Screen
from xStaticText import StaticText

import xstreamity_globals as glob
import os


class XStreamity_Settings(ConfigListScreen, Screen, ProtectedScreen):

    def __init__(self, session):
        Screen.__init__(self, session)

        if cfg.parental.getValue() is True:
            ProtectedScreen.__init__(self)
        self.session = session

        skin = skin_path + 'settings.xml'

        if os.path.exists('/var/lib/dpkg/status'):
            skin = skin_path + 'DreamOS/settings.xml'

        with open(skin, 'r') as f:
            self.skin = f.read()

        self.setup_title = (_('Main Settings'))

        self.onChangedEntry = []

        self.list = []
        ConfigListScreen.__init__(self, self.list, session=self.session, on_change=self.changedEntry)

        self['key_red'] = StaticText(_('Close'))
        self['key_green'] = StaticText(_('Save'))

        self['VirtualKB'].setEnabled(False)
        self['HelpWindow'] = Pixmap()
        self['VKeyIcon'] = Pixmap()
        self['HelpWindow'].hide()
        self['VKeyIcon'].hide()

        self['actions'] = ActionMap(['XStreamityActions'], {
            'cancel': self.cancel,
            'red': self.cancel,
            'green': self.save,
            'ok': self.ok,
        }, -2)

        self.initConfig()

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


    def save(self):
        glob.changed = False
        if self['config'].isChanged():
            glob.changed = True
            for x in self['config'].list:
                x[1].save()
            cfg.save()
            configfile.save()
        self.close()


    def initConfig(self):
        self.cfg_skin = getConfigListEntry(_('Select skin *Restart GUI Required'), cfg.skin)
        self.cfg_location = getConfigListEntry(_('playlists.txt location'), cfg.location)
        self.cfg_timeout = getConfigListEntry(_('Server timeout (seconds)'), cfg.timeout)

        self.cfg_livetype = getConfigListEntry(_('Default LIVE stream type'), cfg.livetype)
        self.cfg_vodtype = getConfigListEntry(_('Default VOD/SERIES stream type'), cfg.vodtype)
        self.cfg_catchuptype = getConfigListEntry(_('Default CATCHUP stream type'), cfg.vodtype)

        self.cfg_livepreview = getConfigListEntry(_('Preview LIVE streams in mini tv before playing'), cfg.livepreview)
        # self.cfg_stopstream = getConfigListEntry(_('Stop stream on back button'), cfg.stopstream)
        self.cfg_downloadlocation = getConfigListEntry(_('VOD download folder'), cfg.downloadlocation)
        self.cfg_parental = getConfigListEntry(_('Parental control'), cfg.parental)
        self.cfg_main = getConfigListEntry(_('Show in main menu *Restart GUI Required'), cfg.main)

        self.cfg_refreshTMDB = getConfigListEntry(_('Update VOD Movie Database information'), cfg.refreshTMDB)
        self.cfg_TMDBLanguage = getConfigListEntry(_('VOD Movie Database language'), cfg.TMDBLanguage)

        self.cfg_catchupstart = getConfigListEntry(_('Margin before catchup (mins)'), cfg.catchupstart)
        self.cfg_catchupend = getConfigListEntry(_('Margin after catchup (mins)'), cfg.catchupend)

        self.createSetup()


    def createSetup(self):
        self.list = []
        self.list.append(self.cfg_skin)
        self.list.append(self.cfg_location)
        self.list.append(self.cfg_timeout)

        self.list.append(self.cfg_livetype)
        self.list.append(self.cfg_vodtype)
        self.list.append(self.cfg_catchuptype)

        self.list.append(self.cfg_livepreview)
        # self.list.append(self.cfg_stopstream)

        self.list.append(self.cfg_downloadlocation)

        self.list.append(self.cfg_refreshTMDB)
        if cfg.refreshTMDB.value is True:
            self.list.append(self.cfg_TMDBLanguage)

        self.list.append(self.cfg_catchupstart)
        self.list.append(self.cfg_catchupend)

        self.list.append(self.cfg_parental)

        self.list.append(self.cfg_main)
        self['config'].list = self.list
        self['config'].l.setList(self.list)
        self.handleInputHelpers()


    def handleInputHelpers(self):
        if self['config'].getCurrent() is not None:
            if isinstance(self['config'].getCurrent()[1], ConfigText) or isinstance(self['config'].getCurrent()[1], ConfigPassword):

                if 'VKeyIcon' in self:
                    if isinstance(self['config'].getCurrent()[1], ConfigNumber):
                        self['VirtualKB'].setEnabled(False)
                        self['VKeyIcon'].hide()
                    else:
                        self['VirtualKB'].setEnabled(True)
                        self['VKeyIcon'].show()

                if not isinstance(self['config'].getCurrent()[1], ConfigNumber):

                    if isinstance(self['config'].getCurrent()[1].help_window, ConfigText) or isinstance(self['config'].getCurrent()[1].help_window, ConfigPassword):
                        if self['config'].getCurrent()[1].help_window.instance is not None:
                            helpwindowpos = self['HelpWindow'].getPosition()

                            if helpwindowpos:
                                helpwindowposx, helpwindowposy = helpwindowpos
                                if helpwindowposx and helpwindowposy:
                                    from enigma import ePoint
                                    self['config'].getCurrent()[1].help_window.instance.move(ePoint(helpwindowposx, helpwindowposy))

            else:
                if 'VKeyIcon' in self:
                    self['VirtualKB'].setEnabled(False)
                    self['VKeyIcon'].hide()
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


    def ok(self):
        ConfigListScreen.keyOK(self)
        sel = self['config'].getCurrent()[1]
        if sel and sel == cfg.location:
            self.openDirectoryBrowser(cfg.location.value, "location")
        elif sel and sel == cfg.downloadlocation:
            self.openDirectoryBrowser(cfg.downloadlocation.value, "downloadlocation")
        else:
            pass


    def openDirectoryBrowser(self, path, cfgitem):
        if cfgitem == "location":
            try:
                self.session.openWithCallback(
                 self.openDirectoryBrowserCB,
                 LocationBox,
                 windowTitle=_('Choose Directory:'),
                 text=_('Choose directory'),
                 currDir=str(path),
                 bookmarks=config.movielist.videodirs,
                 autoAdd=False,
                 editDir=True,
                 inhibitDirs=['/bin', '/boot', '/dev', '/home', '/lib', '/proc', '/run', '/sbin', '/sys', '/var'],
                 minFree=15)
            except Exception as e:
                print(e)
            except:
                pass

        if cfgitem == "downloadlocation":
            try:
                self.session.openWithCallback(
                 self.openDirectoryBrowserCB2,
                 LocationBox,
                 windowTitle=_('Choose Directory:'),
                 text=_('Choose directory'),
                 currDir=str(path),
                 bookmarks=config.movielist.videodirs,
                 autoAdd=False,
                 editDir=True,
                 inhibitDirs=['/bin', '/boot', '/dev', '/home', '/lib', '/proc', '/run', '/sbin', '/sys', '/var'],
                 minFree=15)
            except Exception as e:
                print(e)
            except:
                pass


    def openDirectoryBrowserCB(self, path):
        if path is not None:
            cfg.location.setValue(path)
        return


    def openDirectoryBrowserCB2(self, path):
        if path is not None:
            cfg.downloadlocation.setValue(path)
        return
