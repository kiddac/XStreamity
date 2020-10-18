#!/usr/bin/python
# -*- coding: utf-8 -*-

# for localized messages

from . import _
from . import xstreamity_globals as glob
from . import processfiles as xfiles
from .plugin import skin_path, common_path, VERSION
from .xStaticText import StaticText

from Components.ActionMap import ActionMap
from Components.Sources.List import List
from enigma import eServiceReference
from os import system, chmod
from Screens.Console import Console
from Screens.Screen import Screen
from Tools.LoadPixmap import LoadPixmap

import os
import sys

try:
    pythonVer = sys.version_info.major
except:
    pythonVer = 2


class XStreamity_MainMenu(Screen):

    def __init__(self, session):
        Screen.__init__(self, session)
        self.session = session

        skin = skin_path + 'mainmenu.xml'
        with open(skin, 'r') as f:
            self.skin = f.read()

        self.list = []
        self.drawList = []
        self["list"] = List(self.drawList, enableWrapAround=True)

        self.setup_title = (_('Main Menu'))

        self['key_red'] = StaticText(_('Back'))
        self['key_green'] = StaticText(_('OK'))

        self['version'] = StaticText()

        self['actions'] = ActionMap(['XStreamityActions'], {
            'red': self.quit,
            'green': self.__next__,
            'ok': self.__next__,
            'cancel': self.quit,
            'menu': self.settings,
        }, -2)

        self.clear_caches()
        self['version'].setText(VERSION)

        if self.session.nav.getCurrentlyPlayingServiceReference():
            glob.currentPlayingServiceRef = self.session.nav.getCurrentlyPlayingServiceReference()
            glob.currentPlayingServiceRefString = self.session.nav.getCurrentlyPlayingServiceReference().toString()
            glob.newPlayingServiceRef = self.session.nav.getCurrentlyPlayingServiceReference()
            glob.newPlayingServiceRefString = glob.newPlayingServiceRef.toString()

        self.onFirstExecBegin.append(self.check_dependencies)
        self.onLayoutFinish.append(self.__layoutFinished)

    def __layoutFinished(self):
        self.setTitle(self.setup_title)

    def check_dependencies(self):
        dependencies = True

        """
        if pythonVer == 3:
            if os.path.exists("/usr/bin/apt-get"):
                if not os.path.isfile("/usr/lib/python/imghdr.py") \
                    or not os.path.exists("/usr/lib/python/site-packages/PIL") \
                        or not os.path.exists("/usr/lib/python/site-packages/requests") \
                        or not os.path.exists("/usr/lib/python/multiprocessing"):
                    dependencies = False
            else:
                if not os.path.isfile("/usr/lib/python3.8/imghdr.py") \
                    or not os.path.exists("/usr/lib/python3.8/site-packages/PIL") \
                        or not os.path.exists("/usr/lib/python3.8/site-packages/requests") \
                        or not os.path.exists("/usr/lib/python3.8/multiprocessing"):
                    dependencies = False

        else:
            if not os.path.isfile("/usr/lib/python2.7/imghdr.pyo") \
                or not os.path.exists("/usr/lib/python2.7/site-packages/PIL") \
                    or not os.path.exists("/usr/lib/python2.7/site-packages/requests") \
                    or not os.path.exists("/usr/lib/python2.7/multiprocessing"):
                dependencies = False
                """

        try:
            import requests
            from multiprocessing.pool import ThreadPool
            from PIL import Image
        except:
            dependencies = False

        if dependencies is False:
            chmod("/usr/lib/enigma2/python/Plugins/Extensions/XStreamity/dependencies.sh", 0o0755)
            cmd1 = ". /usr/lib/enigma2/python/Plugins/Extensions/XStreamity/dependencies.sh"
            self.session.openWithCallback(self.start, Console, title="Checking Python Dependencies", cmdlist=[cmd1], closeOnSuccess=False)
        else:
            self.start()

    def clear_caches(self):
        try:
            system("echo 1 > /proc/sys/vm/drop_caches")
            system("echo 2 > /proc/sys/vm/drop_caches")
            system("echo 3 > /proc/sys/vm/drop_caches")
        except:
            pass

    def start(self):
        self.playlists_all = xfiles.processfiles()
        self.createSetup()

    def createSetup(self):
        self.list = []
        if len(self.playlists_all):
            glob.oneplaylist = True

        if self.playlists_all:
            self.list.append([1, "Playlists"])
            self.list.append([2, "Main Settings"])
            self.list.append([3, "Add Playlist"])
        else:
            self.list.append([3, "Add Playlist"])

        self.drawList = []
        self.drawList = [buildListEntry(x[0], x[1]) for x in self.list]
        self["list"].setList(self.drawList)

    def playlists(self):
        from . import playlists
        self.session.openWithCallback(self.start, playlists.XStreamity_Playlists)
        return

    def settings(self):
        from . import settings
        self.session.openWithCallback(self.start, settings.XStreamity_Settings)

    def addServer(self):
        from . import server
        self.session.openWithCallback(self.start, server.XStreamity_AddServer)
        return

    def __next__(self):
        index = self["list"].getCurrent()[0]

        if self["list"].getCurrent():
            if index == 1:
                self.playlists()
            if index == 2:
                self.settings()
            if index == 3:
                self.addServer()

    def quit(self):
        self.playOriginalChannel()

    def playOriginalChannel(self):
        if glob.currentPlayingServiceRefString != glob.newPlayingServiceRefString:
            if glob.newPlayingServiceRefString != '':
                self.session.nav.playService(eServiceReference(glob.currentPlayingServiceRefString))
        self.close()


def buildListEntry(index, title):
    png = None

    if index == 1:
        png = LoadPixmap(common_path + "playlists.png")
    if index == 2:
        png = LoadPixmap(common_path + "settings.png")
    if index == 3:
        png = LoadPixmap(common_path + "addplaylist.png")

    return (index, str(title), png)
