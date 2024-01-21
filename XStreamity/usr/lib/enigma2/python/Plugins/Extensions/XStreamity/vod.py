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
        glob.categoryname = "vod"

        self.skin_path = os.path.join(skin_directory, cfg.skin.getValue())
        skin = os.path.join(self.skin_path, "vod_categories.xml")
        if os.path.exists("/var/lib/dpkg/status"):
            skin = os.path.join(self.skin_path, "DreamOS/vod_categories.xml")

        with codecs.open(skin, "r", encoding="utf-8") as f:
            self.skin = f.read()

        self.setup_title = (_("Vod Categories"))
        self.main_title = (_("Vod"))
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

        self.favourites_category = False
        self.recents_category = False
        self.pin = False
        self.info = ""
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
            "red": self.playStream,
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
        currentCategoryList = glob.current_playlist["data"]["vod_categories"]
        currentHidden = glob.current_playlist["player_info"]["vodhidden"]

        hidden = False
        hiddenfavourites = False
        hiddenrecent = False

        if "0" in currentHidden:
            hidden = True

        if "-1" in currentHidden:
            hiddenfavourites = True

        if "-2" in currentHidden:
            hiddenrecent = True

        self.prelist.append([index, _("FAVOURITES"), "-1", hiddenfavourites])
        index += 1
        self.prelist.append([index, _("RECENTLY WATCHED"), "-2", hiddenrecent])
        index += 1
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

    def getVod(self):
        # print("*** getVod ***")
        # print("*** url ***", glob.nextlist[-1]["next_url"])

        self["key_epg"].setText("IMDB")
        response = self.downloadApiData(glob.nextlist[-1]["next_url"])

        if self.favourites_category:
            response = glob.current_playlist["player_info"]["vodfavourites"]

        elif self.recents_category:
            response = glob.current_playlist["player_info"]["vodrecents"]

        index = 0
        self.list2 = []
        currentChannelList = response
        if currentChannelList:
            for item in currentChannelList:
                name = ""
                stream_id = ""
                stream_icon = ""
                added = ""
                container_extension = "mp4"
                rating = ""
                year = ""
                favourite = False
                hidden = False
                direct_source = ""

                if "name" in item and item["name"]:
                    name = item["name"]

                    # restyle bouquet markers
                    if "stream_type" in item and item["stream_type"] and item["stream_type"] != "movie":
                        pattern = re.compile(r"[^\w\s()\[\]]", re.U)
                        name = re.sub(r"_", "", re.sub(pattern, "", name))
                        name = "** " + str(name) + " **"

                if "stream_id" in item and item["stream_id"]:
                    stream_id = item["stream_id"]

                    if str(stream_id) in glob.current_playlist["player_info"]["vodstreamshidden"]:
                        hidden = True
                else:
                    continue

                if "stream_icon" in item and item["stream_icon"]:
                    if item["stream_icon"].startswith("http"):
                        stream_icon = item["stream_icon"]

                        if stream_icon.startswith("https://image.tmdb.org/t/p/") or stream_icon.startswith("http://image.tmdb.org/t/p/"):
                            dimensions = stream_icon.partition("/p/")[2].partition("/")[0]
                            if screenwidth.width() <= 1280:
                                stream_icon = stream_icon.replace(dimensions, "w300")
                            else:
                                stream_icon = stream_icon.replace(dimensions, "w400")

                if "added" in item and item["added"]:
                    added = item["added"]

                if "container_extension" in item and item["container_extension"]:
                    container_extension = item["container_extension"]

                if "rating" in item and item["rating"]:
                    rating = item["rating"]

                if "year" in item and item["year"]:
                    year = item["year"]

                if "direct_source" in item and item["direct_source"]:
                    direct_source = item["direct_source"]

                next_url = "%s/movie/%s/%s/%s.%s" % (str(self.host), str(self.username), str(self.password), str(stream_id), str(container_extension))

                if "vodfavourites" in glob.current_playlist["player_info"]:
                    for fav in glob.current_playlist["player_info"]["vodfavourites"]:
                        if str(stream_id) == str(fav["stream_id"]):
                            favourite = True
                            break
                else:
                    glob.current_playlist["player_info"]["vodfavourites"] = []

                self.list2.append([index, str(name), str(stream_id), str(stream_icon), str(added), str(rating), str(next_url), favourite, container_extension, year, hidden, str(direct_source)])
                index += 1

            glob.originalChannelList2 = self.list2[:]

    def downloadApiData(self, url):
        # print("**** downloadApiData ****")
        content = ""
        retries = Retry(total=3, backoff_factor=1)
        adapter = HTTPAdapter(max_retries=retries)
        http = requests.Session()
        http.mount("http://", adapter)
        http.mount("https://", adapter)
        try:
            r = http.get(url, headers=hdr, timeout=(10, 30), verify=False)
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
                if glob.nextlist[-1]["index"] != 0:
                    self["main_list"].setIndex(glob.nextlist[-1]["index"])

    def buildVod(self):
        # print("*** buildVod ***")
        self.main_list = []

        if self.favourites_category:
            self.main_list = [buildVodStreamList(x[0], x[1], x[2], x[3], x[4], x[5], x[6], x[7], x[8], x[10], x[11]) for x in self.list2 if x[7] is True]
        else:
            self.main_list = [buildVodStreamList(x[0], x[1], x[2], x[3], x[4], x[5], x[6], x[7], x[8], x[10], x[11]) for x in self.list2 if x[10] is False]
        self["main_list"].setList(self.main_list)
        self.showVod()

        if self["main_list"].getCurrent():
            if glob.nextlist[-1]["index"] != 0:
                self["main_list"].setIndex(glob.nextlist[-1]["index"])

    def downloadVodData(self):
        # print("*** downloadVodData ***")
        if self["main_list"].getCurrent():
            stream_id = self["main_list"].getCurrent()[4]
            url = str(glob.current_playlist["playlist_info"]["player_api"]) + "&action=get_vod_info&vod_id=" + str(stream_id)

            self.info = ""

            retries = Retry(total=1, backoff_factor=1)
            adapter = HTTPAdapter(max_retries=retries)
            http = requests.Session()
            http.mount("http://", adapter)
            http.mount("https://", adapter)
            content = ""
            try:
                r = http.get(url, headers=hdr, timeout=(10, 60), verify=False)
                r.raise_for_status()
                if r.status_code == requests.codes.ok:
                    try:
                        content = r.json()
                    except Exception as e:
                        print(e)

                if content and "info" in content and content["info"]:
                    self.info = content["info"]

                    if "name" not in self.info:
                        if "movie_data" in content and content["movie_data"]:
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
                if "name" in self.info and self.info["name"]:
                    title = self.info["name"]
                elif "o_name" in self.info and self.info["o_name"]:
                    title = self.info["o_name"]

                if "releasedate" in self.info and self.info["releasedate"]:
                    year = self.info["releasedate"]
                    year = year[0:4]

                if "tmdb_id" in self.info and self.info["tmdb_id"]:
                    if str(self.info["tmdb_id"])[:1].isdigit():
                        self.getTMDBDetails(self.info["tmdb_id"])
                        return
                    else:
                        self.isIMDB = True

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

        if self.isIMDB is False:
            searchurl = 'http://api.themoviedb.org/3/search/movie?api_key=' + str(self.check(self.token)) + '&query=' + str(searchtitle)
            if year:
                searchurl = 'http://api.themoviedb.org/3/search/movie?api_key=' + str(self.check(self.token)) + '&primary_release_year=' + str(year) + '&query=' + str(searchtitle)
        else:
            searchurl = 'http://api.themoviedb.org/3/find/' + str(self.info["tmdb_id"]) + '?api_key=' + str(self.check(self.token)) + '&external_source=imdb_id'

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

    def processTMDB(self, result=None):
        # print("*** processTMDB ***")
        IMDB = self.isIMDB
        resultid = ""
        with codecs.open(str(dir_tmp) + "search.txt", "r", encoding="utf-8") as f:
            response = f.read()

        if response != "":
            try:
                self.searchresult = json.loads(response)
                if IMDB is False:
                    if "results" in self.searchresult and self.searchresult["results"]:
                        if "id" in self.searchresult["results"][0]:
                            resultid = self.searchresult["results"][0]["id"]
                else:
                    if "movie_results" in self.searchresult and self.searchresult["movie_results"]:
                        if "id" in self.searchresult["movie_results"][0]:
                            resultid = self.searchresult["movie_results"][0]["id"]

                if not resultid:
                    # print("*** resultid not found **")
                    self.displayTMDB()
                    if cfg.channelcovers.value is True:
                        self.info = ""
                        self.downloadImage()
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

        detailsurl = "http://api.themoviedb.org/3/movie/" + str(resultid) + "?api_key=" + str(self.check(self.token)) + "&append_to_response=credits" + languagestr

        if pythonVer == 3:
            detailsurl = detailsurl.encode()

        filepath = os.path.join(dir_tmp, "tmdb.txt")
        try:
            downloadPage(detailsurl, filepath, timeout=10).addCallback(self.processTMDBDetails).addErrback(self.failed)
        except Exception as e:
            print(("download TMDB details error %s" % e))

    def processTMDBDetails(self, result=None):
        # print("*** processTMDBDetails ***")
        valid = False
        response = ""
        self.info = {}
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
                if "title" in self.tmdbdetails and self.tmdbdetails["title"]:
                    self.info["name"] = str(self.tmdbdetails["title"])

                if "original_title" in self.tmdbdetails and self.tmdbdetails["original_title"]:
                    self.info["o_name"] = str(self.tmdbdetails["original_title"])

                if "runtime" in self.tmdbdetails and self.tmdbdetails["runtime"] and self.tmdbdetails["runtime"] != 0:
                    self.info["duration"] = str(timedelta(minutes=self.tmdbdetails["runtime"]))

                if "production_countries" in self.tmdbdetails and self.tmdbdetails["production_countries"]:
                    country = []
                    for pcountry in self.tmdbdetails["production_countries"]:
                        country.append(str(pcountry["name"]))
                    country = ", ".join(map(str, country))
                    self.info["country"] = country

                if "release_date" in self.tmdbdetails and self.tmdbdetails["release_date"]:
                    self.info["releaseDate"] = str(self.tmdbdetails["release_date"])

                if "poster_path" in self.tmdbdetails and self.tmdbdetails["poster_path"]:
                    if screenwidth.width() <= 1280:
                        self.info["cover_big"] = "http://image.tmdb.org/t/p/w300" + str(self.tmdbdetails["poster_path"])
                    else:
                        self.info["cover_big"] = "http://image.tmdb.org/t/p/w400" + str(self.tmdbdetails["poster_path"])

                if "overview" in self.tmdbdetails and self.tmdbdetails["overview"]:
                    self.info["description"] = str(self.tmdbdetails["overview"])

                if "vote_average" in self.tmdbdetails and self.tmdbdetails["vote_average"] and self.tmdbdetails["vote_average"] != 0:
                    self.info["rating"] = str(self.tmdbdetails["vote_average"])

                if "genres" in self.tmdbdetails and self.tmdbdetails["genres"]:
                    genre = []
                    for genreitem in self.tmdbdetails["genres"]:
                        genre.append(str(genreitem["name"]))
                    genre = " / ".join(map(str, genre))
                    self.info["genre"] = genre

                if "credits" in self.tmdbdetails and self.tmdbdetails["credits"]:
                    if "cast" in self.tmdbdetails["credits"] and self.tmdbdetails["credits"]["cast"]:
                        cast = []
                        for actor in self.tmdbdetails["credits"]["cast"]:
                            if "character" in actor and "name" in actor:
                                cast.append(str(actor["name"]))
                        cast = ", ".join(map(str, cast[:5]))
                        self.info["cast"] = cast

                    if "crew" in self.tmdbdetails["credits"] and self.tmdbdetails["credits"]["crew"]:
                        directortext = False
                        for actor in self.tmdbdetails["credits"]["crew"]:
                            if "job" in actor and actor["job"] == "Director":
                                director.append(str(actor["name"]))
                                directortext = True
                        if directortext:
                            director = ", ".join(map(str, director))
                            self.info["director"] = director

                if cfg.channelcovers.value is True:
                    self.downloadImage()
                self.displayTMDB()

    def displayTMDB(self):
        # print("*** displayTMDB ***")
        if self["main_list"].getCurrent() and self.level == 2:

            stream_url = self["main_list"].getCurrent()[3]

            try:
                self["vod_video_type"].setText(stream_url.split(".")[-1])
            except:
                pass

            if self.info:
                if "name" in self.info:
                    self["x_title"].setText(str(self.info["name"]).strip())
                elif "o_name" in self.info:
                    self["x_title"].setText(str(self.info["o_name"]).strip())

                if "description" in self.info:
                    self["x_description"].setText(str(self.info["description"]).strip())
                elif "plot" in self.info:
                    self["x_description"].setText(str(self.info["plot"]).strip())

                if "duration" in self.info:
                    self["vod_duration"].setText(str(self.info["duration"]).strip())

                if "genre" in self.info:
                    self["vod_genre"].setText(str(self.info["genre"]).strip())

                if "rating" in self.info:
                    self["vod_rating"].setText(str(self.info["rating"]).strip())

                if "country" in self.info:
                    self["vod_country"].setText(str(self.info["country"]).strip())

                if "releaseDate" in self.info and self.info["releaseDate"]:
                    try:
                        self["vod_release_date"].setText(datetime.strptime(self.info["releaseDate"], "%Y-%m-%d").strftime("%d-%m-%Y"))
                    except:
                        pass
                elif "release_date" in self.info and self.info["release_date"]:
                    try:
                        self["vod_release_date"].setText(datetime.strptime(self.info["release_date"], "%Y-%m-%d").strftime("%d-%m-%Y"))
                    except:
                        pass
                elif "releasedate" in self.info and self.info["releasedate"]:
                    try:
                        self["vod_release_date"].setText(datetime.strptime(self.info["releasedate"], "%Y-%m-%d").strftime("%d-%m-%Y"))
                    except:
                        pass

                if "director" in self.info:
                    self["vod_director"].setText(str(self.info["director"]).strip())

                if "cast" in self.info:
                    self["vod_cast"].setText(str(self.info["cast"]).strip())
                elif "actors" in self.info:
                    self["vod_cast"].setText(str(self.info["actors"]).strip())

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

            if self.favourites_category or self.recents_category:
                self["key_menu"].setText("")

            if self.recents_category:
                self["key_blue"].setText(_("Delete"))

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

            if self.info:  # tmbdb
                if "cover_big" in self.info and self.info["cover_big"] and self.info["cover_big"] != "null":
                    desc_image = str(self.info["cover_big"]).strip()
                elif "movie_image" in self.info and self.info["movie_image"] and self.info["movie_image"] != "null":
                    desc_image = str(self.info["movie_image"]).strip()

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
        # print("*** sort ***")
        sortlist = []

        if self.level == 1:
            activelist = self.list1[:]
            activeoriginal = glob.originalChannelList1[:]
        else:
            activelist = self.list2[:]
            activeoriginal = glob.originalChannelList2[:]

        if self.level == 1:
            sortlist = [(_("Sort: A-Z")), (_("Sort: Z-A")), (_("Sort: Original"))]
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
            activelist.sort(key=lambda x: x[4], reverse=True)

        elif current_sort == (_("Sort: Year")):
            activelist.sort(key=lambda x: x[9], reverse=True)

        elif current_sort == (_("Sort: Original")):
            activelist = activeoriginal

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

        if current_filter == (_("Reset Search")):
            self.resetSearch()

        elif current_filter == (_("Delete")):
            self.deleteRecent()

        else:
            self.session.openWithCallback(self.filterChannels, VirtualKeyBoard, title=_("Filter this category..."), text=self.searchString)

    def deleteRecent(self):
        if self["main_list"].getCurrent():
            currentindex = self["main_list"].getIndex()

            with open(playlists_json, "r") as f:
                try:
                    self.playlists_all = json.load(f)
                except:
                    os.remove(playlists_json)

            del glob.current_playlist["player_info"]['vodrecents'][currentindex]
            self.hideVod()

            if self.playlists_all:
                x = 0
                for playlists in self.playlists_all:
                    if playlists["playlist_info"]["domain"] == glob.current_playlist["playlist_info"]["domain"] and playlists["playlist_info"]["username"] == glob.current_playlist["playlist_info"]["username"] and playlists["playlist_info"]["password"] == glob.current_playlist["playlist_info"]["password"]:
                        self.playlists_all[x] = glob.current_playlist
                        break
                    x += 1
            with open(playlists_json, "w") as f:
                json.dump(self.playlists_all, f)

            del self.list2[currentindex]
            self.buildLists()

    def filterChannels(self, result=None):
        # print("*** filterChannels ***")

        activelist = []

        if result:
            self.filterresult = result
            glob.nextlist[-1]["filter"] = self.filterresult

            if self.level == 1:
                activelist = self.list1[:]
            else:
                activelist = self.list2[:]

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
            activeoriginal = glob.originalChannelList1[:]
        else:
            activeoriginal = glob.originalChannelList2[:]

        if self.level == 1:
            self.list1 = activeoriginal
        else:
            self.list2 = activeoriginal

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
                        next_url = str(self.player_api) + "&action=get_vod_streams"
                    else:
                        next_url = str(self.player_api) + "&action=get_vod_streams&category_id=" + str(category_id)

                    if category_id == "-1":
                        self.favourites_category = True
                        self.recents_category = False

                    elif category_id == "-2":
                        self.recents_category = True
                        self.favourites_category = False
                    else:
                        self.favourites_category = False
                        self.recents_category = False

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
                    streamtype = glob.current_playlist["player_info"]["vodtype"]
                    next_url = self["main_list"].getCurrent()[3]
                    try:
                        direct_source = self["main_list"].getCurrent()[10]
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
                        print("********* vod crash *********", e)
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
                    self.session.openWithCallback(self.createSetup, hidden.XStreamity_HiddenCategories, "vod", self.prelist + self.list1, self.level)
                elif self.level == 2 and not self.favourites_category and not self.recents_category:
                    self.session.openWithCallback(self.createSetup, hidden.XStreamity_HiddenCategories, "vod", self.list2, self.level)

    def clearWatched(self):
        if self.level == 2:
            for watched in glob.current_playlist["player_info"]["vodwatched"]:
                if int(self["main_list"].getCurrent()[4]) == int(watched):
                    glob.current_playlist["player_info"]["vodwatched"].remove(watched)
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

    def favourite(self):
        # print("**** favourite ***")
        if self["main_list"].getCurrent():
            currentindex = self["main_list"].getIndex()
            favExists = False
            favStream_id = None

            for fav in glob.current_playlist["player_info"]["vodfavourites"]:
                if self["main_list"].getCurrent()[4] == fav["stream_id"]:
                    favExists = True
                    favStream_id = fav["stream_id"]
                    break

            self.list2[currentindex][7] = not self.list2[currentindex][7]

            if favExists:
                glob.current_playlist["player_info"]["vodfavourites"][:] = [x for x in glob.current_playlist["player_info"]["vodfavourites"] if str(x["stream_id"]) != str(favStream_id)]
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

                glob.current_playlist["player_info"]["vodfavourites"].insert(0, newfavourite)
                self.hideVod()

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

            if self.favourites_category:
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
    for channel in glob.current_playlist["player_info"]["vodwatched"]:
        if int(stream_id) == int(channel):
            png = LoadPixmap(os.path.join(common_path, "watched.png"))

    return (title, png, index, next_url, stream_id, stream_icon, added, rating, container_extension, hidden, direct_source)
