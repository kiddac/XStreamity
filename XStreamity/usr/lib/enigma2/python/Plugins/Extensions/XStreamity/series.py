#!/usr/bin/python
# -*- coding: utf-8 -*-

import base64
import codecs
from datetime import datetime, timedelta

import os
import re

import time
import json
import requests
import math
import zlib

try:
    from http.client import HTTPConnection
    HTTPConnection.debuglevel = 0
except ImportError:
    from httplib import HTTPConnection
    HTTPConnection.debuglevel = 0

try:
    from urlparse import urlparse
    from urllib import quote
except ImportError:
    from urllib.parse import urlparse, quote

from itertools import cycle, islice
from requests.adapters import HTTPAdapter, Retry
from twisted.web.client import downloadPage

from Components.ActionMap import ActionMap
from Components.Pixmap import Pixmap
from Components.Sources.List import List
from Screens.MessageBox import MessageBox
from Screens.Screen import Screen
from Screens.VirtualKeyBoard import VirtualKeyBoard
from Tools.LoadPixmap import LoadPixmap
from collections import OrderedDict

from enigma import eTimer, eServiceReference, ePicLoad

from . import _
# from . import streamplayer
from . import vodplayer
from . import xstreamity_globals as glob

from .plugin import skin_directory, screenwidth, cfg, common_path, dir_tmp, playlists_json, downloads_json, pythonVer
from .xStaticText import StaticText

# https twisted client hack #
try:
    from twisted.internet import ssl
    from twisted.internet._sslverify import ClientTLSOptions
    sslverify = True
except ImportError:
    sslverify = False

if sslverify:
    class SNIFactory(ssl.ClientContextFactory):
        def __init__(self, hostname=None):
            self.hostname = hostname

        def getContext(self):
            ctx = self._contextFactory(self.method)
            if self.hostname:
                ClientTLSOptions(self.hostname, ctx)
            return ctx

hdr = {'User-Agent': str(cfg.useragent.value)}


