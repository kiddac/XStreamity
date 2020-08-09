#!/usr/bin/python
# -*- coding: utf-8 -*-

# for localized messages


from . import _
from . import xstreamity_globals as glob
from .plugin import skin_path, json_file, hdr, playlist_path, cfg, common_path, VERSION

from collections import OrderedDict
from Components.ActionMap import ActionMap
from Components.Pixmap import Pixmap
from Components.Sources.List import List
from datetime import datetime
from enigma import eTimer, eServiceReference

from os import system
from requests.adapters import HTTPAdapter
from Screens.MessageBox import MessageBox
from Screens.Screen import Screen
from Tools.LoadPixmap import LoadPixmap
from .xStaticText import StaticText

import json
import os
import sys

pythonVer = 2
if sys.version_info.major == 3:
    pythonVer = 3

if pythonVer == 2:
    if not os.path.isfile("/usr/lib/python2.7/imghdr.pyo"):
        try:
            system("opkg install python-image")
        except:
            pass

    if not os.path.exists("/usr/lib/python2.7/site-packages/PIL"):
        try:
            system("opkg install python-imaging")
        except:
            pass
            
    if not os.path.exists("/usr/lib/python2.7/site-packages/requests"):
        try:
            system("opkg install python-requests")
        except:
            pass

    if not os.path.exists("/usr/lib/python2.7/multiprocessing"):
        try:
            system("opkg install python-multiprocessing")
        except:
            pass
            
if pythonVer == 3:
    if not os.path.isfile("/usr/lib/python3.8/imghdr.py"):
        try:
            system("opkg install python3-image")
        except:
            pass

    if not os.path.exists("/usr/lib/python3.8/site-packages/PIL"):
        try:
            system("opkg install python3-imaging")
        except:
            pass
            
    if not os.path.exists("/usr/lib/python3.8/site-packages/requests"):
        try:
            system("opkg install python3-requests")
        except:
            pass

    if not os.path.exists("/usr/lib/python3.8/multiprocessing"):
        try:
            system("opkg install python3-multiprocessing")
        except:
            pass

from multiprocessing.pool import ThreadPool
import requests

try:
    from urlparse import urlparse, parse_qs
except:
    from urllib.parse import urlparse, parse_qs

try:
    from requests.packages.urllib3.util.retry import Retry
except:
    from urllib3.util import Retry


