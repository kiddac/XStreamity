#!/usr/bin/python
# -*- coding: utf-8 -*-

# Standard library imports
import os
import json

import time

try:
    from http.client import HTTPConnection
    HTTPConnection.debuglevel = 0
except:
    from httplib import HTTPConnection
    HTTPConnection.debuglevel = 0

# Third-party imports
import requests

# Enigma2 components
from Components.ActionMap import ActionMap
from Components.Pixmap import Pixmap
from Components.Sources.List import List
from enigma import eTimer
from requests.adapters import HTTPAdapter, Retry
from Screens.MessageBox import MessageBox
from Screens.Screen import Screen
from Tools.LoadPixmap import LoadPixmap

# Local application/library-specific imports
from . import _
from . import xstreamity_globals as glob
from .plugin import skin_directory, common_path, hasConcurrent, hasMultiprocessing, cfg, pythonVer
from .xStaticText import StaticText


hdr = {
    'User-Agent': str(cfg.useragent.value),
    'Accept-Encoding': 'gzip, deflate'
}


if pythonVer == 3:
    superscript_to_normal = str.maketrans(
        '⁰¹²³⁴⁵⁶⁷⁸⁹ᵃᵇᶜᵈᵉᶠᵍʰⁱʲᵏˡᵐⁿᵒᵖʳˢᵗᵘᵛʷˣʸᶻ'
        'ᴬᴮᴰᴱᴳᴴᴵᴶᴷᴸᴹᴺᴼᴾᴿᵀᵁⱽᵂ⁺⁻⁼⁽⁾',
        '0123456789abcdefghijklmnoprstuvwxyz'
        'ABDEGHIJKLMNOPRTUVW+-=()'
    )


def normalize_superscripts(text):
    return text.translate(superscript_to_normal)


def clean_names(streams):
    """Clean only the 'name' field in each stream entry."""
    for item in streams:
        if "name" in item and isinstance(item["name"], str):
            item["name"] = normalize_superscripts(item["name"])
    return streams