class XStreamity_Categories(Screen):
    ALLOW_SUSPEND = True

    def __init__(self, session):
        # print("*** init ***")
        Screen.__init__(self, session)
        self.session = session
        glob.categoryname = "series"

        self.skin_path = os.path.join(skin_directory, cfg.skin.value)
        skin = os.path.join(self.skin_path, "vod_categories.xml")
        if os.path.exists("/var/lib/dpkg/status"):
            skin = os.path.join(self.skin_path, "DreamOS/vod_categories.xml")

        with codecs.open(skin, "r", encoding="utf-8") as f:
            self.skin = f.read()

        self.setup_title = _("Series Categories")
        self.main_title = _("Series")
        self["main_title"] = StaticText(self.main_title)

        self.main_list = []  # displayed list
        self["main_list"] = List(self.main_list, enableWrapAround=True)

        self["x_title"] = StaticText()
        self["x_description"] = StaticText()

        # skin vod variables
        self["vod_background"] = Pixmap()
        self["vod_background"].hide()
        self["vod_cover"] = Pixmap()
        self["vod_cover"].hide()
        self["vod_video_type_label"] = StaticText()
        self["vod_duration_label"] = StaticText()
        self["vod_genre_label"] = StaticText()
        self["vod_rating_label"] = StaticText()
        self["vod_country_label"] = StaticText()
        self["vod_release_date_label"] = StaticText()
        self["vod_director_label"] = StaticText()
        self["vod_cast_label"] = StaticText()
        self["vod_video_type"] = StaticText()
        self["vod_duration"] = StaticText()
        self["vod_genre"] = StaticText()
        self["vod_rating"] = StaticText()
        self["vod_country"] = StaticText()
        self["vod_release_date"] = StaticText()
        self["vod_director"] = StaticText()
        self["vod_cast"] = StaticText()

        # pagination variables
        self["page"] = StaticText("")
        self["listposition"] = StaticText("")
        self.itemsperpage = 10

        self.searchString = ""
        self.filterresult = ""

        self.chosen_category = ""

        self.pin = False
        self.tmdbresults = ""

        self.storedtitle = ""
        self.storedseason = ""
        self.storedepisode = ""
        self.storedyear = ""
        self.storedcover = ""
        self.storedtmdb = ""

        # level 2 data
        self.stored2_name = ""
        self.stored2_title = ""
        self.stored2_year = ""
        self.stored2_series_id = ""
        self.stored2_cover = ""
        self.stored2_plot = ""
        self.stored2_cast = ""
        self.stored2_director = ""
        self.stored2_genre = ""
        self.stored2_date = ""
        self.stored2_releaseDate = ""
        self.stored2_last_modified = ""
        self.stored2_rating = ""
        self.stored2_tmdb = ""

        self.sortindex = 0
        self.sortText = _("Sort: A-Z")

        self.level = 1

        self.selectedlist = self["main_list"]

        self.host = glob.active_playlist["playlist_info"]["host"]
        self.username = glob.active_playlist["playlist_info"]["username"]
        self.password = glob.active_playlist["playlist_info"]["password"]
        self.output = glob.active_playlist["playlist_info"]["output"]
        self.name = glob.active_playlist["playlist_info"]["name"]

        self.player_api = glob.active_playlist["playlist_info"]["player_api"]

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
        }, -1)

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
            "1": self.clearWatched
        }, -1)

        self["channel_actions"].setEnabled(False)

        glob.nextlist = []
        glob.nextlist.append({"next_url": next_url, "index": 0, "level": self.level, "sort": self.sortText, "filter": ""})

        self.PicLoad = ePicLoad()

        try:
            self.PicLoad.PictureData.get().append(self.DecodePicture)
        except:
            self.PicLoad_conn = self.PicLoad.PictureData.connect(self.DecodePicture)

        self.onFirstExecBegin.append(self.createSetup)
        self.onLayoutFinish.append(self.__layoutFinished)

    def __layoutFinished(self):
        self.setTitle(self.setup_title)

    def createSetup(self, data=None):
        # print("*** createSetup ***")
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

        self.buildLists()

    def buildLists(self):
        # print("*** buildLists ***")
        if self.level == 1:
            self.buildCategories()

        elif self.level == 2:
            self.buildSeries()

        elif self.level == 3:
            self.buildSeasons()

        elif self.level == 4:
            self.buildEpisodes()

        if (self.level == 1 and self.list1) or (self.level == 2 and self.list2) or (self.level == 3 and self.list3) or (self.level == 4 and self.list4):
            self.resetButtons()
            self.selectionChanged()

        else:
            self.back()

    def getCategories(self):
        # print("*** getCategories **")
        index = 0
        self.list1 = []
        self.prelist = []

        # no need to download. Already downloaded and saved in playlist menu
        currentPlaylist = glob.active_playlist
        currentCategoryList = currentPlaylist.get("data", {}).get("series_categories", [])
        currentHidden = set(currentPlaylist.get("player_info", {}).get("serieshidden", []))

        hidden = "0" in currentHidden
        i = 0
        self.prelist.extend([
            [i, _("ALL"), "0", hidden]
        ])

        for index, item in enumerate(currentCategoryList, start=len(self.prelist)):
            category_name = item.get("category_name", "No category")
            category_id = item.get("category_id", "999999")
            hidden = category_id in currentHidden
            self.list1.append([index, str(category_name), str(category_id), hidden])

        glob.originalChannelList1 = self.list1[:]

    def getSeries(self):
        # print("*** getSeries ***")
        # print("*** url ***", glob.nextlist[-1]["next_url"])
        response = ""
        response = self.downloadApiData(glob.nextlist[-1]["next_url"])
        index = 0
        self.list2 = []

        self.storedyear = ""
        self.storedtitle = ""
        self.storedtmdb = ""

        if response:

            for index, channel in enumerate(response):
                name = str(channel.get("name", ""))

                if not name or name == "None":
                    continue

                if name and '\" ' in name:
                    parts = name.split('\" ', 1)
                    if len(parts) > 1:
                        name = parts[0]

                # restyle bouquet markers
                if "stream_type" in channel and channel["stream_type"] and channel["stream_type"] != "movie":
                    pattern = re.compile(r"[^\w\s()\[\]]", re.U)
                    name = re.sub(r"_", "", re.sub(pattern, "", name))
                    name = "** " + str(name) + " **"

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
                            cover = cover.replace(dimensions, "w300")
                        else:
                            cover = cover.replace(dimensions, "w400")
                else:
                    cover = ""

                last_modified = str(channel.get("last_modified", ""))

                category_id = str(channel.get("category_id", ""))
                if self.chosen_category == "all" and str(category_id) in glob.active_playlist["player_info"]["serieshidden"]:
                    continue

                rating = str(channel.get("rating", ""))

                year = str(channel.get("year", ""))

                plot = str(channel.get("plot", ""))

                cast = str(channel.get("cast", ""))

                director = str(channel.get("director", ""))

                genre = str(channel.get("genre", ""))

                tmdb = channel.get("tmdb", "")

                releaseDate = str(channel.get("releaseDate")) or str(channel.get("release_date")) or str(channel.get("releasedate")) or ""

                next_url = "{}&action=get_series_info&series_id={}".format(str(self.player_api), str(series_id))
                self.list2.append([index, str(name), str(series_id), str(cover), str(plot), str(cast), str(director), str(genre), str(releaseDate), str(rating), str(last_modified), str(tmdb), str(next_url), str(year), hidden])

            glob.originalChannelList2 = self.list2[:]

        else:
            self.session.open(MessageBox, _("No series found in this category."), type=MessageBox.TYPE_ERROR, timeout=5)

    def getSeasons(self):
        # print("**** getSeasons ****")
        # print("*** url ***", glob.nextlist[-1]["next_url"])

        response = self.downloadApiData(glob.nextlist[-1]["next_url"])
        index = 0
        self.list3 = []

        if response:
            currentChannelList = response
            infodict = response.get("info", {})
            if infodict:
                tmdb = infodict.get("tmdb", self.tmdb2)
                name = infodict.get("name", self.title2)
                cover = infodict.get("cover", "")
                overview = infodict.get("plot", self.plot2)
                cast = infodict.get("cast", self.cast2)
                director = infodict.get("director", self.director2)
                genre = infodict.get("genre", self.genre2)
                airdate = infodict.get("releaseDate", self.releaseDate2) or currentChannelList.get("release_date", self.releaseDate2)
                rating = infodict.get("rating", self.rating2)
                last_modified = infodict.get("last_modified", "")

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
                    for season in seasonlist:
                        name = _("Season ") + str(season)

                        if self.isdict:
                            season_number = episodes[str(season)][0]["season"]
                        else:
                            season_number = episodes[season][0]["season"]

                        series_id = 0
                        hidden = False

                        if "seasons" in currentChannelList and currentChannelList["seasons"]:
                            for item in currentChannelList["seasons"]:
                                if "season_number" in item and item["season_number"] == season_number:

                                    if "airdate" in item and item["airdate"]:
                                        airdate = item["airdate"]
                                    elif "air_date" in item and item["air_date"]:
                                        airdate = item["air_date"]

                                    if "name" in item and item["name"]:
                                        name = item["name"]

                                    if "overview" in item and item["overview"] and len(item["overview"]) > 50 and "http" not in item["overview"]:
                                        overview = item["overview"]

                                    if "cover_tmdb" in item and item["cover_tmdb"]:
                                        if item["cover_tmdb"].startswith("http"):
                                            cover = item["cover_tmdb"]

                                    elif "cover_big" in item and item["cover_big"]:
                                        if item["cover_big"].startswith("http"):
                                            cover = item["cover_big"]

                                    elif "cover" in item and item["cover"]:
                                        if item["cover"].startswith("http"):
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
                                cover = ""

                            if cover.startswith("https://image.tmdb.org/t/p/") or cover.startswith("http://image.tmdb.org/t/p/"):
                                dimensions = cover.partition("/p/")[2].partition("/")[0]
                                if screenwidth.width() <= 1280:
                                    cover = cover.replace(dimensions, "w300")
                                else:
                                    cover = cover.replace(dimensions, "w400")
                        else:
                            cover = ""

                        next_url = self.seasons_url

                        self.list3.append([index, str(name), str(series_id), str(cover), str(overview), str(cast), str(director), str(genre), str(airdate), str(rating), season_number, str(next_url), str(last_modified), hidden, tmdb])

                self.list3.sort(key=self.natural_keys)

            if cover:
                self.storedcover = cover

            glob.originalChannelList3 = self.list3[:]

    def getEpisodes(self):
        # print("**** getEpisodes ****")
        # print("*** url ***", glob.nextlist[-1]["next_url"])
        response = self.downloadApiData(glob.nextlist[-1]["next_url"])
        index = 0
        self.list4 = []
        currentChannelList = response

        shorttitle = self.title2
        cover = self.storedcover
        plot = ""
        cast = self["vod_cast"].getText()
        director = self["vod_director"].getText()
        genre = self["vod_genre"].getText()
        releasedate = self["vod_release_date"].getText()
        rating = self["vod_rating"].getText()
        tmdb_id = self["main_list"].getCurrent()[15]
        last_modified = ""

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
                    tmdb_id = currentChannelList["info"]["plot"]

            if "episodes" in currentChannelList:
                if currentChannelList["episodes"]:

                    season_number = str(self.storedseason)
                    if self.isdict is False:
                        season_number = int(self.storedseason)

                    for item in currentChannelList["episodes"][season_number]:
                        title = ""
                        stream_id = ""
                        container_extension = "mp4"
                        tmdb_id = ""
                        duration = ""
                        hidden = False

                        if "id" in item:
                            stream_id = item["id"]
                        else:
                            # Skip this item if "id" key is missing
                            continue

                        if "title" in item:
                            title = item["title"].replace(str(shorttitle) + " - ", "")

                        if "container_extension" in item:
                            container_extension = item["container_extension"]

                        duration = item.get("info", {}).get("duration", "")
                        episode_num = item.get("episode_num", 1)

                        if "info" in item:

                            if "tmdb_id" in item["info"]:
                                tmdb_id = item["info"]["tmdb_id"]

                            if "releaseDate" in item["info"]:
                                releasedate = item["info"]["releaseDate"]

                            elif "release_date" in item["info"]:
                                releasedate = item["info"]["release_date"]

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

                        self.list4.append([index, str(title), str(stream_id), str(cover), str(plot), str(cast), str(director), str(genre), str(releasedate), str(rating), str(duration), str(container_extension), str(tmdb_id), str(next_url), str(shorttitle), str(last_modified), hidden, episode_num])
                        index += 1

            glob.originalChannelList4 = self.list4[:]

    def downloadApiData(self, url):
        try:
            retries = Retry(total=3, backoff_factor=1)
            adapter = HTTPAdapter(max_retries=retries)
            http = requests.Session()
            http.mount("http://", adapter)
            http.mount("https://", adapter)

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
        # print("*** buildCategories ***")
        self.hideVod()

        if self["key_blue"].getText() != _("Reset Search"):
            self.pre_list = [buildCategoryList(x[0], x[1], x[2], x[3]) for x in self.prelist if not x[3]]
        else:
            self.pre_list = []

        if self.list1:
            self.main_list = [buildCategoryList(x[0], x[1], x[2], x[3]) for x in self.list1 if not x[3]]

            self["main_list"].setList(self.pre_list + self.main_list)

            if self["main_list"].getCurrent() and glob.nextlist[-1]["index"] != 0:
                self["main_list"].setIndex(glob.nextlist[-1]["index"])

    def buildSeries(self):
        # print("*** buildSeries ***")
        if self.list2:
            self.main_list = [buildSeriesTitlesList(x[0], x[1], x[2], x[3], x[4], x[5], x[6], x[7], x[8], x[9], x[10], x[11], x[12], x[13], x[14]) for x in self.list2 if not x[14]]
            self["main_list"].setList(self.main_list)

            self.showVod()

            if self["main_list"].getCurrent() and glob.nextlist[-1]["index"] != 0:
                self["main_list"].setIndex(glob.nextlist[-1]["index"])

    def buildSeasons(self):
        # print("*** buildSeasons ***")
        if self.list3:
            self.main_list = [buildSeriesSeasonsList(x[0], x[1], x[2], x[3], x[4], x[5], x[6], x[7], x[8], x[9], x[10], x[11], x[12], x[13], x[14]) for x in self.list3 if not x[13]]
            self["main_list"].setList(self.main_list)

            if self["main_list"].getCurrent() and glob.nextlist[-1]["index"] != 0:
                self["main_list"].setIndex(glob.nextlist[-1]["index"])

    def buildEpisodes(self):
        # print("*** buildEpisodes ***")
        if self.list4:
            self.main_list = [buildSeriesEpisodesList(x[0], x[1], x[2], x[3], x[4], x[5], x[6], x[7], x[8], x[9], x[10], x[11], x[12], x[13], x[14], x[15], x[16], x[17]) for x in self.list4 if not x[16]]
            self["main_list"].setList(self.main_list)

        if self["main_list"].getCurrent() and glob.nextlist[-1]["index"] != 0:
            self["main_list"].setIndex(glob.nextlist[-1]["index"])

    def displaySeriesData(self):
        # print("*** displaySeriesData ***")
        if self["main_list"].getCurrent():
            if cfg.TMDB.value is True:
                if self.level != 1:
                    self.tmdbValid = True
                    self.getTMDB()

            else:
                self.tmdbresults = ""
                self.displayTMDB()

    def selectionChanged(self):
        # print("*** selectionChanged ***")

        current_item = self["main_list"].getCurrent()
        if current_item:
            channel_title = current_item[0]
            current_index = self["main_list"].getIndex()

            position = current_index + 1
            position_all = len(self.pre_list) + len(self.main_list) if self.level == 1 else len(self.main_list)
            page = (position - 1) // self.itemsperpage + 1
            page_all = int(math.ceil(position_all // self.itemsperpage) + 1)

            self["page"].setText(_("Page: ") + "{}/{}".format(page, page_all))
            self["listposition"].setText("{}/{}".format(position, position_all))
            self["main_title"].setText("{}: {}".format(self.main_title, channel_title))

            self.clearVod()

            if self.level != 4:
                self.loadDefaultImage()

            if self.level != 1:
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

    def getTMDB(self):
        # print("**** getTMDB ***")
        title = ""
        searchtitle = ""
        self.searchtitle = ""
        self.tmdb = ""
        year = ""
        tmdb = ""

        try:
            os.remove(os.path.join(dir_tmp, "search.txt"))
        except:
            pass

        current_item = self["main_list"].getCurrent()
        if current_item:
            if self.level == 2:
                title = current_item[0]
                year = current_item[13]
                tmdb = current_item[14]
                cover = current_item[5]

                if not year:
                    # Get year from release date
                    try:
                        year = current_item[10][:4]
                    except IndexError:
                        year = ""

                if year:
                    self.storedyear = year
                if title:
                    self.storedtitle = title
                if cover:
                    self.storedcover = cover

            else:
                title = self.storedtitle
                year = self.storedyear

                if self.level == 3:
                    tmdb = current_item[15]

                if self.level == 4:
                    tmdb = current_item[14]

            if tmdb and self.tmdbValid:
                self.getTMDBDetails(tmdb)
                return

            searchtitle = title.lower()

            # if title ends in "the", move "the" to the beginning
            if searchtitle.endswith("the"):
                searchtitle = "the " + searchtitle[:-4]

            # remove xx: at start
            searchtitle = re.sub(r'^\w{2}:', '', searchtitle)

            # remove xx|xx at start
            searchtitle = re.sub(r'^\w{2}\|\w{2}\s', '', searchtitle)

            # remove xx - at start
            searchtitle = re.sub(r'^.{2}\+? ?- ?', '', searchtitle)

            # remove all leading contend between and including ||
            searchtitle = re.sub(r'^\|\|.*?\|\|', '', searchtitle)
            searchtitle = re.sub(r'^\|.*?\|', '', searchtitle)

            # remove all leading contend between and including ()
            searchtitle = re.sub(r'\(\(.*\)\)|\(.*\)', '', searchtitle)

            # remove all leading contend between and including []
            searchtitle = re.sub(r'\[\[.*\]\]|\[.*\]', '', searchtitle)

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
            searchtitle = re.sub(r'[._\']', ' ', searchtitle)

            # Replace "-" with space and strip trailing spaces
            searchtitle = searchtitle.strip(' -')

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
        # print("*** failed ***")
        if data:
            print(data)
            self.tmdbValid = False
            self.getTMDB()

    def processTMDB(self, result=None):
        # print("*** processTMDB ***")
        resultid = ""
        search_file_path = os.path.join(dir_tmp, "search.txt")
        try:
            with codecs.open(search_file_path, "r", encoding="utf-8") as f:
                response = f.read()

            if response:
                self.searchresult = json.loads(response)
                if "results" not in self.searchresult or not self.searchresult["results"]:
                    self.tmdbValid = False
                    self.getTMDB()
                else:
                    resultid = self.searchresult["results"][0].get("id")

                    if not resultid:
                        self.tmdbresults = ""
                        self.displayTMDB()
                        return

                    self.getTMDBDetails(resultid)
        except Exception as e:
            print("Error processing TMDB response:", e)

    def getTMDBDetails(self, resultid=None):
        # print(" *** getTMDBDetails ***")
        detailsurl = ""

        try:
            os.remove(os.path.join(dir_tmp, "tmdb.txt"))
        except OSError:
            pass

        if cfg.TMDB.value is True:
            language = cfg.TMDBLanguage2.value

        languagestr = ""

        if language:
            languagestr = "&language=" + str(language)

        if self.level == 2:
            detailsurl = "http://api.themoviedb.org/3/tv/{}?api_key={}&append_to_response=credits{}".format(
                resultid, self.check(self.token), languagestr
            )

        elif self.level == 3:
            self.storedseason = self["main_list"].getCurrent()[12]
            detailsurl = "http://api.themoviedb.org/3/tv/{}/season/{}?api_key={}&append_to_response=credits{}".format(
                resultid, self.storedseason, self.check(self.token), languagestr
            )

        elif self.level == 4:
            self.storedepisode = self["main_list"].getCurrent()[18]
            detailsurl = "http://api.themoviedb.org/3/tv/{}/season/{}/episode/{}?api_key={}&append_to_response=credits{}".format(
                resultid, self.storedseason, self.storedepisode, self.check(self.token), languagestr
            )

        if pythonVer == 3:
            detailsurl = detailsurl.encode()

        filepath = os.path.join(dir_tmp, "tmdb.txt")
        try:
            downloadPage(detailsurl, filepath, timeout=10).addCallback(self.processTMDBDetails).addErrback(self.failed2)
        except Exception as e:
            print("download TMDB details error:", e)

    def failed2(self, data=None):
        # print("*** failed 2 ***")
        if data:
            print(data)
            if self.level == 2:
                self.tmdbValid = False
                self.getTMDB()

            else:
                self.tmdbresults = ""
                self.displayTMDB()
                return

    def processTMDBDetails(self, result=None):
        # print("*** processTMDBDetails ***")
        response = ""
        self.tmdbresults = {}
        self.tmdbdetails = []
        director = []

        try:
            with codecs.open(os.path.join(dir_tmp, "tmdb.txt"), "r", encoding="utf-8") as f:
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
                    self.tmdbresults["name"] = str(self.tmdbdetails.get("name", ""))

                    self.tmdbresults["description"] = str(self.tmdbdetails.get("overview", ""))
                    rating_str = self.tmdbdetails.get("vote_average", "")
                    self.tmdbresults["rating"] = str(rating_str)
                    if rating_str and rating_str != 0:
                        try:
                            rating = float(rating_str)
                            rounded_rating = round(rating, 1)
                            self.tmdbresults["rating"] = "{:.1f}".format(rounded_rating)
                        except ValueError:
                            self.tmdbresults["rating"] = str(rating_str)

                if self.level == 2:
                    self.tmdbresults["o_name"] = str(self.tmdbdetails.get("original_name", ""))

                    try:
                        if "episode_run_time" in self.tmdbdetails and self.tmdbdetails["episode_run_time"] and self.tmdbdetails["episode_run_time"] != 0:
                            self.tmdbresults["duration"] = str(timedelta(minutes=int(self.tmdbdetails["episode_run_time"][0])))

                        elif "runtime" in self.tmdbdetails and self.tmdbdetails["runtime"] and self.tmdbdetails["runtime"] != 0:
                            self.tmdbresults["duration"] = str(timedelta(minutes=int(self.tmdbdetails["runtime"])))
                    except Exception as e:
                        self.tmdbresults["duration"] = ""
                        print(e)

                    self.tmdbresults["releaseDate"] = str(self.tmdbdetails.get("first_air_date", ""))

                    genre = " / ".join(str(genreitem["name"]) for genreitem in self.tmdbdetails.get("genres", []))
                    self.tmdbresults["genre"] = genre

                if self.level != 4:
                    cast = ", ".join(actor["name"] for actor in self.tmdbdetails.get("credits", {}).get("cast", [])[:5])
                    self.tmdbresults["cast"] = cast

                    director = ", ".join(actor["name"] for actor in self.tmdbdetails.get("credits", {}).get("crew", []) if actor.get("job") == "Director") or ""
                    self.tmdbresults["director"] = director

                    poster_path = self.tmdbdetails.get("poster_path", "")
                    size = "w300" if screenwidth.width() <= 1280 else "w400"
                    self.tmdbresults["cover_big"] = "http://image.tmdb.org/t/p/{}/{}".format(size, poster_path) if poster_path else self.storedcover

                if self.level != 2:
                    self.tmdbresults["releaseDate"] = str(self.tmdbdetails.get("air_date", ""))

                if self.level == 4:
                    runtime = self.tmdbdetails.get("runtime", "")
                    if runtime and runtime != 0:
                        self.tmdbresults["duration"] = str(timedelta(minutes=runtime))
                    else:
                        self.tmdbresults["duration"] = ""

                self.displayTMDB()

    def displayTMDB(self):
        # print("*** displayTMDB ***")
        current = self["main_list"].getCurrent()

        if current and self.level != 1:

            if self.level == 4:
                self["vod_duration"].setText(current[12])
                self["vod_video_type"].setText(current[13])

            self["x_title"].setText(current[0])
            self["x_description"].setText(current[6])
            self["vod_genre"].setText(current[9])
            self["vod_rating"].setText(current[11])
            try:
                self["vod_release_date"].setText(datetime.strptime(current[10], "%Y-%m-%d").strftime("%d-%m-%Y"))
            except:
                self["vod_release_date"].setText("")
                pass
            self["vod_director"].setText(current[8])
            self["vod_cast"].setText(current[7])

            stream_url = current[3]
            if self.level == 4:
                try:
                    self["vod_video_type"].setText(stream_url.split(".")[-1])
                except Exception:
                    pass
            else:
                self["vod_video_type"].setText("")

            if self.tmdbresults:
                info = self.tmdbresults
                title = info.get("name") or info.get("o_name")
                self["x_title"].setText(str(title).strip())

                description = info.get("description") or info.get("plot")
                self["x_description"].setText(str(description).strip())

                self["vod_duration"].setText(str(info.get("duration", "")).strip())
                self["vod_genre"].setText(str(info.get("genre", "")).strip())
                self["vod_rating"].setText(str(info.get("rating", "")).strip())
                self["vod_country"].setText(str(info.get("country", "")).strip())

                release_date = ""
                for key in ["releaseDate", "release_date", "releasedate"]:
                    if key in info and info[key]:
                        try:
                            release_date = datetime.strptime(info[key], "%Y-%m-%d").strftime("%d-%m-%Y")
                            break
                        except Exception:
                            pass

                if release_date:
                    self["vod_release_date"].setText(release_date)

                self["vod_director"].setText(str(info.get("director", "")).strip())
                self["vod_cast"].setText(str(info.get("cast", info.get("actors", ""))).strip())

            if self.level != 4 and cfg.channelcovers.value:
                self.downloadImage()

    def resetButtons(self):
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

    def stopStream(self):
        # print("*** stopStream ***")
        if glob.currentPlayingServiceRefString != glob.newPlayingServiceRefString:
            if glob.newPlayingServiceRefString != "":
                if self.session.nav.getCurrentlyPlayingServiceReference():
                    self.session.nav.stopService()
                self.session.nav.playService(eServiceReference(glob.currentPlayingServiceRefString))
                glob.newPlayingServiceRefString = glob.currentPlayingServiceRefString

    def downloadImage(self):
        # print("*** downloadimage ***")

        if cfg.channelcovers.value is False:
            return

        if self["main_list"].getCurrent():
            try:
                os.remove(os.path.join(dir_tmp, "original.jpg"))
                os.remove(os.path.join(dir_tmp, "temp.jpg"))
            except:
                pass

            desc_image = ""
            try:
                desc_image = self["main_list"].getCurrent()[5]
            except:
                pass

            if self.tmdbresults:
                desc_image = str(self.tmdbresults.get("cover_big")).strip() or str(self.tmdbresults.get("movie_image")).strip() or ""

            if desc_image and desc_image != "n/A":
                temp = os.path.join(dir_tmp, "temp.jpg")

                try:
                    parsed = urlparse(desc_image)
                    domain = parsed.hostname
                    scheme = parsed.scheme

                    if pythonVer == 3:
                        desc_image = desc_image.encode()

                    if scheme == "https" and sslverify:
                        sniFactory = SNIFactory(domain)
                        downloadPage(desc_image, temp, sniFactory, timeout=5).addCallback(self.resizeImage).addErrback(self.loadDefaultImage)
                    else:
                        downloadPage(desc_image, temp, timeout=5).addCallback(self.resizeImage).addErrback(self.loadDefaultImage)
                except Exception as e:
                    print(e)
                    self.loadDefaultImage()
            else:
                self.loadDefaultImage()

    def loadDefaultImage(self, data=None):
        # print("*** loadDefaultImage ***")
        if self["vod_cover"].instance:
            self["vod_cover"].instance.setPixmapFromFile(os.path.join(skin_directory, "common/vod_cover.png"))

    def resizeImage(self, data=None):
        # print("*** resize image ***")
        # Check if the current item exists in the main_list
        if self["main_list"].getCurrent() and self["vod_cover"].instance:
            width, height = 267, 400

            if screenwidth.width() == 2560:
                width, height = 534, 800
            elif screenwidth.width() > 1280:
                width, height = 400, 600

            self.PicLoad.setPara([width, height, 1, 1, 0, 1, "FF000000"])

            preview = os.path.join(dir_tmp, "temp.jpg")

            if self.PicLoad.startDecode(preview):
                # Retry decoding immediately
                self.PicLoad = ePicLoad()
                try:
                    self.PicLoad.PictureData.get().append(self.DecodePicture)
                except:
                    self.PicLoad_conn = self.PicLoad.PictureData.connect(self.DecodePicture)
                self.PicLoad.setPara([width, height, 1, 1, 0, 1, "FF000000"])
                self.PicLoad.startDecode(preview)

    def DecodePicture(self, PicInfo=None):
        # print("*** DecodePicture ***")
        ptr = self.PicLoad.getData()
        if ptr is not None and self.level != 1:
            self["vod_cover"].instance.setPixmap(ptr)

    def goUp(self):
        instance = self.selectedlist.master.master.instance
        instance.moveSelection(instance.moveUp)
        self.selectionChanged()

    def goDown(self):
        instance = self.selectedlist.master.master.instance
        instance.moveSelection(instance.moveDown)
        self.selectionChanged()

    def pageUp(self):
        instance = self.selectedlist.master.master.instance
        instance.moveSelection(instance.pageUp)
        self.selectionChanged()

    def pageDown(self):
        instance = self.selectedlist.master.master.instance
        instance.moveSelection(instance.pageDown)
        self.selectionChanged()

    # button 0
    def reset(self):
        self.selectedlist.setIndex(0)
        self.selectionChanged()

    def sort(self):

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
            sortlist = [_("Sort: A-Z"), _("Sort: Z-A"), _("Sort: Added"), _("Sort: Original")]

        else:
            sortlist = [_("Sort: A-Z"), _("Sort: Z-A"), _("Sort: Added"), _("Sort: Year"), _("Sort: Original")]

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
            activelist.sort(key=lambda x: x[4], reverse=True)

        elif current_sort == _("Sort: Year"):
            activelist.sort(key=lambda x: x[9], reverse=True)

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
        # print("*** search ***")
        if not self["key_blue"].getText():
            return

        current_filter = self["key_blue"].getText()

        if current_filter == _("Reset Search"):
            self.resetSearch()

        else:
            self.session.openWithCallback(self.filterChannels, VirtualKeyBoard, title=_("Filter this category..."), text=self.searchString)

    def filterChannels(self, result=None):
        # print("*** filterChannels ***")

        activelist = []

        if result:
            self.filterresult = result
            glob.nextlist[-1]["filter"] = self.filterresult

            if self.level == 1:
                activelist = self.list1[:]

            elif self.level == 2:
                activelist = self.list2[:]

            elif self.level == 3:
                activelist = self.list3[:]

            elif self.level == 4:
                activelist = self.list4[:]

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
        # print("*** resetSearch ***")
        self["key_blue"].setText(_("Search"))
        self["key_yellow"].setText(self.sortText)

        if self.level == 1:
            activeoriginal = glob.originalChannelList1[:]
            self.list1 = activeoriginal

        elif self.level == 2:
            activeoriginal = glob.originalChannelList2[:]
            self.list2 = activeoriginal

        elif self.level == 3:
            activeoriginal = glob.originalChannelList3[:]
            self.list3 = activeoriginal

        elif self.level == 4:
            activeoriginal = glob.originalChannelList4[:]
            self.list4 = activeoriginal

        self.filterresult = ""
        glob.nextlist[-1]["filter"] = self.filterresult

        self.buildLists()

    def pinEntered(self, result=None):
        # print("*** pinEntered ***")
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
        # print("*** parentalcheck ***")
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
        # print("*** next ***")
        if self["main_list"].getCurrent():

            currentindex = self["main_list"].getIndex()
            glob.nextlist[-1]["index"] = currentindex
            glob.currentchannellist = self.main_list[:]
            glob.currentchannellistindex = currentindex

            if self.level == 1:
                if self.list1:
                    category_id = self["main_list"].getCurrent()[3]

                    next_url = "{0}&action=get_series&category_id={1}".format(self.player_api, category_id)
                    self.chosen_category = ""

                    if category_id == "0":
                        next_url = "{0}&action=get_series".format(self.player_api)
                        self.chosen_category = "all"

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
                    self.title2 = self["x_title"].getText()
                    self.plot2 = self["x_description"].getText()
                    self.cast2 = self["vod_cast"].getText()
                    self.director2 = self["vod_director"].getText()
                    self.genre2 = self["vod_genre"].getText()
                    self.releaseDate2 = self["vod_release_date"].getText()
                    self.rating2 = self["vod_rating"].getText()
                    self.tmdb2 = self["main_list"].getCurrent()[14]

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
        # print("*** set index ***")
        if self["main_list"].getCurrent():
            self["main_list"].setIndex(glob.currentchannellistindex)
            self.createSetup()

    def back(self, data=None):
        # print("*** back ***")
        del glob.nextlist[-1]

        if len(glob.nextlist) == 0:
            self.stopStream()
            self.close()
        else:
            self["x_title"].setText("")
            self["x_description"].setText("")

            if cfg.stopstream.value:
                self.stopStream()

            self.level -= 1

            self["category_actions"].setEnabled(True)
            self["channel_actions"].setEnabled(False)

            self.buildLists()

    def showHiddenList(self):
        if self["key_menu"].getText() and self["main_list"].getCurrent():
            from . import hidden

            if self["main_list"].getCurrent():
                if self.level == 1:
                    self.session.openWithCallback(self.createSetup, hidden.XStreamity_HiddenCategories, "series", self.prelist + self.list1, self.level)
                elif self.level == 2:
                    self.session.openWithCallback(self.createSetup, hidden.XStreamity_HiddenCategories, "series", self.list2, self.level)
                elif self.level == 3:
                    self.session.openWithCallback(self.createSetup, hidden.XStreamity_HiddenCategories, "series", self.list3, self.level)
                elif self.level == 4:
                    self.session.openWithCallback(self.createSetup, hidden.XStreamity_HiddenCategories, "series", self.list4, self.level)

    def clearWatched(self):
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
            json.dump(self.playlists_all, f)

        self.buildLists()

    def hideVod(self):
        # print("*** hideVod ***")
        self["vod_background"].hide()
        self["vod_cover"].hide()
        self["x_title"].setText("")
        self["x_description"].setText("")
        self["vod_video_type_label"].setText("")
        self["vod_duration_label"].setText("")
        self["vod_genre_label"].setText("")
        self["vod_rating_label"].setText("")
        self["vod_country_label"].setText("")
        self["vod_release_date_label"].setText("")
        self["vod_director_label"].setText("")
        self["vod_cast_label"].setText("")
        self["vod_video_type"].setText("")
        self["vod_duration"].setText("")
        self["vod_genre"].setText("")
        self["vod_rating"].setText("")
        self["vod_country"].setText("")
        self["vod_release_date"].setText("")
        self["vod_director"].setText("")
        self["vod_cast"].setText("")

    def clearVod(self):
        # print("*** clearVod ***")
        self["x_title"].setText("")
        self["x_description"].setText("")
        self["vod_video_type"].setText("")
        self["vod_duration"].setText("")
        self["vod_genre"].setText("")
        self["vod_rating"].setText("")
        self["vod_country"].setText("")
        self["vod_release_date"].setText("")
        self["vod_director"].setText("")
        self["vod_cast"].setText("")

    def showVod(self):
        # print("*** showVod ***")
        self["vod_cover"].show()
        self["vod_background"].show()
        self["vod_video_type_label"].setText(_("Video Type:"))
        self["vod_rating_label"].setText(_("Rating:"))
        self["vod_genre_label"].setText(_("Genre:"))
        self["vod_duration_label"].setText(_("Duration:"))
        self["vod_release_date_label"].setText(_("Release Date:"))
        self["vod_cast_label"].setText(_("Cast:"))
        self["vod_director_label"].setText(_("Director:"))
        self["vod_country_label"].setText(_("Country:"))

    def downloadVideo(self):
        # print("*** downloadVideo ***")
        if self.level != 4:
            return

        if self["main_list"].getCurrent():
            title = self["main_list"].getCurrent()[0]
            stream_url = self["main_list"].getCurrent()[3]

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
                downloads_all.append([_("Series"), title, stream_url, "Not Started", 0, 0])

                with open(downloads_json, "w") as f:
                    json.dump(downloads_all, f)

                self.session.openWithCallback(self.opendownloader, MessageBox, _(title) + "\n\n" + _("Added to download manager") + "\n\n" + _("Note recording acts as an open connection.") + "\n" + _("Do not record and play streams at the same time.") + "\n\n" + _("Open download manager?"))

            else:
                self.session.open(MessageBox, _(title) + "\n\n" + _("Already added to download manager"), MessageBox.TYPE_ERROR, timeout=5)

    def opendownloader(self, answer=None):
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


def buildCategoryList(index, title, category_id, hidden):
    png = LoadPixmap(os.path.join(common_path, "more.png"))
    return (title, png, index, category_id, hidden)


def buildSeriesTitlesList(index, title, series_id, cover, plot, cast, director, genre, releaseDate, rating, lastmodified, tmdb, next_url, year, hidden):
    png = LoadPixmap(os.path.join(common_path, "more.png"))
    return (title, png, index, next_url, series_id, cover, plot, cast, director, genre, releaseDate, rating, lastmodified, year, tmdb, hidden)


def buildSeriesSeasonsList(index, title, series_id, cover, plot, cast, director, genre, airDate, rating, season_number, next_url, lastmodified, hidden, tmdb):
    png = LoadPixmap(os.path.join(common_path, "more.png"))
    try:
        title = _("Season ") + str(int(title))
    except:
        pass

    return (title, png, index, next_url, series_id, cover, plot, cast, director, genre, airDate, rating, season_number, lastmodified, hidden, tmdb)


def buildSeriesEpisodesList(index, title, series_id, cover, plot, cast, director, genre, releaseDate, rating, duration, container_extension, tmdb_id, next_url, shorttitle, lastmodified, hidden, episode_number):
    png = LoadPixmap(os.path.join(common_path, "play.png"))
    for channel in glob.active_playlist["player_info"]["serieswatched"]:
        if int(series_id) == int(channel):
            png = LoadPixmap(os.path.join(common_path, "watched.png"))
    return (title, png, index, next_url, series_id, cover, plot, cast, director, genre, releaseDate, rating, duration, container_extension, tmdb_id, shorttitle, lastmodified, hidden, episode_number)
