#!/usr/bin/python
# -*- coding: utf-8 -*-

from . import _
from . import streamplayer
from . import xstreamity_globals as glob

from .plugin import skin_directory, screenwidth, hdr, cfg, common_path, dir_tmp, playlists_json, downloads_json, pythonVer
from .xStaticText import StaticText

from Components.ActionMap import ActionMap
from Components.Pixmap import Pixmap
from Components.Sources.List import List
from Screens.MessageBox import MessageBox
from Screens.Screen import Screen
from Screens.VirtualKeyBoard import VirtualKeyBoard
from Tools.LoadPixmap import LoadPixmap
from collections import OrderedDict
from datetime import datetime, timedelta
from enigma import eTimer, eServiceReference, ePicLoad
from requests.adapters import HTTPAdapter, Retry
from twisted.web.client import downloadPage
from itertools import cycle, islice

try:
    from urlparse import urlparse
    from urllib import quote
except:
    from urllib.parse import urlparse, quote

import base64
import codecs
import json
import math
import os
import re
import requests
import time
import zlib

try:
    from http.client import HTTPConnection
    HTTPConnection.debuglevel = 0
except:
    from httplib import HTTPConnection
    HTTPConnection.debuglevel = 0

# https twisted client hack #
try:
    from twisted.internet import ssl
    from twisted.internet._sslverify import ClientTLSOptions
    sslverify = True
except:
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