class XStreamity_Menu(Screen):
    ALLOW_SUSPEND = True

    def __init__(self, session):
        Screen.__init__(self, session)
        self.session = session

        skin_path = os.path.join(skin_directory, cfg.skin.value)
        skin = os.path.join(skin_path, "menu.xml")
        with open(skin, "r") as f:
            self.skin = f.read()

        self.list = []
        self.drawList = []
        self["list"] = List(self.drawList, enableWrapAround=True)

        self.playlists_json = cfg.playlists_json.value
        self.setup_title = _("Playlist Menu") + " - " + str(glob.active_playlist["playlist_info"]["name"])

        self["key_red"] = StaticText(_("Back"))
        self["key_green"] = StaticText(_("OK"))
        self["key_blue"] = StaticText("")

        self["splash"] = Pixmap()
        self["splash"].show()

        self["actions"] = ActionMap(["XStreamityActions"], {
            "red": self.quit,
            "cancel": self.quit,
            "menu": self.settings,
            "green": self.__next__,
            "ok": self.__next__,
        }, -2)

        self.player_api = glob.active_playlist["playlist_info"]["player_api"]

        self.p_live_categories_url = self.player_api + "&action=get_live_categories"
        self.p_vod_categories_url = self.player_api + "&action=get_vod_categories"
        self.p_series_categories_url = self.player_api + "&action=get_series_categories"
        self.p_live_streams_url = self.player_api + "&action=get_live_streams"

        glob.active_playlist["data"]["live_streams"] = []

        self.onFirstExecBegin.append(self.start)
        self.onLayoutFinish.append(self.__layoutFinished)

    def __layoutFinished(self):
        self.setTitle(self.setup_title)

    def start(self, data=None):
        # delay to allow splash screen to show
        if glob.active_playlist["data"]["data_downloaded"] is False:
            self.timer = eTimer()
            try:
                self.timer_conn = self.timer.timeout.connect(self.makeUrlList)
            except:
                try:
                    self.timer.callback.append(self.makeUrlList)
                except:
                    self.makeUrlList()
            self.timer.start(10, True)
        else:
            self["splash"].hide()
            self.createSetup()

    def makeUrlList(self):
        self.url_list = [
            [self.p_live_categories_url, 0],
            [self.p_vod_categories_url, 1],
            [self.p_series_categories_url, 2]
        ]

        if not glob.active_playlist["data"]["data_downloaded"]:
            self.url_list.append([self.p_live_streams_url, 3])

        self.process_downloads()

    def download_url(self, url):
        category = url[1]
        response = ""

        retries = Retry(total=1, backoff_factor=1)
        adapter = HTTPAdapter(max_retries=retries)

        with requests.Session() as http:
            http.mount("http://", adapter)
            http.mount("https://", adapter)

            try:
                r = http.get(url[0], headers=hdr, timeout=(10, 20), verify=False)
                r.raise_for_status()
                if r.status_code == requests.codes.ok:
                    try:
                        response = r.json()

                        if pythonVer == 3:
                            response = clean_names(response)

                    except ValueError as e:
                        print("Error decoding JSON:", e)
            except Exception as e:
                print("Request error:", e)

        return category, response

    def process_downloads(self):
        self.retry = 0
        glob.active_playlist["data"]["live_categories"] = []
        glob.active_playlist["data"]["vod_categories"] = []
        glob.active_playlist["data"]["series_categories"] = []

        threads = len(self.url_list)
        results = []

        if hasConcurrent or hasMultiprocessing:
            if hasConcurrent:
                # print("******* trying concurrent futures ******")
                try:
                    from concurrent.futures import ThreadPoolExecutor
                    with ThreadPoolExecutor(max_workers=threads) as executor:
                        results = list(executor.map(self.download_url, self.url_list))
                except Exception as e:
                    print("Concurrent execution error:", e)

            elif hasMultiprocessing:
                try:
                    # print("*** trying multiprocessing ThreadPool ***")
                    from multiprocessing.pool import ThreadPool
                    pool = ThreadPool(threads)
                    results = pool.imap(self.download_url, self.url_list)

                    pool.close()
                    pool.join()

                except Exception as e:
                    print("multiprocessing execution error:", e)

            for category, response in results:
                if response:
                    # add categories to main json file
                    if category == 0:
                        glob.active_playlist["data"]["live_categories"] = response
                    if category == 1:
                        glob.active_playlist["data"]["vod_categories"] = response
                    if category == 2:
                        glob.active_playlist["data"]["series_categories"] = response
                    if category == 3:
                        glob.active_playlist["data"]["live_streams"] = response

        else:
            # print("*** trying sequential ***")
            for url in self.url_list:
                result = self.download_url(url)
                category = result[0]
                response = result[1]
                if response:
                    # add categories to main json file
                    if category == 0:
                        glob.active_playlist["data"]["live_categories"] = response
                    if category == 1:
                        glob.active_playlist["data"]["vod_categories"] = response
                    if category == 2:
                        glob.active_playlist["data"]["series_categories"] = response
                    if category == 3:
                        glob.active_playlist["data"]["live_streams"] = response

        self["splash"].hide()
        glob.active_playlist["data"]["data_downloaded"] = True
        self.createSetup()

    def writeJsonFile(self):
        with open(self.playlists_json, "r") as f:
            playlists_all = json.load(f)

        playlists_all[glob.current_selection] = glob.active_playlist

        with open(self.playlists_json, "w") as f:
            json.dump(playlists_all, f, indent=4)

    def createSetup(self):
        self.list = []
        self.index = 0

        def add_category_to_list(title, category_type, index):
            category_data = glob.active_playlist["data"].get(category_type)
            if (
                isinstance(category_data, list)
                and len(category_data) > 0
                and isinstance(category_data[0], dict)
                and "category_id" in category_data[0]
                and "user_info" not in category_data
            ):
                self.index += 1
                self.list.append([self.index, title, index, ""])

        show_live = glob.active_playlist["player_info"].get("showlive", False)
        show_vod = glob.active_playlist["player_info"].get("showvod", False)
        show_series = glob.active_playlist["player_info"].get("showseries", False)
        show_catchup = glob.active_playlist["player_info"].get("showcatchup", False)

        content = glob.active_playlist["data"]["live_streams"]

        has_catchup = any(str(item.get("tv_archive", "0")) == "1" for item in content if "tv_archive" in item)
        has_custom_sids = any(item.get("custom_sid", False) for item in content if "custom_sid" in item)

        glob.active_playlist["data"]["live_streams"] = []

        if has_custom_sids:
            glob.active_playlist["data"]["customsids"] = True

        if has_catchup:
            glob.active_playlist["data"]["catchup"] = True

        if show_live:
            add_category_to_list(_("Live Streams"), "live_categories", 0)

        if show_vod:
            add_category_to_list(_("Vod"), "vod_categories", 1)

        if show_series:
            add_category_to_list(_("TV Series"), "series_categories", 2)

        if show_catchup and glob.active_playlist["data"]["catchup"]:
            self.index += 1
            self.list.append([self.index, _("Catch Up TV"), 3, ""])

        self.index += 1
        self.list.append([self.index, _("Playlist Settings"), 4, ""])

        try:
            if show_live:
                if glob.active_playlist["data"]["live_categories"] and len(glob.active_playlist["data"]["live_categories"]) > 0 \
                        and "category_id" in glob.active_playlist["data"]["live_categories"][0] and "user_info" not in glob.active_playlist["data"]["live_categories"]:
                    self.index += 1
                    self.list.append([self.index, _("Manual EPG Update"), 5, ""])
        except Exception as e:
            print(e)

        self.drawList = [buildListEntry(x[0], x[1], x[2], x[3]) for x in self.list]
        self["list"].setList(self.drawList)

        self.writeJsonFile()

        if not self.list:
            self.session.openWithCallback(self.close, MessageBox, (_("No data, blocked or playlist not compatible with XStreamity plugin.")), MessageBox.TYPE_WARNING, timeout=5)

    def quit(self):
        self.close()

    def __next__(self):
        current_item = self["list"].getCurrent()
        if current_item:
            category = current_item[2]
            if category == 0:
                from . import live
                self.session.open(live.XStreamity_Live_Categories)
            elif category == 1:
                from . import vod
                self.session.open(vod.XStreamity_Vod_Categories)
            elif category == 2:
                from . import series
                self.session.open(series.XStreamity_Series_Categories)
            elif category == 3:
                from . import catchup
                self.session.open(catchup.XStreamity_Catchup_Categories)
            elif category == 4:
                self.settings()
            elif category == 5:
                self.updateEPG()

    def settings(self):
        from . import playsettings
        self.session.openWithCallback(self.start, playsettings.XStreamity_Settings)

    def updateEPG(self):
        recordings = ""
        next_rec_time = -1

        try:
            recordings = self.session.nav.getRecordings()
            if not recordings:
                next_rec_time = self.session.nav.RecordTimer.getNextRecordingTime()
        except:
            pass

        if recordings or (next_rec_time > 0 and (next_rec_time - time.time()) < 360):
            self.session.open(MessageBox, _("Recordings in progress. EPG not downloaded."), type=MessageBox.TYPE_INFO, timeout=5)
        else:
            self.session.openWithCallback(self.updateEPG2, MessageBox, _("EPGs downloading."), type=MessageBox.TYPE_INFO, timeout=5)

    def updateEPG2(self, data=None):
        from . import update
        update.XStreamity_Update(self.session, "manual")


def buildListEntry(index, title, category_id, playlisturl):
    icon_mapping = {
        0: "live.png",
        1: "vod.png",
        2: "series.png",
        3: "catchup.png",
        4: "settings.png",
        5: "epg_download.png"
    }

    png = None
    icon_filename = icon_mapping.get(category_id)
    if icon_filename:
        png = LoadPixmap(os.path.join(common_path, icon_filename))

    return (index, str(title), category_id, str(playlisturl), png)
