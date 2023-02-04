#!/usr/bin/python
# -*- coding: utf-8 -*-

from . import _
from . import xstreamity_globals as glob
from .plugin import skin_directory, hdr, common_path, playlists_json, hasConcurrent, hasMultiprocessing, cfg
from .xStaticText import StaticText

from Components.ActionMap import ActionMap
from Components.Pixmap import Pixmap
from Components.Sources.List import List
from datetime import datetime
from enigma import eTimer
from requests.adapters import HTTPAdapter, Retry
from Screens.MessageBox import MessageBox
from Screens.Screen import Screen
from Tools.LoadPixmap import LoadPixmap

import os
import json
import requests


class XStreamity_Menu(Screen):
    ALLOW_SUSPEND = True

    def __init__(self, session):
        Screen.__init__(self, session)
        self.session = session

        skin_path = os.path.join(skin_directory, cfg.skin.getValue())
        skin = os.path.join(skin_path, "menu.xml")
        with open(skin, "r") as f:
            self.skin = f.read()

        self.list = []
        self.drawList = []
        self["list"] = List(self.drawList, enableWrapAround=True)

        self.setup_title = str(glob.current_playlist["playlist_info"]["name"])

        self["key_red"] = StaticText(_("Back"))
        self["key_green"] = StaticText(_("OK"))
        self["key_blue"] = StaticText(_("Update"))

        self["lastchecked"] = StaticText(_("Catchup channel check updated: ") + str(glob.current_playlist["data"]["last_check"]))

        self["splash"] = Pixmap()
        self["splash"].show()

        self["actions"] = ActionMap(["XStreamityActions"], {
            "red": self.quit,
            "cancel": self.quit,
            "menu": self.settings,
            "blue": self.updateCategories,
            "green": self.__next__,
            "ok": self.__next__,
        }, -2)

        self.player_api = glob.current_playlist["playlist_info"]["player_api"]

        self.p_live_categories_url = str(self.player_api) + "&action=get_live_categories"
        self.p_vod_categories_url = str(self.player_api) + "&action=get_vod_categories"
        self.p_series_categories_url = str(self.player_api) + "&action=get_series_categories"
        self.p_live_streams_url = str(self.player_api) + "&action=get_live_streams"

        glob.current_playlist["data"]["live_streams"] = []

        self.onFirstExecBegin.append(self.start)
        self.onLayoutFinish.append(self.__layoutFinished)

    def __layoutFinished(self):
        self.setTitle(self.setup_title)

    def start(self):
        if glob.current_playlist["data"]["data_downloaded"] is False:
            glob.current_playlist["data"]["last_check"] = datetime.now().strftime("%d/%m/%Y %H:%M")
            self["lastchecked"].setText(_("Last catchup check: ") + str(glob.current_playlist["data"]["last_check"]))
            # delay to allow splash screen to show
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

        self.url_list.append([self.p_live_categories_url, 0])
        self.url_list.append([self.p_vod_categories_url, 1])
        self.url_list.append([self.p_series_categories_url, 2])

        if glob.current_playlist["player_info"]["showcatchup"] is True:
            if glob.current_playlist["data"]["catchup_checked"] is False or glob.current_playlist["data"]["catchup"] is False:
                self.url_list.append([self.p_live_streams_url, 3])

        self.process_downloads()

    def download_url(self, url):
        category = url[1]
        r = ""

        retries = Retry(total=3, backoff_factor=1)
        adapter = HTTPAdapter(max_retries=retries)
        http = requests.Session()
        http.mount("http://", adapter)
        http.mount("https://", adapter)
        response = ""
        try:
            r = http.get(url[0], headers=hdr, timeout=(10, 20), verify=False)
            r.raise_for_status()
            if r.status_code == requests.codes.ok:
                try:
                    response = r.json()
                    return category, response
                except Exception as e:
                    print(e)
                    return category, ""

        except Exception as e:
            print(e)
            return category, ""

    def process_downloads(self):
        self.retry = 0
        glob.current_playlist["data"]["live_categories"] = []
        glob.current_playlist["data"]["vod_categories"] = []
        glob.current_playlist["data"]["series_categories"] = []

        threads = len(self.url_list)

        if hasConcurrent:
            print("******* trying concurrent futures ******")
            try:
                from concurrent.futures import ThreadPoolExecutor
                executor = ThreadPoolExecutor(max_workers=threads)

                with executor:
                    results = executor.map(self.download_url, self.url_list)
                for category, response in results:
                    if response:
                        if category == 0:
                            glob.current_playlist["data"]["live_categories"] = response
                        if category == 1:
                            glob.current_playlist["data"]["vod_categories"] = response
                        if category == 2:
                            glob.current_playlist["data"]["series_categories"] = response
                        if category == 3:
                            glob.current_playlist["data"]["live_streams"] = response
                            glob.current_playlist["data"]["catchup_checked"] = True

                self["splash"].hide()
                glob.current_playlist["data"]["data_downloaded"] = True
                self.createSetup()
                return
            except Exception as e:
                print(e)

        elif hasMultiprocessing:
            try:
                print("*** trying multiprocessing ThreadPool ***")
                from multiprocessing.pool import ThreadPool
                pool = ThreadPool(threads)
                results = pool.imap(self.download_url, self.url_list)

                pool.close()
                pool.join()

                for category, response in results:
                    if response:
                        # add categories to main json file
                        if category == 0:
                            glob.current_playlist["data"]["live_categories"] = response
                        if category == 1:
                            glob.current_playlist["data"]["vod_categories"] = response
                        if category == 2:
                            glob.current_playlist["data"]["series_categories"] = response
                        if category == 3:
                            glob.current_playlist["data"]["live_streams"] = response
                            glob.current_playlist["data"]["catchup_checked"] = True

                self["splash"].hide()
                glob.current_playlist["data"]["data_downloaded"] = True
                self.createSetup()
                return
            except Exception as e:
                print(e)

        print("*** trying sequential ***")
        for url in self.url_list:
            result = self.download_url(url)
            category = result[0]
            response = result[1]
            if response:
                # add categories to main json file
                if category == 0:
                    glob.current_playlist["data"]["live_categories"] = response
                if category == 1:
                    glob.current_playlist["data"]["vod_categories"] = response
                if category == 2:
                    glob.current_playlist["data"]["series_categories"] = response
                if category == 3:
                    glob.current_playlist["data"]["live_streams"] = response
                    glob.current_playlist["data"]["catchup_checked"] = True

        self["splash"].hide()
        glob.current_playlist["data"]["data_downloaded"] = True
        self.createSetup()

    def writeJsonFile(self):
        with open(playlists_json, "r") as f:
            self.playlists_all = json.load(f)
            self.playlists_all[glob.current_selection] = glob.current_playlist

        with open(playlists_json, "w") as f:
            json.dump(self.playlists_all, f)

    def createSetup(self):
        self.list = []
        self.index = 0

        if glob.current_playlist["player_info"]["showlive"] is True:
            if glob.current_playlist["data"]["live_categories"] != [] and "user_info" not in glob.current_playlist["data"]["live_categories"]:
                self.index += 1
                self.list.append([self.index, _("Live Streams"), 0, ""])

        if glob.current_playlist["player_info"]["showvod"] is True:
            if glob.current_playlist["data"]["vod_categories"] != [] and "user_info" not in glob.current_playlist["data"]["vod_categories"]:
                self.index += 1
                self.list.append([self.index, _("Vod"), 1, ""])

        if glob.current_playlist["player_info"]["showseries"] is True:
            if glob.current_playlist["data"]["series_categories"] != [] and "user_info" not in glob.current_playlist["data"]["series_categories"]:
                self.index += 1
                self.list.append([self.index, _("TV Series"), 2, ""])

        content = glob.current_playlist["data"]["live_streams"]
        hascatchup = any(int(item["tv_archive"]) == 1 for item in content if "tv_archive" in item)
        glob.current_playlist["data"]["live_streams"] = []

        if hascatchup:
            glob.current_playlist["data"]["catchup"] = True

        if glob.current_playlist["player_info"]["showcatchup"] is True:
            if glob.current_playlist["data"]["catchup"] is True:
                self.index += 1
                self.list.append([self.index, _("Catch Up TV"), 3, ""])

        self.index += 1
        self.list.append([self.index, _("Playlist Settings"), 4, ""])

        self.drawList = []
        self.drawList = [buildListEntry(x[0], x[1], x[2], x[3]) for x in self.list]
        self["list"].setList(self.drawList)

        self.writeJsonFile()

        if len(self.list) == 0:
            self.session.openWithCallback(self.close, MessageBox, (_("No data, blocked or playlist not compatible with XStreamity plugin.")), MessageBox.TYPE_WARNING, timeout=5)

    def quit(self):
        self.close()

    def __next__(self):
        if self["list"].getCurrent():
            category = self["list"].getCurrent()[2]
            from . import channels
            if category == 0:
                self.session.open(channels.XStreamity_Categories, "live")
            elif category == 1:
                self.session.open(channels.XStreamity_Categories, "vod")
            elif category == 2:
                self.session.open(channels.XStreamity_Categories, "series")
            elif category == 3:
                self.session.open(channels.XStreamity_Categories, "catchup")
            elif category == 4:
                self.settings()

    def updateCategories(self):
        self["splash"].show()
        glob.current_playlist["data"]["live_categories"] = []
        glob.current_playlist["data"]["vod_categories"] = []
        glob.current_playlist["data"]["series_categories"] = []
        glob.current_playlist["data"]["catchup"] = False
        glob.current_playlist["data"]["catchup_checked"] = False
        glob.current_playlist["data"]["last_check"] = datetime.now().strftime("%d/%m/%Y %H:%M")
        self["lastchecked"].setText(_("Last catchup check: ") + str(glob.current_playlist["data"]["last_check"]))
        self.timer = eTimer()

        try:
            self.timer_conn = self.timer.timeout.connect(self.makeUrlList)
        except:
            try:
                self.timer.callback.append(self.makeUrlList)
            except:
                self.makeUrlList()
        self.timer.start(5, True)

    def settings(self):
        from . import playsettings
        self.session.openWithCallback(self.start, playsettings.XStreamity_Settings)


def buildListEntry(index, title, category_id, playlisturl):
    png = None

    if category_id == 0:
        png = LoadPixmap(os.path.join(common_path, "live.png"))
    if category_id == 1:
        png = LoadPixmap(os.path.join(common_path, "vod.png"))
    if category_id == 2:
        png = LoadPixmap(os.path.join(common_path, "series.png"))
    if category_id == 3:
        png = LoadPixmap(os.path.join(common_path, "catchup.png"))
    if category_id == 4:
        png = LoadPixmap(os.path.join(common_path, "settings.png"))
    return (index, str(title), category_id, str(playlisturl), png)