class XStreamity_Categories(Screen):
    ALLOW_SUSPEND = True

    def __init__(self, session):
        # print("*** init ***")
        Screen.__init__(self, session)
        self.session = session
        glob.categoryname = "series"

        self.skin_path = os.path.join(skin_directory, cfg.skin.getValue())
        skin = os.path.join(self.skin_path, "vod_categories.xml")
        if os.path.exists("/var/lib/dpkg/status"):
            skin = os.path.join(self.skin_path, "DreamOS/vod_categories.xml")

        with codecs.open(skin, "r", encoding="utf-8") as f:
            self.skin = f.read()

        self.setup_title = (_("Series Categories"))
        self.main_title = (_("Series"))
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
        self.page = 0
        self.pageall = 0
        self.position = 0
        self.positionall = 0
        self.itemsperpage = 10

        self.searchString = ""
        self.filterresult = ""

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
        self.sortText = (_("Sort: A-Z"))

        self.level = 1

        self.selectedlist = self["main_list"]

        self.host = glob.current_playlist["playlist_info"]["host"]
        self.username = glob.current_playlist["playlist_info"]["username"]
        self.password = glob.current_playlist["playlist_info"]["password"]
        self.output = glob.current_playlist["playlist_info"]["output"]
        self.name = glob.current_playlist["playlist_info"]["name"]

        self.player_api = glob.current_playlist["playlist_info"]["player_api"]

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
            "red": self.playStream,
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
        # print("*** url ***", glob.nextlist[-1]["next_url"])
        index = 0
        self.list1 = []
        self.prelist = []

        # no need to download. Already downloaded and saved in playlist menu
        currentCategoryList = glob.current_playlist["data"]["series_categories"]
        currentHidden = glob.current_playlist["player_info"]["serieshidden"]

        hidden = False

        if "0" in currentHidden:
            hidden = True

        self.prelist.append([index, _("ALL"), "0", hidden])
        index += 1

        for item in currentCategoryList:
            hidden = False
            if "category_name" in item:
                category_name = item["category_name"]
            else:
                category_name = "No category"

            if "category_id" in item:
                category_id = item["category_id"]
            else:
                category_id = "999999"

            if category_id in currentHidden:
                hidden = True

            self.list1.append([index, str(category_name), str(category_id), hidden])
            index += 1

        glob.originalChannelList1 = self.list1[:]

    def getSeries(self):
        # print("*** getSeries ***")
        # print("*** url ***", glob.nextlist[-1]["next_url"])
        response = self.downloadApiData(glob.nextlist[-1]["next_url"])
        index = 0
        self.list2 = []

        self.storedyear = ""
        self.storedtitle = ""
        self.storedtmdb = ""

        currentChannelList = response
        if currentChannelList:
            for item in currentChannelList:

                hidden = False

                name = ""
                year = ""
                series_id = 0
                cover = ""
                plot = ""
                cast = ""
                director = ""
                genre = ""
                releaseDate = ""
                last_modified = ""
                rating = ""
                tmdb = ""

                if "name" in item and item["name"]:
                    name = item["name"]

                if "year" in item and item["year"]:
                    year = item["year"]

                if "series_id" in item and item["series_id"]:
                    series_id = item["series_id"]

                    if str(series_id) in glob.current_playlist["player_info"]["seriestitleshidden"]:
                        hidden = True

                if "cover" in item and item["cover"]:
                    if item["cover"].startswith("http"):
                        cover = item["cover"]

                        if cover:
                            if cover.startswith("https://image.tmdb.org/t/p/") or cover.startswith("http://image.tmdb.org/t/p/"):
                                dimensions = cover.partition("/p/")[2].partition("/")[0]
                                if screenwidth.width() <= 1280:
                                    cover = cover.replace(dimensions, "w300")
                                else:
                                    cover = cover.replace(dimensions, "w400")

                if "plot" in item and item["plot"]:
                    plot = item["plot"]

                if "cast" in item and item["cast"]:
                    cast = item["cast"]

                if "director" in item and item["director"]:
                    director = item["director"]

                if "genre" in item and item["genre"]:
                    genre = item["genre"]

                if "releaseDate" in item and item["releaseDate"]:
                    releaseDate = item["releaseDate"]

                elif "release_date" in item and item["release_date"]:
                    releaseDate = item["release_date"]

                elif "releasedate" in item and item["releasedate"]:
                    releaseDate = item["releasedate"]

                if "rating" in item and item["rating"]:
                    rating = item["rating"]

                if "last_modified" in item and item["last_modified"]:
                    last_modified = item["last_modified"]

                if "tmdb" in item and item["tmdb"]:
                    tmdb = item["tmdb"]

                next_url = str(self.player_api) + "&action=get_series_info&series_id=" + str(series_id)

                self.list2.append([index, str(name), str(series_id), str(cover), str(plot), str(cast), str(director), str(genre), str(releaseDate), str(rating), str(last_modified), str(tmdb), str(next_url), str(year), hidden])

                index += 1

            glob.originalChannelList2 = self.list2[:]

        else:
            self.session.open(MessageBox, _("No series found in this category."), type=MessageBox.TYPE_ERROR, timeout=5)

    def getSeasons(self):
        # print("**** getSeasons ****")
        # print("*** url ***", glob.nextlist[-1]["next_url"])
        response = self.downloadApiData(glob.nextlist[-1]["next_url"])
        index = 0
        self.list3 = []
        currentChannelList = response

        name = self.title2
        cover = ""
        overview = self.plot2
        cast = self.cast2
        director = self.director2
        genre = self.genre2
        airdate = self.releaseDate2
        rating = self.rating2
        tmdb = self.tmdb2
        last_modified = ""

        if currentChannelList:
            if "info" in currentChannelList:
                if "tmdb" in currentChannelList["info"] and currentChannelList["info"]["tmdb"]:
                    tmdb = currentChannelList["info"]["tmdb"]

                if "name" in currentChannelList["info"] and currentChannelList["info"]["name"]:
                    name = currentChannelList["info"]["name"]

                if "cover" in currentChannelList["info"] and currentChannelList["info"]["cover"] and currentChannelList["info"]["cover"].startswith("http"):
                    cover = currentChannelList["info"]["cover"]

                if "plot" in currentChannelList["info"] and currentChannelList["info"]["plot"]:
                    overview = currentChannelList["info"]["plot"]

                if "cast" in currentChannelList["info"] and currentChannelList["info"]["cast"]:
                    cast = currentChannelList["info"]["cast"]

                if "director" in currentChannelList["info"] and currentChannelList["info"]["director"]:
                    director = currentChannelList["info"]["director"]

                if "genre" in currentChannelList["info"] and currentChannelList["info"]["genre"]:
                    genre = currentChannelList["info"]["genre"]

                if "releaseDate" in currentChannelList["info"] and currentChannelList["info"]["releaseDate"]:
                    airdate = currentChannelList["info"]["releaseDate"]

                elif "release_date" in currentChannelList["info"] and currentChannelList["info"]["release_date"]:
                    airdate = currentChannelList["info"]["release_date"]

                if "rating" in currentChannelList["info"] and currentChannelList["info"]["rating"]:
                    rating = currentChannelList["info"]["rating"]

                if "last_modified" in currentChannelList["info"] and currentChannelList["info"]["last_modified"]:
                    last_modified = currentChannelList["info"]["last_modified"]

            if "episodes" in currentChannelList and currentChannelList["episodes"]:
                episodekeys = []
                self.isdict = True
                try:
                    episodekeys = list(currentChannelList["episodes"].keys())
                    # print("*** is dict ***")
                except:
                    # print("*** is not dict ***")
                    self.isdict = False
                    x = 0
                    for item in currentChannelList["episodes"]:
                        episodekeys.append(x)
                        x += 1

                if episodekeys:
                    for episodekey in episodekeys:

                        name = str(episodekey)

                        if self.isdict:
                            season_number = currentChannelList["episodes"][str(episodekey)][0]["season"]
                        else:
                            season_number = currentChannelList["episodes"][episodekey][0]["season"]

                        # print("*** *season number 2 ***", season_number)

                        if "seasons" in currentChannelList and currentChannelList["seasons"]:
                            for season in currentChannelList["seasons"]:
                                series_id = 0
                                hidden = False

                                if "season_number" in season and str(season["season_number"]) == str(season_number):
                                    season_number = season["season_number"]

                                    if "name" in season and season["name"]:
                                        name = season["name"]

                                    if "airdate" in season and season["airdate"]:
                                        airdate = season["airdate"]

                                    elif "air_date" in season and season["air_date"]:
                                        airdate = season["air_date"]

                                    if "overview" in season and season["overview"] and len(season["overview"]) > 50 and "http" not in season["overview"]:
                                        overview = season["overview"]

                                    if "cover_big" in season and season["cover_big"] and season["cover_big"].startswith("http") and len(season["cover_big"]) > 50:
                                        cover = season["cover_big"]

                                    elif "cover" in season and season["cover"] and season["cover"].startswith("http") and len(season["cover"]) > 50:
                                        cover = season["cover"]

                                    if "id" in season and season["id"]:
                                        series_id = season["id"]

                                    break
                        else:
                            series_id = 0
                            hidden = False

                        if str(series_id) in glob.current_playlist["player_info"]["seriesseasonshidden"]:
                            hidden = True

                        if cover and (cover.startswith("https://image.tmdb.org/t/p/") or cover.startswith("http://image.tmdb.org/t/p/")):
                            dimensions = cover.partition("/p/")[2].partition("/")[0]
                            if screenwidth.width() <= 1280:
                                cover = cover.replace(dimensions, "w300")
                            else:
                                cover = cover.replace(dimensions, "w400")

                        next_url = self.seasons_url

                        self.list3.append([index, str(name), str(series_id), str(cover), str(overview), str(cast), str(director), str(genre), str(airdate), str(rating), season_number, str(next_url), str(last_modified), hidden, tmdb])
                self.list3.sort(key=self.natural_keys)

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

                if "tmdb" in currentChannelList["info"] and currentChannelList["info"]["tmdb"]:
                    tmdb_id = currentChannelList["info"]["tmdb"]

                if "name" in currentChannelList["info"] and currentChannelList["info"]["name"]:
                    shorttitle = currentChannelList["info"]["name"]

                if "title" in currentChannelList["info"] and currentChannelList["info"]["title"]:
                    shorttitle = currentChannelList["info"]["title"]

                if "cover" in currentChannelList["info"] and currentChannelList["info"]["cover"] and currentChannelList["info"]["cover"].startswith("http"):
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

            if "episodes" in currentChannelList and currentChannelList["episodes"]:
                season_number = str(self.storedseason)
                if self.isdict is False:
                    season_number = int(self.storedseason)

                # print("*** season number ***", season_number)
                for item in currentChannelList["episodes"][season_number]:
                    title = ""
                    stream_id = ""
                    container_extension = "mp4"
                    tmdb_id = ""
                    duration = ""
                    hidden = False
                    direct_source = ""
                    episode_num = 1

                    if "id" in item:
                        stream_id = item["id"]
                    else:
                        continue

                    if "episode_num" in item:
                        episode_num = item["episode_num"]

                    if "title" in item:
                        title = item["title"].replace(str(shorttitle) + " - ", "")

                    if "container_extension" in item:
                        container_extension = item["container_extension"]

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

                    if "direct_source" in item and item["direct_source"]:
                        direct_source = item["direct_source"]

                    if "seasons" in currentChannelList and currentChannelList["seasons"]:
                        for season in currentChannelList["seasons"]:
                            if int(season["season_number"]) == int(season_number):
                                if "cover" in season and season["cover"]:
                                    cover = season["cover"]

                                if "cover_big" in season and season["cover_big"]:
                                    cover = season["cover_big"]
                                break

                    if cover:
                        if cover.startswith("https://image.tmdb.org/t/p/") or cover.startswith("http://image.tmdb.org/t/p/"):
                            dimensions = cover.partition("/p/")[2].partition("/")[0]
                            if screenwidth.width() <= 1280:
                                cover = cover.replace(dimensions, "w300")
                            else:
                                cover = cover.replace(dimensions, "w400")

                    if str(stream_id) in glob.current_playlist["player_info"]["seriesepisodeshidden"]:
                        hidden = True

                    next_url = "%s/series/%s/%s/%s.%s" % (self.host, self.username, self.password, stream_id, container_extension)

                    self.list4.append([index, str(title), str(stream_id), str(cover), str(plot), str(cast), str(director), str(genre), str(releasedate), str(rating), str(duration), str(container_extension), str(tmdb_id), str(next_url), str(shorttitle), str(last_modified), hidden, str(direct_source), episode_num])
                    index += 1

            glob.originalChannelList4 = self.list4[:]

    def downloadApiData(self, url):
        # print("**** downloadApiData ****")
        content = ""
        retries = Retry(total=1, backoff_factor=1)
        adapter = HTTPAdapter(max_retries=retries)
        http = requests.Session()
        http.mount("http://", adapter)
        http.mount("https://", adapter)
        try:
            r = http.get(url, headers=hdr, timeout=(10, 20), verify=False)
            r.raise_for_status()
            if r.status_code == requests.codes.ok:
                try:
                    content = r.json()
                except Exception as e:
                    print(e)
            return content

        except Exception as e:
            print(e)
            self.session.openWithCallback(self.back, MessageBox, _("Server error or invalid link."), MessageBox.TYPE_ERROR, timeout=3)

    def buildCategories(self):
        # print("*** buildCategories ***")

        self.hideVod()

        self.pre_list = []
        if self["key_blue"].getText() != (_("Reset Search")) and self.prelist:
            self.pre_list = [buildCategoryList(x[0], x[1], x[2], x[3]) for x in self.prelist if x[3] is False]

        self.main_list = []
        if self.list1:
            self.main_list = [buildCategoryList(x[0], x[1], x[2], x[3]) for x in self.list1 if x[3] is False]

            self.combined_list = []
            self.combined_list.extend(self.pre_list + self.main_list)

            self["main_list"].setList(self.combined_list)

            if self["main_list"].getCurrent():

                # remember previous list position
                if glob.nextlist[-1]["index"] != 0:
                    self["main_list"].setIndex(glob.nextlist[-1]["index"])

    def buildSeries(self):
        # print("*** buildSeries ***")
        self.main_list = []

        if self.list2:
            self.main_list = [buildSeriesTitlesList(x[0], x[1], x[2], x[3], x[4], x[5], x[6], x[7], x[8], x[9], x[10], x[11], x[12], x[13], x[14]) for x in self.list2 if x[14] is False]
            self["main_list"].setList(self.main_list)

            self.showVod()

            if self["main_list"].getCurrent():
                if glob.nextlist[-1]["index"] != 0:
                    self["main_list"].setIndex(glob.nextlist[-1]["index"])

    def buildSeasons(self):
        # print("*** buildSeasons ***")
        self.main_list = []

        if self.list3:
            self.main_list = [buildSeriesSeasonsList(x[0], x[1], x[2], x[3], x[4], x[5], x[6], x[7], x[8], x[9], x[10], x[11], x[12], x[13], x[14]) for x in self.list3 if x[13] is False]
            self["main_list"].setList(self.main_list)

            if self["main_list"].getCurrent():
                if glob.nextlist[-1]["index"] != 0:
                    self["main_list"].setIndex(glob.nextlist[-1]["index"])

    def buildEpisodes(self):
        # print("*** buildEpisodes ***")
        self.main_list = []

        if self.list4:
            self.main_list = [buildSeriesEpisodesList(x[0], x[1], x[2], x[3], x[4], x[5], x[6], x[7], x[8], x[9], x[10], x[11], x[12], x[13], x[14], x[15], x[16], x[17], x[18]) for x in self.list4 if x[16] is False]
            self["main_list"].setList(self.main_list)

        if self["main_list"].getCurrent():
            if glob.nextlist[-1]["index"] != 0:
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

        if self["main_list"].getCurrent():

            channeltitle = self["main_list"].getCurrent()[0]
            currentindex = self["main_list"].getIndex()

            self.position = currentindex + 1
            self.positionall = len(self.main_list)
            self.page = int(math.ceil(float(self.position) / float(self.itemsperpage)))
            self.pageall = int(math.ceil(float(self.positionall) / float(self.itemsperpage)))

            self["page"].setText(_("Page: ") + str(self.page) + _(" of ") + str(self.pageall))
            self["listposition"].setText(str(self.position) + "/" + str(self.positionall))

            self["main_title"].setText(self.main_title + ": " + str(channeltitle))

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
            self.position = 0
            self.positionall = 0
            self.page = 0
            self.pageall = 0

            self["page"].setText(_("Page: ") + str(self.page) + _(" of ") + str(self.pageall))
            self["listposition"].setText(str(self.position) + "/" + str(self.positionall))

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

        if self["main_list"].getCurrent():
            if self.level == 2:
                title = self["main_list"].getCurrent()[0]
                year = self["main_list"].getCurrent()[13]
                tmdb = self["main_list"].getCurrent()[14]

                if not year:
                    # get year from release date
                    try:
                        year = self["main_list"].getCurrent()[10]
                        year = year[0:4]
                    except:
                        year = ""

                self.storedyear = year
                self.storedtitle = title

            else:
                title = self.storedtitle
                year = self.storedyear

                if self.level == 3:
                    tmdb = self["main_list"].getCurrent()[15]

                if self.level == 4:
                    tmdb = self["main_list"].getCurrent()[14]

            if tmdb and self.tmdbValid is True:
                self.getTMDBDetails(tmdb)
                return

            if title:
                searchtitle = title.lower()

                # if title ends in "the", move "the" to the beginning
                if searchtitle.endswith("the"):
                    searchtitle.rsplit(" ", 1)[0]
                    searchtitle = searchtitle.rsplit(" ", 1)[0]
                    searchtitle = "the " + str(searchtitle)

                # remove xx: at start
                searchtitle = re.sub(r'^\w{2}:', '', searchtitle)

                # remove xx|xx at start
                searchtitle = re.sub(r'^\w{2}\|\w{2}\s', '', searchtitle)

                # remove || content at start
                searchtitle = re.sub(r'^\|[\w\-\|]*\|', '', searchtitle)

                # remove () content
                n = 1  # run at least once
                while n:
                    searchtitle, n = re.subn(r'\([^\(\)]*\)', '', searchtitle)

                # remove [] content
                n = 1  # run at least once
                while n:
                    searchtitle, n = re.subn(r'\[[^\[\]]*\]', '', searchtitle)

                bad_chars = ["1080p-dual-lat-cinecalidad.mx", "1080p-lat-cinecalidad.mx", "1080p-dual-lat-cine-calidad.com-1", "1080p-dual-lat-cine-calidad.com", "1080p-lat-cine-calidad.com-1", "1080p-lat-cine-calidad.com",
                             "1080p.dual.lat.cine-calidad.com",

                             "sd", "hd", "fhd", "uhd", "4k", "vod", "1080p", "720p", "blueray", "x264", "aac", "ozlem", "hindi", "hdrip", "imdb", "top250", "multi-audio",
                             "multi-subs", "multi-sub", "multisub",

                             "ex-yu:",

                             "-ae-", "-al-", "-ar-", "-at-", "-ba-", "-be-", "-bg-", "-br-", "-cg-", "-ch-", "-cz-", "-da-", "-de-", "-dk-", "-ee-", "-en-", "-es-", "-ex-yu-", "-fi-", "-fr-", "-gr-", "-hr-", "-hu-", "-in-", "-ir-", "-it-", "-lt-", "-mk-",
                             "-mx-", "-nl-", "-no-", "-pl-", "-pt-", "-ro-", "-rs-", "-ru-", "-se-", "-si-", "-sk-", "-tr-", "-uk-", "-us-", "-yu-",

                             "|ae|", "|al|", "|ar|", "|at|", "|ba|", "|be|", "|bg|", "|br|", "|cg|", "|ch|", "|cz|", "|da|", "|de|", "|dk|", "|ee|", "|en|", "|es|", "|eu|", "|ex-yu|", "|fi|", "|fr|", "|gr|", "|hr|", "|hu|", "|in|", "|ir|", "|it|", "|lt|", "|mk|",
                             "|mx|", "|nl|", "|no|", "|pl|", "|pt|", "|ro|", "|rs|", "|ru|", "|se|", "|si|", "|sk|", "|tr|", "|uk|", "|us|", "|yu|",

                             "(", ")", "[", "]", "u-", "3d", "'", "#", "/"]

                for j in range(1900, 2025):
                    bad_chars.append(str(j))

                for i in bad_chars:
                    searchtitle = searchtitle.replace(i, "")

                bad_suffix = [" de", " al", " nl", " pt", " pl", " ru", " ar", " ro", " gr", " fi", " no", " rs", " ba", " si", " mk", " ex-yu", " hr", " yu", " fr", " da", " es", " sw", " swe", " tr", " en", " uk", "eu"]

                for i in bad_suffix:
                    if searchtitle.endswith(i):
                        suffixlength = len(i)
                        searchtitle = searchtitle[:-suffixlength]

                searchtitle = searchtitle.replace("multi:", "")
                searchtitle = searchtitle.replace(".", " ")
                searchtitle = searchtitle.replace("_", " ")
                searchtitle = searchtitle.replace("  ", " ")
                searchtitle = searchtitle.replace("'", "")
                searchtitle = searchtitle.strip("-")
                searchtitle = searchtitle.strip()

                searchtitle = quote(searchtitle, safe="")

                searchurl = 'http://api.themoviedb.org/3/search/tv?api_key=' + str(self.check(self.token)) + '&query=' + str(searchtitle)
                if self.storedyear:
                    searchurl = 'http://api.themoviedb.org/3/search/tv?api_key=' + str(self.check(self.token)) + '&first_air_date_year=' + str(self.storedyear) + '&query=' + str(searchtitle)

                if pythonVer == 3:
                    searchurl = searchurl.encode()

                filepath = os.path.join(dir_tmp, "search.txt")

                try:
                    downloadPage(searchurl, filepath, timeout=10).addCallback(self.processTMDB).addErrback(self.failed)
                except Exception as e:
                    print(("download TMDB error %s" % e))

    def failed(self, data=None):
        # print("*** failed ***")
        if data:
            print(data)
            self.tmdbValid = False
            self.getTMDB()

    def processTMDB(self, result=None):
        # print("*** processTMDB ***")

        resultid = ""
        with codecs.open(str(dir_tmp) + "search.txt", "r", encoding="utf-8") as f:
            response = f.read()

        if response != "":
            try:
                self.searchresult = json.loads(response)
                if "results" not in self.searchresult:
                    self.tmdbValid = False
                    self.getTMDB()
                else:
                    if "results" in self.searchresult and self.searchresult["results"]:
                        if "id" in self.searchresult["results"][0]:
                            resultid = self.searchresult["results"][0]["id"]

                    if not resultid:
                        self.tmdbresults = ""
                        self.displayTMDB()
                        return

                    self.getTMDBDetails(resultid)
            except:
                pass

    def getTMDBDetails(self, resultid=None):
        # print(" *** getTMDBDetails ***")
        detailsurl = ""

        try:
            os.remove(os.path.join(dir_tmp, "tmdb.txt"))
        except:
            pass

        language = ""

        if cfg.TMDB.value is True:
            language = cfg.TMDBLanguage2.value

        languagestr = ""

        if language:
            languagestr = "&language=" + str(language)

        if self.level == 2:
            detailsurl = "http://api.themoviedb.org/3/tv/" + str(resultid) + "?api_key=" + str(self.check(self.token)) + "&append_to_response=credits" + languagestr

        elif self.level == 3:
            self.storedseason = self["main_list"].getCurrent()[12]
            detailsurl = "http://api.themoviedb.org/3/tv/" + str(resultid) + "/season/" + str(self.storedseason) + "?api_key=" + str(self.check(self.token)) + "&append_to_response=credits" + languagestr

        elif self.level == 4:
            self.storedepisode = self["main_list"].getCurrent()[19]
            detailsurl = "http://api.themoviedb.org/3/tv/" + str(resultid) + "/season/" + str(self.storedseason) + "/episode/" + str(self.storedepisode) + "?api_key=" + str(self.check(self.token)) + "&append_to_response=credits" + languagestr

        if pythonVer == 3:
            detailsurl = detailsurl.encode()

        filepath = os.path.join(dir_tmp, "tmdb.txt")
        try:
            downloadPage(detailsurl, filepath, timeout=10).addCallback(self.processTMDBDetails).addErrback(self.failed2)
        except Exception as e:
            print(("download TMDB details error %s" % e))

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
        valid = False
        response = ""
        self.tmdbresults = {}
        self.tmdbdetails = []
        director = []

        try:
            with codecs.open(str(dir_tmp) + "tmdb.txt", "r", encoding="utf-8") as f:
                response = f.read()
        except:
            pass

        if response != "":
            valid = False
            try:
                self.tmdbdetails = json.loads(response, object_pairs_hook=OrderedDict)
                valid = True
            except Exception as e:
                print(e)

            if valid:
                if "name" in self.tmdbdetails and self.tmdbdetails["name"]:
                    self.tmdbresults["name"] = str(self.tmdbdetails["name"])

                if "overview" in self.tmdbdetails:
                    self.tmdbresults["description"] = str(self.tmdbdetails["overview"])

                if "vote_average" in self.tmdbdetails and self.tmdbdetails["vote_average"]:
                    self.tmdbresults["rating"] = str(self.tmdbdetails["vote_average"])
                    if self.tmdbresults["rating"] == "0" or self.tmdbresults["rating"] == "0.0":
                        self.tmdbresults["rating"] = ""
                else:
                    self.tmdbresults["rating"] = ""

                if self.level == 2:
                    if "original_name" in self.tmdbdetails and self.tmdbdetails["original_name"]:
                        self.tmdbresults["o_name"] = str(self.tmdbdetails["original_name"])

                    try:
                        if "episode_run_time" in self.tmdbdetails and self.tmdbdetails["episode_run_time"] and self.tmdbdetails["episode_run_time"] != 0:
                            self.tmdbresults["duration"] = str(timedelta(minutes=int(self.tmdbdetails["episode_run_time"][0])))

                        elif "runtime" in self.tmdbdetails and self.tmdbdetails["runtime"] and self.tmdbdetails["runtime"] != 0:
                            self.tmdbresults["duration"] = str(timedelta(minutes=int(self.tmdbdetails["runtime"])))
                    except Exception as e:
                        self.tmdbresults["duration"] = ""
                        print(e)

                    if "first_air_date" in self.tmdbdetails and self.tmdbdetails["first_air_date"]:
                        self.tmdbresults["releaseDate"] = str(self.tmdbdetails["first_air_date"])

                    if "genres" in self.tmdbdetails and self.tmdbdetails["genres"]:
                        genre = []
                        for genreitem in self.tmdbdetails["genres"]:
                            genre.append(str(genreitem["name"]))
                        genre = " / ".join(map(str, genre))
                        self.tmdbresults["genre"] = genre

                if self.level != 4:
                    if "credits" in self.tmdbdetails and self.tmdbdetails["credits"]:
                        if "cast" in self.tmdbdetails["credits"] and self.tmdbdetails["credits"]["cast"]:
                            cast = []
                            for actor in self.tmdbdetails["credits"]["cast"]:
                                if "character" in actor and "name" in actor:
                                    cast.append(str(actor["name"]))
                            cast = ", ".join(map(str, cast[:5]))
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
                            self.tmdbresults["cover_big"] = "http://image.tmdb.org/t/p/w300" + str(self.tmdbdetails["poster_path"])
                        else:
                            self.tmdbresults["cover_big"] = "http://image.tmdb.org/t/p/w400" + str(self.tmdbdetails["poster_path"])

                if self.level != 2:
                    if "air_date" in self.tmdbdetails and self.tmdbdetails["air_date"]:
                        self.tmdbresults["releaseDate"] = str(self.tmdbdetails["air_date"])

                if self.level == 4:
                    if "runtime" in self.tmdbdetails and self.tmdbdetails["runtime"] and self.tmdbdetails["runtime"] != 0:
                        self.tmdbresults["duration"] = str(timedelta(minutes=int(self.tmdbdetails["runtime"])))

            self.displayTMDB()

    def displayTMDB(self):
        # print("*** displayTMDB ***")
        if self["main_list"].getCurrent() and self.level != 1:

            current = self["main_list"].getCurrent()

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

            stream_url = self["main_list"].getCurrent()[3]

            if self.level == 4:
                try:
                    self["vod_video_type"].setText(stream_url.split(".")[-1])
                except:
                    pass
            else:
                self["vod_video_type"].setText("")

            if self.tmdbresults:
                if "name" in self.tmdbresults:
                    self["x_title"].setText(str(self.tmdbresults["name"]).strip())
                elif "o_name" in self.tmdbresults:
                    self["x_title"].setText(str(self.tmdbresults["o_name"]).strip())

                if "description" in self.tmdbresults:
                    self["x_description"].setText(str(self.tmdbresults["description"]).strip())
                elif "plot" in self.tmdbresults:
                    self["x_description"].setText(str(self.tmdbresults["plot"]).strip())

                if "duration" in self.tmdbresults:
                    self["vod_duration"].setText(str(self.tmdbresults["duration"]).strip())

                if "genre" in self.tmdbresults:
                    self["vod_genre"].setText(str(self.tmdbresults["genre"]).strip())

                if "rating" in self.tmdbresults:
                    self["vod_rating"].setText(str(self.tmdbresults["rating"]).strip())

                if "country" in self.tmdbresults:
                    self["vod_country"].setText(str(self.tmdbresults["country"]).strip())

                if "releaseDate" in self.tmdbresults and self.tmdbresults["releaseDate"]:
                    try:
                        self["vod_release_date"].setText(datetime.strptime(self.tmdbresults["releaseDate"], "%Y-%m-%d").strftime("%d-%m-%Y"))
                    except:
                        pass
                elif "release_date" in self.tmdbresults and self.tmdbresults["release_date"]:
                    try:
                        self["vod_release_date"].setText(datetime.strptime(self.tmdbresults["release_date"], "%Y-%m-%d").strftime("%d-%m-%Y"))
                    except:
                        pass
                elif "releasedate" in self.tmdbresults and self.tmdbresults["releasedate"]:
                    try:
                        self["vod_release_date"].setText(datetime.strptime(self.tmdbresults["releasedate"], "%Y-%m-%d").strftime("%d-%m-%Y"))
                    except:
                        pass

                if "director" in self.tmdbresults:
                    self["vod_director"].setText(str(self.tmdbresults["director"]).strip())

                if "cast" in self.tmdbresults:
                    self["vod_cast"].setText(str(self.tmdbresults["cast"]).strip())
                elif "actors" in self.tmdbresults:
                    self["vod_cast"].setText(str(self.tmdbresults["actors"]).strip())

            if self.level != 4:
                self.downloadImage()

    def resetButtons(self):
        if glob.nextlist[-1]["filter"]:
            self["key_yellow"].setText("")
            self["key_blue"].setText(_("Reset Search"))
            self["key_menu"].setText("")
        else:
            self["key_blue"].setText(_("Search"))
            if not glob.nextlist[-1]["sort"]:
                self.sortText = (_("Sort: A-Z"))
                glob.nextlist[-1]["sort"] = self.sortText

            self["key_yellow"].setText(_(glob.nextlist[-1]["sort"]))
            self["key_menu"].setText("+/-")

    def playStream(self):
        # print("*** playStream ***")
        # back button back to playing stream
        if self["main_list"].getCurrent():
            if self.session.nav.getCurrentlyPlayingServiceReference():
                if self.session.nav.getCurrentlyPlayingServiceReference().toString() == glob.currentPlayingServiceRefString:
                    self.back()
                else:
                    self["main_list"].setIndex(glob.nextlist[-1]["index"])
                    self.next()
            else:
                self.back()

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
                if "cover_big" in self.tmdbresults and self.tmdbresults["cover_big"] and self.tmdbresults["cover_big"] != "null":
                    desc_image = str(self.tmdbresults["cover_big"]).strip()
                elif "movie_image" in self.tmdbresults and self.tmdbresults["movie_image"] and self.tmdbresults["movie_image"] != "null":
                    desc_image = str(self.tmdbresults["movie_image"]).strip()

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
                except:
                    self.loadDefaultImage()
            else:
                self.loadDefaultImage()

    def loadDefaultImage(self, data=None):
        # print("*** loadDefaultImage ***")
        if self["vod_cover"].instance:
            self["vod_cover"].instance.setPixmapFromFile(os.path.join(skin_directory, "common/vod_cover.png"))

    def resizeImage(self, data=None):
        # print("*** resizeImage ***")
        if self["main_list"].getCurrent():
            if self["vod_cover"].instance:
                preview = os.path.join(dir_tmp, "temp.jpg")

                if screenwidth.width() == 2560:
                    width = 534
                    height = 800
                elif screenwidth.width() > 1280:
                    width = 400
                    height = 600
                else:
                    width = 267
                    height = 400

                self.PicLoad.setPara([width, height, 1, 1, 0, 1, "FF000000"])

                if self.PicLoad.startDecode(preview):
                    # if this has failed, then another decode is probably already in progress
                    # throw away the old picload and try again immediately
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
        # print("*** sort ***")
        sortlist = []

        if self.level == 1:
            activelist = self.list1[:]
            activeoriginal = glob.originalChannelList1[:]

        elif self.level == 2:
            activelist = self.list2[:]
            activeoriginal = glob.originalChannelList2[:]

        elif self.level == 3:
            activelist = self.list3[:]
            activeoriginal = glob.originalChannelList3[:]

        elif self.level == 4:
            activelist = self.list4[:]
            activeoriginal = glob.originalChannelList4[:]

        if self.level == 1:
            sortlist = [(_("Sort: A-Z")), (_("Sort: Z-A")), (_("Sort: Original"))]

        elif self.level == 2:
            sortlist = [(_("Sort: A-Z")), (_("Sort: Z-A")), (_("Sort: Added")), (_("Sort: Original"))]

        else:
            sortlist = [(_("Sort: A-Z")), (_("Sort: Z-A")), (_("Sort: Added")), (_("Sort: Year")), (_("Sort: Original"))]

        for index, item in enumerate(sortlist, start=0):
            if str(item) == str(self.sortText):
                self.sortindex = index
                break

        if self["main_list"].getCurrent():
            self["main_list"].setIndex(0)

        current_sort = self["key_yellow"].getText()

        if current_sort == (_("Sort: A-Z")):
            activelist.sort(key=lambda x: x[1], reverse=False)

        elif current_sort == (_("Sort: Z-A")):
            activelist.sort(key=lambda x: x[1], reverse=True)

        elif current_sort == (_("Sort: Added")):
            if self.level == 2:
                activelist.sort(key=lambda x: x[10], reverse=True)

            if self.level == 3:
                activelist.sort(key=lambda x: x[12], reverse=True)

            if self.level == 4:
                activelist.sort(key=lambda x: x[15], reverse=True)

        elif current_sort == (_("Sort: Year")):
            if self.level == 2:
                activelist.sort(key=lambda x: x[8], reverse=True)

            if self.level == 3:
                activelist.sort(key=lambda x: x[8], reverse=True)

            if self.level == 4:
                activelist.sort(key=lambda x: x[8], reverse=True)

        elif current_sort == (_("Sort: Original")):
            activelist = activeoriginal

        nextSortType = islice(cycle(sortlist), self.sortindex + 1, None)
        self.sortText = str(next(nextSortType))

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

        if current_filter == (_("Reset Search")):
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

        elif self.level == 2:
            activeoriginal = glob.originalChannelList2[:]

        elif self.level == 3:
            activeoriginal = glob.originalChannelList3[:]

        elif self.level == 4:
            activeoriginal = glob.originalChannelList4[:]

        if self.level == 1:
            self.list1 = activeoriginal

        elif self.level == 2:
            self.list2 = activeoriginal

        elif self.level == 3:
            self.list3 = activeoriginal

        elif self.level == 4:
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
        # print("*** parentalCheck ***")
        self.pin = True
        if pythonVer == 2:
            nowtime = int(time.mktime(datetime.now().timetuple()))
        else:
            nowtime = int(datetime.timestamp(datetime.now()))

        if self.level == 1 and self["main_list"].getCurrent():
            adult = "+18", "adult", "adults", "18+", "18 rated", "xxx", "sex", "porn", "pink", "blue", "الكل", "vše", "alle", "kõik", "kaikki", "tout", "tutto", "alles", "wszystko", "todos", "všetky", "të gjitha", "sve", "allt", "hepsi", "所有"

            if str(self["main_list"].getCurrent()[0]).lower() == _("all") or str(self["main_list"].getCurrent()[0]).lower() == "all":
                glob.adultChannel = True

            elif any(s in str(self["main_list"].getCurrent()[0]).lower() for s in adult):
                glob.adultChannel = True

            else:
                glob.adultChannel = False

            if cfg.adult.value is True and (nowtime - int(glob.pintime) > 900):
                if glob.adultChannel is True:
                    from Screens.InputBox import PinInput
                    self.session.openWithCallback(self.pinEntered, PinInput, pinList=[cfg.adultpin.value], triesEntry=cfg.retries.adultpin, title=_("Please enter the parental control pin code"), windowTitle=_("Enter pin code"))
                else:
                    self.next()
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

                    if category_id == "0":
                        next_url = str(self.player_api) + "&action=get_series"
                    else:
                        next_url = str(self.player_api) + "&action=get_series&category_id=" + str(category_id)

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
                    self.storedepisode = self["main_list"].getCurrent()[19]
                    streamtype = glob.current_playlist["player_info"]["vodtype"]
                    next_url = self["main_list"].getCurrent()[3]
                    try:
                        direct_source = self["main_list"].getCurrent()[18]
                    except Exception as e:
                        print(e)
                        direct_source = ""

                    stream_id = self["main_list"].getCurrent()[4]
                    self.reference = eServiceReference(int(streamtype), 0, next_url)

                    try:
                        if glob.current_playlist["player_info"]["directsource"] == "Direct Source":
                            if direct_source:
                                self.reference = eServiceReference(int(streamtype), 0, direct_source)

                        self.reference.setName(glob.currentchannellist[glob.currentchannellistindex][0])
                        self.session.openWithCallback(self.setIndex, streamplayer.XStreamity_VodPlayer, str(next_url), str(streamtype), str(direct_source), stream_id)
                    except Exception as e:
                        print("********* series crash *********", e)
                        self.createSetup()
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
        # print("*** showHiddenList ***")
        if self["key_menu"].getText() != "":
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
            for watched in glob.current_playlist["player_info"]["serieswatched"]:
                if self["main_list"].getCurrent() and int(self["main_list"].getCurrent()[4]) == int(watched):
                    glob.current_playlist["player_info"]["serieswatched"].remove(watched)
                    break

        with open(playlists_json, "r") as f:
            try:
                self.playlists_all = json.load(f)
            except:
                os.remove(playlists_json)

        if self.playlists_all:
            x = 0
            for playlists in self.playlists_all:
                if playlists["playlist_info"]["domain"] == glob.current_playlist["playlist_info"]["domain"] and playlists["playlist_info"]["username"] == glob.current_playlist["playlist_info"]["username"] and playlists["playlist_info"]["password"] == glob.current_playlist["playlist_info"]["password"]:
                    self.playlists_all[x] = glob.current_playlist
                    break
                x += 1

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


def buildSeriesEpisodesList(index, title, series_id, cover, plot, cast, director, genre, releaseDate, rating, duration, container_extension, tmdb_id, next_url, shorttitle, lastmodified, hidden, direct_source, episode_number):
    png = LoadPixmap(os.path.join(common_path, "play.png"))
    for channel in glob.current_playlist["player_info"]["serieswatched"]:
        if int(series_id) == int(channel):
            png = LoadPixmap(os.path.join(common_path, "watched.png"))
    return (title, png, index, next_url, series_id, cover, plot, cast, director, genre, releaseDate, rating, duration, container_extension, tmdb_id, shorttitle, lastmodified, hidden, direct_source, episode_number)
