#!/usr/bin/python
# -*- coding: utf-8 -*-

# Standard library imports
import base64
import codecs
from datetime import datetime, timedelta
import json
import math
import os
import re
import time
from itertools import cycle, islice
import zlib

try:
    from http.client import HTTPConnection
    HTTPConnection.debuglevel = 0
except ImportError:
    from httplib import HTTPConnection
    HTTPConnection.debuglevel = 0

try:
    from urllib import quote
except ImportError:
    from urllib.parse import quote

# Third-party imports
import requests
from PIL import Image
from requests.adapters import HTTPAdapter, Retry
from twisted.internet import reactor
from twisted.web.client import Agent, downloadPage, readBody
from twisted.web.http_headers import Headers

try:
    # Try to import BrowserLikePolicyForHTTPS
    from twisted.web.client import BrowserLikePolicyForHTTPS
    contextFactory = BrowserLikePolicyForHTTPS()
except ImportError:
    # Fallback to WebClientContextFactory if BrowserLikePolicyForHTTPS is not available
    from twisted.web.client import WebClientContextFactory
    contextFactory = WebClientContextFactory()

# Enigma2 components
from Components.ActionMap import ActionMap
from Components.Pixmap import Pixmap
from Components.Sources.List import List
from Screens.MessageBox import MessageBox
from Screens.Screen import Screen
from Screens.VirtualKeyBoard import VirtualKeyBoard
from Tools.LoadPixmap import LoadPixmap
from collections import OrderedDict
from enigma import ePicLoad, eServiceReference, eTimer

# Local imports
from . import _
from . import vodplayer
from . import xstreamity_globals as glob
from .plugin import (cfg, common_path, dir_tmp, downloads_json, pythonVer, screenwidth, skin_directory, debugs)
from .xStaticText import StaticText

hdr = {
    'User-Agent': str(cfg.useragent.value),
    'Accept-Encoding': 'gzip, deflate'
}

playlists_json = cfg.playlists_json.value


