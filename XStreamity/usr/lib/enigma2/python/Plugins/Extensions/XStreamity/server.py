from . import _

from .plugin import skin_path, playlist_path
from .xStaticText import StaticText

from Components.ActionMap import ActionMap
from Components.ConfigList import ConfigListScreen
from Components.config import getConfigListEntry, NoSave, ConfigText, ConfigSelection, ConfigNumber, ConfigYesNo, ConfigEnableDisable
from Components.Pixmap import Pixmap
from Screens.MessageBox import MessageBox
from Screens.Screen import Screen

import os


class XStreamity_AddServer(ConfigListScreen, Screen):

    def __init__(self, session):
        Screen.__init__(self, session)
        self.session = session

        skin = skin_path + 'settings.xml'

        if os.path.exists('/var/lib/dpkg/status'):
            skin = skin_path + 'DreamOS/settings.xml'

        with open(skin, 'r') as f:
            self.skin = f.read()

        self.setup_title = (_('Add Xtream Codes Playlist'))

        self.onChangedEntry = []

        self.list = []
        ConfigListScreen.__init__(self, self.list, session=self.session, on_change=self.changedEntry)

        self['key_red'] = StaticText(_('Back'))
        self['key_green'] = StaticText(_('Save'))

        self['VKeyIcon'] = Pixmap()
        self['VKeyIcon'].hide()
        self['HelpWindow'] = Pixmap()
        self['HelpWindow'].hide()

        self.protocol = 'http://'
        self.server = 'domain.xyz'
        self.port = 80
        self.username = 'username'
        self.password = 'password'
        self.listType = 'm3u'
        self.output = 'ts'

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
        self.nameCfg = NoSave(ConfigText(default="IPTV", fixed_size=False))
        self.protocolCfg = NoSave(ConfigSelection(default=self.protocol, choices=[('http://', _('http://')), ('https://', _('https://'))]))
        self.serverCfg = NoSave(ConfigText(default=self.server, fixed_size=False))
        self.portCfg = NoSave(ConfigNumber(default=self.port))
        self.usernameCfg = NoSave(ConfigText(default=self.username, fixed_size=False))
        self.passwordCfg = NoSave(ConfigText(default=self.password, fixed_size=False))
        self.outputCfg = NoSave(ConfigSelection(default=self.output, choices=[('ts', 'ts'), ('m3u8', 'm3u8')]))
        self.createSetup()

    def createSetup(self):
        self.list = []

        self.list.append(getConfigListEntry(_('Short name or provider name:'), self.nameCfg))
        self.list.append(getConfigListEntry(_('Protocol:'), self.protocolCfg))
        self.list.append(getConfigListEntry(_('Server URL:'), self.serverCfg))
        self.list.append(getConfigListEntry(_('Port:'), self.portCfg))
        self.list.append(getConfigListEntry(_('Username:'), self.usernameCfg))
        self.list.append(getConfigListEntry(_('Password:'), self.passwordCfg))
        self.list.append(getConfigListEntry(_('Output:'), self.outputCfg))

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

    def save(self):
        if self['config'].isChanged():

            self.name = self.nameCfg.value.strip()
            protocol = self.protocolCfg.value
            domain = self.serverCfg.value.strip()
            port = self.portCfg.value
            username = self.usernameCfg.value.strip()
            password = self.passwordCfg.value.strip()
            listtype = "m3u"
            output = self.outputCfg.value

            playlistline = '%s%s:%s/get.php?username=%s&password=%s&type=%s&output=%s #%s' % (protocol, domain, port, username, password, listtype, output, self.name)
            self.apiline = '%s%s:%s/player_api.php?username=%s&password=%s' % (protocol, domain, port, username, password)

            valid = self.checkline()

            if not valid:
                self.session.open(MessageBox, _("URL is not a valid or unauthorised"), type=MessageBox.TYPE_INFO, timeout=5)
                return

            # update playlists.txt file
            if not os.path.isfile(playlist_path):
                with open(playlist_path, 'w+') as f:
                    f.close()

            with open(playlist_path, 'r') as f:
                lines = f.readlines()
                exists = False
                for line in lines:
                    if domain in line and username in line and password in line:
                        exists = True

            if exists is False:
                with open(playlist_path, 'a') as f:
                    f.write("\n" + str(playlistline) + "\n")
            self.session.open(MessageBox, _("Playlist added successfully."), type=MessageBox.TYPE_INFO, timeout=5)
            self.close()

    def changedEntry(self):
        self.item = self['config'].getCurrent()
        for x in self.onChangedEntry:
            x()
        try:
            if isinstance(self['config'].getCurrent()[1], ConfigEnableDisable) or isinstance(self['config'].getCurrent()[1], ConfigYesNo) or isinstance(self['config'].getCurrent()[1], ConfigSelection):
                self.createSetup()
        except:
            pass

    def checkline(self):
        import requests
        valid = False
        try:
            r = requests.get(self.apiline, allow_redirects=True)
            if r.status_code == 200:
                response = r.json()
                if 'user_info' in response:
                    if 'auth' in response['user_info']:
                        if response['user_info']['auth'] == 1:
                            valid = True

        except requests.exceptions.ConnectionError as e:
            print(("Error Connecting: %s" % e))

        except requests.exceptions.RequestException as e:
            print(e)

        return valid
