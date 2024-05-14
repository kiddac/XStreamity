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

from .plugin import skin_directory, screenwidth, hdr, cfg, common_path, dir_tmp, playlists_json, downloads_json, pythonVer
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


class XStreamity_Categories(Screen):
    ALLOW_SUSPEND = True

    def __init__(self, session):
        # print("*** init ***")
        Screen.__init__(self, session)
        self.session = session
        glob.categoryname = "vod"

        self.skin_path = os.path.join(skin_directory, cfg.skin.value)
        skin = os.path.join(self.skin_path, "vod_categories.xml")
        if os.path.exists("/var/lib/dpkg/status"):
            skin = os.path.join(self.skin_path, "DreamOS/vod_categories.xml")

        with codecs.open(skin, "r", encoding="utf-8") as f:
            self.skin = f.read()

        self.setup_title = _("Vod Categories")
        self.main_title = _("Vod")
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
        self.info = ""
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

        next_url = str(self.player_api) + "&action=get_vod_categories"

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
            "epg": self.imdb,
            "info": self.imdb,
            "text": self.imdb,
            "left": self.pageUp,
            "right": self.pageDown,
            "up": self.goUp,
            "down": self.goDown,
            "channelUp": self.pageUp,
            "channelDown": self.pageDown,
            "rec": self.downloadVideo,
            "5": self.downloadVideo,
            "tv": self.favourite,
            "stop": self.favourite,
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
        else:
            self.getVod()

        self.buildLists()

    def buildLists(self):
        # print("*** buildLists ***")
        if self.level == 1:
            self.buildCategories()
        else:
            self.buildVod()

        self.resetButtons()
        self.selectionChanged()

    def getCategories(self):
        # print("*** getCategories **")
        index = 0
        self.list1 = []
        self.prelist = []

        self["key_epg"].setText("")

        # no need to download. Already downloaded and saved in playlist menu
        currentPlaylist = glob.active_playlist
        currentCategoryList = currentPlaylist.get("data", {}).get("vod_categories", [])
        currentHidden = set(currentPlaylist.get("player_info", {}).get("vodhidden", []))

        hiddenfavourites = "-1" in currentHidden
        hiddenrecent = "-2" in currentHidden
        hidden = "0" in currentHidden

        i = 0

        self.prelist.extend([
            [i, _("FAVOURITES"), "-1", hiddenfavourites],
            [i + 1, _("RECENTLY WATCHED"), "-2", hiddenrecent],
            [i + 2, _("ALL"), "0", hidden]
        ])

        for index, item in enumerate(currentCategoryList, start=len(self.prelist)):
            category_name = item.get("category_name", "No category")
            category_id = item.get("category_id", "999999")
            hidden = category_id in currentHidden
            self.list1.append([index, str(category_name), str(category_id), hidden])

        glob.originalChannelList1 = self.list1[:]

    def getVod(self):
        # print("*** getVod ***")
        # print("*** url ***", glob.nextlist[-1]["next_url"])

        self["key_epg"].setText("IMDB")
        response = ""

        if self.chosen_category == "favourites":
            response = glob.active_playlist["player_info"].get("vodfavourites", [])
        elif self.chosen_category == "recents":
            response = glob.active_playlist["player_info"].get("vodrecents", [])
        else:
            response = self.downloadApiData(glob.nextlist[-1]["next_url"])

        index = 0
        self.list2 = []

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

                stream_id = channel.get("stream_id", "")
                if not stream_id:
                    continue

                hidden = str(stream_id) in glob.active_playlist["player_info"]["vodstreamshidden"]

                stream_icon = str(channel.get("stream_icon", ""))

                if stream_icon and stream_icon.startswith("http"):

                    try:
                        stream_icon = stream_icon.replace(r"\/", "/")
                    except:
                        pass

                    if stream_icon == "https://image.tmdb.org/t/p/w600_and_h900_bestv2":
                        stream_icon = ""

                    if stream_icon.startswith("https://image.tmdb.org/t/p/") or stream_icon.startswith("http://image.tmdb.org/t/p/"):
                        dimensions = stream_icon.partition("/p/")[2].partition("/")[0]
                        if screenwidth.width() <= 1280:
                            stream_icon = stream_icon.replace(dimensions, "w300")
                        else:
                            stream_icon = stream_icon.replace(dimensions, "w400")
                else:
                    stream_icon = ""

                added = str(channel.get("added", ""))

                category_id = str(channel.get("category_id", ""))
                if self.chosen_category == "all" and str(category_id) in glob.active_playlist["player_info"]["vodhidden"]:
                    continue

                container_extension = channel.get("container_extension", "mp4")

                rating = str(channel.get("rating", ""))

                year = str(channel.get("year", ""))

                direct_source = str(channel.get("direct_source", ""))

                next_url = "{}/movie/{}/{}/{}.{}".format(self.host, self.username, self.password, stream_id, container_extension)

                favourite = False
                if "vodfavourites" in glob.active_playlist["player_info"]:
                    for fav in glob.active_playlist["player_info"]["vodfavourites"]:
                        if str(stream_id) == str(fav["stream_id"]):
                            favourite = True
                            break
                else:
                    glob.active_playlist["player_info"]["vodfavourites"] = []

                self.list2.append([index, str(name), str(stream_id), str(stream_icon), str(added), str(rating), str(next_url), favourite, container_extension, year, hidden, str(direct_source)])

            glob.originalChannelList2 = self.list2[:]

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

        self.main_list = [buildCategoryList(x[0], x[1], x[2], x[3]) for x in self.list1 if not x[3]]

        self["main_list"].setList(self.pre_list + self.main_list)

        if self["main_list"].getCurrent() and glob.nextlist[-1]["index"] != 0:
            self["main_list"].setIndex(glob.nextlist[-1]["index"])

    def buildVod(self):
        # print("*** buildVod ***")
        self.main_list = []

        if self.chosen_category == "favourites":
            self.main_list = [buildVodStreamList(x[0], x[1], x[2], x[3], x[4], x[5], x[6], x[7], x[8], x[10], x[11]) for x in self.list2 if x[7] is True]
        else:
            self.main_list = [buildVodStreamList(x[0], x[1], x[2], x[3], x[4], x[5], x[6], x[7], x[8], x[10], x[11]) for x in self.list2 if x[10] is False]
        self["main_list"].setList(self.main_list)
        self.showVod()

        if self["main_list"].getCurrent() and glob.nextlist[-1]["index"] != 0:
            self["main_list"].setIndex(glob.nextlist[-1]["index"])

    def downloadVodData(self):
        # print("*** downloadVodData ***")
        if self["main_list"].getCurrent():
            stream_id = self["main_list"].getCurrent()[4]
            url = str(glob.active_playlist["playlist_info"]["player_api"]) + "&action=get_vod_info&vod_id=" + str(stream_id)

            self.info = ""

            retries = Retry(total=1, backoff_factor=1)
            adapter = HTTPAdapter(max_retries=retries)
            http = requests.Session()
            http.mount("http://", adapter)
            http.mount("https://", adapter)
            try:
                r = http.get(url, headers=hdr, timeout=(10, 60), verify=False)
                r.raise_for_status()
                if r.status_code == requests.codes.ok:
                    try:
                        content = r.json()
                    except ValueError as e:
                        print(e)
                        content = None

                if content and "info" in content and content["info"]:
                    self.info = content["info"]

                if "name" not in self.info and "movie_data" in content and content["movie_data"]:
                    self.info["name"] = content["movie_data"]["name"]

                elif "movie_data" in content and content["movie_data"]:
                    self.info = content["movie_data"]
                else:
                    self.info = None

                if cfg.TMDB.value is True:
                    self.getTMDB()
                else:
                    self.displayTMDB()
                    if cfg.channelcovers.value is True:
                        self.downloadImage()

            except Exception as e:
                print(e)

    def selectionChanged(self):
        # print("*** selectionChanged ***")
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

            self.clearVod()
            self.loadDefaultImage()

            if self.level == 2:
                self.timerVOD = eTimer()
                try:
                    self.timerVOD.stop()
                except:
                    pass

                try:
                    self.timerVOD.callback.append(self.downloadVodData)
                except:
                    self.timerVOD_conn = self.timerVOD.timeout.connect(self.downloadVodData)
                self.timerVOD.start(300, True)

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
        self.isIMDB = False
        self.tmdb_id_exists = False
        year = ""

        try:
            os.remove(os.path.join(dir_tmp, "search.txt"))
        except:
            pass

        next_url = self["main_list"].getCurrent()[3]

        if next_url != "None" and "/movie/" in next_url:
            title = self["main_list"].getCurrent()[0]

            if self.info:
                title = self.info.get("name", self.info.get("o_name", title))
                year = self.info.get("releasedate", "")[0:4]

                if "tmdb_id" in self.info and self.info["tmdb_id"]:
                    if str(self.info["tmdb_id"])[:1].isdigit():
                        self.getTMDBDetails(self.info["tmdb_id"])
                        return
                    else:
                        self.isIMDB = True

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
        searchtitle = re.sub(r'^\(\(.*\)\)|^\(.*\)', '', searchtitle)

        # remove all leading contend between and including []
        searchtitle = re.sub(r'^\[\[.*\]\]|^\[.*\]', '', searchtitle)

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

        if self.isIMDB is False:
            searchurl = 'http://api.themoviedb.org/3/search/movie?api_key={}&query={}'.format(self.check(self.token), searchtitle)
            if year:
                searchurl = 'http://api.themoviedb.org/3/search/movie?api_key={}&primary_release_year={}&query={}'.format(self.check(self.token), year, searchtitle)
        else:
            searchurl = 'http://api.themoviedb.org/3/find/{}?api_key={}&external_source=imdb_id'.format(self.info["tmdb_id"], self.check(self.token))

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
        return

    def processTMDB(self, result=None):
        # print("***processTMDB ***")
        IMDB = self.isIMDB
        resultid = ""
        search_file_path = os.path.join(dir_tmp, "search.txt")

        try:
            with codecs.open(search_file_path, "r", encoding="utf-8") as f:
                response = f.read()

            if response:
                self.searchresult = json.loads(response)
                if IMDB is False:
                    results = self.searchresult.get("results", [])
                else:
                    results = self.searchresult.get("movie_results", [])

                if results:
                    resultid = results[0].get("id", "")

                if not resultid:
                    self.displayTMDB()
                    if cfg.channelcovers.value:
                        self.info = ""
                        self.downloadImage()
                    return

                self.getTMDBDetails(resultid)
        except Exception as e:
            print("Error processing TMDB response:", e)

    def getTMDBDetails(self, resultid=None):
        # print(" *** getTMDBDetails ***")
        detailsurl = ""
        languagestr = ""

        try:
            os.remove(os.path.join(dir_tmp, "tmdb.txt"))
        except OSError:
            pass

        if cfg.TMDB.value:
            language = cfg.TMDBLanguage2.value
            if language:
                languagestr = "&language=" + str(language)

        detailsurl = "http://api.themoviedb.org/3/movie/{}?api_key={}&append_to_response=credits{}".format(
            resultid, self.check(self.token), languagestr)

        if pythonVer == 3:
            detailsurl = detailsurl.encode()

        filepath = os.path.join(dir_tmp, "tmdb.txt")
        try:
            downloadPage(detailsurl, filepath, timeout=10).addCallback(self.processTMDBDetails).addErrback(self.failed)
        except Exception as e:
            print("download TMDB details error:", e)

    def processTMDBDetails(self, result=None):
        # print("*** processTMDBDetails ***")
        response = ""
        self.info = {}
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
                    # print("*** self.tmdbdetails ***", self.tmdbdetails)
                    self.info["name"] = str(self.tmdbdetails.get("title", ""))

                    self.info["o_name"] = str(self.tmdbdetails.get("original_title", ""))

                    runtime = self.tmdbdetails.get("runtime", "")
                    if runtime and runtime != 0:
                        self.info["duration"] = str(timedelta(minutes=runtime))
                    else:
                        self.info["duration"] = ""

                    country = ", ".join(str(pcountry["name"]) for pcountry in self.tmdbdetails.get("production_countries", []))
                    self.info["country"] = country

                    self.info["releaseDate"] = str(self.tmdbdetails.get("release_date", ""))

                    poster_path = self.tmdbdetails.get("poster_path", "")
                    size = "w300" if screenwidth.width() <= 1280 else "w400"
                    self.info["cover_big"] = "http://image.tmdb.org/t/p/{}/{}".format(size, poster_path) if poster_path else ""

                    self.info["description"] = str(self.tmdbdetails.get("overview", ""))

                    rating_str = self.tmdbdetails.get("vote_average", "")
                    self.info["rating"] = str(rating_str)

                    if rating_str and rating_str != 0:
                        try:
                            rating = float(rating_str)
                            rounded_rating = round(rating, 1)
                            self.info["rating"] = "{:.1f}".format(rounded_rating)
                        except ValueError:
                            self.info["rating"] = str(rating_str)

                    genre = " / ".join(str(genreitem["name"]) for genreitem in self.tmdbdetails.get("genres", []))
                    self.info["genre"] = genre

                    cast = ", ".join(actor["name"] for actor in self.tmdbdetails.get("credits", {}).get("cast", [])[:5])
                    self.info["cast"] = cast

                    director = ", ".join(actor["name"] for actor in self.tmdbdetails.get("credits", {}).get("crew", []) if actor.get("job") == "Director") or ""

                    self.info["director"] = director

                    if cfg.channelcovers.value:
                        self.downloadImage()
                    self.displayTMDB()

    def displayTMDB(self):
        # print("*** displayTMDB ***")

        current_item = self["main_list"].getCurrent()

        if current_item and self.level == 2:
            stream_url = current_item[3]

            try:
                self["vod_video_type"].setText(stream_url.split(".")[-1])
            except Exception:
                pass

            if self.info:
                info = self.info

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

            if self.chosen_category in ("favourites", "recents"):
                self["key_menu"].setText("")

            if self.chosen_category == "recents":
                self["key_blue"].setText(_("Delete"))

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

            if self.info:  # tmbdb
                desc_image = str(self.info.get("cover_big")).strip() or str(self.info.get("movie_image")).strip() or ""

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
        if ptr is not None and self.level == 2:
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
        sort_functions = {
            _("Sort: A-Z"): lambda x: x[1].lower(),
            _("Sort: Z-A"): lambda x: x[1].lower(),
            _("Sort: Added"): lambda x: x[4],
            _("Sort: Year"): lambda x: x[9],
            _("Sort: Original"): lambda x: x[0],  # Use original order
        }

        if self.level == 1:
            activelist = self.list1[:]
            activeoriginal = glob.originalChannelList1[:]
        else:
            activelist = self.list2[:]
            activeoriginal = glob.originalChannelList2[:]

        print("*** self.list2 ***", self.list2)

        if self.level == 1:
            sortlist = [_("Sort: A-Z"), _("Sort: Z-A"), _("Sort: Original")]
        else:
            sortlist = [_("Sort: A-Z"), _("Sort: Z-A"), _("Sort: Added"), _("Sort: Year"), _("Sort: Original")]

        self.sortindex = sortlist.index(self.sortText)

        if self["main_list"].getCurrent():
            self["main_list"].setIndex(0)

        current_sort = self["key_yellow"].getText()

        if current_sort == _("Sort: Original"):
            activelist = activeoriginal
        else:
            activelist.sort(key=sort_functions.get(current_sort, lambda x: x))

        nextSortType = islice(cycle(sortlist), self.sortindex + 1, None)
        self.sortText = str(next(nextSortType))

        self["key_yellow"].setText(self.sortText)
        glob.nextlist[-1]["sort"] = self["key_yellow"].getText()

        if self.level == 1:
            self.list1 = activelist
        else:
            self.list2 = activelist

        self.buildLists()

    def search(self, result=None):
        # print("*** search ***")
        if not self["key_blue"].getText():
            return

        current_filter = self["key_blue"].getText()

        if current_filter == _("Reset Search"):
            self.resetSearch()

        elif current_filter == _("Delete"):
            self.deleteRecent()

        else:
            self.session.openWithCallback(self.filterChannels, VirtualKeyBoard, title=_("Filter this category..."), text=self.searchString)

    def deleteRecent(self):
        # print("*** deleterecent ***")
        current_item = self["main_list"].getCurrent()
        if current_item:
            current_index = self["main_list"].getIndex()

            with open(playlists_json, "r") as f:
                try:
                    self.playlists_all = json.load(f)
                except Exception:
                    os.remove(playlists_json)

            del glob.active_playlist["player_info"]['vodrecents'][current_index]
            self.hideVod()

            if self.playlists_all:
                for idx, playlists in enumerate(self.playlists_all):
                    if playlists["playlist_info"]["domain"] == glob.active_playlist["playlist_info"]["domain"] and playlists["playlist_info"]["username"] == glob.active_playlist["playlist_info"]["username"] and playlists["playlist_info"]["password"] == glob.active_playlist["playlist_info"]["password"]:
                        self.playlists_all[idx] = glob.active_playlist
                        break

            with open(playlists_json, "w") as f:
                json.dump(self.playlists_all, f)

            del self.list2[current_index]
            self.buildLists()

    def filterChannels(self, result=None):
        # print("*** filterChannels ***")

        activelist = []

        if result:
            self.filterresult = result
            glob.nextlist[-1]["filter"] = self.filterresult

            activelist = self.list1 if self.level == 1 else self.list2

            self.searchString = result
            activelist = [channel for channel in activelist if str(result).lower() in str(channel[1]).lower()]

            if not activelist:
                self.searchString = ""
                self.session.openWithCallback(self.search, MessageBox, _("No results found."), type=MessageBox.TYPE_ERROR, timeout=5)
            else:
                if self.level == 1:
                    self.list1 = activelist
                else:
                    self.list2 = activelist

                self["key_blue"].setText(_("Reset Search"))
                self["key_yellow"].setText("")

                self.hideVod()
                self.buildLists()

    def resetSearch(self):
        # print("*** resetSearch ***")
        self["key_blue"].setText(_("Search"))
        self["key_yellow"].setText(self.sortText)

        if self.level == 1:
            activelist = glob.originalChannelList1[:]
            self.list1 = activelist
        else:
            activelist = glob.originalChannelList2[:]
            self.list2 = activelist

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

                    next_url = "{0}&action=get_vod_streams&category_id={1}".format(self.player_api, category_id)
                    self.chosen_category = ""

                    if category_id == "0":
                        next_url = "{0}&action=get_vod_streams".format(self.player_api)
                        self.chosen_category = "all"

                    elif category_id == "-1":
                        self.chosen_category = "favourites"

                    elif category_id == "-2":
                        self.chosen_category = "recents"

                    self.level += 1
                    self["main_list"].setIndex(0)
                    self["category_actions"].setEnabled(False)
                    self["channel_actions"].setEnabled(True)
                    self["key_yellow"].setText(_("Sort: A-Z"))

                    glob.nextlist.append({"next_url": next_url, "index": 0, "level": self.level, "sort": self["key_yellow"].getText(), "filter": ""})

                    self.createSetup()
                else:
                    self.createSetup()

            else:
                if self.list2:
                    streamtype = glob.active_playlist["player_info"]["vodtype"]
                    next_url = self["main_list"].getCurrent()[3]
                    stream_id = self["main_list"].getCurrent()[4]

                    try:
                        direct_source = self["main_list"].getCurrent()[10]
                    except Exception as e:
                        print(e)
                        direct_source = ""

                    self.reference = eServiceReference(int(streamtype), 0, next_url)

                    if glob.active_playlist["player_info"]["directsource"] == "Direct Source" and direct_source:
                        self.reference = eServiceReference(int(streamtype), 0, direct_source)
                    self.reference.setName(glob.currentchannellist[glob.currentchannellistindex][0])
                    self.session.openWithCallback(self.setIndex, vodplayer.XStreamity_VodPlayer, str(next_url), str(streamtype), str(direct_source), stream_id)

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
            current_list = self.prelist + self.list1 if self.level == 1 else self.list2
            if self.level == 1 or (self.level == 2 and self.chosen_category not in ["favourites", "recents"]):
                self.session.openWithCallback(self.createSetup, hidden.XStreamity_HiddenCategories, "vod", current_list, self.level)

    def clearWatched(self):
        if self.level == 2:
            current_id = str(self["main_list"].getCurrent()[4])
            watched_list = glob.active_playlist["player_info"].get("vodwatched", [])
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

    def favourite(self):
        # print("*** favourite ***")
        if not self["main_list"].getCurrent():
            return

        currentindex = self["main_list"].getIndex()
        favExists = False
        favStream_id = ""

        for fav in glob.active_playlist["player_info"]["vodfavourites"]:
            if self["main_list"].getCurrent()[4] == fav["stream_id"]:
                favExists = True
                favStream_id = fav["stream_id"]
                break

        self.list2[currentindex][7] = not self.list2[currentindex][7]

        if favExists:
            glob.active_playlist["player_info"]["vodfavourites"] = [x for x in glob.active_playlist["player_info"]["vodfavourites"] if str(x["stream_id"]) != str(favStream_id)]
        else:
            # index = 0
            # name = 1
            # stream_id = 2
            # stream_icon = 3
            # added = 4
            # rating = 5
            # next_url = 6
            # favourite = 7
            # container_extension = 8

            newfavourite = {
                "name": self.list2[currentindex][1],
                "stream_id": self.list2[currentindex][2],
                "stream_icon": self.list2[currentindex][3],
                "added": self.list2[currentindex][4],
                "rating": self.list2[currentindex][5],
                "container_extension": self.list2[currentindex][8]
            }

            glob.active_playlist["player_info"]["vodfavourites"].insert(0, newfavourite)
            self.hideVod()

        with open(playlists_json, "r") as f:
            try:
                self.playlists_all = json.load(f)
            except Exception as e:
                print("Error loading playlists JSON:", e)
                os.remove(playlists_json)

        if self.playlists_all:
            for playlists in self.playlists_all:
                if (playlists["playlist_info"]["domain"] == glob.active_playlist["playlist_info"]["domain"]
                        and playlists["playlist_info"]["username"] == glob.active_playlist["playlist_info"]["username"]
                        and playlists["playlist_info"]["password"] == glob.active_playlist["playlist_info"]["password"]):
                    playlists.update(glob.active_playlist)
                    break

        with open(playlists_json, "w") as f:
            json.dump(self.playlists_all, f)

        if self.chosen_category == "favourites":
            del self.list2[currentindex]

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
        # load x-downloadlist.json file

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
                downloads_all.append([_("Movie"), title, stream_url, "Not Started", 0, 0])

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

    def imdb(self):
        # print("*** imdb ***")
        if self["main_list"].getCurrent():
            if self.level == 2:
                self.openIMDb()

    def openIMDb(self):
        # print("*** openIMDb ***")
        try:
            from Plugins.Extensions.IMDb.plugin import IMDB
            try:
                name = str(self["main_list"].getCurrent()[0])
            except:
                name = ""
            self.session.open(IMDB, name, False)
        except ImportError:
            self.session.open(MessageBox, _("The IMDb plugin is not installed!\nPlease install it."), type=MessageBox.TYPE_INFO, timeout=10)

    def check(self, token):
        result = base64.b64decode(token)
        result = zlib.decompress(base64.b64decode(result))
        result = base64.b64decode(result).decode()
        return result


def buildCategoryList(index, title, category_id, hidden):
    png = LoadPixmap(os.path.join(common_path, "more.png"))
    return (title, png, index, category_id, hidden)


def buildVodStreamList(index, title, stream_id, stream_icon, added, rating, next_url, favourite, container_extension, hidden, direct_source):
    png = LoadPixmap(os.path.join(common_path, "play.png"))
    if favourite:
        png = LoadPixmap(os.path.join(common_path, "favourite.png"))
    for channel in glob.active_playlist["player_info"]["vodwatched"]:
        if int(stream_id) == int(channel):
            png = LoadPixmap(os.path.join(common_path, "watched.png"))

    return (title, png, index, next_url, stream_id, stream_icon, added, rating, container_extension, hidden, direct_source)
