from . import _
from . import xstreamity_globals as glob
from . import processfiles as xfiles
from .plugin import skin_path, json_file, hdr, playlist_path, cfg, common_path, VERSION
from .xStaticText import StaticText

from Components.ActionMap import ActionMap
from Components.Pixmap import Pixmap
from Components.Sources.List import List
from datetime import datetime
from enigma import eTimer
from Screens.MessageBox import MessageBox
from Screens.Screen import Screen
from Tools.LoadPixmap import LoadPixmap

import json
import os
import re
import sys

try:
    pythonVer = sys.version_info.major
except:
    pythonVer = 2


class XStreamity_Playlists(Screen):

    def __init__(self, session):
        Screen.__init__(self, session)
        self.session = session

        skin = skin_path + 'playlists.xml'
        with open(skin, 'r') as f:
            self.skin = f.read()

        self.list = []
        self['menu'] = List(self.list, enableWrapAround=True)
        self.setup_title = (_('Select Playlist'))

        self['key_red'] = StaticText(_('Back'))
        self['key_green'] = StaticText(_('OK'))
        self['key_yellow'] = StaticText(_('Delete'))
        self['key_blue'] = StaticText(_('Info'))
        self['version'] = StaticText()

        self.list = []
        self.drawList = []
        self["playlists"] = List(self.drawList)
        self['playlists'].onSelectionChanged.append(self.getCurrentEntry)
        self["splash"] = Pixmap()
        self["splash"].show()
        self["scroll_up"] = Pixmap()
        self["scroll_down"] = Pixmap()
        self["scroll_up"].hide()
        self["scroll_down"].hide()

        self['actions'] = ActionMap(['XStreamityActions'], {
            'red': self.quit,
            'green': self.getStreamTypes,
            'cancel': self.quit,
            'ok': self.getStreamTypes,
            'blue': self.openUserInfo,
            'info': self.openUserInfo,
            'yellow': self.deleteServer,
        }, -2)

        self.onFirstExecBegin.append(self.start)
        self.onLayoutFinish.append(self.__layoutFinished)

    def __layoutFinished(self):
        self.setTitle(self.setup_title)

    def start(self):
        self['version'].setText(VERSION)

        self.playlists_all = []

        # check if playlists.json file exists in specified location
        if os.path.isfile(json_file):
            with open(json_file, "r") as f:
                try:
                    self.playlists_all = json.load(f)
                    self.playlists_all.sort(key=lambda e: e['playlist_info']['index'], reverse=False)
                except:
                    os.remove(json_file)

        if os.path.isfile(playlist_path) and os.stat(playlist_path).st_size > 0:
            self.delayedDownload()

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

        if self.url_list:
            self.process_downloads()

    def download_url(self, url):
        index = url[1]

        import requests
        from requests.adapters import HTTPAdapter

        r = ''
        adapter = HTTPAdapter()
        http = requests.Session()
        http.mount("http://", adapter)
        http.mount("https://", adapter)

        try:
            r = http.get(url[0], headers=hdr, stream=True, timeout=10, verify=False)
            r.raise_for_status()
            if r.status_code == requests.codes.ok:
                try:
                    response = r.json()
                    return index, response
                except:
                    print("***** JSON FAIL ********")
                    return index, ''

        except requests.ConnectionError as e:
            print("OOPS!! Connection Error. \n")
            print(str(e))

        except requests.Timeout as e:
            print("OOPS!! Timeout Error")
            print(str(e))

        except requests.RequestException as e:
            print("OOPS!! General Error")
            print(str(e))

        return index, ''

    def process_downloads(self):

        from multiprocessing.pool import ThreadPool

        threads = len(self.url_list)
        if threads:
            pool = ThreadPool(5)
            results = pool.imap_unordered(self.download_url, self.url_list)
            for index, response in results:
                if response != '':
                    self.playlists_all[index].update(response)
                else:
                    self.playlists_all[index]['user_info'] = []
            pool.close()
            pool.join()
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

                    if 'time_now' in playlists['server_info']:
                        time_now_datestamp = datetime.strptime(str(playlists['server_info']['time_now']), "%Y-%m-%d %H:%M:%S")
                        playlists['player_info']['serveroffset'] = datetime.now().hour - time_now_datestamp.hour

                if 'auth' in playlists:
                    try:
                        auth = int(playlists['user_info']['auth'])
                    except:
                        playlists['user_info']['auth'] = 1

                if 'status' in playlists['user_info']:
                    if playlists['user_info']['status'] != "Active" and playlists['user_info']['status'] != "Banned" and playlists['user_info']['status'] != "Disabled" and playlists['user_info']['status'] != "Expired":
                        playlists['user_info']['status'] = "Active"

                if 'active_cons' in playlists['user_info']:
                    if not playlists['user_info']['active_cons']:
                        playlists['user_info']['active_cons'] = 0

                if 'max_connections' in playlists['user_info']:
                    if not playlists['user_info']['max_connections']:
                        playlists['user_info']['max_connections'] = 0

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

        if len(self.list) == 1 and cfg.skipplaylistsscreen.getValue() is True and 'user_info' in playlist and 'status' in playlist['user_info'] and playlist['user_info']['status'] == 'Active':
            self.getStreamTypes()

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
        self.close()

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

                self.deleteEpgImporterRef()

    def deleteEpgImporterRef(self, data=None):

        if data is None:
            self.session.openWithCallback(self.deleteEpgImporterRef, MessageBox, _('Delete EPG Importer references?'))

        else:
            cleanName = re.sub(r'[\<\>\:\"\/\\\|\?\*]', '_', str(glob.current_playlist['playlist_info']['name']))
            cleanName = re.sub(r' ', '_', cleanName)
            cleanName = re.sub(r'_+', '_', cleanName)

            filepath = '/etc/epgimport/'
            filename = 'xstreamity.' + str(cleanName) + '.sources.xml'
            sourcepath = filepath + filename
            epgfilename = 'xstreamity.' + str(cleanName) + '.channels.xml'
            channelpath = filepath + epgfilename

            if os.path.exists(sourcepath):
                os.remove(sourcepath)
            if os.path.exists(channelpath):
                os.remove(channelpath)

            self.playlists_all = xfiles.processfiles()
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
                    self.checkoneplaylist()

    def checkoneplaylist(self):
        if len(self.list) == 1 and cfg.skipplaylistsscreen.getValue() is True:
            self.quit()