class XStreamity_Series_Categories(Screen):
    ALLOW_SUSPEND = True

    def __init__(self, session):
        if debugs:
            print("*** init ***")

        Screen.__init__(self, session)
        self.session = session
        glob.categoryname = "series"

        self.agent = Agent(reactor, contextFactory=contextFactory)
        self.cover_download_deferred = None
        self.logo_download_deferred = None
        self.backdrop_download_deferred = None

        self.skin_path = os.path.join(skin_directory, cfg.skin.value)
        skin = os.path.join(self.skin_path, "vod_categories.xml")
        if os.path.exists("/var/lib/dpkg/status"):
            skin = os.path.join(self.skin_path, "DreamOS/vod_categories.xml")

        with codecs.open(skin, "r", encoding="utf-8") as f:
            self.skin = f.read()

        self.setup_title = _("Series Categories")

        self.main_title = _("Series")
        self["main_title"] = StaticText(self.main_title)

        self.main_list = []
        self["main_list"] = List(self.main_list, enableWrapAround=True)

        self["x_title"] = StaticText()
        self["x_description"] = StaticText()

        self["overview"] = StaticText()
        self["tagline"] = StaticText()
        self["facts"] = StaticText()

        # skin vod variables
        self["vod_cover"] = Pixmap()
        self["vod_cover"].hide()
        self["vod_backdrop"] = Pixmap()
        self["vod_backdrop"].hide()
        self["vod_logo"] = Pixmap()
        self["vod_logo"].hide()
        self["vod_director_label"] = StaticText()
        self["vod_country_label"] = StaticText()
        self["vod_cast_label"] = StaticText()
        self["vod_director"] = StaticText()
        self["vod_country"] = StaticText()
        self["vod_cast"] = StaticText()

        self["rating_text"] = StaticText()
        self["rating_percent"] = StaticText()

        # pagination variables
        self["page"] = StaticText("")
        self["listposition"] = StaticText("")
        self.itemsperpage = 10

        self.searchString = ""
        self.filterresult = ""

        self.chosen_category = ""

        self.pin = False
        self.tmdbresults = {}

        self.storedtitle = ""
        self.storedseason = ""
        self.storedepisode = ""
        self.storedyear = ""
        self.storedcover = ""
        self.storedtmdb = ""
        self.storedbackdrop = ""
        self.storedlogo = ""
        self.storeddescription = ""
        self.storedcast = ""
        self.storeddirector = ""
        self.storedgenre = ""
        self.storedreleasedate = ""
        self.storedrating = ""

        self.repeatcount = 0

        self.sortindex = 0
        self.sortText = _("Sort: A-Z")

        self.level = 1

        self.host = glob.active_playlist["playlist_info"]["host"]
        self.username = glob.active_playlist["playlist_info"]["username"]
        self.password = glob.active_playlist["playlist_info"]["password"]
        self.output = glob.active_playlist["playlist_info"]["output"]
        self.name = glob.active_playlist["playlist_info"]["name"]

        self.player_api = glob.active_playlist["playlist_info"]["player_api"]
        # self.liveStreamsData = []

        self.token = "ZUp6enk4cko4ZzBKTlBMTFNxN3djd25MOHEzeU5Zak1Bdkd6S3lPTmdqSjhxeUxMSTBNOFRhUGNBMjBCVmxBTzlBPT0K"

        next_url = str(self.player_api) + "&action=get_series_categories"

        # buttons / keys
        self["key_red"] = StaticText(_("Back"))
        self["key_green"] = StaticText(_("OK"))
        self["key_yellow"] = StaticText(self.sortText)
        self["key_blue"] = StaticText(_("Search"))
        self["key_epg"] = StaticText("")
        self["key_menu"] = StaticText("")

        self["category_actions"] = ActionMap(["XStreamityActions"], {
            "cancel": self.back,
            "red": self.back,
            "ok": self.parentalCheck,
            "green": self.parentalCheck,
            "yellow": self.sort,
            "blue": self.search,
            "left": self.pageUp,
            "right": self.pageDown,
            "up": self.goUp,
            "down": self.goDown,
            "channelUp": self.pageUp,
            "channelDown": self.pageDown,
            "0": self.reset,
            "menu": self.showHiddenList,
        }, -2)

        self["channel_actions"] = ActionMap(["XStreamityActions"], {
            "cancel": self.back,
            "red": self.back,
            "ok": self.parentalCheck,
            "green": self.parentalCheck,
            "yellow": self.sort,
            "blue": self.search,
            "left": self.pageUp,
            "right": self.pageDown,
            "up": self.goUp,
            "down": self.goDown,
            "channelUp": self.pageUp,
            "channelDown": self.pageDown,
            "rec": self.downloadVideo,
            "5": self.downloadVideo,
            "0": self.reset,
            "menu": self.showHiddenList,
            "1": self.clearWatched,
            "tv": self.favourite,
            "stop": self.favourite,
        }, -2)

        self["channel_actions"].setEnabled(False)

        glob.nextlist = []
        glob.nextlist.append({"next_url": next_url, "index": 0, "level": self.level, "sort": self.sortText, "filter": ""})

        self.coverLoad = ePicLoad()
        try:
            self.coverLoad.PictureData.get().append(self.DecodeCover)
        except:
            self.coverLoad_conn = self.coverLoad.PictureData.connect(self.DecodeCover)

        self.backdropLoad = ePicLoad()
        try:
            self.backdropLoad.PictureData.get().append(self.DecodeBackdrop)
        except:
            self.backdropLoad_conn = self.backdropLoad.PictureData.connect(self.DecodeBackdrop)

        self.logoLoad = ePicLoad()
        try:
            self.logoLoad.PictureData.get().append(self.DecodeLogo)
        except:
            self.logoLoad_conn = self.logoLoad.PictureData.connect(self.DecodeLogo)

        self.onFirstExecBegin.append(self.createSetup)
        self.onLayoutFinish.append(self.__layoutFinished)

    def __layoutFinished(self):
        self.setTitle(self.setup_title)

    def goUp(self):
        instance = self["main_list"].master.master.instance
        instance.moveSelection(instance.moveUp)
        self.selectionChanged()

    def goDown(self):
        instance = self["main_list"].master.master.instance
        instance.moveSelection(instance.moveDown)
        self.selectionChanged()

    def pageUp(self):
        instance = self["main_list"].master.master.instance
        instance.moveSelection(instance.pageUp)
        self.selectionChanged()

    def pageDown(self):
        instance = self["main_list"].master.master.instance
        instance.moveSelection(instance.pageDown)
        self.selectionChanged()

    def reset(self):
        self["main_list"].setIndex(0)
        self.selectionChanged()

    def createSetup(self, data=None):
        if debugs:
            print("*** createSetup ***")

        self["x_title"].setText("")
        self["x_description"].setText("")

        if self.level == 1:
            self.getCategories()

        elif self.level == 2:
            self.getSeries()

        elif self.level == 3:
            self.getSeasons()

        elif self.level == 4:
            self.getEpisodes()

        self.getSortOrder()
        self.buildLists()

    def getSortOrder(self):
        if debugs:
            print("*** getSortOrder ***")

        if self.level == 1:
            self.sortText = cfg.seriescategoryorder.value
            sortlist = [_("Sort: A-Z"), _("Sort: Z-A"), _("Sort: Original")]
            activelist = self.list1
        elif self.level == 2:
            self.sortText = cfg.seriesorder.value
            sortlist = [_("Sort: A-Z"), _("Sort: Z-A"), _("Sort: Added"), _("Sort: Year"), _("Sort: Original")]
            activelist = self.list2
        else:
            return

        current_sort = self.sortText

        if not current_sort:
            return

        self.sortindex = 0

        for index, item in enumerate(sortlist):
            if str(item) == str(self.sortText):
                self.sortindex = index
                break

        if self["main_list"].getCurrent():
            self["main_list"].setIndex(0)

        if current_sort == _("Sort: A-Z"):
            activelist.sort(key=lambda x: x[1].lower(), reverse=False)

        elif current_sort == _("Sort: Z-A"):
            activelist.sort(key=lambda x: x[1].lower(), reverse=True)

        elif current_sort == _("Sort: Added"):
            activelist.sort(key=lambda x: x[1].lower(), reverse=False)
            activelist.sort(key=lambda x: (x[10] or ""), reverse=True)

        elif current_sort == _("Sort: Year"):
            activelist.sort(key=lambda x: x[1].lower(), reverse=False)
            activelist.sort(key=lambda x: (x[14] or ""), reverse=True)

        elif current_sort == _("Sort: Original"):
            activelist.sort(key=lambda x: x[0], reverse=False)

        next_sort_type = next(islice(cycle(sortlist), self.sortindex + 1, None))
        self.sortText = str(next_sort_type)

        self["key_yellow"].setText(self.sortText)
        glob.nextlist[-1]["sort"] = self["key_yellow"].getText()

        if self.level == 1:
            self.list1 = activelist

        elif self.level == 2:
            self.list2 = activelist

        elif self.level == 3:
            self.list3 = activelist

        elif self.level == 4:
            self.list4 = activelist

    def buildLists(self):
        if debugs:
            print("*** buildLists ***")

        if self.level == 1:
            self.buildCategories()

        elif self.level == 2:
            self.buildSeries()

        elif self.level == 3:
            self.buildSeasons()

        elif self.level == 4:
            self.buildEpisodes()

        self.resetButtons()
        self.selectionChanged()

    def getCategories(self):
        if debugs:
            print("*** getCategories **")

        index = 0
        self.list1 = []
        self.prelist = []

        # no need to download. Already downloaded and saved in playlist menu
        currentPlaylist = glob.active_playlist
        currentCategoryList = currentPlaylist.get("data", {}).get("series_categories", [])
        currentHidden = set(currentPlaylist.get("player_info", {}).get("serieshidden", []))

        hiddenfavourites = "-1" in currentHidden
        hidden = "0" in currentHidden

        i = 0

        self.prelist.extend([
            [i, _("FAVOURITES"), "-1", hiddenfavourites],
            [i + 1, _("ALL"), "0", hidden]
        ])

        for index, item in enumerate(currentCategoryList, start=len(self.prelist)):
            category_name = item.get("category_name", "No category")
            category_id = item.get("category_id", "999999")
            hidden = category_id in currentHidden
            self.list1.append([index, str(category_name), str(category_id), hidden])

        glob.originalChannelList1 = self.list1[:]

    def getSeries(self):
        if debugs:
            print("*** getSeries ***")

        response = ""

        if self.chosen_category == "favourites":
            response = glob.active_playlist["player_info"].get("seriesfavourites", [])
        else:
            response = self.downloadApiData(glob.nextlist[-1]["next_url"])

        self.series_info = ""
        index = 0
        self.list2 = []

        self.storedtitle = ""
        self.storedseason = ""
        self.storedepisode = ""
        self.storedyear = ""
        self.storedcover = ""
        self.storedtmdb = ""
        self.storedbackdrop = ""
        self.storedlogo = ""
        self.storeddescription = ""
        self.storedcast = ""
        self.storeddirector = ""
        self.storedgenre = ""
        self.storedreleasedate = ""
        self.storedrating = ""
        self.tmdbretry = 0

        if response:
            for index, channel in enumerate(response):
                name = str(channel.get("name", ""))

                if not name or name == "None":
                    continue

                if name and '\" ' in name:
                    parts = name.split('\" ', 1)
                    if len(parts) > 1:
                        name = parts[0]

                if "stream_type" in channel and channel["stream_type"] and (channel["stream_type"] not in ["movie", "series"]):
                    continue

                series_id = channel.get("series_id", "")
                if not series_id:
                    continue

                hidden = str(series_id) in glob.active_playlist["player_info"]["seriestitleshidden"]

                cover = str(channel.get("cover", ""))
                if cover and cover.startswith("http"):
                    try:
                        cover = cover.replace(r"\/", "/")
                    except:
                        pass

                    if cover == "https://image.tmdb.org/t/p/w600_and_h900_bestv2":
                        cover = ""

                    if cover.startswith("https://image.tmdb.org/t/p/") or cover.startswith("http://image.tmdb.org/t/p/"):
                        dimensions = cover.partition("/p/")[2].partition("/")[0]

                        if screenwidth.width() <= 1280:
                            cover = cover.replace(dimensions, "w200")
                        elif screenwidth.width() <= 1920:
                            cover = cover.replace(dimensions, "w300")
                        else:
                            cover = cover.replace(dimensions, "w400")
                else:
                    cover = ""

                last_modified = str(channel.get("last_modified", "0"))

                category_id = str(channel.get("category_id", ""))
                if self.chosen_category == "all" and str(category_id) in glob.active_playlist["player_info"]["serieshidden"]:
                    continue

                rating = str(channel.get("rating", ""))

                plot = str(channel.get("plot", ""))

                cast = str(channel.get("cast", ""))

                director = str(channel.get("director", ""))

                genre = str(channel.get("genre", ""))

                tmdb = channel.get("tmdb", "")

                releaseDate = (channel.get("releaseDate") or channel.get("release_date") or channel.get("releasedate") or "")
                releaseDate = str(releaseDate) if releaseDate is not None else ""

                year = str(channel.get("year", ""))

                if year == "":
                    pattern = r'\b\d{4}\b'
                    matches = re.findall(pattern, name)
                    if matches:
                        year = str(matches[-1])

                if not year and releaseDate:
                    year_match = re.match(r'(\d{4})', releaseDate)
                    if year_match:
                        year = year_match.group(1)

                if year:
                    self.storedyear = year
                else:
                    self.storedyear = ""

                backdrop_path = channel.get("backdrop_path", "")

                if backdrop_path:
                    try:
                        backdrop_path = channel["backdrop_path"][0]
                    except:
                        pass

                favourite = False
                if "seriesfavourites" in glob.active_playlist["player_info"]:
                    for fav in glob.active_playlist["player_info"]["seriesfavourites"]:
                        if str(series_id) == str(fav["series_id"]):
                            favourite = True
                            break
                else:
                    glob.active_playlist["player_info"]["vodfavourites"] = []

                next_url = "{}&action=get_series_info&series_id={}".format(str(self.player_api), str(series_id))

                # 0 index, 1 name, 2 series_id, 3 cover, 4 plot, 5 cast, 6 director, 7 genre, 8 releaseDate, 9 rating, 10 last_modified, 11 next_url, 12 tmdb, 13 hidden, 14 year, 15 backdrop
                self.list2.append([index, str(name), str(series_id), str(cover), str(plot), str(cast), str(director), str(genre), str(releaseDate), str(rating), str(last_modified), str(next_url), str(tmdb), hidden, str(year), str(backdrop_path), favourite])

        glob.originalChannelList2 = self.list2[:]

        """
        else:
            if not self.chosen_category == "favourites":
                self.session.open(MessageBox, _("No series found in this category."), type=MessageBox.TYPE_ERROR, timeout=5)
            else:
                self.session.open(MessageBox, _("No Favourites added."), type=MessageBox.TYPE_ERROR, timeout=5)
                """

    def getSeasons(self):
        if debugs:
            print("**** getSeasons ****")

        if not self.series_info:
            response = self.downloadApiData(glob.nextlist[-1]["next_url"])
            self.series_info = response
        else:
            response = self.series_info

        index = 0
        self.list3 = []

        if response:
            currentChannelList = response
            if "info" in currentChannelList and currentChannelList["info"]:
                infodict = response["info"]
                if infodict:
                    tmdb = infodict.get("tmdb", self.tmdb2)
                    if tmdb:
                        self.tmdb2 = tmdb
                    name = infodict.get("name", self.title2)
                    cover = infodict.get("cover", self.cover2)
                    if not cover.startswith("http"):
                        cover = self.cover2
                    overview = infodict.get("plot", self.plot2)
                    cast = infodict.get("cast", self.cast2)
                    director = infodict.get("director", self.director2)
                    genre = infodict.get("genre", self.genre2)
                    airdate = infodict.get("releaseDate") or infodict.get("release_date") or self.releaseDate2
                    rating = infodict.get("rating", self.rating2)
                    last_modified = infodict.get("last_modified", "0")
                    backdrop_path = infodict.get("backdrop_path", self.backdrop_path2)

                    if "backdrop_path" in infodict and infodict["backdrop_path"]:
                        try:
                            backdrop_path = infodict["backdrop_path"][0]
                        except:
                            pass
            else:
                return

            if "episodes" in currentChannelList and currentChannelList["episodes"]:
                episodes = currentChannelList["episodes"]
                seasonlist = []
                self.isdict = True

                try:
                    seasonlist = list(episodes.keys())
                except Exception as e:
                    print(e)

                    self.isdict = False
                    x = 0
                    for item in episodes:
                        seasonlist.append(x)
                        x += 1

                if seasonlist:
                    parent_index = glob.nextlist[1]["index"]
                    parent_id = self.list2[parent_index][2]

                    for index, season in enumerate(seasonlist):
                        name = _("Season ") + str(season)

                        if self.isdict:
                            season_number = episodes[str(season)][0]["season"]
                        else:
                            season_number = episodes[season][0]["season"]

                        series_id = 0
                        hidden = False

                        if "seasons" in currentChannelList and currentChannelList["seasons"]:
                            for item in currentChannelList["seasons"]:
                                if "season_number" in item and str(item["season_number"]) == str(season_number):

                                    if "airdate" in item and item["airdate"]:
                                        airdate = item["airdate"]
                                    elif "air_date" in item and item["air_date"]:
                                        airdate = item["air_date"]

                                    if "name" in item and item["name"]:
                                        name = item["name"]

                                    if "overview" in item and item["overview"] and len(item["overview"]) > 50 and "http" not in item["overview"]:
                                        overview = item["overview"]

                                    if "cover_tmdb" in item and item["cover_tmdb"] and item["cover_tmdb"].startswith("http") and len(item["cover_tmdb"]) > 50:
                                        cover = item["cover_tmdb"]

                                    elif "cover_big" in item and item["cover_big"] and item["cover_big"].startswith("http") and len(item["cover_big"]) > 50:
                                        cover = item["cover_big"]

                                    elif "cover" in item and item["cover"] and item["cover"].startswith("http") and len(item["cover_big"]) > 50:
                                        cover = item["cover"]

                                    if "id" in item and item["id"]:
                                        series_id = item["id"]
                                    break

                        if str(series_id) in glob.active_playlist["player_info"]["seriesseasonshidden"]:
                            hidden = True

                        if cover and cover.startswith("http"):

                            try:
                                cover = cover.replace(r"\/", "/")
                            except:
                                pass

                            if cover == "https://image.tmdb.org/t/p/w600_and_h900_bestv2":
                                cover = self.cover2

                            if cover.startswith("https://image.tmdb.org/t/p/") or cover.startswith("http://image.tmdb.org/t/p/"):
                                dimensions = cover.partition("/p/")[2].partition("/")[0]

                                if screenwidth.width() <= 1280:
                                    cover = cover.replace(dimensions, "w200")
                                elif screenwidth.width() <= 1920:
                                    cover = cover.replace(dimensions, "w300")
                                else:
                                    cover = cover.replace(dimensions, "w400")

                        next_url = self.seasons_url

                        # 0 index, 1 name, 2 series_id, 3 cover, 4 overview, 5 cast, 6 director, 7 genre, 8 airdate, 9 rating, 10 last_modified, 11 next_url, 12 tmdb, 13 hidden, 14 season_number, 15 backdrop, 16 parent_index, 17 parent_id
                        self.list3.append([index, str(name), str(series_id), str(cover), str(overview), str(cast), str(director), str(genre), str(airdate), str(rating), str(last_modified), str(next_url), tmdb, hidden, season_number, str(backdrop_path), parent_index, str(parent_id)])

                self.list3.sort(key=self.natural_keys)

            if cover:
                self.storedcover = cover

        glob.originalChannelList3 = self.list3[:]

    def getEpisodes(self):
        if debugs:
            print("**** getEpisodes ****")

        response = self.series_info
        index = 0
        self.list4 = []
        currentChannelList = response

        shorttitle = self.title2
        cover = self.storedcover
        plot = ""
        cast = self["vod_cast"].getText()
        director = self["vod_director"].getText()
        genre = ""
        releasedate = ""
        rating = ""

        tmdb_id = self.tmdb2
        last_modified = "0"

        if currentChannelList:
            if "info" in currentChannelList:
                if "name" in currentChannelList["info"] and currentChannelList["info"]["name"]:
                    shorttitle = currentChannelList["info"]["name"]

                if "cover" in currentChannelList["info"] and currentChannelList["info"]["cover"]:
                    cover = currentChannelList["info"]["cover"]

                if "plot" in currentChannelList["info"] and currentChannelList["info"]["plot"]:
                    plot = currentChannelList["info"]["plot"]

                if "cast" in currentChannelList["info"] and currentChannelList["info"]["cast"]:
                    cast = currentChannelList["info"]["cast"]

                if "director" in currentChannelList["info"] and currentChannelList["info"]["director"]:
                    director = currentChannelList["info"]["director"]

                if "genre" in currentChannelList["info"] and currentChannelList["info"]["genre"]:
                    genre = currentChannelList["info"]["genre"]

                if "releaseDate" in currentChannelList["info"] and currentChannelList["info"]["releaseDate"]:
                    releasedate = currentChannelList["info"]["releaseDate"]

                elif "release_date" in currentChannelList["info"] and currentChannelList["info"]["release_date"]:
                    releasedate = currentChannelList["info"]["release_date"]

                if "rating" in currentChannelList["info"] and currentChannelList["info"]["rating"]:
                    rating = currentChannelList["info"]["rating"]

                if "last_modified" in currentChannelList["info"] and currentChannelList["info"]["last_modified"]:
                    last_modified = currentChannelList["info"]["last_modified"]

                if "tmdb_id" in currentChannelList["info"] and currentChannelList["info"]["tmdb_id"]:
                    tmdb_id = currentChannelList["info"]["tmdb_id"]

            if "episodes" in currentChannelList:
                if currentChannelList["episodes"]:

                    season_number = str(self.storedseason)
                    if self.isdict is False:
                        season_number = int(self.storedseason)

                    parent_index = glob.nextlist[1]["index"]
                    parent_id = self.list2[parent_index][2]

                    for index, item in enumerate(currentChannelList["episodes"][season_number]):
                        title = ""
                        stream_id = ""
                        container_extension = "mp4"
                        # tmdb_id = ""
                        duration = ""
                        hidden = False

                        if "id" in item:
                            stream_id = item["id"]
                        else:
                            continue

                        if "title" in item:
                            title = item["title"].replace(str(shorttitle) + " - ", "")
                            title = re.sub(r'^.*?\.', '', title)

                        if "container_extension" in item:
                            container_extension = item["container_extension"]

                        if "episode_num" in item:
                            episode_num = item["episode_num"]

                        if "info" in item:
                            if "releaseDate" in item["info"]:
                                releasedate = item["info"]["releaseDate"]

                            elif "release_date" in item["info"]:
                                releasedate = item["info"]["release_date"]

                            elif "air_date" in item["info"]:
                                releasedate = item["info"]["air_date"]

                            if "plot" in item["info"]:
                                plot = item["info"]["plot"]

                            if "duration" in item["info"]:
                                duration = item["info"]["duration"]

                            if "rating" in item["info"]:
                                rating = item["info"]["rating"]

                            if "seasons" in currentChannelList:
                                if currentChannelList["seasons"]:
                                    for season in currentChannelList["seasons"]:
                                        if int(season["season_number"]) == int(season_number):
                                            if "cover" in season and season["cover"]:
                                                cover = season["cover"]

                                            if "cover_big" in season and season["cover_big"]:
                                                cover = season["cover_big"]
                                            break

                        if cover:
                            cover = cover.replace(r"\/", "/")
                            if cover and cover.startswith("http"):
                                if cover == "https://image.tmdb.org/t/p/w600_and_h900_bestv2":
                                    cover = ""

                                if cover.startswith("https://image.tmdb.org/t/p/") or cover.startswith("http://image.tmdb.org/t/p/"):
                                    dimensions = cover.partition("/p/")[2].partition("/")[0]
                                    if screenwidth.width() <= 1280:
                                        cover = cover.replace(dimensions, "w300")
                                    else:
                                        cover = cover.replace(dimensions, "w400")

                            else:
                                cover = ""

                        hidden = str(stream_id) in glob.active_playlist["player_info"]["seriesepisodeshidden"]

                        next_url = "{}/series/{}/{}/{}.{}".format(self.host, self.username, self.password, stream_id, container_extension)

                        # 0 index, 1 title, 2 stream_id, 3 cover, 4 plot, 5 cast, 6 director, 7 genre, 8 releasedate, 9 rating, 10 last_modified, 11 next_url, 12 tmdb_id, 13 hidden, 14 duration, 15 container_extension, 16 shorttitle, 17 episode_num, 18 parent_index, 19 parent_id
                        self.list4.append([index, str(title), str(stream_id), str(cover), str(plot), str(cast), str(director), str(genre), str(releasedate), str(rating), str(last_modified), str(next_url), str(tmdb_id), hidden, str(duration), str(container_extension),  str(shorttitle), episode_num, parent_index, str(parent_id)])

        glob.originalChannelList4 = self.list4[:]

    def downloadApiData(self, url):
        if debugs:
            print("*** downloadApiData ***", url)

        retries = Retry(total=2, backoff_factor=1)
        adapter = HTTPAdapter(max_retries=retries)

        with requests.Session() as http:
            http.mount("http://", adapter)
            http.mount("https://", adapter)

            try:
                response = http.get(url, headers=hdr, timeout=(10, 30), verify=False)
                response.raise_for_status()

                if response.status_code == requests.codes.ok:
                    try:
                        return response.json()
                    except ValueError:
                        print("JSON decoding failed.")
                        return None
            except Exception as e:
                print("Error occurred during API data download:", e)
                self.session.openWithCallback(self.back, MessageBox, _("Server error or invalid link."), MessageBox.TYPE_ERROR, timeout=3)

    def buildCategories(self):
        if debugs:
            print("*** buildCategories ***")

        self.hideVod()

        if self["key_blue"].getText() != _("Reset Search"):
            self.pre_list = [buildCategoryList(x[0], x[1], x[2], x[3]) for x in self.prelist if not x[3]]
        else:
            self.pre_list = []

        self.main_list = [buildCategoryList(x[0], x[1], x[2], x[3]) for x in self.list1 if not x[3]]

        self["main_list"].setList(self.pre_list + self.main_list)

        if self["main_list"].getCurrent():
            self["main_list"].setIndex(glob.nextlist[-1]["index"])

    def buildSeries(self):
        if debugs:
            print("*** buildSeries ***")

        self.main_list = []

        # 0 index, 1 name, 2 series_id, 3, cover, 4 plot, 5 cast, 6 director, 7 genre, 8 releasedate, 9 last modified, 10 rating, 11 backdrop_path, 12 tmdb, 13 year, 14 next url, 15 hidden
        self.main_list = [buildSeriesTitlesList(x[0], x[1], x[2], x[3], x[4], x[5], x[6], x[7], x[8], x[9], x[10], x[11], x[12], x[13], x[14], x[15], x[16]) for x in self.list2 if not x[13]]
        self["main_list"].setList(self.main_list)

        self.showVod()

        if self["main_list"].getCurrent():
            self["main_list"].setIndex(glob.nextlist[-1]["index"])

    def buildSeasons(self):
        if debugs:
            print("*** buildSeasons ***")

        self.main_list = []

        self.main_list = [buildSeriesSeasonsList(x[0], x[1], x[2], x[3], x[4], x[5], x[6], x[7], x[8], x[9], x[10], x[11], x[12], x[13], x[14], x[15], x[16], x[17]) for x in self.list3 if not x[13]]
        self["main_list"].setList(self.main_list)

        if self["main_list"].getCurrent():
            self["main_list"].setIndex(glob.nextlist[-1]["index"])

    def buildEpisodes(self):
        if debugs:
            print("*** buildEpisodes ***")

        self.main_list = []

        self.main_list = [buildSeriesEpisodesList(x[0], x[1], x[2], x[3], x[4], x[5], x[6], x[7], x[8], x[9], x[10], x[11], x[12], x[13], x[14], x[15], x[16], x[17], x[18], x[19]) for x in self.list4 if not x[13]]
        self["main_list"].setList(self.main_list)
        if self["main_list"].getCurrent():
            self["main_list"].setIndex(glob.nextlist[-1]["index"])

    def displaySeriesData(self):
        if debugs:
            print("*** displaySeriesData ***")

        if self["main_list"].getCurrent():
            if cfg.TMDB.value is True:
                if self.level != 1:
                    self.tmdbValid = True
                    self.tmdbfailedcount = 0
                    self.getTMDB()

            else:
                self.displayTMDB()

    def selectionChanged(self):
        if debugs:
            print("*** selectionChanged ***")

        self.tmdbresults = ""
        self.tmdbretry = 0

        if self.cover_download_deferred:
            self.cover_download_deferred.cancel()

        if self.logo_download_deferred:
            self.logo_download_deferred.cancel()

        if self.backdrop_download_deferred:
            self.backdrop_download_deferred.cancel()

        current_item = self["main_list"].getCurrent()

        if current_item:
            channel_title = current_item[0]
            current_index = self["main_list"].getIndex()

            glob.currentchannellistindex = current_index
            glob.nextlist[-1]["index"] = current_index

            position = current_index + 1
            position_all = len(self.pre_list) + len(self.main_list) if self.level == 1 else len(self.main_list)
            page = (position - 1) // self.itemsperpage + 1
            page_all = int(math.ceil(position_all // self.itemsperpage) + 1)

            self["page"].setText(_("Page: ") + "{}/{}".format(page, page_all))
            self["listposition"].setText("{}/{}".format(position, position_all))

            self["main_title"].setText("{}: {}".format(self.main_title, channel_title))

            if self.level == 2:
                self.loadDefaultCover()
                self.loadDefaultBackdrop()

                self["vod_cover"].hide()
                self["vod_logo"].hide()
                self["vod_backdrop"].hide()

            if self.level == 3:
                self.loadDefaultCover()
                self["vod_cover"].hide()
                self["vod_logo"].hide()

            if self.level != 1:
                self.clearVod()
                self.timerSeries = eTimer()
                try:
                    self.timerSeries.stop()
                except:
                    pass
                try:
                    self.timerSeries.callback.append(self.displaySeriesData)
                except:
                    self.timerSeries_conn = self.timerSeries.timeout.connect(self.displaySeriesData)
                self.timerSeries.start(300, True)

        else:
            position = 0
            position_all = 0
            page = 0
            page_all = 0

            self["page"].setText(_("Page: ") + "{}/{}".format(page, page_all))
            self["listposition"].setText("{}/{}".format(position, position_all))
            self["key_yellow"].setText("")
            self["key_blue"].setText("")
            self.hideVod()

    def stripjunk(self, text, database=None):
        searchtitle = text.lower()

        # if title ends in "the", move "the" to the beginning
        if searchtitle.endswith("the"):
            searchtitle = "the " + searchtitle[:-4]

        # remove xx: at start
        searchtitle = re.sub(r'^\w{2}:', '', searchtitle)

        # remove xx|xx at start
        searchtitle = re.sub(r'^\w{2}\|\w{2}\s', '', searchtitle)

        # remove xx - at start
        searchtitle = re.sub(r'^.{2}\+? ?- ?', '', searchtitle)

        # remove all leading content between and including ||
        searchtitle = re.sub(r'^\|\|.*?\|\|', '', searchtitle)
        searchtitle = re.sub(r'^\|.*?\|', '', searchtitle)

        # remove everything left between pipes.
        searchtitle = re.sub(r'\|.*?\|', '', searchtitle)

        # remove all content between and including () multiple times unless it contains only numbers.
        searchtitle = re.sub(r'\((?!\d+\))[^()]*\)', '', searchtitle)

        # remove all content between and including [] multiple times
        searchtitle = re.sub(r'\[\[.*?\]\]|\[.*?\]', '', searchtitle)

        # List of bad strings to remove
        bad_strings = [

            "ae|", "al|", "ar|", "at|", "ba|", "be|", "bg|", "br|", "cg|", "ch|", "cz|", "da|", "de|", "dk|",
            "ee|", "en|", "es|", "eu|", "ex-yu|", "fi|", "fr|", "gr|", "hr|", "hu|", "in|", "ir|", "it|", "lt|",
            "mk|", "mx|", "nl|", "no|", "pl|", "pt|", "ro|", "rs|", "ru|", "se|", "si|", "sk|", "sp|", "tr|",
            "uk|", "us|", "yu|",
            "1080p", "1080p-dual-lat-cine-calidad.com", "1080p-dual-lat-cine-calidad.com-1",
            "1080p-dual-lat-cinecalidad.mx", "1080p-lat-cine-calidad.com", "1080p-lat-cine-calidad.com-1",
            "1080p-lat-cinecalidad.mx", "1080p.dual.lat.cine-calidad.com", "3d", "'", "#", "(", ")", "-", "[]", "/",
            "4k", "720p", "aac", "blueray", "ex-yu:", "fhd", "hd", "hdrip", "hindi", "imdb", "multi:", "multi-audio",
            "multi-sub", "multi-subs", "multisub", "ozlem", "sd", "top250", "u-", "uhd", "vod", "x264"
        ]

        # Remove numbers from 1900 to 2030
        if database == "TMDB":
            bad_strings.extend(map(str, range(1900, 2030)))

        # Construct a regex pattern to match any of the bad strings
        bad_strings_pattern = re.compile('|'.join(map(re.escape, bad_strings)))

        # Remove bad strings using regex pattern
        searchtitle = bad_strings_pattern.sub('', searchtitle)

        # List of bad suffixes to remove
        bad_suffix = [
            " al", " ar", " ba", " da", " de", " en", " es", " eu", " ex-yu", " fi", " fr", " gr", " hr", " mk",
            " nl", " no", " pl", " pt", " ro", " rs", " ru", " si", " swe", " sw", " tr", " uk", " yu"
        ]

        # Construct a regex pattern to match any of the bad suffixes at the end of the string
        bad_suffix_pattern = re.compile(r'(' + '|'.join(map(re.escape, bad_suffix)) + r')$')

        # Remove bad suffixes using regex pattern
        searchtitle = bad_suffix_pattern.sub('', searchtitle)

        # Replace ".", "_", "'" with " "
        searchtitle = re.sub(r'[._\'\*]', ' ', searchtitle)

        # Replace "-" with space and strip trailing spaces
        searchtitle = searchtitle.strip(' -')

        searchtitle = searchtitle.strip()
        return str(searchtitle)

    def getTMDB(self):
        if debugs:
            print("**** getTMDB ***")

        current_item = self["main_list"].getCurrent()

        if current_item:
            if self.level == 2:
                title = current_item[0]
                year = current_item[13]
                tmdb = current_item[14]
                cover = current_item[5]
                backdrop = current_item[15]

                if not year:
                    # Get year from release date
                    try:
                        year = current_item[10][:4]
                    except IndexError:
                        year = ""

                if year:
                    self.storedyear = year
                else:
                    self.storedyear = ""
                if title:
                    self.storedtitle = title
                if cover:
                    self.storedcover = cover
                if backdrop:
                    self.storedbackdrop = backdrop

            else:
                title = self.storedtitle
                year = self.storedyear

                if self.level == 3:
                    tmdb = current_item[15]

                if self.level == 4:
                    tmdb = current_item[14]

            if tmdb and self.tmdbValid and tmdb != "0":
                self.getTMDBDetails(tmdb)
                return

            try:
                os.remove(os.path.join(dir_tmp, "search.txt"))
            except:
                pass

            searchtitle = self.stripjunk(title, "TMDB")
            searchtitle = quote(searchtitle, safe="")

            searchurl = 'http://api.themoviedb.org/3/search/tv?api_key={}&query={}'.format(self.check(self.token), searchtitle)
            if self.storedyear:
                searchurl = 'http://api.themoviedb.org/3/search/tv?api_key={}&first_air_date_year={}&query={}'.format(self.check(self.token), self.storedyear, searchtitle)

            if pythonVer == 3:
                searchurl = searchurl.encode()

            filepath = os.path.join(dir_tmp, "search.txt")
            try:
                downloadPage(searchurl, filepath, timeout=10).addCallback(self.processTMDB).addErrback(self.failed)
            except Exception as e:
                print("download TMDB error {}".format(e))

    def failed(self, data=None):
        if debugs:
            print("*** failed ***")

        if data:
            print(data)
            self.tmdbValid = False
            self.getTMDB()

    def processTMDB(self, result=None):
        if debugs:
            print("*** processTMDB ***")

        resultid = ""
        search_file_path = os.path.join(dir_tmp, "search.txt")
        try:
            with codecs.open(search_file_path, "r", encoding="utf-8") as f:
                response = f.read()

            if response:
                self.searchresult = json.loads(response)
                if "results" in self.searchresult and self.searchresult["results"]:
                    resultid = self.searchresult["results"][0].get("id")
                    self.tmdb2 = resultid

                    if not resultid:
                        self.displayTMDB()
                        return

                    self.getTMDBDetails(resultid)
                else:
                    self.storedyear = ""
                    self.tmdbretry += 1
                    if self.tmdbretry < 2:
                        self.getTMDB()
                    else:
                        self.tmdbretry = 0
                        self.displayTMDB()
                        return

        except Exception as e:
            print("Error processing TMDB response:", e)

    def getTMDBDetails(self, resultid=None):
        if debugs:
            print(" *** getTMDBDetails ***")

        detailsurl = ""

        try:
            os.remove(os.path.join(dir_tmp, "search.txt"))
        except OSError:
            pass

        language = cfg.TMDBLanguage2.value
        languagestr = ""

        if language:
            languagestr = "&language=" + str(language)

        if self.level == 2:
            detailsurl = "http://api.themoviedb.org/3/tv/{}?api_key={}&append_to_response=credits,images,content_ratings{}&include_image_language=en".format(
                resultid, self.check(self.token), languagestr
            )

        elif self.level == 3:
            self.storedseason = self["main_list"].getCurrent()[12]
            detailsurl = "http://api.themoviedb.org/3/tv/{}/season/{}?api_key={}&append_to_response=credits,images,content_ratings{}&include_image_language=en".format(
                resultid, self.storedseason, self.check(self.token), languagestr
            )

        elif self.level == 4:
            self.storedepisode = self["main_list"].getCurrent()[18]
            detailsurl = "http://api.themoviedb.org/3/tv/{}/season/{}/episode/{}?api_key={}&append_to_response=credits,images,content_ratings{}&include_image_language=en".format(
                resultid, self.storedseason, self.storedepisode, self.check(self.token), languagestr
            )

        if pythonVer == 3:
            detailsurl = detailsurl.encode()

        filepath = os.path.join(dir_tmp, "search.txt")

        try:
            downloadPage(detailsurl, filepath, timeout=10).addCallback(self.processTMDBDetails).addErrback(self.failed2)
        except Exception as e:
            print("download TMDB details error:", e)

    def failed2(self, data=None):
        if debugs:
            print("*** failed 2 ***")

        if data:
            print(data)
            if self.level == 2:
                self.tmdbValid = False
                if self.repeatcount == 0:
                    self.getTMDB()
                    self.repeatcount += 1

            else:
                self.displayTMDB()
                return

    def processTMDBDetails(self, result=None):
        if debugs:
            print("*** processTMDBDetails ***")

        self.repeatcount = 0
        response = ""

        self.tmdbresults = {}
        self.tmdbdetails = []
        director = []
        country = []

        logos = None

        try:
            with codecs.open(os.path.join(dir_tmp, "search.txt"), "r", encoding="utf-8") as f:
                response = f.read()
        except Exception as e:
            print("Error reading TMDB response:", e)

        if response:
            try:
                self.tmdbdetails = json.loads(response, object_pairs_hook=OrderedDict)
            except Exception as e:
                print("Error parsing TMDB response:", e)
            else:
                if self.tmdbdetails:
                    if "name" in self.tmdbdetails and self.tmdbdetails["name"]:
                        self.tmdbresults["name"] = str(self.tmdbdetails["name"])

                    if "overview" in self.tmdbdetails and self.tmdbdetails["overview"]:
                        self.tmdbresults["description"] = str(self.tmdbdetails["overview"])

                    if "vote_average" in self.tmdbdetails and self.tmdbdetails["vote_average"]:
                        rating_str = str(self.tmdbdetails["vote_average"])

                        if rating_str not in [None, 0, 0.0, "0", "0.0"]:
                            try:
                                rating = float(rating_str)
                                rounded_rating = round(rating, 1)
                                self.tmdbresults["rating"] = "{:.1f}".format(rounded_rating)
                            except ValueError:
                                self.tmdbresults["rating"] = rating_str
                        else:
                            self.tmdbresults["rating"] = 0

                    if self.level == 2:
                        if "original_name" in self.tmdbdetails and self.tmdbdetails["original_name"]:
                            self.tmdbresults["o_name"] = str(self.tmdbdetails["original_name"])

                        if "episode_run_time" in self.tmdbdetails and self.tmdbdetails["episode_run_time"]:
                            runtime = self.tmdbdetails["episode_run_time"][0]
                        elif "runtime" in self.tmdbdetails:
                            runtime = self.tmdbdetails["runtime"]
                        else:
                            runtime = 0

                        if runtime and runtime != 0:
                            duration_timedelta = timedelta(minutes=runtime)
                            formatted_time = "{:0d}h {:02d}m".format(duration_timedelta.seconds // 3600, (duration_timedelta.seconds % 3600) // 60)
                            self.tmdbresults["duration"] = str(formatted_time)

                        if "first_air_date" in self.tmdbdetails and self.tmdbdetails["first_air_date"]:
                            self.tmdbresults["releaseDate"] = str(self.tmdbdetails["first_air_date"])

                        if "genres" in self.tmdbdetails and self.tmdbdetails["genres"]:
                            genre = []
                            for genreitem in self.tmdbdetails["genres"]:
                                genre.append(str(genreitem["name"]))
                            genre = " / ".join(map(str, genre))
                            self.tmdbresults["genre"] = genre

                        if "origin_country" in self.tmdbdetails and self.tmdbdetails["origin_country"]:
                            try:
                                country = self.tmdbdetails["origin_country"][0]
                                self.tmdbresults["country"] = country
                            except:
                                pass

                        if not country and "production_countries" in self.tmdbdetails and self.tmdbdetails["production_countries"]:
                            country = ", ".join(str(pcountry["name"]) for pcountry in self.tmdbdetails["production_countries"])
                            self.tmdbresults["country"] = country

                    if self.level != 4:
                        if "credits" in self.tmdbdetails:
                            if "cast" in self.tmdbdetails["credits"] and self.tmdbdetails["credits"]["cast"]:
                                cast = []
                                for actor in self.tmdbdetails["credits"]["cast"]:
                                    if "character" in actor and "name" in actor:
                                        cast.append(str(actor["name"]))
                                cast = ", ".join(map(str, cast[:10]))
                                self.tmdbresults["cast"] = cast

                            if "crew" in self.tmdbdetails["credits"] and self.tmdbdetails["credits"]["crew"]:
                                directortext = False
                                for actor in self.tmdbdetails["credits"]["crew"]:
                                    if "job" in actor and actor["job"] == "Director":
                                        director.append(str(actor["name"]))
                                        directortext = True
                                if directortext:
                                    director = ", ".join(map(str, director))
                                    self.tmdbresults["director"] = director

                        if "poster_path" in self.tmdbdetails and self.tmdbdetails["poster_path"]:
                            if screenwidth.width() <= 1280:
                                self.tmdbresults["cover_big"] = "http://image.tmdb.org/t/p/w200" + str(self.tmdbdetails["poster_path"])
                            elif screenwidth.width() <= 1920:
                                self.tmdbresults["cover_big"] = "http://image.tmdb.org/t/p/w300" + str(self.tmdbdetails["poster_path"])
                            else:
                                self.tmdbresults["cover_big"] = "http://image.tmdb.org/t/p/w400" + str(self.tmdbdetails["poster_path"])

                        if "backdrop_path" in self.tmdbdetails and self.tmdbdetails["backdrop_path"]:
                            self.tmdbresults["backdrop_path"] = "http://image.tmdb.org/t/p/w1280" + str(self.tmdbdetails["backdrop_path"])

                        if "images" in self.tmdbdetails and "logos" in self.tmdbdetails["images"]:
                            logos = self.tmdbdetails["images"]["logos"]
                            if logos:
                                logo_path = logos[0].get("file_path")

                                if screenwidth.width() <= 1280:
                                    self.tmdbresults["logo"] = "http://image.tmdb.org/t/p/w300" + str(logo_path)
                                elif screenwidth.width() <= 1920:
                                    self.tmdbresults["logo"] = "http://image.tmdb.org/t/p/w300" + str(logo_path)
                                else:
                                    self.tmdbresults["logo"] = "http://image.tmdb.org/t/p/w500" + str(logo_path)

                    if self.level != 2:
                        if "air_date" in self.tmdbdetails and self.tmdbdetails["air_date"]:
                            self.tmdbresults["releaseDate"] = str(self.tmdbdetails["air_date"])

                    if self.level == 4:
                        if "run_time" in self.tmdbdetails and self.tmdbdetails["run_time"]:
                            runtime = self.tmdbdetails["run_time"][0]
                        elif "runtime" in self.tmdbdetails:
                            runtime = self.tmdbdetails["runtime"]
                        # else:
                        #    runtime = 0

                        if runtime and runtime != 0:
                            duration_timedelta = timedelta(minutes=runtime)
                            formatted_time = "{:0d}h {:02d}m".format(duration_timedelta.seconds // 3600, (duration_timedelta.seconds % 3600) // 60)
                            self.tmdbresults["duration"] = str(formatted_time)

                    def get_certification(data, language_code):
                        fallback_codes = ["GB", "US"]

                        # First attempt to find the certification with the specified language code
                        if "content_ratings" in data and "results" in data["content_ratings"]:
                            for result in data["content_ratings"]["results"]:
                                if "iso_3166_1" in result and "rating" in result:
                                    if result["iso_3166_1"] == language_code:
                                        return result["rating"]

                            # If no match found or language_code is blank, try the fallback codes
                            for fallback_code in fallback_codes:
                                for result in data["content_ratings"]["results"]:
                                    if "iso_3166_1" in result and "rating" in result:
                                        if result["iso_3166_1"] == fallback_code:
                                            return result["rating"]

                            # If no match found in fallback codes, return None or an appropriate default value
                        return None

                    language = cfg.TMDBLanguage2.value
                    if not language:
                        language = "en-GB"

                    language = language.split("-")[1]

                    certification = get_certification(self.tmdbdetails, language)

                    if certification:
                        self.tmdbresults["certification"] = str(certification)

                    if "tagline" in self.tmdbdetails and self.tmdbdetails["tagline"].strip():
                        self.tmdbresults["tagline"] = str(self.tmdbdetails["tagline"])

                    self.displayTMDB()

    def displayTMDB(self):
        if debugs:
            print("*** displayTMDB ***")

        director = ""
        cast = ""
        facts = []
        tagline = ""
        duration = ""
        certification = ""
        release_date = ""
        genre = ""
        duration = ""
        rating = "0"
        country = ""

        current_item = self["main_list"].getCurrent()

        if current_item and self.level != 1:

            if self.level == 4:
                duration = current_item[12]
                try:
                    time_obj = datetime.strptime(duration, '%H:%M:%S')
                    duration = "{:0d}h {:02d}m".format(time_obj.hour, time_obj.minute)
                except:
                    pass

                stream_format = current_item[13]

            rating_texts = {
                (0.0, 0.0): "",
                (0.1, 0.5): "",
                (0.6, 1.0): "",
                (1.1, 1.5): "",
                (1.6, 2.0): "",
                (2.1, 2.5): "",
                (2.6, 3.0): "",
                (3.1, 3.5): "",
                (3.6, 4.0): "",
                (4.1, 4.5): "",
                (4.6, 5.0): "",
                (5.1, 5.5): "",
                (5.6, 6.0): "",
                (6.1, 6.5): "",
                (6.6, 7.0): "",
                (7.1, 7.5): "",
                (7.6, 8.0): "",
                (8.1, 8.5): "",
                (8.6, 9.0): "",
                (9.1, 9.5): "",
                (9.6, 10.0): "",
            }

            self["x_title"].setText(current_item[0])
            self["x_description"].setText(current_item[6])
            genre = current_item[9]

            try:
                rating = float(current_item[11])
            except:
                rating = 0

            director = current_item[8]
            cast = current_item[7]

            release_date = current_item[10]

            stream_url = current_item[3]

            if self.level == 4:
                try:
                    stream_format = stream_url.split(".")[-1]
                except:
                    pass
            else:
                stream_format = ""

            # # # # # # # # # # # # # # # # # # # # # # # # #

            if self.tmdbresults:
                info = self.tmdbresults

                if "name" in info:
                    self["x_title"].setText(str(info["name"]).strip())
                elif "o_name" in info:
                    self["x_title"].setText(str(info["o_name"]).strip())

                if "description" in info:
                    self["x_description"].setText(str(info["description"]).strip())
                elif "plot" in info:
                    self["x_description"].setText(str(info["plot"]).strip())

                if "duration" in info:
                    duration = str(info["duration"]).strip()

                if "genre" in info:
                    genre = str(info["genre"]).strip()

                try:
                    rating = float(info.get("rating", 0) or 0)
                except:
                    rating = 0

                for key in ["releaseDate", "release_date", "releasedate"]:
                    if key in info and info[key]:
                        try:
                            release_date = datetime.strptime(info[key], "%Y-%m-%d").strftime("%d-%m-%Y")
                            break
                        except Exception:
                            pass

                if "director" in info:
                    director = str(info["director"]).strip()

                if "country" in info:
                    country = str(info["country"]).strip()

                if "cast" in info:
                    cast = str(info["cast"]).strip()
                elif "actors" in info:
                    cast = str(info["actors"]).strip()

                certification = info.get("certification", "").strip().upper()

                if certification:
                    certification = _("Rating: ") + certification

                if "tagline" in info:
                    tagline = str(info["tagline"]).strip()

            for rating_range, rating_text in rating_texts.items():
                if rating_range[0] <= rating <= rating_range[1]:
                    text = rating_text
                    break
                else:
                    text = ""

            # percent dial
            self["rating_percent"].setText(str(text))

            rating_str = rating
            if rating_str and rating_str != 0:
                try:
                    rating = float(rating_str)
                    rounded_rating = round(rating, 1)
                    rating = "{:.1f}".format(rounded_rating)
                    if self.tmdbresults:
                        info["rating"] = rating
                except ValueError:
                    if self.tmdbresults:
                        info["rating"] = str(rating_str)

            self["rating_text"].setText(str(rating).strip())

            # # # facts section  # # #

            release_date = str(release_date).strip()

            try:
                release_date = datetime.strptime(release_date, "%Y-%m-%d").strftime("%d-%m-%Y")
            except Exception:
                pass

            facts = self.buildFacts(str(certification), str(release_date), str(genre), str(duration), str(stream_format))

            # # # # # # # # # # # #

            self["facts"].setText(str(facts))

            self["tagline"].setText(str(tagline).strip())

            self["vod_cast"].setText(str(cast).strip())

            self["vod_director"].setText(str(director).strip())

            self["vod_country"].setText(str(country).strip())

            if self["vod_cast"].getText() != "":
                self["vod_cast_label"].setText(_("Cast:"))
            else:
                self["vod_cast_label"].setText("")

            if self["vod_director"].getText() != "":
                self["vod_director_label"].setText(_("Director:"))
            else:
                self["vod_director_label"].setText("")

            if self["vod_country"].getText() != "":
                self["vod_country_label"].setText(_("Country:"))
            else:
                self["vod_country_label"].setText("")

            if self["x_description"].getText() != "":
                self["overview"].setText(_("Overview"))
            else:
                self["overview"].setText("")

            if self.level in (2, 3) and cfg.channelcovers.value:
                self.downloadCover()
                self.downloadBackdrop()
                self.downloadLogo()

    def resetButtons(self):
        if debugs:
            print("*** resetButtons ***")

        if glob.nextlist[-1]["filter"]:
            self["key_yellow"].setText("")
            self["key_blue"].setText(_("Reset Search"))
            self["key_menu"].setText("")
        else:
            if not glob.nextlist[-1]["sort"]:
                self.sortText = _("Sort: A-Z")
                glob.nextlist[-1]["sort"] = self.sortText

            self["key_blue"].setText(_("Search"))
            self["key_yellow"].setText(_(glob.nextlist[-1]["sort"]))
            self["key_menu"].setText("+/-")

            if self.chosen_category == "favourites":
                self["key_menu"].setText("")

    def downloadCover(self):
        if debugs:
            print("*** downloadCover ***")

        if cfg.channelcovers.value is False:
            return

        if self["main_list"].getCurrent():
            try:
                os.remove(os.path.join(dir_tmp, "cover.jpg"))
            except:
                pass

            desc_image = ""
            try:
                desc_image = self["main_list"].getCurrent()[5]
            except:
                pass

            if self.tmdbresults:
                desc_image = (str(self.tmdbresults.get("cover_big") or "").strip() or str(self.tmdbresults.get("movie_image") or "").strip() or self.storedcover or "")

            if self.cover_download_deferred and not self.cover_download_deferred.called:
                self.cover_download_deferred.cancel()

            if "http" in desc_image:
                self.redirect_count = 0
                self.cover_download_deferred = self.agent.request(b'GET', desc_image.encode(), Headers({'User-Agent': [b"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"]}))
                self.cover_download_deferred.addCallback(self.handleCoverResponse)
                self.cover_download_deferred.addErrback(self.handleCoverError)
            else:
                self.loadDefaultCover()

    def downloadLogo(self):
        if debugs:
            print("*** downloadLogo ***")

        if cfg.channelcovers.value is False:
            return

        if self["main_list"].getCurrent():
            try:
                os.remove(os.path.join(dir_tmp, "logo.png"))
            except:
                pass

            logo_image = ""

            if self.tmdbresults:  # tmbdb
                logo_image = str(self.tmdbresults.get("logo") or "").strip() or self.storedlogo or ""

                if self.logo_download_deferred and not self.logo_download_deferred.called:
                    self.logo_download_deferred.cancel()

                if "http" in logo_image:
                    self.logo_download_deferred = self.agent.request(b'GET', logo_image.encode(), Headers({'User-Agent': [b"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"]}))
                    self.logo_download_deferred.addCallback(self.handleLogoResponse)
                    self.logo_download_deferred.addErrback(self.handleLogoError)
                else:
                    self.loadDefaultLogo()
            else:
                self.loadDefaultLogo()

    def downloadBackdrop(self):
        if debugs:
            print("*** downloadBackdrop ***")

        if cfg.channelcovers.value is False:
            return

        if self["main_list"].getCurrent():
            try:
                os.remove(os.path.join(dir_tmp, "backdrop.jpg"))
            except:
                pass

            backdrop_image = ""

            if self.level == 2:
                try:
                    backdrop_image = self["main_list"].getCurrent()[15]
                except:
                    pass

            elif self.level == 3:
                try:
                    backdrop_image = self["main_list"].getCurrent()[16]
                except:
                    pass

            if self.tmdbresults:  # tmbdb
                # Check if "backdrop_path" exists and is not None
                backdrop_path = self.tmdbresults.get("backdrop_path")
                if backdrop_path:
                    backdrop_image = str(backdrop_path[0] if isinstance(backdrop_path, list) else backdrop_path).strip() or self.storedbackdrop or ""
                else:
                    backdrop_image = self.storedbackdrop or ""

            if self.backdrop_download_deferred and not self.backdrop_download_deferred.called:
                self.backdrop_download_deferred.cancel()

            if "http" in backdrop_image:
                self.backdrop_download_deferred = self.agent.request(b'GET', backdrop_image.encode(), Headers({'User-Agent': [b"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"]}))
                self.backdrop_download_deferred.addCallback(self.handleBackdropResponse)
                self.backdrop_download_deferred.addErrback(self.handleBackdropError)
            else:
                self.loadDefaultBackdrop()

    def downloadCoverFromUrl(self, url):
        if debugs:
            print("*** downloadCoverFromUrl ***")

        self.cover_download_deferred = self.agent.request(
            b'GET',
            url.encode(),
            Headers({'User-Agent': [b"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"]})
        )
        self.cover_download_deferred.addCallback(self.handleCoverResponse)
        self.cover_download_deferred.addErrback(self.handleCoverError)

    def handleCoverResponse(self, response):
        if debugs:
            print("*** handleCoverResponse ***")

        if response.code == 200:
            d = readBody(response)
            d.addCallback(self.handleCoverBody)
            return d
        elif response.code in (301, 302):
            if self.redirect_count < 2:
                self.redirect_count += 1
                location = response.headers.getRawHeaders('location')[0]
                self.downloadCoverFromUrl(location)
        else:
            self.handleCoverError("HTTP error code: %s" % response.code)

    def handleLogoResponse(self, response):
        if debugs:
            print("*** handleLogoResponse ***")

        if response.code == 200:
            d = readBody(response)
            d.addCallback(self.handleLogoBody)
            return d

    def handleBackdropResponse(self, response):
        if debugs:
            print("*** handleBackdropResponse ***")

        if response.code == 200:
            d = readBody(response)
            d.addCallback(self.handleBackdropBody)
            return d

    def handleCoverBody(self, body):
        if debugs:
            print("*** handleCoverBody ***")

        temp = os.path.join(dir_tmp, "cover.jpg")
        with open(temp, 'wb') as f:
            f.write(body)
        self.resizeCover(temp)

    def handleLogoBody(self, body):
        if debugs:
            print("***  handleLogoBody ***")
        temp = os.path.join(dir_tmp, "logo.png")
        with open(temp, 'wb') as f:
            f.write(body)
        self.resizeLogo(temp)

    def handleBackdropBody(self, body):
        if debugs:
            print("*** handleBackdropBody ***")
        temp = os.path.join(dir_tmp, "backdrop.jpg")
        with open(temp, 'wb') as f:
            f.write(body)
        self.resizeBackdrop(temp)

    def handleCoverError(self, error):
        if debugs:
            print("*** handleCoverError ***")

        print(error)
        self.loadDefaultCover()

    def handleLogoError(self, error):
        if debugs:
            print("*** handleLogoError ***")

        print(error)
        self.loadDefaultLogo()

    def handleBackdropError(self, error):
        if debugs:
            print("*** handleBackdropError ***")

        print(error)
        self.loadDefaultBackdrop()

    def loadDefaultCover(self, data=None):
        if debugs:
            print("*** loadDefaultCover ***")

        if self["vod_cover"].instance:
            self["vod_cover"].instance.setPixmapFromFile(os.path.join(skin_directory, "common/blank.png"))

    def loadDefaultLogo(self, data=None):
        if debugs:
            print("*** loadDefaultLogo ***")

        if self["vod_logo"].instance:
            self["vod_logo"].instance.setPixmapFromFile(os.path.join(skin_directory, "common/blank.png"))

    def loadDefaultBackdrop(self, data=None):
        if debugs:
            print("*** loadDefaultBackdrop ***")

        if self["vod_backdrop"].instance:
            self["vod_backdrop"].instance.setPixmapFromFile(os.path.join(skin_directory, "common/blank.png"))

    def resizeCover(self, data=None):
        if debugs:
            print("*** resizeCover ***")
        if self["main_list"].getCurrent() and self["vod_cover"].instance:
            preview = os.path.join(dir_tmp, "cover.jpg")
            if os.path.isfile(preview):
                try:
                    self.coverLoad.setPara([self["vod_cover"].instance.size().width(), self["vod_cover"].instance.size().height(), 1, 1, 0, 1, "FF000000"])
                    self.coverLoad.startDecode(preview)
                except Exception as e:
                    print(e)

    def resizeLogo(self, data=None):
        if debugs:
            print("*** resizeLogo ***")

        if self["main_list"].getCurrent() and self["vod_logo"].instance:
            preview = os.path.join(dir_tmp, "logo.png")
            if os.path.isfile(preview):
                width = self["vod_logo"].instance.size().width()
                height = self["vod_logo"].instance.size().height()
                size = [width, height]

                try:
                    im = Image.open(preview)
                    if im.mode != "RGBA":
                        im = im.convert("RGBA")

                    try:
                        im.thumbnail(size, Image.Resampling.LANCZOS)
                    except:
                        im.thumbnail(size, Image.ANTIALIAS)

                    bg = Image.new("RGBA", size, (255, 255, 255, 0))

                    left = (size[0] - im.size[0])

                    bg.paste(im, (left, 0), mask=im)

                    bg.save(preview, "PNG")

                    if self["vod_logo"].instance:
                        self["vod_logo"].instance.setPixmapFromFile(preview)
                        self["vod_logo"].show()
                except Exception as e:
                    print("Error resizing logo:", e)
                    self["vod_logo"].hide()

    def resizeBackdrop(self, data=None):
        if debugs:
            print("*** resizeBackdrop ***")

        if not (self["main_list"].getCurrent() and self["vod_backdrop"].instance):
            return

        preview = os.path.join(dir_tmp, "backdrop.jpg")
        if not os.path.isfile(preview):
            return

        try:
            bd_width, bd_height = self["vod_backdrop"].instance.size().width(), self["vod_backdrop"].instance.size().height()
            bd_size = [bd_width, bd_height]

            bg_size = [int(bd_width * 1.5), int(bd_height * 1.5)]

            im = Image.open(preview)
            if im.mode != "RGBA":
                im = im.convert("RGBA")

            try:
                im.thumbnail(bd_size, Image.Resampling.LANCZOS)
            except:
                im.thumbnail(bd_size, Image.ANTIALIAS)

            background = Image.open(os.path.join(self.skin_path, "images/background.png")).convert('RGBA')
            bg = background.crop((bg_size[0] - bd_width, 0, bg_size[0], bd_height))
            bg.save(os.path.join(dir_tmp, "backdrop2.png"), compress_level=0)
            mask = Image.open(os.path.join(skin_directory, "common/mask.png")).convert('RGBA')
            offset = (bg.size[0] - im.size[0], 0)
            bg.paste(im, offset, mask)
            bg.save(os.path.join(dir_tmp, "backdrop.png"), compress_level=0)

            output = os.path.join(dir_tmp, "backdrop.png")

            if self["vod_backdrop"].instance:
                self["vod_backdrop"].instance.setPixmapFromFile(output)
                self["vod_backdrop"].show()

        except Exception as e:
            print("Error resizing backdrop:", e)
            self["vod_backdrop"].hide()

    def DecodeCover(self, PicInfo=None):
        if debugs:
            print("*** DecodeCover ***")

        ptr = self.coverLoad.getData()
        if ptr is not None and self.level != 1:
            self["vod_cover"].instance.setPixmap(ptr)
            self["vod_cover"].show()
        else:
            self["vod_cover"].hide()

    def DecodeLogo(self, PicInfo=None):
        if debugs:
            print("*** DecodeLogo ***")

        ptr = self.logoLoad.getData()
        if ptr is not None and self.level != 2:
            self["vod_logo"].instance.setPixmap(ptr)
            self["vod_logo"].show()
        else:
            self["vod_logo"].hide()

    def DecodeBackdrop(self, PicInfo=None):
        if debugs:
            print("*** DecodeBackdrop ***")

        ptr = self.backdropLoad.getData()
        if ptr is not None and self.level != 2:
            self["vod_backdrop"].instance.setPixmap(ptr)
            self["vod_backdrop"].show()
        else:
            self["vod_backdrop"].hide()

    def sort(self):
        if debugs:
            print("*** sort ***")

        current_sort = self["key_yellow"].getText()
        if not current_sort:
            return

        if self.level == 1:
            activelist = self.list1

        elif self.level == 2:
            activelist = self.list2

        elif self.level == 3:
            activelist = self.list3

        elif self.level == 4:
            activelist = self.list4

        if self.level == 1:
            sortlist = [_("Sort: A-Z"), _("Sort: Z-A"), _("Sort: Original")]

        elif self.level == 2:
            sortlist = [_("Sort: A-Z"), _("Sort: Z-A"), _("Sort: Added"), _("Sort: Year"), _("Sort: Original")]
        else:
            sortlist = [_("Sort: A-Z"), _("Sort: Z-A"), _("Sort: Added"), _("Sort: Original")]

        self.sortindex = 0
        for index, item in enumerate(sortlist):
            if str(item) == str(self.sortText):
                self.sortindex = index
                break

        if self["main_list"].getCurrent():
            self["main_list"].setIndex(0)

        if current_sort == _("Sort: A-Z"):
            activelist.sort(key=lambda x: x[1].lower(), reverse=False)

        elif current_sort == _("Sort: Z-A"):
            activelist.sort(key=lambda x: x[1].lower(), reverse=True)

        elif current_sort == _("Sort: Added"):
            activelist.sort(key=lambda x: x[1].lower(), reverse=False)
            activelist.sort(key=lambda x: (x[10] or ""), reverse=True)

        elif current_sort == _("Sort: Year"):
            activelist.sort(key=lambda x: x[1].lower(), reverse=False)
            activelist.sort(key=lambda x: (x[14] or ""), reverse=True)

        elif current_sort == _("Sort: Original"):
            activelist.sort(key=lambda x: x[0], reverse=False)

        next_sort_type = next(islice(cycle(sortlist), self.sortindex + 1, None))
        self.sortText = str(next_sort_type)

        self["key_yellow"].setText(self.sortText)
        glob.nextlist[-1]["sort"] = self["key_yellow"].getText()

        if self.level == 1:
            self.list1 = activelist

        elif self.level == 2:
            self.list2 = activelist

        elif self.level == 3:
            self.list3 = activelist

        elif self.level == 4:
            self.list4 = activelist

        self.buildLists()

    def search(self, result=None):
        if debugs:
            print("*** search ***")

        if not self["key_blue"].getText():
            return

        current_filter = self["key_blue"].getText()

        if current_filter == _("Reset Search"):
            self.resetSearch()

        else:
            self.session.openWithCallback(self.filterChannels, VirtualKeyBoard, title=_("Filter this category..."), text=self.searchString)

    def filterChannels(self, result=None):
        if debugs:
            print("*** filterChannels ***")

        activelist = []

        if result:
            self.filterresult = result
            glob.nextlist[-1]["filter"] = self.filterresult

            if self.level == 1:
                activelist = self.list1

            elif self.level == 2:
                activelist = self.list2

            elif self.level == 3:
                activelist = self.list3

            elif self.level == 4:
                activelist = self.list4

            self.searchString = result
            activelist = [channel for channel in activelist if str(result).lower() in str(channel[1]).lower()]

            if not activelist:
                self.searchString = ""
                self.session.openWithCallback(self.search, MessageBox, _("No results found."), type=MessageBox.TYPE_ERROR, timeout=5)
            else:
                if self.level == 1:
                    self.list1 = activelist

                elif self.level == 2:
                    self.list2 = activelist

                elif self.level == 3:
                    self.list3 = activelist

                elif self.level == 4:
                    self.list4 = activelist

                self["key_blue"].setText(_("Reset Search"))
                self["key_yellow"].setText("")

                self.hideVod()
                self.buildLists()

    def resetSearch(self):
        if debugs:
            print("*** resetSearch ***")

        self["key_blue"].setText(_("Search"))
        self["key_yellow"].setText(self.sortText)

        if self.level == 1:
            activelist = glob.originalChannelList1[:]
            self.list1 = activelist

        elif self.level == 2:
            activelist = glob.originalChannelList2[:]
            self.list2 = activelist

        elif self.level == 3:
            activelist = glob.originalChannelList3[:]
            self.list3 = activelist

        elif self.level == 4:
            activelist = glob.originalChannelList4[:]
            self.list4 = activelist

        self.filterresult = ""
        glob.nextlist[-1]["filter"] = self.filterresult

        self.getSortOrder()
        self.buildLists()

    def pinEntered(self, result=None):
        if debugs:
            print("*** pinEntered ***")

        if not result:
            self.pin = False
            self.session.open(MessageBox, _("Incorrect pin code."), type=MessageBox.TYPE_ERROR, timeout=5)

        if self.pin is True:
            if pythonVer == 2:
                glob.pintime = int(time.mktime(datetime.now().timetuple()))
            else:
                glob.pintime = int(datetime.timestamp(datetime.now()))

            self.next()
        else:
            return

    def parentalCheck(self):
        if debugs:
            print("*** parentalCheck ***")

        self.pin = True
        nowtime = int(time.mktime(datetime.now().timetuple())) if pythonVer == 2 else int(datetime.timestamp(datetime.now()))

        if self.level == 1 and self["main_list"].getCurrent():
            adult_keywords = {"adult", "+18", "18+", "18 rated", "xxx", "sex", "porn", "voksen", "volwassen", "aikuinen", "Erwachsene", "dorosly", "взрослый", "vuxen", "£дорослий"}
            current_title_lower = str(self["main_list"].getCurrent()[0]).lower()

            if current_title_lower in {"all", _("all")} or "sport" in current_title_lower:
                glob.adultChannel = False
            elif any(keyword in current_title_lower for keyword in adult_keywords):
                glob.adultChannel = True
            else:
                glob.adultChannel = False

            if cfg.adult.value and nowtime - int(glob.pintime) > 900 and glob.adultChannel:
                from Screens.InputBox import PinInput
                self.session.openWithCallback(self.pinEntered, PinInput, pinList=[cfg.adultpin.value], triesEntry=cfg.retries.adultpin, title=_("Please enter the parental control pin code"), windowTitle=_("Enter pin code"))
            else:
                self.next()
        else:
            self.next()

    def next(self):
        if debugs:
            print("*** next ***")

        if self["main_list"].getCurrent():
            current_index = self["main_list"].getIndex()
            glob.nextlist[-1]["index"] = current_index
            glob.currentchannellist = self.main_list[:]
            glob.currentchannellistindex = current_index

            if self.level == 1:
                if self.list1:
                    category_id = self["main_list"].getCurrent()[3]

                    next_url = "{0}&action=get_series&category_id={1}".format(self.player_api, category_id)
                    self.chosen_category = ""

                    if category_id == "0":
                        next_url = "{0}&action=get_series".format(self.player_api)
                        self.chosen_category = "all"

                    elif category_id == "-1":
                        self.chosen_category = "favourites"

                    self.level += 1
                    self["main_list"].setIndex(0)

                    self["category_actions"].setEnabled(False)
                    self["channel_actions"].setEnabled(True)
                    self["key_yellow"].setText(_("Sort: A-Z"))

                    glob.nextlist.append({"next_url": next_url, "index": 0, "level": self.level, "sort": self["key_yellow"].getText(), "filter": ""})

                    self.createSetup()
                else:
                    self.createSetup()

            elif self.level == 2:
                if self.list2:
                    self.title2 = self["main_list"].getCurrent()[0]
                    self.cover2 = self["main_list"].getCurrent()[5]
                    self.plot2 = self["main_list"].getCurrent()[6]
                    self.cast2 = self["main_list"].getCurrent()[7]
                    self.director2 = self["main_list"].getCurrent()[8]
                    self.genre2 = self["main_list"].getCurrent()[9]
                    self.releaseDate2 = self["main_list"].getCurrent()[10]
                    self.rating2 = self["main_list"].getCurrent()[11]
                    self.backdrop_path2 = self["main_list"].getCurrent()[15]

                    if self["main_list"].getCurrent()[14] and self["main_list"].getCurrent()[14] != "0":
                        self.tmdb2 = self["main_list"].getCurrent()[14]
                    else:
                        self.tmdb2 = ""

                    next_url = self["main_list"].getCurrent()[3]
                    if "&action=get_series_info" in next_url:
                        self.seasons_url = self["main_list"].getCurrent()[3]

                    self.level += 1

                    self["main_list"].setIndex(0)
                    self["category_actions"].setEnabled(False)
                    self["channel_actions"].setEnabled(True)
                    self["key_yellow"].setText(_("Sort: A-Z"))

                    glob.nextlist.append({"next_url": next_url, "index": 0, "level": self.level, "sort": self["key_yellow"].getText(), "filter": ""})

                    self.createSetup()
                else:
                    self.createSetup()

            elif self.level == 3:
                if self.list3:
                    next_url = self["main_list"].getCurrent()[3]
                    self.storedseason = self["main_list"].getCurrent()[12]

                    self.level += 1
                    self["main_list"].setIndex(0)
                    self["category_actions"].setEnabled(False)
                    self["channel_actions"].setEnabled(True)
                    self["key_yellow"].setText(_("Sort: A-Z"))
                    glob.nextlist.append({"next_url": next_url, "index": 0, "level": self.level, "sort": self["key_yellow"].getText(), "filter": ""})
                    self.createSetup()
                else:
                    self.createSetup()

            elif self.level == 4:
                if self.list4:
                    self.storedepisode = self["main_list"].getCurrent()[18]
                    streamtype = glob.active_playlist["player_info"]["vodtype"]
                    next_url = self["main_list"].getCurrent()[3]
                    stream_id = self["main_list"].getCurrent()[4]

                    self.reference = eServiceReference(int(streamtype), 0, next_url)
                    self.reference.setName(glob.currentchannellist[glob.currentchannellistindex][0])
                    self.session.openWithCallback(self.setIndex, vodplayer.XStreamity_VodPlayer, str(next_url), str(streamtype), stream_id)

                else:
                    self.createSetup()

    def setIndex(self, data=None):
        if debugs:
            print("*** setIndex ***")

        if self["main_list"].getCurrent():
            self["main_list"].setIndex(glob.currentchannellistindex)
            self.createSetup()

    def back(self, data=None):
        if debugs:
            print("*** back ***")

        if self.level != 1:
            try:
                self.timerSeries.stop()
            except:
                pass

            if self.cover_download_deferred:
                self.cover_download_deferred.cancel()

            if self.logo_download_deferred:
                self.logo_download_deferred.cancel()

            if self.backdrop_download_deferred:
                self.backdrop_download_deferred.cancel()

        try:
            del glob.nextlist[-1]
        except Exception as e:
            print(e)
            self.close()

        if self.level == 3:
            self.series_info = ""

        if not glob.nextlist:
            self.close()
        else:
            self["x_title"].setText("")
            self["x_description"].setText("")
            self["key_epg"].setText("")
            self.level -= 1
            if self.level == 1:
                self["category_actions"].setEnabled(True)
                self["channel_actions"].setEnabled(False)
            self.buildLists()

            self.loadDefaultCover()
            self.loadDefaultLogo()
            self.loadDefaultBackdrop()

    def showHiddenList(self):
        if debugs:
            print("*** showHiddenList ***")

        if self["key_menu"].getText() and self["main_list"].getCurrent():
            from . import hidden

            if self["main_list"].getCurrent():
                if self.level == 1:
                    self.session.openWithCallback(self.createSetup, hidden.XStreamity_HiddenCategories, "series", self.prelist + self.list1, self.level)
                elif self.level == 2 and self.chosen_category != "favourites":
                    self.session.openWithCallback(self.createSetup, hidden.XStreamity_HiddenCategories, "series", self.list2, self.level)
                elif self.level == 3 and self.chosen_category != "favourites":
                    self.session.openWithCallback(self.createSetup, hidden.XStreamity_HiddenCategories, "series", self.list3, self.level)
                elif self.level == 4 and self.chosen_category != "favourites":
                    self.session.openWithCallback(self.createSetup, hidden.XStreamity_HiddenCategories, "series", self.list4, self.level)

    def clearWatched(self):
        if debugs:
            print("*** clearWatched ***")

        if self.level == 4:
            current_id = str(self["main_list"].getCurrent()[4])
            watched_list = glob.active_playlist["player_info"].get("serieswatched", [])
            if current_id in watched_list:
                watched_list.remove(current_id)

        with open(playlists_json, "r") as f:
            try:
                self.playlists_all = json.load(f)
            except:
                os.remove(playlists_json)
                return

            for i, playlist in enumerate(self.playlists_all):
                playlist_info = playlist.get("playlist_info", {})
                current_playlist_info = glob.active_playlist.get("playlist_info", {})
                if (playlist_info.get("domain") == current_playlist_info.get("domain") and
                        playlist_info.get("username") == current_playlist_info.get("username") and
                        playlist_info.get("password") == current_playlist_info.get("password")):
                    self.playlists_all[i] = glob.active_playlist
                    break

        with open(playlists_json, "w") as f:
            json.dump(self.playlists_all, f, indent=4)

        self.buildLists()

    def favourite(self):
        if debugs:
            print("*** favourite ***")
            print("*** self.level ***", self.level)

        if not self["main_list"].getCurrent():
            return

        if self.chosen_category == "favourites" and not self.level == 2:
            return

        current_index = self["main_list"].getIndex()
        favExists = False
        favStream_id = None

        if self.level == 2:
            series_id = str(self["main_list"].getCurrent()[4])
            current_index = self["main_list"].getIndex()

        elif self.level == 3:
            current_index = self["main_list"].getCurrent()[17]
            series_id = str(self["main_list"].getCurrent()[18])

        elif self.level == 4:
            current_index = self["main_list"].getCurrent()[19]
            series_id = str(self["main_list"].getCurrent()[20])

        self.list2[current_index][16] = not self.list2[current_index][16]

        for fav in glob.active_playlist["player_info"]["seriesfavourites"]:
            if str(series_id) == str(fav["series_id"]):
                favExists = True
                favStream_id = str(fav["series_id"])
                break

        # remove for glob favourites

        if favExists:
            if self.level == 2:
                glob.active_playlist["player_info"]["seriesfavourites"] = [x for x in glob.active_playlist["player_info"]["seriesfavourites"] if str(x["series_id"]) != str(favStream_id)]
        else:
            newfavourite = {
                "name": self.list2[current_index][1],
                "series_id": self.list2[current_index][2],
                "cover": self.list2[current_index][3],
                "plot": self.list2[current_index][4],
                "cast": self.list2[current_index][5],
                "director": self.list2[current_index][6],
                "genre": self.list2[current_index][7],
                "releaseDate": self.list2[current_index][8],
                "rating": self.list2[current_index][9],
                "last_modified": self.list2[current_index][10],
                "tmdb": self.list2[current_index][12],
                "year": self.list2[current_index][14],
                "backdrop": self.list2[current_index][15]
            }

            glob.active_playlist["player_info"]["seriesfavourites"].insert(0, newfavourite)

        with open(playlists_json, "r") as f:
            try:
                self.playlists_all = json.load(f)
            except:
                os.remove(playlists_json)
                self.playlists_all = []

        if self.playlists_all:
            for playlists in self.playlists_all:
                if (playlists["playlist_info"]["domain"] == glob.active_playlist["playlist_info"]["domain"]
                        and playlists["playlist_info"]["username"] == glob.active_playlist["playlist_info"]["username"]
                        and playlists["playlist_info"]["password"] == glob.active_playlist["playlist_info"]["password"]):
                    playlists.update(glob.active_playlist)
                    break

        with open(playlists_json, "w") as f:
            json.dump(self.playlists_all, f, indent=4)

        if self.level == 2:
            self.createSetup()
        else:
            if not favExists:
                self.session.open(MessageBox, _("Series group added to favourites."), type=MessageBox.TYPE_INFO, timeout=2)
            else:
                self.session.open(MessageBox, _("Series group removed from favourites."), type=MessageBox.TYPE_INFO, timeout=2)

    def hideVod(self):
        if debugs:
            print("*** hideVod ***")

        self["vod_cover"].hide()
        self["vod_logo"].hide()
        self["vod_backdrop"].hide()
        self["main_title"].setText("")
        self["x_title"].setText("")
        self["x_description"].setText("")
        self["tagline"].setText("")
        self["facts"].setText("")
        self["vod_director_label"].setText("")
        self["vod_country_label"].setText("")
        self["vod_cast_label"].setText("")
        self["vod_director"].setText("")
        self["vod_country"].setText("")
        self["vod_cast"].setText("")
        self["rating_text"].setText("")
        self["rating_percent"].setText("")
        self["overview"].setText("")

    def clearVod(self):
        if debugs:
            print("*** clearVod ***")
        self["main_title"].setText("")
        self["x_title"].setText("")
        self["x_description"].setText("")
        self["tagline"].setText("")
        self["facts"].setText("")
        self["vod_director"].setText("")
        self["vod_country"].setText("")
        self["vod_cast"].setText("")
        self["rating_text"].setText("")
        self["rating_percent"].setText("")

    def showVod(self):
        if debugs:
            print("*** showVod ***")
        if self["main_list"].getCurrent():
            self["vod_cover"].show()
            self["vod_logo"].show()
            self["vod_backdrop"].show()

    def downloadVideo(self):
        if debugs:
            print("*** downloadVideo ***")

        if self.level != 4:
            return

        if self["main_list"].getCurrent():
            title = self["main_list"].getCurrent()[0]
            stream_url = self["main_list"].getCurrent()[3]
            description = self["main_list"].getCurrent()[6]
            duration = self["main_list"].getCurrent()[12]

            try:
                h, m, s = map(int, duration.split(":"))
                duration = h * 60 + m + s // 60
            except:
                duration = 0

            timestamp = ""
            channel = _("Series")

            downloads_all = []
            if os.path.isfile(downloads_json):
                with open(downloads_json, "r") as f:
                    try:
                        downloads_all = json.load(f)
                    except:
                        pass

            exists = False
            for video in downloads_all:
                url = video[2]
                if stream_url == url:
                    exists = True

            if exists is False:
                downloads_all.append([_("Series"), title, stream_url, "Not Started", 0, 0, description, duration, channel, timestamp])

                with open(downloads_json, "w") as f:
                    json.dump(downloads_all, f, indent=4)

                self.session.openWithCallback(self.opendownloader, MessageBox, _(title) + "\n\n" + _("Added to download manager") + "\n\n" + _("Note recording acts as an open connection.") + "\n" + _("Do not record and play streams at the same time.") + "\n\n" + _("Open download manager?"))

            else:
                self.session.open(MessageBox, _(title) + "\n\n" + _("Already added to download manager"), MessageBox.TYPE_ERROR, timeout=5)

    def opendownloader(self, answer=None):
        if debugs:
            print("*** opendownloader ***")

        if not answer:
            return
        else:
            from . import downloadmanager
            self.session.openWithCallback(self.createSetup, downloadmanager.XStreamity_DownloadManager)

    def check(self, token):
        result = base64.b64decode(token)
        result = zlib.decompress(base64.b64decode(result))
        result = base64.b64decode(result).decode()
        return result

    # code for natural sorting of numbers in string
    def atoi(self, text):
        return int(text) if text.isdigit() else text

    def natural_keys(self, text):
        return [self.atoi(c) for c in re.split(r"(\d+)", text[1])]

    def buildFacts(self, certification, release_date, genre, duration, stream_format):
        if debugs:
            print("*** buildFacts ***")

        facts = []

        if certification:
            facts.append(certification)
        if release_date:
            facts.append(release_date)
        if genre:
            facts.append(genre)
        if duration:
            facts.append(duration)
        if stream_format:
            facts.append(str(stream_format).upper())

        return " • ".join(facts)


def buildCategoryList(index, title, category_id, hidden):
    png = LoadPixmap(os.path.join(common_path, "more.png"))
    return (title, png, index, category_id, hidden)

# 0 index, 1 name, 2 series_id, 3 cover, 4 plot, 5 cast, 6 director, 7 genre, 8 releaseDate, 9 rating, 10 last_modified, 11 next_url, 12 tmdb, 13 hidden, 14 year, 15 backdrop
# 0 index, 1 name, 2 series_id, 3 cover, 4 overview, 5 cast, 6 director, 7 genre, 8 airdate, 9 rating, 10 last_modified, 11 next_url, 12 tmdb, 13 hidden, 14 season_number, 15 backdrop
# 0 index, 1 title, 2 stream_id, 3 cover, 4 plot, 5 cast, 6 director, 7 genre, 8 releasedate, 9 rating, 10 last_modified, 11 next_url, 12 tmdb_id, 13 hidden, 14 duration, 15 container_extension, 16 shorttitle, 17 episode_num


def buildSeriesTitlesList(index, title, series_id, cover, plot, cast, director, genre, releaseDate, rating, lastmodified, next_url, tmdb, hidden, year, backdrop_path, favourite):
    png = LoadPixmap(os.path.join(common_path, "more.png"))
    if favourite:
        png = LoadPixmap(os.path.join(common_path, "favourite.png"))
    return (title, png, index, next_url, series_id, cover, plot, cast, director, genre, releaseDate, rating, lastmodified, year, tmdb, backdrop_path, hidden, favourite)


def buildSeriesSeasonsList(index, title, series_id, cover, plot, cast, director, genre, airDate, rating, lastmodified, next_url, tmdb, hidden, season_number, backdrop_path, parent_index, parent_id):
    png = LoadPixmap(os.path.join(common_path, "more.png"))
    try:
        title = _("Season ") + str(int(title))
    except:
        pass

    return (title, png, index, next_url, series_id, cover, plot, cast, director, genre, airDate, rating, season_number, lastmodified, hidden, tmdb, backdrop_path, parent_index, parent_id)


def buildSeriesEpisodesList(index, title, series_id, cover, plot, cast, director, genre, releaseDate, rating, lastmodified, next_url, tmdb_id, hidden, duration, container_extension, shorttitle, episode_number, parent_index, parent_id):
    png = LoadPixmap(os.path.join(common_path, "play.png"))
    for channel in glob.active_playlist["player_info"]["serieswatched"]:
        if int(series_id) == int(channel):
            png = LoadPixmap(os.path.join(common_path, "watched.png"))
    return (title, png, index, next_url, series_id, cover, plot, cast, director, genre, releaseDate, rating, duration, container_extension, tmdb_id, shorttitle, lastmodified, hidden, episode_number, parent_index, parent_id)