class XStreamity_Main(Screen):

    def __init__(self, session):
        Screen.__init__(self, session)
        self.session = session

        skin = skin_path + 'playlists.xml'
        with open(skin, 'r') as f:
            self.skin = f.read()

        self.list = []
        self['menu'] = List(self.list, enableWrapAround=True)
        self.setup_title = (_('Select Server'))

        self['key_red'] = StaticText(_('Back'))
        self['key_green'] = StaticText(_('Add'))
        self['key_yellow'] = StaticText()
        self['key_blue'] = StaticText()
        self['key_info'] = StaticText()
        self['key_menu'] = StaticText(_('Settings'))
        self['version'] = StaticText()

        self.list = []
        self.drawList = []
        self["playlists"] = List(self.drawList)
        self['playlists'].onSelectionChanged.append(self.getCurrentEntry)
        self["splash"] = Pixmap()
        self["splash"].hide()
        self["scroll_up"] = Pixmap()
        self["scroll_down"] = Pixmap()
        self["scroll_up"].hide()
        self["scroll_down"].hide()

        glob.configchanged = True

        self['actions'] = ActionMap(['XStreamityActions'], {
            'red': self.quit,
            'green': self.addServer,
            'yellow': self.editServer,
            'blue': self.deleteServer,
            'cancel': self.quit,
            'info': self.openUserInfo,
            'ok': self.getStreamTypes,
            'menu': self.settings
        }, -2)

        self.onFirstExecBegin.append(self.start)
        self.onLayoutFinish.append(self.__layoutFinished)

    def __layoutFinished(self):
        self.setTitle(self.setup_title)

    def clear_caches(self):
        try:
            system("echo 1 > /proc/sys/vm/drop_caches")
            system("echo 2 > /proc/sys/vm/drop_caches")
            system("echo 3 > /proc/sys/vm/drop_caches")
        except:
            pass

    def start(self):
        # get version number
        self.clear_caches()
        self['version'].setText(VERSION)

        # check if playlists.json file exists in specified location
        self.playlists_all = []

        if os.path.isfile(json_file):
            with open(json_file, "r") as f:
                try:
                    # self.playlists_all = json.load(f, object_pairs_hook=OrderedDict)
                    self.playlists_all = json.load(f)
                except:
                    os.remove(json_file)

        if os.path.isfile(playlist_path) and os.stat(playlist_path).st_size > 0:
            self.checkPlaylistUserFile()

    def checkPlaylistUserFile(self):
        self["splash"].show()

        with open(playlist_path, 'r+') as f:
            lines = f.readlines()
            f.seek(0)
            f.writelines((line.strip(' ') for line in lines if line.strip()))
            f.truncate()
            f.seek(0)
            for line in lines:
                if not line.startswith('http://') and not line.startswith('https://') and not line.startswith('#'):
                    line = '# ' + line
                if "=mpegts" in line:
                    line = line.replace("=mpegts", "=ts")
                if "=hls" in line:
                    line = line.replace("=hls", "=m3u8")
                if line.strip() == "#":
                    line = ""
                f.write(line)
            f.truncate()
        self.getPlaylistUserFile()

    def getPlaylistUserFile(self):
        with open(playlist_path, "r") as f:
            lines = f.readlines()
            self.index = 0

            for line in lines:
                line = line.strip()
                self.port = 80
                self.username = ''
                self.password = ''
                self.type = 'm3u_plus'
                self.output = 'ts'
                self.livetype = cfg.livetype.getValue()
                self.vodtype = cfg.vodtype.getValue()
                self.catchuptype = cfg.catchuptype.getValue()
                self.epgshift = 0
                self.livehidden = []
                self.vodhidden = []
                self.serieshidden = []
                self.showlive = True
                self.showvod = True
                self.showseries = True
                self.showcatchup = True
                self.epgtype = "1"
                self.epgquickshift = 0

                parsed_uri = urlparse(line)

                self.protocol = parsed_uri.scheme + "://"

                if not (self.protocol == "http://" or self.protocol == "https://"):
                    continue

                self.domain = parsed_uri.hostname

                if parsed_uri.port:
                    self.port = parsed_uri.port
                self.host = "%s%s:%s" % (self.protocol, self.domain, self.port)

                query = parse_qs(parsed_uri.query, keep_blank_values=True)

                if "username" in query:
                    self.username = query['username'][0]
                else:
                    continue

                if "password" in query:
                    self.password = query['password'][0]
                else:
                    continue

                if "type" in query:
                    self.type = query['type'][0]

                if "output" in query:
                    self.output = query['output'][0]

                self.player_api = "%s/player_api.php?username=%s&password=%s" % (self.host, self.username, self.password)
                self.enigma2_api = "%s/enigma2.php?username=%s&password=%s" % (self.host, self.username, self.password)
                self.xmltv_api = "%s/xmltv.php?username=%s&password=%s" % (self.host, self.username, self.password)
                self.full_url = "%s/get.php?username=%s&password=%s&type=%s&output=%s" % (self.host, self.username, self.password, self.type, self.output)

                playlist_exists = False

                if self.playlists_all:
                    for playlists in self.playlists_all:

                        # extra check in case playlists.txt details have been amended
                        if "domain" in playlists["playlist_info"] and "username" in playlists["playlist_info"] and "password" in playlists["playlist_info"]:
                            if playlists["playlist_info"]["domain"] == self.domain and playlists["playlist_info"]["username"] == self.username and playlists["playlist_info"]["password"] == self.password:
                                playlist_exists = True
                                playlists["playlist_info"]["type"] = self.type
                                playlists["playlist_info"]["output"] = self.output
                                playlists["playlist_info"]["full_url"] = self.full_url  # get.php

                                if "epgtype" not in playlists["player_info"]:
                                    playlists["player_info"]["epgtype"] = self.epgtype

                                if "epgquickshift" not in playlists["player_info"]:
                                    playlists["player_info"]["epgquickshift"] = self.epgquickshift

                if playlist_exists is False:
                    self.playlists_all.append({
                        "playlist_info": dict([
                            ("index", self.index),
                            ("name", self.domain),
                            ("protocol", self.protocol),
                            ("domain", self.domain),
                            ("port", self.port),
                            ("username", self.username),
                            ("password", self.password),
                            ("type", self.type),
                            ("output", self.output),
                            ("host", self.host),
                            ("player_api", self.player_api),
                            ("enigma2_api", self.enigma2_api),
                            ("xmltv_api", self.xmltv_api),
                            ("full_url", self.full_url),
                        ]),
                        "player_info": OrderedDict([
                            ("livetype", self.livetype),
                            ("vodtype", self.vodtype),
                            ("catchuptype", self.catchuptype),
                            ("epgshift", self.epgshift),
                            ("livehidden", self.livehidden),
                            ("vodhidden", self.vodhidden),
                            ("serieshidden", self.serieshidden),
                            ("showlive", self.showlive),
                            ("showvod", self.showvod),
                            ("showseries", self.showseries),
                            ("showcatchup", self.showcatchup),
                            ("epgtype", self.epgtype),
                            ("epgquickshift", self.epgquickshift),
                        ]),

                        "data": dict([
                            ("live_categories", []),
                            ("vod_categories", []),
                            ("series_categories", []),
                            ("live_streams", []),
                            ("catchup", False),
                            ("catchup_checked", False),
                            ("last_check", ''),
                            ("epg_date", ''),
                        ]),
                    })

                self.index += 1

        self.removeOldPlaylists()

    def removeOldPlaylists(self):
        if self.playlists_all:
            newList = []
            with open(playlist_path, "r") as f:
                lines = f.readlines()

            for playlist in self.playlists_all:
                exists = False
                for line in lines:
                    if not line.startswith('#'):
                        if str(playlist["playlist_info"]["domain"]) in line and 'username=' + str(playlist["playlist_info"]["username"]) in line and 'password=' + str(playlist["playlist_info"]["password"]) in line:
                            exists = True

                if exists:
                    newList.append(playlist)

            self.playlists_all = newList

        self.getCurrentPlaying()

    def getCurrentPlaying(self):
        if self.session.nav.getCurrentlyPlayingServiceReference():
            glob.currentPlayingServiceRef = self.session.nav.getCurrentlyPlayingServiceReference()
            glob.currentPlayingServiceRefString = self.session.nav.getCurrentlyPlayingServiceReference().toString()
            glob.newPlayingServiceRef = self.session.nav.getCurrentlyPlayingServiceReference()
            glob.newPlayingServiceRefString = glob.newPlayingServiceRef.toString()
        self.delayedDownload()

    # delay to allow splash screen to show
    def delayedDownload(self):
        self.timer = eTimer()
        try:
            self.timer_conn = self.timer.timeout.connect(self.makeUrlList)
        except:
            try:
                self.timer.callback.append(self.makeUrlList)
            except:
                self.self.makeUrlList()
        self.timer.start(5, True)

    def makeUrlList(self):
        self.url_list = []
        x = 0
        for playlists in self.playlists_all:
            player_api = str(playlists["playlist_info"]["player_api"])
            full_url = str(playlists["playlist_info"]["full_url"])
            domain = str(playlists["playlist_info"]["domain"])
            username = str(playlists["playlist_info"]["username"])
            password = str(playlists["playlist_info"]["password"])
            if 'get.php' in full_url and domain != '' and username != '' and password != '':
                self.url_list.append([player_api, x])
            x += 1

        if self.url_list != []:
            self.process_downloads()
        else:
            self["splash"].hide()

    def download_url(self, url):
        index = url[1]
        r = ''
        # retries = Retry(total=1, status_forcelist=[408, 429, 500, 503, 504], method_whitelist=["HEAD", "GET", "OPTIONS"], backoff_factor = 3)
        adapter = HTTPAdapter(max_retries=0)
        http = requests.Session()
        http.mount("http://", adapter)

        try:
            r = http.get(url[0], headers=hdr, stream=True, timeout=10, verify=False)
            r.raise_for_status()
            if r.status_code == requests.codes.ok:
                try:
                    response = r.json()
                    return index, response

                except:
                    return index, ''

        except requests.exceptions.ConnectionError as e:
            print(("Error Connecting: %s" % e))
            return index, ''

        except requests.exceptions.RequestException as e:
            print(e)
            return index, ''

    def process_downloads(self):
        threads = len(self.url_list)
        pool = ThreadPool(threads)
        results = pool.imap_unordered(self.download_url, self.url_list)
        for index, response in results:
            if response != '':
                self.playlists_all[index].update(response)
            else:
                self.playlists_all[index]['user_info'] = []
        pool.terminate()
        self.buildPlaylistList()

    def buildPlaylistList(self):
        for playlists in self.playlists_all:
            if 'user_info' in playlists:
                if 'message' in playlists['user_info']:
                    del playlists['user_info']['message']

                if 'server_info' in playlists:
                    if 'https_port' in playlists['server_info']:
                        del playlists['server_info']['https_port']

                    if 'rtmp_port' in playlists['server_info']:
                        del playlists['server_info']['rtmp_port']

            if 'available_channels' in playlists:
                del playlists['available_channels']
        self.writeJsonFile()

    def writeJsonFile(self):
        with open(json_file, 'w') as f:
            json.dump(self.playlists_all, f)
        self.createSetup()

    def createSetup(self):
        self["splash"].hide()
        self.list = []
        index = 0

        for playlist in self.playlists_all:
            name = ''
            url = ''
            active = ''
            activenum = ''
            maxc = ''
            maxnum = ''
            status = (_('Server Not Responding'))
            expires = ''
            timeshift = 'EPG Timeshift: '

            if playlist:
                if'name' in playlist['playlist_info']:
                    name = playlist['playlist_info']['name']
                elif 'domain' in playlist['playlist_info']:
                    name = playlist['playlist_info']['domain']

                url = playlist['playlist_info']['host']

                if 'user_info' in playlist and 'auth' in playlist['user_info']:
                    status = (_('Not Authorised'))

                    if playlist['user_info']['auth'] == 1:

                        if playlist['user_info']['status'] == 'Active':
                            status = (_('Active'))
                        elif playlist['user_info']['status'] == 'Banned':
                            status = (_('Banned'))
                        elif playlist['user_info']['status'] == 'Disabled':
                            status = (_('Disabled'))
                        elif playlist['user_info']['status'] == 'Expired':
                            status = (_('Expired'))

                        if status == (_('Active')):

                            try:
                                expires = str("Expires: ") + str(datetime.fromtimestamp(int(playlist['user_info']['exp_date'])).strftime('%d-%m-%Y'))
                            except:
                                expires = str("Expires: Null")

                            active = str("Active Conn:")
                            activenum = playlist['user_info']['active_cons']

                            maxc = str("Max Conn:")
                            maxnum = playlist['user_info']['max_connections']

                timeshift += str(playlist['player_info']['epgshift'])

                self.list.append([index, name, url, expires, status, active, activenum, maxc, maxnum, timeshift])
                index += 1

        self.drawList = []
        self.drawList = [self.buildListEntry(x[0], x[1], x[2], x[3], x[4], x[5], x[6], x[7], x[8], x[9]) for x in self.list]
        self["playlists"].setList(self.drawList)

        if self.list != []:
            self['key_yellow'].setText(_('Edit'))
            self['key_blue'].setText(_('Delete'))
            self['key_info'].setText(_('Info'))
        else:
            self['key_yellow'].setText('')
            self['key_blue'].setText('')
            self['key_info'].setText('')

    def buildListEntry(self, index, name, url, expires, status, active, activenum, maxc, maxnum, timeshift):
        if status == (_('Active')):
            pixmap = LoadPixmap(cached=True, path=common_path + 'led_green.png')

            if int(activenum) >= int(maxnum) and int(maxnum) != 0:
                pixmap = LoadPixmap(cached=True, path=common_path + 'led_yellow.png')
        if status == (_('Banned')):
            pixmap = LoadPixmap(cached=True, path=common_path + 'led_red.png')
        if status == (_('Expired')):
            pixmap = LoadPixmap(cached=True, path=common_path + 'led_grey.png')
        if status == (_('Disabled')):
            pixmap = LoadPixmap(cached=True, path=common_path + 'led_grey.png')
        if status == (_('Server Not Responding')):
            pixmap = LoadPixmap(cached=True, path=common_path + 'led_red.png')
        if status == (_('Not Authorised')):
            pixmap = LoadPixmap(cached=True, path=common_path + 'led_red.png')

        return(index, str(name), str(url), str(expires), str(status), pixmap, str(active), str(activenum), str(maxc), str(maxnum), str(timeshift))

    def quit(self):
        self.playOriginalChannel()

    def playOriginalChannel(self):
        if glob.currentPlayingServiceRefString != glob.newPlayingServiceRefString:
            if glob.newPlayingServiceRefString != '':
                self.session.nav.playService(eServiceReference(glob.currentPlayingServiceRefString))
        self.close()

    def addServer(self):
        from . import server
        glob.configchanged = False
        self.session.openWithCallback(self.refresh, server.XStreamity_AddServer, False)
        return

    def editServer(self):
        from . import server
        if self.list != []:
            glob.configchanged = False
            self.session.openWithCallback(self.refresh, server.XStreamity_AddServer, True)
        return

    def deleteServer(self, answer=None):
        if self.list != []:
            currentplaylist = glob.current_playlist.copy()

            if answer is None:
                self.session.openWithCallback(self.deleteServer, MessageBox, _('Delete selected playlist?'))
            elif answer:
                with open(playlist_path, 'r+') as f:
                    lines = f.readlines()
                    f.seek(0)
                    for line in lines:

                        if str(currentplaylist['playlist_info']['domain']) in line and "username=" + str(currentplaylist['playlist_info']['username']) in line:
                            line = '#%s' % line
                        f.write(line)
            self.refresh()

    def refresh(self):
        # self["splash"].show()
        self.playlists_all = []
        if os.path.isfile(json_file):
            with open(json_file, "r") as f:
                try:
                    self.playlists_all = json.load(f)
                except:
                    os.remove(json_file)

        self.start()

    def getCurrentEntry(self):
        if self.list != []:
            glob.current_selection = self['playlists'].getIndex()
            glob.current_playlist = self.playlists_all[glob.current_selection]

            if self['playlists'].count() > 5:
                self["scroll_up"].show()
                self["scroll_down"].show()

            if self['playlists'].getIndex() < 5:
                self["scroll_up"].hide()

            if self['playlists'].getIndex() + 1 > ((self['playlists'].count() // 5) * 5):
                self["scroll_down"].hide()
        else:
            glob.current_selection = 0
            glob.current_playlist = []

    def openUserInfo(self):
        from . import serverinfo
        if self.list != []:
            if 'user_info' in glob.current_playlist:
                if 'auth' in glob.current_playlist['user_info']:
                    if glob.current_playlist['user_info']['auth'] == 1:
                        self.session.open(serverinfo.XStreamity_UserInfo)

    def getStreamTypes(self):
        from . import menu
        if 'user_info' in glob.current_playlist:
            if 'auth' in glob.current_playlist['user_info']:
                if glob.current_playlist['user_info']['auth'] == 1 and glob.current_playlist['user_info']['status'] == "Active":
                    self.session.open(menu.XStreamity_Menu)

    def settings(self):
        from . import settings
        self.session.openWithCallback(self.settingsChanged, settings.XStreamity_Settings)

    def settingsChanged(self, data=None):
        if glob.changed:
            self.close()
