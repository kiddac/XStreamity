#!/usr/bin/python
# -*- coding: utf-8 -*-

from . import _
from . import xstreamity_globals as glob
from .plugin import skin_path, hdr, cfg, common_path, json_file
from .xStaticText import StaticText

from Components.ActionMap import ActionMap
from Components.Pixmap import Pixmap
from Components.Sources.List import List
from enigma import eTimer
from requests.adapters import HTTPAdapter
from Screens.MessageBox import MessageBox
from Screens.Screen import Screen
from Tools.LoadPixmap import LoadPixmap

import json
import requests

try:
    from concurrent.futures import ThreadPoolExecutor
    concurrent = True
except:
    concurrent = False
    from multiprocessing.pool import ThreadPool

retryfailed = False

try:
    from requests.packages.urllib3.util.retry import Retry
except:
    try:
        from urllib3.util import Retry
    except:
        retryfailed = True


class XStreamity_Menu(Screen):

    def __init__(self, session):
        Screen.__init__(self, session)
        self.session = session

        skin = skin_path + 'menu.xml'
        with open(skin, 'r') as f:
            self.skin = f.read()

        self.list = []
        self.drawList = []
        self["list"] = List(self.drawList, enableWrapAround=True)

        self.setup_title = str(glob.current_playlist['playlist_info']['name'])

        self['key_red'] = StaticText(_('Back'))
        self['key_green'] = StaticText(_('OK'))

        self["splash"] = Pixmap()
        self["splash"].show()

        self['actions'] = ActionMap(['XStreamityActions'], {
            'red': self.quit,
            'cancel': self.quit,
            'menu': self.settings,
            'green': self.__next__,
            'ok': self.__next__,
        }, -2)

        self.protocol = glob.current_playlist['playlist_info']['protocol']
        self.domain = glob.current_playlist['playlist_info']['domain']
        self.host = glob.current_playlist['playlist_info']['host']
        self.username = glob.current_playlist['playlist_info']['username']
        self.password = glob.current_playlist['playlist_info']['password']

        self.live_streams = "%s/player_api.php?username=%s&password=%s&action=get_live_streams" % (self.host, self.username, self.password)
        self.p_live_categories_url = "%s/player_api.php?username=%s&password=%s&action=get_live_categories" % (self.host, self.username, self.password)
        self.p_vod_categories_url = "%s/player_api.php?username=%s&password=%s&action=get_vod_categories" % (self.host, self.username, self.password)
        self.p_series_categories_url = "%s/player_api.php?username=%s&password=%s&action=get_series_categories" % (self.host, self.username, self.password)
        self.p_live_streams_url = "%s/player_api.php?username=%s&password=%s&action=get_live_streams" % (self.host, self.username, self.password)

        self.onFirstExecBegin.append(self.start)
        self.onLayoutFinish.append(self.__layoutFinished)

    def __layoutFinished(self):
        self.setTitle(self.setup_title)

    # delay to allow splash screen to show
    def start(self):
        if glob.current_playlist['data']['data_downloaded'] is False:
            self.timer = eTimer()
            try:
                self.timer_conn = self.timer.timeout.connect(self.makeUrlList)
            except:
                try:
                    self.timer.callback.append(self.makeUrlList)
                except:
                    self.makeUrlList()
            self.timer.start(5, True)
        else:
            self["splash"].hide()
            self.createSetup()

    def makeUrlList(self):
        self.url_list = []

        if glob.current_playlist['player_info']['showlive'] is True:
            self.url_list.append([self.p_live_categories_url, 0])

        if glob.current_playlist['player_info']['showvod'] is True:
            self.url_list.append([self.p_vod_categories_url, 1])

        if glob.current_playlist['player_info']['showseries'] is True:
            self.url_list.append([self.p_series_categories_url, 2])

        if glob.current_playlist['player_info']['showcatchup'] is True:
            self.url_list.append([self.p_live_streams_url, 3])

        self.process_downloads()

    def download_url(self, url):
        timeout = cfg.timeout.getValue()
        category = url[1]
        r = ''

        if retryfailed is False:
            retries = Retry(total=1, status_forcelist=[429, 503, 504], backoff_factor=1)
        else:
            retries = 1

        adapter = HTTPAdapter(max_retries=retries)
        http = requests.Session()
        http.mount("http://", adapter)

        try:
            r = http.get(url[0], headers=hdr, stream=False, timeout=timeout, verify=False)
            r.raise_for_status()
            if r.status_code == requests.codes.ok:
                # response = r.json()
                return category, r.json()
        except Exception as e:
            print(e)
            return category, ''

    def process_downloads(self):
        threads = len(self.url_list)
        if threads > 10:
            threads = 10

        if threads:
            """
            if concurrent is False:
                try:
                    print("********** multiprocessing threadpool *******")
                    pool = ThreadPool(processes=5)
                    glob.current_playlist['data']['live_categories'] = []
                    glob.current_playlist['data']['vod_categories'] = []
                    glob.current_playlist['data']['series_categories'] = []

                    results = pool.imap_unordered(self.download_url, self.url_list)
                    for category, response in results:
                        if response != '':
                            # add categories to main json file
                            if category == 0:
                                glob.current_playlist['data']['live_categories'] = response
                            elif category == 1:
                                glob.current_playlist['data']['vod_categories'] = response
                            elif category == 2:
                                glob.current_playlist['data']['series_categories'] = response
                            elif category == 3:
                                hascatchup = any(int(item["tv_archive"]) == 1 for item in response if "tv_archive" in item)
                                if hascatchup:
                                    glob.current_playlist['data']['catchup'] = True
                                else:
                                    glob.current_playlist['data']['catchup'] = False
                    pool.close()
                    pool.join()
                except:
                    print("********** sequential download *******")
                    for url in self.url_list:
                        result = self.download_url(url)
                        category = result[0]
                        response = result[1]
                        if response != '':
                            # add categories to main json file
                            if category == 0:
                                glob.current_playlist['data']['live_categories'] = response
                            elif category == 1:
                                glob.current_playlist['data']['vod_categories'] = response
                            elif category == 2:
                                glob.current_playlist['data']['series_categories'] = response
                            elif category == 3:
                                hascatchup = any(int(item["tv_archive"]) == 1 for item in response if "tv_archive" in item)
                                if hascatchup:
                                    glob.current_playlist['data']['catchup'] = True
                                else:
                                    glob.current_playlist['data']['catchup'] = False
            else:
                print("******* concurrent futures ******")
                executor = ThreadPoolExecutor(max_workers=threads)

                with executor:
                    results = executor.map(self.download_url, self.url_list)
                for category, response in results:
                    if response != '':
                        # add categories to main json file
                        if category == 0:
                            glob.current_playlist['data']['live_categories'] = response
                        elif category == 1:
                            glob.current_playlist['data']['vod_categories'] = response
                        elif category == 2:
                            glob.current_playlist['data']['series_categories'] = response
                        elif category == 3:
                            hascatchup = any(int(item["tv_archive"]) == 1 for item in response if "tv_archive" in item)
                            if hascatchup:
                                glob.current_playlist['data']['catchup'] = True
                            else:
                                glob.current_playlist['data']['catchup'] = False
                                """

            for url in self.url_list:
                result = self.download_url(url)
                category = result[0]
                response = result[1]
                if response != '':
                    # add categories to main json file
                    if category == 0:
                        glob.current_playlist['data']['live_categories'] = response
                    elif category == 1:
                        glob.current_playlist['data']['vod_categories'] = response
                    elif category == 2:
                        glob.current_playlist['data']['series_categories'] = response
                    elif category == 3:
                        hascatchup = any(int(item["tv_archive"]) == 1 for item in response if "tv_archive" in item)
                        if hascatchup:
                            glob.current_playlist['data']['catchup'] = True
                        else:
                            glob.current_playlist['data']['catchup'] = False
        self["splash"].hide()
        glob.current_playlist['data']['data_downloaded'] = True
        self.createSetup()

    def writeJsonFile(self):
        with open(json_file, "r") as f:
            self.playlists_all = json.load(f)
            self.playlists_all[glob.current_selection] = glob.current_playlist

        with open(json_file, "w") as f:
            json.dump(self.playlists_all, f)

    def createSetup(self):
        self.list = []
        self.index = 0

        if glob.current_playlist['player_info']['showlive'] is True:
            if glob.current_playlist['data']['live_categories'] != []:
                self.index += 1
                self.list.append([self.index, _("Live Streams"), 0, ""])

        if glob.current_playlist['player_info']['showvod'] is True:
            if glob.current_playlist['data']['vod_categories'] != []:
                self.index += 1
                self.list.append([self.index, _("Vod"), 1, ""])

        if glob.current_playlist['player_info']['showseries'] is True:
            if glob.current_playlist['data']['series_categories'] != []:
                self.index += 1
                self.list.append([self.index, _("TV Series"), 2, ""])

        if glob.current_playlist['player_info']['showcatchup'] is True:
            if glob.current_playlist['data']['catchup']:
                self.index += 1
                self.list.append([self.index, _("Catch Up TV"), 3, ""])

        self.index += 1
        self.list.append([self.index, _("Playlist Settings"), 4, ""])

        self.drawList = []
        self.drawList = [buildListEntry(x[0], x[1], x[2], x[3]) for x in self.list]
        self["list"].setList(self.drawList)

        self.writeJsonFile()

        if len(self.list) == 0:
            self.session.openWithCallback(self.close, MessageBox, (_('No data, blocked or playlist not compatible with XStreamity plugin.')), MessageBox.TYPE_WARNING, timeout=5)

    def quit(self):
        self.close()

    def __next__(self):
        category = self["list"].getCurrent()[2]
        if self["list"].getCurrent():
            if category == 0:
                from . import live
                self.session.open(live.XStreamity_Categories)

            elif category == 1:
                from . import vod
                self.session.open(vod.XStreamity_Categories)
            elif category == 2:
                from . import series
                self.session.open(series.XStreamity_Categories)
            elif category == 3:
                from . import catchup
                self.session.open(catchup.XStreamity_Catchup)
            elif category == 4:
                self.settings()

    def settings(self):
        from . import playsettings
        self.session.openWithCallback(self.start, playsettings.XStreamity_Settings)


def buildListEntry(index, title, category_id, playlisturl):
    png = None

    if category_id == 0:
        png = LoadPixmap(common_path + "live.png")
    if category_id == 1:
        png = LoadPixmap(common_path + "vod.png")
    if category_id == 2:
        png = LoadPixmap(common_path + "series.png")
    if category_id == 3:
        png = LoadPixmap(common_path + "catchup.png")
    if category_id == 4:
        png = LoadPixmap(common_path + "settings.png")
    return (index, str(title), category_id, str(playlisturl), png)
