#!/usr/bin/python
# -*- coding: utf-8 -*-

from . import _
from . import streamplayer
from . import xstreamity_globals as glob

from .plugin import skin_path, screenwidth, hdr, cfg, common_path, dir_tmp, playlists_json, downloads_json, pythonVer
from .xStaticText import StaticText

from Components.AVSwitch import AVSwitch
from Components.ActionMap import ActionMap
from Components.Pixmap import Pixmap
from Components.ProgressBar import ProgressBar
from Components.Sources.List import List
from Components.config import ConfigClock, NoSave, ConfigText
from PIL import Image, ImageChops, ImageFile, PngImagePlugin
from RecordTimer import RecordTimerEntry
from Screens.MessageBox import MessageBox
from Screens.Screen import Screen
from Screens.VirtualKeyBoard import VirtualKeyBoard
from ServiceReference import ServiceReference
from Tools.LoadPixmap import LoadPixmap
from collections import OrderedDict
from datetime import datetime, timedelta
from enigma import eTimer, eServiceReference, eEPGCache, ePicLoad
from requests.adapters import HTTPAdapter
from twisted.web.client import downloadPage
from itertools import cycle, islice

try:
    from urlparse import urlparse
except:
    from urllib.parse import urlparse

import base64
import calendar
import codecs
import json
import math
import os
import re
import requests
import sys
import tempfile
import time
import zlib

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


# png hack
def mycall(self, cid, pos, length):
    if cid.decode("ascii") == "tRNS":
        return self.chunk_TRNS(pos, length)
    else:
        return getattr(self, "chunk_" + cid.decode("ascii"))(pos, length)


def mychunk_TRNS(self, pos, length):
    i16 = PngImagePlugin.i16
    _simple_palette = re.compile(b"^\xff*\x00\xff*$")
    s = ImageFile._safe_read(self.fp, length)
    if self.im_mode == "P":
        if _simple_palette.match(s):
            i = s.find(b"\0")
            if i >= 0:
                self.im_info["transparency"] = i
        else:
            self.im_info["transparency"] = s
    elif self.im_mode in ("1", "L", "I"):
        self.im_info["transparency"] = i16(s)
    elif self.im_mode == "RGB":
        self.im_info["transparency"] = i16(s), i16(s, 2), i16(s, 4)
    return s


if pythonVer != 2:
    PngImagePlugin.ChunkStream.call = mycall
    PngImagePlugin.PngStream.chunk_TRNS = mychunk_TRNS

_initialized = 0


def _mypreinit():
    global _initialized
    if _initialized >= 1:
        return
    try:
        from . import MyPngImagePlugin
        assert MyPngImagePlugin
    except ImportError:
        pass

    _initialized = 1


Image.preinit = _mypreinit

epgimporter = False
if os.path.isdir("/usr/lib/enigma2/python/Plugins/Extensions/EPGImport"):
    epgimporter = True


# epg times
def quickptime(str):
    return time.struct_time((int(str[0:4]), int(str[4:6]), int(str[6:8]), int(str[8:10]), int(str[10:12]), 0, 1, -1, 0))


def get_time_utc(timestring, fdateparse):
    try:
        values = timestring.split(" ")
        tm = fdateparse(values[0])
        timegm = calendar.timegm(tm)
        timegm -= (3600 * int(values[1]) / 100)
        return timegm
    except Exception as e:
        print("[XMLTVConverter] get_time_utc error:", e)
        return 0


class XStreamity_Categories(Screen):
    def __init__(self, session, categoryname):
        Screen.__init__(self, session)
        self.session = session
        self.categoryname = categoryname

        skin = skin_path + "categories.xml"
        if os.path.exists("/var/lib/dpkg/status"):
            skin = skin_path + "DreamOS/categories.xml"

        with codecs.open(skin, "r", encoding="utf-8") as f:
            self.skin = f.read()

        self.setup_title = ""

        # skin top section variables
        self.main_title = ""
        self["main_title"] = StaticText(self.main_title)

        self.main_list = []  # displayed list
        self["main_list"] = List(self.main_list, enableWrapAround=True)

        self["x_title"] = StaticText()
        self["x_description"] = StaticText()

        self["picon"] = Pixmap()
        self["picon"].hide()

        self["progress"] = ProgressBar()
        self["progress"].hide()

        # skin epg variables
        self["epg_bg"] = Pixmap()
        self["epg_bg"].hide()

        self.epglist = []
        self["epg_list"] = List(self.epglist, enableWrapAround=True)

        # skin short epg variables
        self.epgshortlist = []
        self["epg_short_list"] = List(self.epgshortlist, enableWrapAround=True)
        self["epg_short_list"].onSelectionChanged.append(self.displayShortEPG)

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

        # xmltv variables
        self.xmltvdownloaded = False
        self.xmltv_channel_list = []

        # pagination variables
        self["page"] = StaticText("")
        self["listposition"] = StaticText("")
        self.page = 0
        self.pageall = 0
        self.position = 0
        self.positionall = 0
        self.itemsperpage = 10

        self.lastviewed_url = ""
        self.lastviewed_id = ""
        self.lastviewed_index = 0

        self.searchString = ""
        self.filterresult = ""

        self.showingshortEPG = False
        self.favourites_category = False
        self.recents_category = False
        self.pin = False
        self.isStream = False
        self.info = ""
        self.storedtitle = ""
        self.storedseason = ""
        self.sortindex = 0
        self.sortText = (_("Sort: A-Z"))

        self.storedcover = ""

        self.epgtimeshift = 0

        self.level = 1

        self.selectedlist = self["main_list"]

        self.protocol = glob.current_playlist["playlist_info"]["protocol"]
        self.domain = glob.current_playlist["playlist_info"]["domain"]
        self.host = glob.current_playlist["playlist_info"]["host"]
        self.livetype = glob.current_playlist["player_info"]["livetype"]
        self.vodtype = glob.current_playlist["player_info"]["vodtype"]
        self.username = glob.current_playlist["playlist_info"]["username"]
        self.password = glob.current_playlist["playlist_info"]["password"]
        self.output = glob.current_playlist["playlist_info"]["output"]
        self.name = glob.current_playlist["playlist_info"]["name"]
        self.xmltv = glob.current_playlist["playlist_info"]["xmltv_api"] + str("&next_days=2")

        self.liveStreamsData = []
        self.liveStreamsUrl = str(glob.current_playlist["playlist_info"]["player_api"]) + "&action=get_live_streams"
        self.simpledatatable = str(glob.current_playlist["playlist_info"]["player_api"]) + "&action=get_simple_data_table&stream_id="
        self.listType = ""

        self.token = "ZUp6enk4cko4ZzBKTlBMTFNxN3djd25MOHEzeU5Zak1Bdkd6S3lPTmdqSjhxeUxMSTBNOFRhUGNBMjBCVmxBTzlBPT0K"

        # xmltv folders/files
        # self.epgfolder = str(dir_etc) + "epg/" + str(self.domain)

        epglocation = str(cfg.epglocation.value)
        if not epglocation.endswith("/"):
            epglocation = epglocation + str("/")

        self.epgfolder = epglocation + str(self.domain)
        self.epgjsonfile = str(self.epgfolder) + "/" + str("epg.json")

        self.timerVOD = eTimer()
        self.timerVODBusy = eTimer()

        # buttons / keys
        self["key_red"] = StaticText(_("Back"))
        self["key_green"] = StaticText(_("OK"))
        self["key_yellow"] = StaticText(self.sortText)
        self["key_blue"] = StaticText(_("Search"))
        self["key_epg"] = StaticText("")
        self["key_menu"] = StaticText("")

        if self.categoryname != "catchup":
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

        if self.categoryname == "live":
            self.setup_title = (_("Live Categories"))
            self.main_title = (_("Live Streams"))
            nexturl = str(glob.current_playlist["playlist_info"]["player_api"]) + "&action=get_live_categories"

            self["channel_actions"] = ActionMap(["XStreamityActions"], {
                "cancel": self.back,
                "red": self.playStream,
                "ok": self.parentalCheck,
                "green": self.parentalCheck,
                "yellow": self.sort,
                "blue": self.search,
                "epg": self.nownext,
                "info": self.nownext,
                "text": self.nownext,
                "epg_long": self.shortEPG,
                "info_long": self.shortEPG,
                "text_long": self.shortEPG,
                "left": self.pageUp,
                "right": self.pageDown,
                "up": self.goUp,
                "down": self.goDown,
                "channelUp": self.pageUp,
                "channelDown": self.pageDown,
                "rec": self.downloadStream,
                "5": self.downloadStream,
                "tv": self.favourite,
                "stop": self.favourite,
                "0": self.reset,
                "menu": self.showHiddenList,
                "7": self.epgminus,
                "8": self.epgreset,
                "9": self.epgplus,
            }, -1)

            self["channel_actions"].setEnabled(False)

        elif self.categoryname == "vod":
            self.setup_title = (_("Vod Categories"))
            self.main_title = (_("Vod"))
            nexturl = str(glob.current_playlist["playlist_info"]["player_api"]) + "&action=get_vod_categories"

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
            }, -1)

            self["channel_actions"].setEnabled(False)

        elif self.categoryname == "series":
            self.setup_title = (_("Series Categories"))
            self.main_title = (_("Series"))
            nexturl = str(glob.current_playlist["playlist_info"]["player_api"]) + "&action=get_series_categories"

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
            }, -1)

            self["channel_actions"].setEnabled(False)

        elif self.categoryname == "catchup":
            self.setup_title = (_("Catch Up Categories"))
            self.main_title = (_("Catch Up TV"))
            nexturl = str(glob.current_playlist["playlist_info"]["player_api"]) + "&action=get_live_categories"

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
            }, -1)

        glob.nextlist = []
        glob.nextlist.append({"next_url": nexturl, "index": 0, "level": self.level, "sort": self.sortText, "filter": ""})

        self.PicLoad = ePicLoad()
        self.Scale = AVSwitch().getFramebufferScale()

        try:
            self.PicLoad.PictureData.get().append(self.DecodePicture)
        except:
            self.PicLoad_conn = self.PicLoad.PictureData.connect(self.DecodePicture)

        self.onFirstExecBegin.append(self.createSetup)
        self.onLayoutFinish.append(self.__layoutFinished)

    def __layoutFinished(self):
        self.setTitle(self.setup_title)

    def createSetup(self):
        self["x_title"].setText("")
        self["x_description"].setText("")

        if self.level == 1:
            self.getCategories()
            if self.categoryname == "live":
                self.xmltvCheckData()

        elif self.level == 2:
            self.getLevel2()

        elif self.level == 3:
            self.getLevel3()

        elif self.level == 4:
            self.getLevel4()

        self.buildLists()

    def buildLists(self):
        if self.level == 1:
            self.buildList1()

        elif self.level == 2:
            self.buildList2()

        elif self.level == 3:
            self.buildList3()

        elif self.level == 4:
            self.buildList4()

    def getCategories(self):
        # print("*** getCategories **")
        index = 0
        self.list1 = []

        if self.categoryname == "live":
            currentCategoryList = glob.current_playlist["data"]["live_categories"]
            currentHidden = glob.current_playlist["player_info"]["livehidden"]

        elif self.categoryname == "vod":
            currentCategoryList = glob.current_playlist["data"]["vod_categories"]
            currentHidden = glob.current_playlist["player_info"]["vodhidden"]

        elif self.categoryname == "series":
            currentCategoryList = glob.current_playlist["data"]["series_categories"]
            currentHidden = glob.current_playlist["player_info"]["serieshidden"]

        elif self.categoryname == "catchup":
            currentCategoryList = glob.current_playlist["data"]["live_categories"]
            currentHidden = glob.current_playlist["player_info"]["catchuphidden"]

        hidden = False

        if (self.categoryname == "live" or self.categoryname == "vod") and ("-1" in currentHidden):
            hidden = True

        if self.categoryname == "live" or self.categoryname == "vod":
            self.list1.append([index, _("FAVOURITES"), "-1", hidden])
            index += 1
            self.list1.append([index, _("RECENTLY WATCHED"), "-2", hidden])
            index += 1

        # add ALL category to list
        hidden = False
        if "0" in currentHidden:
            hidden = True
        self.list1.append([index, _("ALL"), "0", hidden])
        index += 1

        if self.categoryname == "catchup":
            if not self.liveStreamsData:
                self.liveStreamsData = self.downloadApiData(self.liveStreamsUrl)
            tempList = []
            archivelist = [x for x in self.liveStreamsData if x["tv_archive"] == 1 and x["tv_archive_duration"] != "0" and x["category_id"] not in glob.current_playlist["player_info"]["livehidden"]]

            for item in currentCategoryList:
                for archive in archivelist:
                    if item["category_id"] == archive["category_id"] or ("category_ids" in archive and item["category_id"] in archive["category_ids"]):
                        tempList.append(item)
                        break
            currentCategoryList = tempList[:]

        for item in currentCategoryList:
            hidden = False
            category_name = item["category_name"]
            category_id = item["category_id"]

            if category_id in currentHidden:
                hidden = True

            self.list1.append([index, str(category_name), str(category_id), hidden])
            index += 1

        glob.originalChannelList1 = self.list1[:]

    def getLevel2(self):
        # print("*** getLevel2 ***")

        if self.categoryname == "live":
            response = self.downloadApiData(glob.nextlist[-1]["next_url"])

            if self.favourites_category:
                response = glob.current_playlist["player_info"]["livefavourites"]

            elif self.recents_category:
                response = glob.current_playlist["player_info"]["liverecents"]

            index = 0

            self.list2 = []
            currentChannelList = response
            if currentChannelList:
                for item in currentChannelList:
                    name = ""
                    stream_id = ""
                    stream_icon = ""
                    epg_channel_id = ""
                    added = ""
                    category_id = ""
                    custom_sid = ""
                    serviceref = ""
                    nowtime = ""
                    nowTitle = ""
                    nowDesc = ""
                    nexttime = ""
                    nextTitle = ""
                    nextDesc = ""
                    direct_source = ""

                    favourite = False
                    watching = False
                    hidden = False

                    if "name" in item and item["name"]:
                        name = item["name"]

                        # restyle bouquet markers
                        if "stream_type" in item and item["stream_type"] and item["stream_type"] != "live":
                            pattern = re.compile(r"[^\w\s()\[\]]", re.U)
                            name = re.sub(r"_", "", re.sub(pattern, "", name))
                            name = "** " + str(name) + " **"

                    if "stream_id" in item and item["stream_id"]:
                        stream_id = item["stream_id"]

                        if str(stream_id) in glob.current_playlist["player_info"]["channelshidden"]:
                            hidden = True

                    if "stream_icon" in item and item["stream_icon"]:
                        if item["stream_icon"].startswith("http"):
                            stream_icon = item["stream_icon"]

                        if stream_icon.startswith("https://vignette.wikia.nocookie.net/tvfanon6528"):
                            if "scale-to-width-down" not in stream_icon:
                                stream_icon = str(stream_icon) + "/revision/latest/scale-to-width-down/220"

                    if "epg_channel_id" in item and item["epg_channel_id"]:
                        epg_channel_id = item["epg_channel_id"]

                        if epg_channel_id and "&" in epg_channel_id:
                            epg_channel_id = epg_channel_id.replace("&", "&amp;")

                    if "added" in item and item["added"]:
                        added = item["added"]

                    if "category_id" in item and item["category_id"]:
                        category_id = item["category_id"]

                    if "direct_source" in item and item["direct_source"]:
                        direct_source = item["direct_source"]

                    bouquet_id = 0
                    calc_remainder = int(stream_id) // 65535
                    bouquet_id = bouquet_id + calc_remainder
                    bouquet_stream_id = int(stream_id) - int(calc_remainder * 65535)
                    unique_ref = 999 + int(glob.current_playlist["playlist_info"]["index"])
                    serviceref = "1:0:1:" + str(format(bouquet_id, "04x")) + ":" + str(format(bouquet_stream_id, "04x")) + ":" + str(format(unique_ref, "08x")) + ":0:0:0:0:" + "http%3a//example.m3u8"

                    if "custom_sid" in item and item["custom_sid"]:
                        custom_sid = item["custom_sid"]

                        if custom_sid and custom_sid != "None":
                            if custom_sid.startswith(":"):
                                custom_sid = "1" + str(custom_sid)
                            serviceref = str(":".join(custom_sid.split(":")[:7])) + ":0:0:0:" + "http%3a//example.m3u8"

                    next_url = "%s/live/%s/%s/%s.%s" % (self.host, self.username, self.password, stream_id, self.output)

                    if "livefavourites" in glob.current_playlist["player_info"]:
                        for fav in glob.current_playlist["player_info"]["livefavourites"]:
                            if str(stream_id) == str(fav["stream_id"]):
                                favourite = True
                                break
                    else:
                        glob.current_playlist["player_info"]["livefavourites"] = []

                    self.list2.append([index, str(name), str(stream_id), str(stream_icon), str(epg_channel_id), str(added), str(category_id), str(custom_sid), str(serviceref),
                                      str(nowtime), str(nowTitle), str(nowDesc), str(nexttime), str(nextTitle), str(nextDesc), str(next_url), favourite, watching, hidden, str(direct_source)])
                    index += 1

                glob.originalChannelList2 = self.list2[:]

        elif self.categoryname == "vod":
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

        elif self.categoryname == "series":
            response = self.downloadApiData(glob.nextlist[-1]["next_url"])
            index = 0
            self.list2 = []
            currentChannelList = response
            if currentChannelList:
                for item in currentChannelList:
                    name = ""
                    series_id = ""
                    cover = ""
                    plot = ""
                    cast = self["vod_cast"].getText()
                    director = self["vod_director"].getText()
                    genre = self["vod_genre"].getText()
                    releaseDate = self["vod_release_date"].getText()
                    rating = self["vod_rating"].getText()
                    last_modified = ""
                    hidden = False

                    if "name" in item and item["name"]:
                        name = item["name"]

                    if "series_id" in item and item["series_id"]:
                        series_id = item["series_id"]

                        if str(series_id) in glob.current_playlist["player_info"]["seriestitleshidden"]:
                            hidden = True

                    if "cover" in item and item["cover"]:
                        if item["cover"].startswith("http"):
                            cover = item["cover"]

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

                    if "releaseDate" not in item and "release_date" in item and item["release_date"]:
                        releaseDate = item["release_date"]

                    if "rating" in item and item["rating"]:
                        rating = item["rating"]

                    if "last_modified" in item and item["last_modified"]:
                        last_modified = item["last_modified"]

                    if cover:
                        if cover.startswith("https://image.tmdb.org/t/p/") or cover.startswith("http://image.tmdb.org/t/p/"):
                            dimensions = cover.partition("/p/")[2].partition("/")[0]
                            if screenwidth.width() <= 1280:
                                cover = cover.replace(dimensions, "w300")
                            else:
                                cover = cover.replace(dimensions, "w400")

                    next_url = str(glob.current_playlist["playlist_info"]["player_api"]) + "&action=get_series_info&series_id=" + str(series_id)

                    self.list2.append([index, str(name), str(series_id), str(cover), str(plot), str(cast), str(director), str(genre), str(releaseDate), str(rating), str(last_modified), str(next_url), hidden])

                    index += 1

                glob.originalChannelList2 = self.list2[:]

        elif self.categoryname == "catchup":
            response = self.downloadApiData(glob.nextlist[-1]["next_url"])

            index = 0

            self.list2 = []
            currentChannelList = response
            if currentChannelList:
                for item in currentChannelList:
                    name = ""
                    stream_id = ""
                    stream_icon = ""
                    epg_channel_id = ""
                    added = ""
                    hidden = False

                    if "tv_archive" in item and "tv_archive_duration" in item:
                        if item["tv_archive"] == 1 and item["tv_archive_duration"] != "0":

                            if "name" in item and item["name"]:
                                name = item["name"]
                            if "stream_id" in item and item["stream_id"]:
                                stream_id = item["stream_id"]
                                if str(stream_id) in glob.current_playlist["player_info"]["catchupchannelshidden"]:
                                    hidden = True
                            if "stream_icon" in item and item["stream_icon"]:
                                if item["stream_icon"].startswith("http"):
                                    stream_icon = item["stream_icon"]
                            if "epg_channel_id" in item and item["epg_channel_id"]:
                                epg_channel_id = item["epg_channel_id"]

                                if epg_channel_id and "&" in epg_channel_id:
                                    epg_channel_id = epg_channel_id.replace("&", "&amp;")
                            if "added" in item and item["added"]:
                                added = item["added"]
                            epgnowtitle = epgnowtime = epgnowdescription = epgnexttitle = epgnexttime = epgnextdescription = ""

                            next_url = "%s/live/%s/%s/%s.%s" % (self.host, self.username, self.password, stream_id, self.output)
                            self.list2.append([
                                index, str(name), str(stream_id), str(stream_icon), str(epg_channel_id), str(added), str(next_url),
                                epgnowtime, epgnowtitle, epgnowdescription, epgnexttime, epgnexttitle, epgnextdescription, hidden
                            ])

                            index += 1

                glob.originalChannelList2 = self.list2[:]

    def getLevel3(self):
        # print("**** getLevel3 ****")
        if self.categoryname == "series":
            response = self.downloadApiData(glob.nextlist[-1]["next_url"])
            index = 0
            self.list3 = []
            currentChannelList = response
            name = ""
            cover = ""
            overview = ""
            cast = self["vod_cast"].getText()
            director = self["vod_director"].getText()
            genre = self["vod_genre"].getText()
            airdate = self["vod_release_date"].getText()
            rating = self["vod_rating"].getText()
            last_modified = ""

            if currentChannelList:
                if "info" in currentChannelList:
                    if "name" in currentChannelList["info"] and currentChannelList["info"]["name"]:
                        name = currentChannelList["info"]["name"]

                    if "cover" in currentChannelList["info"] and currentChannelList["info"]["cover"]:
                        if currentChannelList["info"]["cover"].startswith("http"):
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

                    if "releaseDate" not in currentChannelList["info"] and "release_date" in currentChannelList["info"] and currentChannelList["info"]["release_date"]:
                        airdate = currentChannelList["info"]["release_date"]

                    if "rating" in currentChannelList["info"] and currentChannelList["info"]["rating"]:
                        rating = currentChannelList["info"]["rating"]

                    if "last_modified" in currentChannelList["info"] and currentChannelList["info"]["last_modified"]:
                        last_modified = currentChannelList["info"]["last_modified"]

                if "episodes" in currentChannelList:
                    if currentChannelList["episodes"]:

                        seasonlist = []
                        isdict = True
                        try:
                            seasonlist = list(currentChannelList["episodes"].keys())
                        except:
                            isdict = False
                            x = 0
                            for item in currentChannelList["episodes"]:
                                seasonlist.append(x)
                                x += 1

                        if seasonlist:
                            for season in seasonlist:

                                name = _("Season ") + str(season)

                                if isdict:
                                    season_number = currentChannelList["episodes"][str(season)][0]["season"]
                                else:
                                    season_number = currentChannelList["episodes"][season][0]["season"]

                                series_id = 0
                                hidden = False
                                if "seasons" in currentChannelList:
                                    if currentChannelList["seasons"]:
                                        for item in currentChannelList["seasons"]:

                                            if "season_number" in item:
                                                if item["season_number"] == season_number:

                                                    if "airdate" in item and item["airdate"]:
                                                        airdate = item["airdate"]

                                                    if "name" in item and item["name"]:
                                                        name = item["name"]

                                                    if "overview" in item and item["overview"]:
                                                        overview = item["overview"]

                                                    if "cover_big" in item and item["cover_big"]:
                                                        if item["cover_big"].startswith("http"):
                                                            cover = item["cover_big"]
                                                    elif "cover" in item and item["cover"]:
                                                        if item["cover"].startswith("http"):
                                                            cover = item["cover"]
                                                    if "id" in item and item["id"]:
                                                        series_id = item["id"]
                                                    break

                                if str(series_id) in glob.current_playlist["player_info"]["seriesseasonshidden"]:
                                    hidden = True

                                if cover:
                                    if cover.startswith("https://image.tmdb.org/t/p/") or cover.startswith("http://image.tmdb.org/t/p/"):
                                        dimensions = cover.partition("/p/")[2].partition("/")[0]
                                        if screenwidth.width() <= 1280:
                                            cover = cover.replace(dimensions, "w300")
                                        else:
                                            cover = cover.replace(dimensions, "w400")

                                next_url = self.seasons_url
                                self.list3.append([index, str(name), str(series_id), str(cover), str(overview), str(cast), str(director), str(genre), str(airdate), str(rating), season_number, str(next_url), str(last_modified), hidden])

                    self.list3.sort(key=self.natural_keys)

                self.storedcover = cover
                glob.originalChannelList3 = self.list3[:]

    def getLevel4(self):
        # print("**** getLevel4 ****")
        if self.categoryname == "series":
            response = self.downloadApiData(glob.nextlist[-1]["next_url"])
            index = 0
            self.list4 = []
            currentChannelList = response

            shorttitle = ""
            cover = self.storedcover
            plot = ""
            cast = self["vod_cast"].getText()
            director = self["vod_director"].getText()
            genre = self["vod_genre"].getText()
            releasedate = self["vod_release_date"].getText()
            rating = self["vod_rating"].getText()

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

                    if "rating" in currentChannelList["info"] and currentChannelList["info"]["rating"]:
                        rating = currentChannelList["info"]["rating"]

                    if "last_modified" in currentChannelList["info"] and currentChannelList["info"]["last_modified"]:
                        last_modified = currentChannelList["info"]["last_modified"]

                if "episodes" in currentChannelList:
                    if currentChannelList["episodes"]:
                        season_number = str(self.season_number)
                        try:
                            currentChannelList["episodes"][season_number]
                        except:
                            season_number = int(self.season_number)

                        for item in currentChannelList["episodes"][season_number]:
                            title = ""
                            stream_id = ""
                            container_extension = "mp4"
                            tmdb_id = ""
                            duration = ""
                            hidden = False
                            direct_source = ""

                            if "id" in item:
                                stream_id = item["id"]

                            if "title" in item:
                                title = item["title"].replace(str(shorttitle) + " - ", "")

                            if "container_extension" in item:
                                container_extension = item["container_extension"]

                            if "tmdb_id" in item:
                                tmdb_id = item["info"]["tmdb_id"]

                            if "releasedate" in item["info"]:
                                releasedate = item["info"]["releasedate"]

                            if "plot" in item["info"]:
                                plot = item["info"]["plot"]

                            if "duration" in item["info"]:
                                duration = item["info"]["duration"]

                            if "rating" in item["info"]:
                                rating = item["info"]["rating"]

                            if "direct_source" in item and item["direct_source"]:
                                direct_source = item["direct_source"]

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
                                if cover.startswith("https://image.tmdb.org/t/p/") or cover.startswith("http://image.tmdb.org/t/p/"):
                                    dimensions = cover.partition("/p/")[2].partition("/")[0]
                                    if screenwidth.width() <= 1280:
                                        cover = cover.replace(dimensions, "w300")
                                    else:
                                        cover = cover.replace(dimensions, "w400")

                            if str(stream_id) in glob.current_playlist["player_info"]["seriesepisodeshidden"]:
                                hidden = True

                            next_url = "%s/series/%s/%s/%s.%s" % (self.host, self.username, self.password, stream_id, container_extension)

                            self.list4.append([index, str(title), str(stream_id), str(cover), str(plot), str(cast), str(director), str(genre), str(releasedate), str(rating), str(duration), str(container_extension), str(tmdb_id), str(next_url), str(shorttitle), str(last_modified), hidden, str(direct_source)])
                            index += 1

                glob.originalChannelList4 = self.list4[:]

    def downloadApiData(self, url):
        content = ""
        adapter = HTTPAdapter(max_retries=0)
        http = requests.Session()
        http.mount("http://", adapter)
        http.mount("https://", adapter)
        try:
            r = http.get(url, headers=hdr, stream=True, timeout=cfg.timeout.value, verify=False)
            r.raise_for_status()
            if r.status_code == requests.codes.ok:
                try:
                    content = r.json()
                except Exception as e:
                    print(e)
                    content = ""
            return content

        except Exception as e:
            print(e)

    def xmltvCheckData(self):
        safeName = re.sub(r'[\<\>\:\"\/\\\|\?\*]', "_", str(glob.current_playlist["playlist_info"]["name"]))
        safeName = re.sub(r" ", "_", safeName)
        safeName = re.sub(r"_+", "_", safeName)

        filepath = "/etc/epgimport/"
        filename = "xstreamity." + str(safeName) + ".sources.xml"
        sourcepath = filepath + filename
        epgfilename = "xstreamity." + str(safeName) + ".channels.xml"
        channelpath = filepath + epgfilename

        if not os.path.exists(sourcepath) or not os.path.exists(channelpath):
            self.downloadXMLTVdata()

        else:
            # check file creation times - refresh if older than 24 hours.
            try:
                nowtime = time.time()
                sourcemodified = os.path.getctime(sourcepath)
                channelmodified = os.path.getctime(channelpath)
                if int(nowtime) - int(sourcemodified) > 14400 or int(nowtime) - int(channelmodified) > 14400:
                    self.downloadXMLTVdata()
            except Exception as e:
                print(e)

    def buildList1(self):
        # print("*** buildlist1 ***")
        if self.categoryname == "live":
            self["key_epg"].setText("")
            self.hideEPG()
            self.xmltvdownloaded = False

        elif self.categoryname == "vod" or self.categoryname == "series":
            self.hideVod()

        elif self.categoryname == "catchup":
            self["picon"].hide()

        self.main_list = []
        self.main_list = [buildCategoryList(x[0], x[1], x[2], x[3]) for x in self.list1 if x[3] is False]
        self["main_list"].setList(self.main_list)

        if self["main_list"].getCurrent():
            if glob.nextlist[-1]["index"] != 0:
                self["main_list"].setIndex(glob.nextlist[-1]["index"])

        self.buttons()
        self.selectionChanged()

    def buildList2(self):
        # print("*** buildlist2 ***")
        self.main_list = []

        if self.categoryname == "live":
            self.epglist = []
            # index = 0, name = 1, stream_id = 2, stream_icon = 3, epg_channel_id = 4, added = 5, category_id = 6, custom_sid = 7, nowtime = 9
            # nowTitle = 10, nowDesc = 11, nexttime = 12, nextTitle = 13, nextDesc = 14, next_url = 15, favourite = 16, watching = 17, hidden = 18, direct_source = 19
            if self.favourites_category:
                self.main_list = [buildLiveStreamList(x[0], x[1], x[2], x[3], x[15], x[16], x[17], x[18], x[19]) for x in self.list2 if x[16] is True]
                self.epglist = [buildEPGListEntry(x[0], x[2], x[9], x[10], x[11], x[12], x[13], x[14], x[18], x[19]) for x in self.list2 if x[16] is True]
            else:
                self.main_list = [buildLiveStreamList(x[0], x[1], x[2], x[3], x[15], x[16], x[17], x[18], x[19]) for x in self.list2 if x[18] is False]
                self.epglist = [buildEPGListEntry(x[0], x[2], x[9], x[10], x[11], x[12], x[13], x[14], x[18], x[19]) for x in self.list2 if x[18] is False]

            self["main_list"].setList(self.main_list)
            self["epg_list"].setList(self.epglist)
            self.showEPG()

        elif self.categoryname == "vod":
            if self.favourites_category:
                self.main_list = [buildVodStreamList(x[0], x[1], x[2], x[3], x[4], x[5], x[6], x[7], x[8], x[10], x[11]) for x in self.list2 if x[7] is True]
            else:
                self.main_list = [buildVodStreamList(x[0], x[1], x[2], x[3], x[4], x[5], x[6], x[7], x[8], x[10], x[11]) for x in self.list2 if x[10] is False]
            self["main_list"].setList(self.main_list)
            self.showVod()

        elif self.categoryname == "series":
            self.main_list = [buildSeriesTitlesList(x[0], x[1], x[2], x[3], x[4], x[5], x[6], x[7], x[8], x[9], x[10], x[11], x[12]) for x in self.list2 if x[12] is False]
            self["main_list"].setList(self.main_list)
            self.showVod()

        elif self.categoryname == "catchup":
            self.main_list = [buildCatchupStreamList(x[0], x[1], x[2], x[3], x[4], x[5], x[6], x[13]) for x in self.list2 if x[13] is False]
            self["main_list"].setList(self.main_list)
            self["picon"].show()

        if self["main_list"].getCurrent():
            if glob.nextlist[-1]["index"] != 0:
                self["main_list"].setIndex(glob.nextlist[-1]["index"])
        self.buttons()
        self.selectionChanged()

    def buildList3(self):
        # print("*** buildlist3 ***")
        self.main_list = []

        if self.categoryname == "series":
            # [index, str(name), str(series_id), str(cover), str(overview), str(cast), str(director), str(genre), str(airdate), str(rating), season_number, str(next_url), str(last_modified), hidden])
            if self.list3:
                self.main_list = [buildSeriesSeasonsList(x[0], x[1], x[2], x[3], x[4], x[5], x[6], x[7], x[8], x[9], x[10], x[11], x[12], x[13]) for x in self.list3 if x[13] is False]
                self["main_list"].setList(self.main_list)

        if self["main_list"].getCurrent():
            if glob.nextlist[-1]["index"] != 0:
                self["main_list"].setIndex(glob.nextlist[-1]["index"])
        self.buttons()
        self.selectionChanged()

    def buildList4(self):
        # print("*** buildlist4 ***")
        self.main_list = []
        if self.categoryname == "series":
            if self.list4:
                self.main_list = [buildSeriesEpisodesList(x[0], x[1], x[2], x[3], x[4], x[5], x[6], x[7], x[8], x[9], x[10], x[11], x[12], x[13], x[14], x[15], x[16], x[17]) for x in self.list4 if x[16] is False]
                self["main_list"].setList(self.main_list)

        if self["main_list"].getCurrent():
            if glob.nextlist[-1]["index"] != 0:
                self["main_list"].setIndex(glob.nextlist[-1]["index"])

        self.buttons()
        self.selectionChanged()

    def buttons(self):
        if glob.nextlist[-1]["filter"]:
            self["key_yellow"].setText("")
            self["key_blue"].setText(_("Reset Search"))
            self["key_menu"].setText("")
        else:

            if self.categoryname == "catchup" and self.selectedlist == self["epg_short_list"]:
                self["key_blue"].setText("")
                self["key_yellow"].setText(_("Reverse"))
                self["key_menu"].setText(_("Hide/Show"))

            else:
                self["key_blue"].setText(_("Search"))
                if not glob.nextlist[-1]["sort"]:
                    self.sortText = (_("Sort: A-Z"))
                    glob.nextlist[-1]["sort"] = self.sortText

                self["key_yellow"].setText(_(glob.nextlist[-1]["sort"]))
                self["key_menu"].setText(_("Hide/Show"))

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
                elif self.selectedlist == self["epg_short_list"]:
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

            if self.level != 4:
                self.loadDefaultImage()

            if self.level == 2:
                if self.categoryname == "live":
                    if not self.showingshortEPG:
                        self["epg_list"].setIndex(currentindex)

                        if self.xmltvdownloaded is False:
                            if os.path.isfile(self.epgjsonfile):
                                self.xmltvdownloaded = True
                                self.addEPG()

                        self.refreshEPGInfo()
                        self.timerimage = eTimer()
                        try:
                            self.timerimage.stop()
                        except:
                            pass

                    if cfg.channelpicons.value is True:
                        try:
                            self.timerimage.callback.append(self.downloadImage)
                        except:
                            self.timerimage_conn = self.timerimage.timeout.connect(self.downloadImage)
                        self.timerimage.start(250, True)

                elif self.categoryname == "vod":
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

            if self.categoryname == "series" and self.level != 1:
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

            if self.categoryname == "catchup" and self.level != 1:
                self.timerimage = eTimer()
                try:
                    self.timerimage.stop()
                except:
                    pass
                if cfg.channelpicons.value is True:
                    try:
                        self.timerimage.callback.append(self.downloadImage)
                    except:
                        self.timerimage_conn = self.timerimage.timeout.connect(self.downloadImage)
                    self.timerimage.start(250, True)

        else:
            self.position = 0
            self.positionall = 0
            self.page = 0
            self.pageall = 0

            self["page"].setText(_("Page: ") + str(self.page) + _(" of ") + str(self.pageall))
            self["listposition"].setText(str(self.position) + "/" + str(self.positionall))

            self["key_yellow"].setText("")
            self["key_blue"].setText("")

    def downloadImage(self):
        # print("*** downloadimage ***")
        if self["main_list"].getCurrent():
            try:
                os.remove(str(dir_tmp) + "original.png")
                os.remove(str(dir_tmp) + "temp.png")
            except:
                pass

            try:
                os.remove(str(dir_tmp) + "original.jpg")
                os.remove(str(dir_tmp) + "temp.jpg")
            except:
                pass

            desc_image = ""
            try:
                desc_image = self["main_list"].getCurrent()[5]
            except:
                pass

            if self.categoryname == "vod" or self.categoryname == "series":
                if self.info:  # tmbdb
                    if "cover_big" in self.info and self.info["cover_big"] and self.info["cover_big"] != "null":
                        desc_image = str(self.info["cover_big"]).strip()

            if desc_image and desc_image != "n/A":
                if self.categoryname == "live" or self.categoryname == "catchup":
                    temp = dir_tmp + "temp.png"
                elif self.categoryname == "vod" or self.categoryname == "series":
                    temp = dir_tmp + "temp.jpg"

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
        if self["picon"].instance:
            self["picon"].instance.setPixmapFromFile(common_path + "picon.png")

        if self["vod_cover"].instance:
            self["vod_cover"].instance.setPixmapFromFile(skin_path + "images/vod_cover.png")

    def resizeImage(self, data=None):
        # print("*** resizeImage ***")
        if self["main_list"].getCurrent():

            if self.categoryname == "live" or self.categoryname == "catchup":
                original = str(dir_tmp) + "temp.png"

                size = [147, 88]
                if screenwidth.width() > 1280:
                    size = [220, 130]

                if os.path.exists(original):
                    try:
                        im = Image.open(original).convert("RGBA")
                        im.thumbnail(size, Image.ANTIALIAS)

                        # crop and center image
                        bg = Image.new("RGBA", size, (255, 255, 255, 0))

                        imagew, imageh = im.size
                        im_alpha = im.convert("RGBA").split()[-1]
                        bgwidth, bgheight = bg.size
                        bg_alpha = bg.convert("RGBA").split()[-1]
                        temp = Image.new("L", (bgwidth, bgheight), 0)
                        temp.paste(im_alpha, (int((bgwidth - imagew) / 2), int((bgheight - imageh) / 2)), im_alpha)
                        bg_alpha = ImageChops.screen(bg_alpha, temp)
                        bg.paste(im, (int((bgwidth - imagew) / 2), int((bgheight - imageh) / 2)))
                        im = bg
                        im.save(original, "PNG")

                        if self["picon"].instance:
                            self["picon"].instance.setPixmapFromFile(original)

                    except Exception as e:
                        print(e)
                else:
                    self.loadDefaultImage()

            elif self.categoryname == "vod" or self.categoryname == "series":
                if self["vod_cover"].instance:
                    preview = str(dir_tmp) + "temp.jpg"

                    width = 267
                    height = 400
                    if screenwidth.width() > 1280:
                        width = 400
                        height = 600

                    self.PicLoad.setPara([width, height, self.Scale[0], self.Scale[1], 0, 1, "FF000000"])

                    if self.PicLoad.startDecode(preview):
                        # if this has failed, then another decode is probably already in progress
                        # throw away the old picload and try again immediately
                        self.PicLoad = ePicLoad()
                        try:
                            self.PicLoad.PictureData.get().append(self.DecodePicture)
                        except:
                            self.PicLoad_conn = self.PicLoad.PictureData.connect(self.DecodePicture)
                        self.PicLoad.setPara([width, height, self.Scale[0], self.Scale[1], 0, 1, "FF000000"])
                        self.PicLoad.startDecode(preview)

    def DecodePicture(self, PicInfo=None):
        # print("*** DecodePicture ***")
        ptr = self.PicLoad.getData()
        if ptr is not None and self.level != 1:
            self["vod_cover"].instance.setPixmap(ptr)
            self["vod_cover"].instance.show()

    def goUp(self):
        # print("*** goUp ***")
        instance = self.selectedlist.master.master.instance
        instance.moveSelection(instance.moveUp)
        self.selectionChanged()

    def goDown(self):
        # print("*** goDown ***")
        instance = self.selectedlist.master.master.instance
        instance.moveSelection(instance.moveDown)
        self.selectionChanged()

    def pageUp(self):
        # print("*** pageUp ***")
        instance = self.selectedlist.master.master.instance
        instance.moveSelection(instance.pageUp)
        self.selectionChanged()

    def pageDown(self):
        # print("*** pageDown ***")
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

        if self.categoryname == "catchup" and self.selectedlist == self["epg_short_list"]:
            self.reverse()
            return

        if not self["key_yellow"].getText() or self["key_yellow"].getText() == _("Reverse"):
            return

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

        elif self.level != 1 and (self.categoryname == "live" or self.categoryname == "catchup"):
            sortlist = [(_("Sort: A-Z")), (_("Sort: Z-A")), (_("Sort: Added")), (_("Sort: Original"))]

        elif self.level != 1 and (self.categoryname == "vod" or self.categoryname == "series"):
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
            if self.categoryname == "live":
                activelist.sort(key=lambda x: x[5], reverse=True)
            elif self.categoryname == "vod":
                activelist.sort(key=lambda x: x[4], reverse=True)
            elif self.categoryname == "series":
                if self.level == 2:
                    activelist.sort(key=lambda x: x[10], reverse=True)
                if self.level == 3:
                    activelist.sort(key=lambda x: x[12], reverse=True)
                if self.level == 4:
                    activelist.sort(key=lambda x: x[15], reverse=True)
            elif self.categoryname == "catchup":
                activelist.sort(key=lambda x: x[5], reverse=True)

        elif current_sort == (_("Sort: Year")):
            if self.categoryname == "vod":
                activelist.sort(key=lambda x: x[9], reverse=True)
            elif self.categoryname == "series":
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

    def search(self):
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

            if self.categoryname == "live":
                del glob.current_playlist["player_info"]['liverecents'][currentindex]
                self.hideEPG()

            elif self.categoryname == "vod":
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
        if result or self.filterresult:
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
            self["key_blue"].setText(_("Reset Search"))
            self["key_yellow"].setText("")
            activelist = [channel for channel in activelist if str(result).lower() in str(channel[1]).lower()]

            if self.level == 1:
                self.list1 = activelist

            elif self.level == 2:
                self.list2 = activelist

            elif self.level == 3:
                self.list3 = activelist

            elif self.level == 4:
                self.list4 = activelist

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
            glob.pintime = time.time()
            self.next()
        else:
            return

    def parentalCheck(self):
        # print("*** parentalCheck ***")
        self.pin = True

        if self.level == 1:
            adult = _("all"), "all", "+18", "adult", "18+", "18 rated", "xxx", "sex", "porn", "pink", "blue"
            if any(s in str(self["main_list"].getCurrent()[0]).lower() and str(self["main_list"].getCurrent()[0]).lower() != "Allgemeines" for s in adult):
                glob.adultChannel = True
            else:
                glob.adultChannel = False

            if cfg.adult.value is True and int(time.time()) - int(glob.pintime) > 900:
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
            glob.currentepglist = self.epglist[:]

            if self.level == 1:
                category_id = self["main_list"].getCurrent()[3]

                if self.categoryname == "live":
                    next_url = str(glob.current_playlist["playlist_info"]["player_api"]) + "&action=get_live_streams&category_id=" + str(category_id)
                if self.categoryname == "vod":
                    next_url = str(glob.current_playlist["playlist_info"]["player_api"]) + "&action=get_vod_streams&category_id=" + str(category_id)
                if self.categoryname == "series":
                    next_url = str(glob.current_playlist["playlist_info"]["player_api"]) + "&action=get_series&category_id=" + str(category_id)
                if self.categoryname == "catchup":
                    next_url = str(glob.current_playlist["playlist_info"]["player_api"]) + "&action=get_live_streams&category_id=" + str(category_id)

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
                return

            elif self.level == 2:
                if self.categoryname == "live":
                    if self.selectedlist == self["epg_short_list"]:
                        self.shortEPG()

                    streamtype = glob.current_playlist["player_info"]["livetype"]
                    next_url = self["main_list"].getCurrent()[3]
                    stream_id = self["main_list"].getCurrent()[4]
                    direct_source = self["main_list"].getCurrent()[7]

                    if str(os.path.splitext(next_url)[-1]) == ".m3u8":
                        if streamtype == "1":
                            streamtype = "4097"

                    self.reference = eServiceReference(int(streamtype), 0, next_url)
                    if direct_source:
                        self.reference = eServiceReference(int(streamtype), 0, direct_source)
                    self.reference.setName(glob.currentchannellist[glob.currentchannellistindex][0])

                    if self.session.nav.getCurrentlyPlayingServiceReference():

                        if self.session.nav.getCurrentlyPlayingServiceReference().toString() != self.reference.toString() and cfg.livepreview.value is True:
                            self.session.nav.stopService()
                            self.session.nav.playService(self.reference)

                            if self.session.nav.getCurrentlyPlayingServiceReference():
                                glob.newPlayingServiceRef = self.session.nav.getCurrentlyPlayingServiceReference()
                                glob.newPlayingServiceRefString = glob.newPlayingServiceRef.toString()

                            for channel in self.list2:
                                if channel[2] == stream_id:
                                    channel[17] = True  # set watching icon
                                else:
                                    channel[17] = False
                            self.buildLists()

                        else:
                            # return to last played stream
                            callingfunction = sys._getframe().f_back.f_code.co_name
                            if callingfunction == "playStream":
                                next_url = str(self.lastviewed_url)
                                stream_id = str(self.lastviewed_id)
                                self["main_list"].setIndex(self.lastviewed_index)
                                self.reference = eServiceReference(int(streamtype), 0, next_url)
                                glob.newPlayingServiceRef = self.reference
                                glob.newPlayingServiceRefString = self.reference.toString()
                                glob.currentchannellistindex = self.lastviewed_index
                                self.reference.setName(glob.currentchannellist[glob.currentchannellistindex][0])

                            else:
                                self.lastviewed_url = next_url
                                if direct_source:
                                    self.lastviewed_url = direct_source
                                self.lastviewed_id = stream_id
                                self.lastviewed_index = self["main_list"].getIndex()

                            for channel in self.list2:
                                if channel[2] == stream_id:
                                    channel[17] = True  # set watching icon
                                else:
                                    channel[17] = False
                            self.buildLists()

                            self.session.openWithCallback(self.setIndex, streamplayer.XStreamity_StreamPlayer, str(next_url), str(streamtype), str(direct_source))
                    else:
                        self.session.openWithCallback(self.setIndex, streamplayer.XStreamity_StreamPlayer, str(next_url), str(streamtype), str(direct_source))

                    self["category_actions"].setEnabled(False)

                elif self.categoryname == "vod":
                    streamtype = glob.current_playlist["player_info"]["vodtype"]
                    next_url = self["main_list"].getCurrent()[3]
                    direct_source = self["main_list"].getCurrent()[10]

                    self.reference = eServiceReference(int(streamtype), 0, next_url)
                    if direct_source:
                        self.reference = eServiceReference(int(streamtype), 0, direct_source)
                    self.reference.setName(glob.currentchannellist[glob.currentchannellistindex][0])
                    self.session.openWithCallback(self.setIndex, streamplayer.XStreamity_VodPlayer, str(next_url), str(streamtype), str(direct_source))

                elif self.categoryname == "series":
                    next_url = self["main_list"].getCurrent()[3]
                    if "&action=get_series_info" in next_url:
                        self.seasons_url = self["main_list"].getCurrent()[3]
                    self.level += 1
                    self["main_list"].setIndex(0)
                    self["category_actions"].setEnabled(False)
                    self["channel_actions"].setEnabled(True)
                    glob.nextlist.append({"next_url": next_url, "index": 0, "level": self.level, "sort": self["key_yellow"].getText(), "filter": ""})
                    self.createSetup()
                    return

                elif self.categoryname == "catchup":
                    if self.selectedlist == self["main_list"]:
                        self.catchupEPG()
                        self.buttons()
                    else:
                        self.playCatchup()

            elif self.level == 3:
                if self.categoryname == "series":
                    next_url = self["main_list"].getCurrent()[3]
                    if "&action=get_series_info" in next_url:
                        self.season_number = self["main_list"].getCurrent()[12]
                    self.level += 1
                    self["main_list"].setIndex(0)
                    self["category_actions"].setEnabled(False)
                    self["channel_actions"].setEnabled(True)
                    glob.nextlist.append({"next_url": next_url, "index": 0, "level": self.level, "sort": self["key_yellow"].getText(), "filter": ""})
                    self.createSetup()
                    return

            elif self.level == 4:
                streamtype = glob.current_playlist["player_info"]["vodtype"]
                next_url = self["main_list"].getCurrent()[3]
                direct_source = self["main_list"].getCurrent()[18]
                self.reference = eServiceReference(int(streamtype), 0, next_url)
                self.reference.setName(glob.currentchannellist[glob.currentchannellistindex][0])
                self.session.openWithCallback(self.setIndex, streamplayer.XStreamity_VodPlayer, str(next_url), str(streamtype), str(direct_source))

    def setIndex(self):
        # print("*** set index ***")
        self["main_list"].setIndex(glob.currentchannellistindex)
        if self.categoryname == "live":
            self["epg_list"].setIndex(glob.currentchannellistindex)
        self.selectionChanged()
        self.buildLists()

    def back(self):
        # print("*** back ***")

        if self.categoryname != "catchup":
            if self.categoryname == "live":
                if self.selectedlist == self["epg_short_list"]:
                    self.shortEPG()
                    return

                try:
                    os.remove(str(dir_tmp) + "liveepg.xml")
                except:
                    pass

            del glob.nextlist[-1]

            if len(glob.nextlist) == 0:
                self.stopStream()
                self.close()
            else:
                if self.categoryname == "live":
                    self.lastviewed_url = ""
                    self.lastviewed_id = ""
                    self.lastviewed_index = 0

                self["x_title"].setText("")
                self["x_description"].setText("")

                if cfg.stopstream.value:
                    self.stopStream()

                levelpath = str(dir_tmp) + "level" + str(self.level) + ".json"
                if self.categoryname == "series":
                    levelpath = str(dir_tmp) + "level" + str(self.level) + ".xml"

                try:
                    os.remove(levelpath)
                except:
                    pass

                self.level -= 1

                self["category_actions"].setEnabled(True)
                self["channel_actions"].setEnabled(False)

                self.buildLists()
        else:
            self.hideEPG()

            if self.selectedlist == self["epg_short_list"]:

                instance = self["epg_short_list"].master.master.instance
                instance.setSelectionEnable(0)
                self.catchup_all = []
                self["epg_short_list"].setList(self.catchup_all)
                instance = self["main_list"].master.master.instance
                instance.setSelectionEnable(1)
                self.selectedlist = self["main_list"]
                self.buttons()
            else:

                del glob.nextlist[-1]

                if len(glob.nextlist) == 0:
                    self.close()
                else:

                    self.stopStream()

                    levelpath = str(dir_tmp) + "level" + str(self.level) + ".xml"
                    try:
                        os.remove(levelpath)
                    except:
                        pass
                    self.level -= 1
                    self.createSetup()

    def showHiddenList(self):
        # print("*** showHiddenList ***")
        if self["key_menu"].getText() != "":
            from . import hidden
            if self["main_list"].getCurrent():
                if self.categoryname == "live":
                    if self.level == 1:
                        self.session.openWithCallback(self.createSetup, hidden.XStreamity_HiddenCategories, "live", self.list1, self.level)
                    elif self.level == 2 and not self.favourites_category and not self.recents_category:
                        self.session.openWithCallback(self.createSetup, hidden.XStreamity_HiddenCategories, "live", self.list2, self.level)
                elif self.categoryname == "vod":
                    if self.level == 1:
                        self.session.openWithCallback(self.createSetup, hidden.XStreamity_HiddenCategories, "vod", self.list1, self.level)
                    elif self.level == 2 and not self.favourites_category and not self.recents_category:
                        self.session.openWithCallback(self.createSetup, hidden.XStreamity_HiddenCategories, "vod", self.list2, self.level)
                elif self.categoryname == "series":
                    if self.level == 1:
                        self.session.openWithCallback(self.createSetup, hidden.XStreamity_HiddenCategories, "series", self.list1, self.level)
                    elif self.level == 2:
                        self.session.openWithCallback(self.createSetup, hidden.XStreamity_HiddenCategories, "series", self.list2, self.level)
                    elif self.level == 3:
                        self.session.openWithCallback(self.createSetup, hidden.XStreamity_HiddenCategories, "series", self.list3, self.level)
                    elif self.level == 4:
                        self.session.openWithCallback(self.createSetup, hidden.XStreamity_HiddenCategories, "series", self.list4, self.level)
                elif self.categoryname == "catchup":
                    if self.level == 1:
                        self.session.openWithCallback(self.createSetup, hidden.XStreamity_HiddenCategories, "catchup", self.list1, self.level)
                    elif self.level == 2 and not self.favourites_category and not self.recents_category:
                        self.session.openWithCallback(self.createSetup, hidden.XStreamity_HiddenCategories, "catchup", self.list2, self.level)

    def favourite(self):
        # print("**** favourite ***")
        if self["main_list"].getCurrent():
            currentindex = self["main_list"].getIndex()
            favExists = False
            favStream_id = None

            if self.categoryname == "live":
                for fav in glob.current_playlist["player_info"]["livefavourites"]:
                    if self["main_list"].getCurrent()[4] == fav["stream_id"]:
                        favExists = True
                        favStream_id = fav["stream_id"]
                        break

                self.list2[currentindex][16] = not self.list2[currentindex][16]
                if favExists:
                    glob.current_playlist["player_info"]["livefavourites"][:] = [x for x in glob.current_playlist["player_info"]["livefavourites"] if str(x["stream_id"]) != str(favStream_id)]
                else:
                    newfavourite = {
                        "name": self.list2[currentindex][1],
                        "stream_id": self.list2[currentindex][2],
                        "stream_icon": self.list2[currentindex][3],
                        "epg_channel_id": self.list2[currentindex][4],
                        "added": self.list2[currentindex][5],
                        "category_id": self.list2[currentindex][6],
                        "custom_sid": self.list2[currentindex][7]
                    }

                    glob.current_playlist["player_info"]["livefavourites"].insert(0, newfavourite)
                    self.hideEPG()

            elif self.categoryname == "vod":
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

    def addEPG(self):
        # print("*** addEPG ***")
        if self["main_list"].getCurrent():
            now = time.time() + (self.epgtimeshift * 3600)

            self.epgcache = eEPGCache.getInstance()

            with open(self.epgjsonfile, "rb") as f:
                try:
                    self.epgJson = json.load(f)
                    for channel in self.list2:
                        epg_channel_id = channel[4].lower()

                        if epg_channel_id in self.epgJson:
                            for index, entry in enumerate(self.epgJson[epg_channel_id]):
                                if (index + 1 < len(self.epgJson[epg_channel_id])):
                                    next_el = self.epgJson[epg_channel_id][index + 1]

                                    entry[0] = int(entry[0]) + (int(glob.current_playlist["player_info"]["epgoffset"]) * 3600)
                                    entry[1] = int(entry[1]) + (int(glob.current_playlist["player_info"]["epgoffset"]) * 3600)

                                    if int(entry[0]) < now and int(entry[1]) > now:

                                        channel[9] = str(time.strftime("%H:%M", time.localtime(int(entry[0]))))
                                        channel[10] = str(entry[2])
                                        channel[11] = str(entry[3])

                                        channel[12] = str(time.strftime("%H:%M", time.localtime(int(entry[1]))))
                                        channel[13] = str(next_el[2])
                                        channel[14] = str(next_el[3])

                                        break
                        else:
                            self.eventslist = []
                            serviceref = channel[8]

                            events = ["IBDTEX", (serviceref, -1, -1, -1)]  # search next 12 hours
                            self.eventslist = [] if self.epgcache is None else self.epgcache.lookupEvent(events)

                            # print("**** self.eventslist %s" % self.eventslist)

                            for i in range(len(self.eventslist)):
                                if self.eventslist[i][1] is not None:
                                    self.eventslist[i] = (self.eventslist[i][0], self.eventslist[i][1], self.eventslist[i][2], self.eventslist[i][3], self.eventslist[i][4])

                            if self.eventslist:
                                if len(self.eventslist) > 0:
                                    try:
                                        # start time
                                        if self.eventslist[0][1]:
                                            channel[9] = str(time.strftime("%H:%M", time.localtime(self.eventslist[0][1])))

                                        # title
                                        if self.eventslist[0][3]:
                                            channel[10] = str(self.eventslist[0][3])

                                        # description
                                        if self.eventslist[0][4]:
                                            channel[11] = str(self.eventslist[0][4])

                                    except Exception as e:
                                        print(e)

                            if len(self.eventslist) > 1:
                                try:
                                    # next start time
                                    if self.eventslist[1][1]:
                                        channel[12] = str(time.strftime("%H:%M", time.localtime(self.eventslist[1][1])))

                                    # next title
                                    if self.eventslist[1][3]:
                                        channel[13] = str(self.eventslist[1][3])

                                    # next description
                                    if self.eventslist[1][4]:
                                        channel[14] = str(self.eventslist[1][4])
                                except Exception as e:
                                    print(e)

                    self.epglist = []
                    self.epglist = [buildEPGListEntry(x[0], x[1], x[9], x[10], x[11], x[12], x[13], x[14], x[18], x[19]) for x in self.list2 if x[18] is False]
                    self["epg_list"].updateList(self.epglist)

                    instance = self["epg_list"].master.master.instance
                    instance.setSelectionEnable(0)
                    self.xmltvdownloaded = True
                    self.refreshEPGInfo()
                except Exception as e:
                    print(e)

    def hideEPG(self):
        # print("*** hide EPG ***")
        self["epg_list"].setList([])
        self["picon"].hide()
        self["epg_bg"].hide()
        self["x_title"].setText("")
        self["x_description"].setText("")
        if self.categoryname != "catchup":
            self["progress"].hide()

    def showEPG(self):
        # print("*** showEPGElements ***")
        self["picon"].show()
        self["epg_bg"].show()
        if self.categoryname != "catchup":
            self["progress"].show()

    def refreshEPGInfo(self):
        # print("*** refreshEPGInfo ***")

        if self["epg_list"].getCurrent():
            instance = self["epg_list"].master.master.instance
            instance.setSelectionEnable(1)

            startnowtime = self["epg_list"].getCurrent()[2]
            titlenow = self["epg_list"].getCurrent()[3]
            descriptionnow = self["epg_list"].getCurrent()[4]
            startnexttime = self["epg_list"].getCurrent()[5]

            if titlenow:
                nowTitle = "%s - %s  %s" % (startnowtime, startnexttime, titlenow)
                self["key_epg"].setText(_("Next Info"))

            else:
                nowTitle = ""
                self["key_epg"].setText("")
                instance.setSelectionEnable(0)

            self["x_title"].setText(nowTitle)
            self["x_description"].setText(descriptionnow)

            percent = 0

            if startnowtime and startnexttime:
                self["progress"].show()

                start_time = datetime.strptime(startnowtime, "%H:%M")
                end_time = datetime.strptime(startnexttime, "%H:%M")

                if end_time < start_time:
                    end_time = datetime.strptime(startnexttime, "%H:%M") + timedelta(hours=24)

                total_time = end_time - start_time
                duration = 0
                if total_time.total_seconds() > 0:
                    duration = float(total_time.total_seconds() / 60)

                now = datetime.now().strftime("%H:%M")
                current_time = datetime.strptime(now, "%H:%M")
                elapsed = current_time - start_time

                if elapsed.days < 0:
                    elapsed = timedelta(days=0, seconds=elapsed.seconds)

                elapsedmins = 0
                if elapsed.total_seconds() > 0:
                    elapsedmins = float(elapsed.total_seconds() / 60)

                if duration > 0:
                    percent = int(elapsedmins / duration * 100)
                else:
                    percent = 100

                self["progress"].setValue(percent)
            else:
                self["progress"].hide()

    def nownext(self):
        # print("*** nownext ***")
        if self["main_list"].getCurrent():
            if self.level == 2:
                if self["key_epg"].getText() and self["epg_list"].getCurrent():
                    startnowtime = self["epg_list"].getCurrent()[2]
                    titlenow = self["epg_list"].getCurrent()[3]
                    descriptionnow = self["epg_list"].getCurrent()[4]

                    startnexttime = self["epg_list"].getCurrent()[5]
                    titlenext = self["epg_list"].getCurrent()[6]
                    descriptionnext = self["epg_list"].getCurrent()[7]

                    if self["key_epg"].getText() == (_("Next Info")):
                        nextTitle = "Next %s:  %s" % (startnexttime, titlenext)
                        self["x_title"].setText(nextTitle)
                        self["x_description"].setText(descriptionnext)
                        self["key_epg"].setText(_("Now Info"))
                    else:
                        nowTitle = "%s - %s  %s" % (startnowtime, startnexttime, titlenow)
                        self["x_title"].setText(nowTitle)
                        self["x_description"].setText(descriptionnow)
                        self["key_epg"].setText(_("Next Info"))

    def shortEPG(self):
        # print("*** shortEPG ***")
        self.showingshortEPG = not self.showingshortEPG
        if self.showingshortEPG:
            self["key_menu"].setText("")

            if self["main_list"].getCurrent():
                currentindex = self["main_list"].getIndex()
                glob.nextlist[-1]["index"] = currentindex

                self["epg_list"].setList([])
                next_url = self["main_list"].getCurrent()[3]

                if self.level == 2:

                    response = ""
                    player_api = str(glob.current_playlist["playlist_info"]["player_api"])
                    stream_id = next_url.rpartition("/")[-1].partition(".")[0]

                    shortEPGJson = []

                    url = str(player_api) + "&action=get_short_epg&stream_id=" + str(stream_id) + "&limit=1000"
                    adapter = HTTPAdapter(max_retries=0)
                    http = requests.Session()
                    http.mount("http://", adapter)
                    http.mount("https://", adapter)

                    try:
                        r = http.get(url, headers=hdr, stream=True, timeout=cfg.timeout.value, verify=False)
                        r.raise_for_status()
                        if r.status_code == requests.codes.ok:
                            try:
                                response = r.json()
                            except:
                                response = ""

                    except Exception as e:
                        print(e)
                        response = ""

                    if response != "":
                        shortEPGJson = response
                        index = 0

                        self.epgshortlist = []
                        duplicatecheck = []

                        if "epg_listings" in shortEPGJson:
                            for listing in shortEPGJson["epg_listings"]:

                                title = ""
                                description = ""
                                epg_date_all = ""
                                epg_time_all = ""
                                start = ""
                                end = ""

                                if "title" in listing:
                                    title = base64.b64decode(listing["title"]).decode("utf-8")

                                if "description" in listing:
                                    description = base64.b64decode(listing["description"]).decode("utf-8")

                                shift = 0

                                if "serveroffset" in glob.current_playlist["player_info"]:
                                    shift = int(glob.current_playlist["player_info"]["serveroffset"])

                                if listing["start"] and listing["end"]:

                                    start = listing["start"]
                                    end = listing["end"]

                                    start_datetime = datetime.strptime(start, "%Y-%m-%d %H:%M:%S") + timedelta(hours=shift)
                                    try:
                                        end_datetime = datetime.strptime(end, "%Y-%m-%d %H:%M:%S") + timedelta(hours=shift)
                                    except:
                                        try:
                                            stop = listing["stop"]
                                            end_datetime = datetime.strptime(stop, "%Y-%m-%d %H:%M:%S") + timedelta(hours=shift)
                                        except:
                                            return

                                    epg_date_all = start_datetime.strftime("%a %d/%m")
                                    epg_time_all = str(start_datetime.strftime("%H:%M")) + " - " + str(end_datetime.strftime("%H:%M"))
                                    if [epg_date_all, epg_time_all] not in duplicatecheck:
                                        duplicatecheck.append([epg_date_all, epg_time_all])
                                        self.epgshortlist.append(buildShortEPGListEntry(str(epg_date_all), str(epg_time_all), str(title), str(description), index, start_datetime, end_datetime))

                                        index += 1

                            self["epg_short_list"].setList(self.epgshortlist)
                            duplicatecheck = []

                            instance = self["epg_short_list"].master.master.instance
                            instance.setSelectionEnable(1)

                            self["progress"].hide()
                            self["key_yellow"].setText("")
                            self["key_blue"].setText("")
                            self["key_epg"].setText("")

                            self.selectedlist = self["epg_short_list"]
                            self.displayShortEPG()

        else:
            self["epg_short_list"].setList([])

            self.selectedlist = self["main_list"]
            self.buildLists()
        return

    def displayShortEPG(self):
        # print("*** displayShortEPG ***")
        if self["epg_short_list"].getCurrent():
            title = str(self["epg_short_list"].getCurrent()[0])
            description = str(self["epg_short_list"].getCurrent()[3])
            timeall = str(self["epg_short_list"].getCurrent()[2])
            self["x_title"].setText(timeall + " " + title)
            self["x_description"].setText(description)
            if self.categoryname == "catchup":
                self.showEPG()

    # record button download video file
    def downloadStream(self, limitEvent=True):
        # print("*** downloadStream ***")
        from . import record
        currentindex = self["main_list"].getIndex()

        begin = int(time.time())
        end = begin + 3600
        dt_now = datetime.now()
        self.date = time.time()

        # recording name - programme title = fallback channel name
        if self.epglist[currentindex][3]:
            name = self.epglist[currentindex][3]
        else:
            name = self.epglist[currentindex][0]

        if self.epglist[currentindex][5]:  # end time
            end_dt = datetime.strptime(str(self.epglist[currentindex][5]), "%H:%M")
            end_dt = end_dt.replace(year=dt_now.year, month=dt_now.month, day=dt_now.day)
            end = int(time.mktime(end_dt.timetuple()))

        if self.showingshortEPG:
            currentindex = self["epg_short_list"].getIndex()

            if self.epgshortlist[currentindex][1]:
                shortdate_dt = datetime.strptime(self.epgshortlist[currentindex][1], "%a %d/%m")
                shortdate_dt = shortdate_dt.replace(year=dt_now.year)
                self.date = int(time.mktime(shortdate_dt.timetuple()))

            if self.epgshortlist[currentindex][2]:

                beginstring = self.epgshortlist[currentindex][2].partition(" - ")[0]
                endstring = self.epgshortlist[currentindex][2].partition(" - ")[-1]

                shortbegin_dt = datetime.strptime(beginstring, "%H:%M")
                shortbegin_dt = shortbegin_dt.replace(year=dt_now.year, month=shortdate_dt.month, day=shortdate_dt.day)
                begin = int(time.mktime(shortbegin_dt.timetuple()))

                shortend_dt = datetime.strptime(endstring, "%H:%M")
                shortend_dt = shortend_dt.replace(year=dt_now.year, month=shortdate_dt.month, day=shortdate_dt.day)
                end = int(time.mktime(shortend_dt.timetuple()))

            if self.epgshortlist[currentindex][0]:
                name = self.epgshortlist[currentindex][0]

        self.name = NoSave(ConfigText(default=name, fixed_size=False))
        self.starttime = NoSave(ConfigClock(default=begin))
        self.endtime = NoSave(ConfigClock(default=end))

        self.session.openWithCallback(self.RecordDateInputClosed, record.RecordDateInput, self.name, self.date, self.starttime, self.endtime)

    def RecordDateInputClosed(self, data=None):
        # print("*** RecordDateInputClosed ***")
        if data:
            begin = data[1]
            end = data[2]
            name = data[3]

            currentindex = self["main_list"].getIndex()
            description = ""
            streamurl = self["main_list"].getCurrent()[3]
            direct_source = self["main_list"].getCurrent()[7]
            streamtype = 1

            if self.epglist[currentindex][4]:
                description = self.epglist[currentindex][4]

            if self.showingshortEPG:
                currentindex = self["epg_short_list"].getIndex()
                if self.epgshortlist[currentindex][3]:
                    description = str(self.epgshortlist[currentindex][3])

            eventid = int(streamurl.rpartition("/")[-1].partition(".")[0])

            if streamurl.endswith("m3u8"):
                streamtype = 4097

            self.reference = eServiceReference(streamtype, 0, streamurl)
            if direct_source:
                self.reference = eServiceReference(streamtype, 0, direct_source)

            # switch channel to prevent multi active users
            if self.session.nav.getCurrentlyPlayingServiceReference().toString() != self.reference.toString():
                self.session.nav.stopService()
                self.session.nav.playService(self.reference)

                if self.session.nav.getCurrentlyPlayingServiceReference():
                    glob.newPlayingServiceRef = self.session.nav.getCurrentlyPlayingServiceReference()
                    glob.newPlayingServiceRefString = glob.newPlayingServiceRef.toString()

            if isinstance(self.reference, eServiceReference):
                serviceref = ServiceReference(self.reference)

            recording = RecordTimerEntry(serviceref, begin, end, name, description, eventid, dirname=str(cfg.downloadlocation.getValue()))
            recording.dontSave = True

            simulTimerList = self.session.nav.RecordTimer.record(recording)

            if simulTimerList is None:  # no conflict
                recording.autoincrease = False
                self.session.open(MessageBox, _("Recording Timer Set."), MessageBox.TYPE_INFO, timeout=5)
            else:
                self.session.open(MessageBox, _("Recording Failed."), MessageBox.TYPE_WARNING)
        return

    def downloadXMLTVdata(self):
        # print("*** downloadXMLTVdata ***")
        if epgimporter is False:
            return

        url = str(glob.current_playlist["playlist_info"]["player_api"]) + "&action=get_live_streams"
        tmpfd, tempfilename = tempfile.mkstemp()

        parsed = urlparse(url)
        domain = parsed.hostname
        scheme = parsed.scheme

        if pythonVer == 3:
            url = url.encode()

        if scheme == "https" and sslverify:
            sniFactory = SNIFactory(domain)
            downloadPage(url, tempfilename, sniFactory).addCallback(self.downloadComplete).addErrback(self.downloadFail)
        else:
            downloadPage(url, tempfilename).addCallback(self.downloadComplete, tempfilename).addErrback(self.downloadFail)

        os.close(tmpfd)

    def downloadFail(self, failure):
        # print("*** downloadFail ***")
        print(("[EPG] download failed:", failure))

    def downloadComplete(self, data, filename):
        # print("***** download complete ****")
        channellist_all = []
        with open(filename, "r+b") as f:
            try:
                channellist_all = json.load(f)
                self.xmltv_channel_list = []
                for channel in channellist_all:

                    self.xmltv_channel_list.append({"name": str(channel["name"]), "stream_id": str(channel["stream_id"]), "epg_channel_id": str(channel["epg_channel_id"]), "custom_sid": channel["custom_sid"]})
            except:
                pass

        os.remove(filename)
        self.buildXMLTV()

    def buildXMLTV(self):
        # print("***** buildXMLTV ****")

        safeName = re.sub(r'[\<\>\:\"\/\\\|\?\*]', "_", str(glob.current_playlist["playlist_info"]["name"]))
        safeName = re.sub(r" ", "_", safeName)
        safeName = re.sub(r"_+", "_", safeName)

        filepath = "/etc/epgimport/"
        epgfilename = "xstreamity." + str(safeName) + ".channels.xml"
        channelpath = filepath + epgfilename

        # if xmltv file doesn't already exist, create file and build.
        if not os.path.isfile(channelpath):
            open(channelpath, "a").close()

        # buildXMLTVSourceFile
        # print("*** new xml code ***")

        sourcefile = "/etc/epgimport/xstreamity.sources.xml"
        if not os.path.isfile(sourcefile) or os.stat(sourcefile).st_size == 0:
            with open(sourcefile, "w") as f:
                xml_str = '<?xml version="1.0" encoding="utf-8"?>\n'
                xml_str += '<sources>\n'
                xml_str += '<sourcecat sourcecatname="XStreamity EPG">\n'
                xml_str += '</sourcecat>\n'
                xml_str += '</sources>\n'
                f.write(xml_str)

        import xml.etree.ElementTree as ET

        tree = ET.parse(sourcefile)
        root = tree.getroot()
        sourcecat = root.find("sourcecat")

        exists = False
        for sourceitem in sourcecat:
            if channelpath in sourceitem.attrib["channels"]:
                exists = True
                break

        if exists is False:
            source = ET.SubElement(sourcecat, "source", type="gen_xmltv", nocheck="1", channels=channelpath)
            description = ET.SubElement(source, "description")
            description.text = str(safeName)

            url = ET.SubElement(source, "url")
            url.text = str(glob.current_playlist["playlist_info"]["xmltv_api"])

            tree.write(sourcefile)

        # buildXMLTVChannelFile
        with open(channelpath, "w") as f:
            xml_str = '<?xml version="1.0" encoding="utf-8"?>\n'
            xml_str += '<channels>\n'

            for i in range(len(self.xmltv_channel_list)):

                channelid = self.xmltv_channel_list[i]["epg_channel_id"]
                if channelid and "&" in channelid:
                    channelid = channelid.replace("&", "&amp;")
                bouquet_id = 0

                stream_id = int(self.xmltv_channel_list[i]["stream_id"])
                calc_remainder = int(stream_id) // 65535
                bouquet_id = bouquet_id + calc_remainder
                stream_id = int(stream_id) - int(calc_remainder * 65535)

                unique_ref = 999 + int(glob.current_playlist["playlist_info"]["index"])

                serviceref = "1:0:1:" + str(format(bouquet_id, "04x")) + ":" + str(format(stream_id, "04x")) + ":" + str(format(unique_ref, "08x")) + ":0:0:0:0:" + "http%3a//example.m3u8"

                if "custom_sid" in self.xmltv_channel_list[i]:
                    if self.xmltv_channel_list[i]["custom_sid"] and self.xmltv_channel_list[i]["custom_sid"] != "None":
                        if self.xmltv_channel_list[i]["custom_sid"].startswith(":"):
                            self.xmltv_channel_list[i]["custom_sid"] = "1" + self.xmltv_channel_list[i]["custom_sid"]
                        serviceref = str(":".join(self.xmltv_channel_list[i]["custom_sid"].split(":")[:7])) + ":0:0:0:" + "http%3a//example.m3u8"

                self.xmltv_channel_list[i]["serviceref"] = str(serviceref)
                name = self.xmltv_channel_list[i]["name"]

                if channelid and channelid != "None":
                    xml_str += '<channel id="' + str(channelid) + '">' + str(serviceref) + '</channel><!--' + str(name) + '-->\n'

            xml_str += '</channels>\n'
            f.write(xml_str)

        self.buildLists()

    def epgminus(self):
        self.epgtimeshift -= 1
        if self.epgtimeshift <= 0:
            self.epgtimeshift = 0
        self.addEPG()

    def epgplus(self):
        self.epgtimeshift += 1
        self.addEPG()

    def epgreset(self):
        self.epgtimeshift = 0
        self.addEPG()

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
        self["x_title"].setText(self.searchtitle.strip())
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

    def downloadVodData(self):
        # print("*** downloadVodData ***")
        if self["main_list"].getCurrent():
            stream_id = self["main_list"].getCurrent()[4]
            url = str(glob.current_playlist["playlist_info"]["player_api"]) + "&action=get_vod_info&vod_id=" + str(stream_id)
            self.info = ""

            adapter = HTTPAdapter(max_retries=0)
            http = requests.Session()
            http.mount("http://", adapter)
            http.mount("https://", adapter)
            try:
                r = http.get(url, headers=hdr, stream=True, timeout=cfg.timeout.value, verify=False)
                r.raise_for_status()
                if r.status_code == requests.codes.ok:
                    content = r.json()

                if "info" in content and content["info"]:
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
                    if cfg.channelcovers.value is True:
                        self.downloadImage()
                    self.displayTMDB()

            except Exception as e:
                print(e)

    def downloadVideo(self):
        # load x-downloadlist.json file

        if self.categoryname == "series" and self.level != 4:
            return

        if self.categoryname == "catchup" and self.selectedlist != self["epg_short_list"]:
            return

        if self["main_list"].getCurrent():

            if self.categoryname == "catchup":
                next_url = self["main_list"].getCurrent()[3]
                stream = next_url.rpartition("/")[-1]
                date = str(self["epg_short_list"].getCurrent()[4])
                duration = str(self["epg_short_list"].getCurrent()[5])
                playurl = "%s/timeshift/%s/%s/%s/%s/%s" % (self.host, self.username, self.password, duration, date, stream)

                date_all = str(self["epg_short_list"].getCurrent()[1]).strip()
                time_all = str(self["epg_short_list"].getCurrent()[2]).strip()
                time_start = time_all.partition(" - ")[0].strip()
                current_year = int(datetime.now().year)
                date = str(datetime.strptime(str(current_year) + str(date_all) + str(time_start), "%Y%a %d/%m%H:%M")).replace("-", "").replace(":", "")[:-2]

                otitle = str(self["epg_short_list"].getCurrent()[0])
                channel = str(self["main_list"].getCurrent()[0])
                title = str(date) + " - " + str(channel) + " - " + str(otitle)

            else:
                title = self["main_list"].getCurrent()[0]
                stream_url = self["main_list"].getCurrent()[3]

                """
                if self.categoryname == "live":
                    direct_source = self["main_list"].getCurrent()[7]

                if self.categoryname == "vod":
                    direct_source = self["main_list"].getCurrent()[10]

                if self.categoryname == "series":
                    direct_source = self["main_list"].getCurrent()[18]

                if direct_source:
                    stream_url = direct_source
                    """

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

                if self.categoryname == "vod" or self.categoryname == "series":
                    if stream_url == url:
                        exists = True

                if self.categoryname == "catchup":
                    if playurl == url:
                        exists = True

            if exists is False:
                if self.categoryname == "vod":
                    downloads_all.append([_("Movie"), title, stream_url, _("Not Started"), 0, 0])
                elif self.categoryname == "series":
                    downloads_all.append([_("Series"), title, stream_url, _("Not Started"), 0, 0])
                elif self.categoryname == "catchup":
                    downloads_all.append([_("Catch-up"), title, playurl, _("Not Started"), 0, 0])

                with open(downloads_json, "w") as f:
                    json.dump(downloads_all, f)

                self.session.open(MessageBox, _(title) + "\n\n" + _("Added to download manager"), MessageBox.TYPE_INFO, timeout=5)
            else:
                self.session.open(MessageBox, _(title) + "\n\n" + _("Already added to download manager"), MessageBox.TYPE_ERROR, timeout=5)

    def getTMDB(self):
        # print("**** getTMDB ***")
        title = ""
        searchtitle = ""
        self.searchtitle = ""
        self.isIMDB = False
        self.tmdb_id_exists = False

        try:
            os.remove(str(dir_tmp) + "search.txt")
        except:
            pass

        if self.categoryname == "vod":
            next_url = self["main_list"].getCurrent()[3]

            if next_url != "None" and "/movie/" in next_url:
                title = self["main_list"].getCurrent()[0]

                if self.info:
                    if "name" in self.info and self.info["name"]:
                        title = self.info["name"]
                    elif "o_name" in self.info and self.info["o_name"]:
                        title = self.info["o_name"]

                    if "tmdb_id" in self.info and self.info["tmdb_id"]:
                        if str(self.info["tmdb_id"])[:1].isdigit():
                            self.getTMDBDetails(self.info["tmdb_id"])
                            self.tmdb_id_exists = True
                        else:
                            self.isIMDB = True

        elif self.categoryname == "series":
            if self.level == 2:
                title = self["main_list"].getCurrent()[0]
                self.storedtitle = title
            else:
                title = self.storedtitle

            if self.level == 3:
                self.storedseason = self["main_list"].getCurrent()[12]

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

        searchtitle = searchtitle.replace(".", " ")
        searchtitle = searchtitle.replace("_", " ")
        searchtitle = searchtitle.replace("  ", " ")
        searchtitle = searchtitle.replace(" ", "%20")
        searchtitle = searchtitle.strip()

        self.searchtitle = searchtitle.replace("%20", " ").title()

        if self.tmdb_id_exists:
            return

        if self.categoryname == "vod":
            if self.isIMDB is False:
                searchurl = "http://api.themoviedb.org/3/search/movie?api_key=" + str(self.check(self.token)) + "&query=%22" + str(searchtitle) + "%22"
            else:
                searchurl = "http://api.themoviedb.org/3/find/" + str(self.info["tmdb_id"]) + "?api_key=" + str(self.check(self.token)) + "&external_source=imdb_id"

        elif self.categoryname == "series":
            searchurl = "http://api.themoviedb.org/3/search/tv?api_key=" + str(self.check(self.token)) + "&query=%22" + str(searchtitle) + "%22"

        if pythonVer == 3:
            searchurl = searchurl.encode()

        filepath = str(dir_tmp) + "search.txt"
        try:
            downloadPage(searchurl, filepath, timeout=10).addCallback(self.processTMDB).addErrback(self.failed)
        except Exception as e:
            print(("download TMDB error %s" % e))

    def failed(self, data=None):
        if data:
            print(data)

    def processTMDB(self, result=None):
        # print("*** processTMDB ***")
        IMDB = self.isIMDB
        with codecs.open(str(dir_tmp) + "search.txt", "r", encoding="utf-8") as f:
            response = f.read()

        if response != "":
            try:
                self.searchresult = json.loads(response)
                if IMDB is False or self.categoryname == "series":
                    if "results" in self.searchresult and self.searchresult["results"]:
                        if "id" in self.searchresult["results"][0]:
                            resultid = self.searchresult["results"][0]["id"]
                        else:
                            return
                    else:
                        self.clearVod()
                else:
                    if "movie_results" in self.searchresult and self.searchresult["movie_results"]:
                        if "id" in self.searchresult["movie_results"][0]:
                            resultid = self.searchresult["movie_results"][0]["id"]
                        else:

                            return

                self.getTMDBDetails(resultid)
            except:
                pass

    def getTMDBDetails(self, resultid=None):
        # print(" *** getTMDBDetails ***")
        detailsurl = ""

        try:
            os.remove(str(dir_tmp) + "tmdb.txt")
        except:
            pass

        language = "en"

        if cfg.TMDB.value is True:
            language = cfg.TMDBLanguage.value

        if self.categoryname == "vod":
            detailsurl = "http://api.themoviedb.org/3/movie/" + str(resultid) + "?api_key=" + str(self.check(self.token)) + "&append_to_response=credits&language=" + str(language)

        elif self.categoryname == "series":
            if self.level == 2:
                detailsurl = "http://api.themoviedb.org/3/tv/" + str(resultid) + "?api_key=" + str(self.check(self.token)) + "&append_to_response=credits&language=" + str(language)

            if self.level == 3 or self.level == 4:
                detailsurl = "http://api.themoviedb.org/3/tv/" + str(resultid) + "/season/" + str(self.storedseason) + "?api_key=" + str(self.check(self.token)) + "&append_to_response=credits&language=" + str(language)

        if pythonVer == 3:
            detailsurl = detailsurl.encode()

        filepath = str(dir_tmp) + "tmdb.txt"
        try:
            downloadPage(detailsurl, filepath, timeout=10).addCallback(self.processTMDBDetails).addErrback(self.failed)
        except Exception as e:
            print(("download TMDB details error %s" % e))

    def processTMDBDetails(self, result=None):
        # print("*** processTMDBDetails ***")
        valid = False
        response = ""
        self.info = {}
        self.detailsresult = []
        director = []

        try:
            with codecs.open(str(dir_tmp) + "tmdb.txt", "r", encoding="utf-8") as f:
                response = f.read()
        except:
            pass

        if response != "":
            valid = False
            try:
                self.detailsresult = json.loads(response, object_pairs_hook=OrderedDict)

                valid = True
            except Exception as e:
                print(e)

            if self.categoryname == "series" and self.level == 4:
                episodes = self.detailsresult["episodes"]
                result = False
                for episode in episodes:
                    if episode["name"] == str(self["main_list"].getCurrent()[0]):
                        self.detailsresult = episode
                        result = True
                        break

                if result is False:
                    for episode in episodes:
                        try:
                            if episode["episode_number"] == str(self["main_list"].getCurrent()[0]).partition(" ")[-1]:
                                self.detailsresult = episode
                                result = True
                                break
                        except Exception as e:
                            print(e)

            if valid:
                if self.categoryname == "vod":
                    if "title" in self.detailsresult and self.detailsresult["title"]:
                        self.info["name"] = str(self.detailsresult["title"])

                    if "original_title" in self.detailsresult and self.detailsresult["original_title"]:
                        self.info["o_name"] = str(self.detailsresult["original_title"])

                    if "runtime" in self.detailsresult and self.detailsresult["runtime"] and self.detailsresult["runtime"] != 0:
                        self.info["duration"] = str(timedelta(minutes=self.detailsresult["runtime"]))

                    if "production_countries" in self.detailsresult and self.detailsresult["production_countries"]:
                        country = []
                        for pcountry in self.detailsresult["production_countries"]:
                            country.append(str(pcountry["name"]))
                        country = ", ".join(map(str, country))
                        self.info["country"] = country

                    if "release_date" in self.detailsresult and self.detailsresult["release_date"]:
                        self.info["releaseDate"] = str(self.detailsresult["release_date"])

                elif self.categoryname == "series":
                    if "name" in self.detailsresult and self.detailsresult["name"]:
                        self.info["name"] = str(self.detailsresult["name"])

                    if "original_name" in self.detailsresult and self.detailsresult["original_name"]:
                        self.info["o_name"] = str(self.detailsresult["original_name"])

                    if "episode_run_time" in self.detailsresult and self.detailsresult["episode_run_time"] and self.detailsresult["episode_run_time"] != 0:
                        self.info["duration"] = str(timedelta(minutes=self.detailsresult["episode_run_time"][0]))

                    if "first_air_date" in self.detailsresult and self.detailsresult["first_air_date"]:
                        self.info["releaseDate"] = str(self.detailsresult["first_air_date"])

                    if "air_date" in self.detailsresult and self.detailsresult["air_date"]:
                        self.info["releaseDate"] = str(self.detailsresult["air_date"])

                if "poster_path" in self.detailsresult and self.detailsresult["poster_path"]:
                    if screenwidth.width() <= 1280:
                        self.info["cover_big"] = "http://image.tmdb.org/t/p/w300" + str(self.detailsresult["poster_path"])
                    else:
                        self.info["cover_big"] = "http://image.tmdb.org/t/p/w400" + str(self.detailsresult["poster_path"])

                if "overview" in self.detailsresult and self.detailsresult["overview"]:
                    self.info["description"] = str(self.detailsresult["overview"])

                if "vote_average" in self.detailsresult and self.detailsresult["vote_average"] and self.detailsresult["vote_average"] != 0:
                    self.info["rating"] = str(self.detailsresult["vote_average"])

                if "genres" in self.detailsresult and self.detailsresult["genres"]:
                    genre = []
                    for genreitem in self.detailsresult["genres"]:
                        genre.append(str(genreitem["name"]))
                    genre = " / ".join(map(str, genre))
                    self.info["genre"] = genre

                if "credits" in self.detailsresult:
                    if "cast" in self.detailsresult["credits"] and self.detailsresult["credits"]["cast"]:
                        cast = []
                        for actor in self.detailsresult["credits"]["cast"]:
                            if "character" in actor and "name" in actor:
                                cast.append(str(actor["name"]))
                        cast = ", ".join(map(str, cast[:5]))
                        self.info["cast"] = cast

                if "credits" in self.detailsresult and "crew" in self.detailsresult["credits"]:
                    directortext = False
                    for actor in self.detailsresult["credits"]["crew"]:
                        if "job" in actor and actor["job"] == "Director":
                            director.append(str(actor["name"]))
                            directortext = True
                    if directortext:
                        director = ", ".join(map(str, director))
                        self.info["director"] = director
                    else:
                        self.info["director"] = self["vod_director"].getText()

                if cfg.channelcovers.value is True:
                    self.downloadImage()
                self.displayTMDB()

    def displayTMDB(self):
        # print("*** displayTMDB ***")
        if self["main_list"].getCurrent() and self.info and self.level >= 2:

            stream_url = self["main_list"].getCurrent()[3]

            if "name" in self.info:
                self["x_title"].setText(str(self.info["name"]).strip())
            elif "o_name" in self.info:
                self["x_title"].setText(str(self.info["o_name"]).strip())

            if "description" in self.info:
                self["x_description"].setText(str(self.info["description"]).strip())
            elif "plot" in self.info:
                self["x_description"].setText(str(self.info["plot"]).strip())

            if self.categoryname == "vod" or self.level == 4:
                try:
                    self["vod_video_type"].setText(stream_url.split(".")[-1])
                except:
                    pass
            if self.categoryname == "series" and self.level != 4:
                self["vod_video_type"].setText("")

            if "duration" in self.info:
                self["vod_duration"].setText(str(self.info["duration"]).strip())

            if "genre" in self.info:
                self["vod_genre"].setText(str(self.info["genre"]).strip())

            if "rating" in self.info:
                self["vod_rating"].setText(str(self.info["rating"]).strip())

            if "country" in self.info:
                self["vod_country"].setText(str(self.info["country"]).strip())

            if "releasedate" in self.info and self.info["releasedate"]:
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

    def imdb(self):
        if self["main_list"].getCurrent():
            if self.level == 2:
                self.openIMDb()

    def openIMDb(self):
        try:
            from Plugins.Extensions.IMDb.plugin import IMDB
            try:
                name = str(self.searchtitle)
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

    # code for natural sorting of numbers in string
    def atoi(self, text):
        return int(text) if text.isdigit() else text

    def natural_keys(self, text):
        return [self.atoi(c) for c in re.split(r"(\d+)", text[1])]

    def displaySeriesData(self):
        # print("*** displaySeriesData ***")
        if self["main_list"].getCurrent():
            current = self["main_list"].getCurrent()

            if self.level == 2 or self.level == 3:
                if cfg.TMDB.value is True:
                    self.getTMDB()
                else:
                    if cfg.channelcovers.value is True:
                        self.downloadImage()

            if self.level != 1:
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

            if self.level == 4:
                self["vod_duration"].setText(current[12])
                self["vod_video_type"].setText(current[13])

    def playCatchup(self):
        next_url = self["main_list"].getCurrent()[3]
        stream = next_url.rpartition("/")[-1]

        date = str(self["epg_short_list"].getCurrent()[4])

        duration = str(self["epg_short_list"].getCurrent()[5])

        playurl = "%s/timeshift/%s/%s/%s/%s/%s" % (self.host, self.username, self.password, duration, date, stream)
        if next_url != "None" and "/live/" in next_url:
            streamtype = glob.current_playlist["player_info"]["vodtype"]
            self.reference = eServiceReference(int(streamtype), 0, str(playurl))
            glob.catchupdata = [str(self["epg_short_list"].getCurrent()[0]), str(self["epg_short_list"].getCurrent()[3])]
            self.session.openWithCallback(self.createSetup, streamplayer.XStreamity_CatchupPlayer, str(playurl), str(streamtype))
        else:
            from Screens.MessageBox import MessageBox
            self.session.open(MessageBox, _("Catchup error. No data for this slot"), MessageBox.TYPE_WARNING, timeout=5)

    def catchupEPG(self):
        if self["main_list"].getCurrent():
            next_url = self["main_list"].getCurrent()[3]

            if next_url != "None":
                if "/live/" in next_url:
                    stream_id = next_url.rpartition("/")[-1].partition(".")[0]
                    response = ""
                    shortEPGJson = []

                    url = str(self.simpledatatable) + str(stream_id)

                    adapter = HTTPAdapter(max_retries=0)
                    http = requests.Session()
                    http.mount("http://", adapter)
                    http.mount("https://", adapter)

                    try:
                        r = http.get(url, headers=hdr, stream=True, timeout=cfg.timeout.value, verify=False)
                        r.raise_for_status()
                        if r.status_code == requests.codes.ok:
                            try:
                                response = r.json()
                            except:
                                response = ""

                    except Exception as e:
                        print(e)
                        response = ""

                    if response != "":
                        shortEPGJson = response
                        index = 0
                        self.epgshortlist = []
                        duplicatecheck = []

                        if "epg_listings" in shortEPGJson:
                            if shortEPGJson["epg_listings"]:
                                for listing in shortEPGJson["epg_listings"]:
                                    if ("has_archive" in listing and listing["has_archive"] == 1) or ("now_playing" in listing and listing["now_playing"] == 1):

                                        title = ""
                                        description = ""
                                        epg_date_all = ""
                                        epg_time_all = ""
                                        start = ""
                                        end = ""

                                        catchupstart = int(cfg.catchupstart.getValue())
                                        catchupend = int(cfg.catchupend.getValue())

                                        if "title" in listing:
                                            title = base64.b64decode(listing["title"]).decode("utf-8")

                                        if "description" in listing:
                                            description = base64.b64decode(listing["description"]).decode("utf-8")

                                        shift = 0

                                        if "serveroffset" in glob.current_playlist["player_info"]:
                                            shift = int(glob.current_playlist["player_info"]["serveroffset"])

                                        if listing["start"] and listing["end"]:

                                            start = listing["start"]
                                            end = listing["end"]

                                            start_datetime_original = datetime.strptime(start, "%Y-%m-%d %H:%M:%S")
                                            start_datetime_offset = datetime.strptime(start, "%Y-%m-%d %H:%M:%S") + timedelta(hours=shift)
                                            start_datetime_margin = datetime.strptime(start, "%Y-%m-%d %H:%M:%S") + timedelta(hours=shift) - timedelta(minutes=catchupstart)

                                            try:
                                                # end_datetime_original = datetime.strptime(end, "%Y-%m-%d %H:%M:%S")
                                                end_datetime_offset = datetime.strptime(end, "%Y-%m-%d %H:%M:%S") + timedelta(hours=shift)
                                                end_datetime_margin = datetime.strptime(end, "%Y-%m-%d %H:%M:%S") + timedelta(hours=shift) + timedelta(minutes=catchupend)
                                            except:
                                                try:
                                                    end = listing["stop"]
                                                    # end_datetime_original = datetime.strptime(end, "%Y-%m-%d %H:%M:%S")
                                                    end_datetime_offset = datetime.strptime(end, "%Y-%m-%d %H:%M:%S") + timedelta(hours=shift)
                                                    end_datetime_margin = datetime.strptime(end, "%Y-%m-%d %H:%M:%S") + timedelta(hours=shift) + timedelta(minutes=catchupend)
                                                except:
                                                    return

                                            epg_date_all = start_datetime_offset.strftime("%a %d/%m")
                                            epg_time_all = str(start_datetime_offset.strftime("%H:%M")) + " - " + str(end_datetime_offset.strftime("%H:%M"))

                                        epg_duration = int((end_datetime_margin - start_datetime_margin).total_seconds() / 60.0)

                                        url_datestring = str(start_datetime_original.strftime("%Y-%m-%d:%H-%M"))

                                        if [epg_date_all, epg_time_all] not in duplicatecheck:
                                            duplicatecheck.append([epg_date_all, epg_time_all])
                                            self.epgshortlist.append(buildCatchupEPGListEntry(str(epg_date_all), str(epg_time_all), str(title), str(description), str(url_datestring), str(epg_duration), index))

                                            index += 1

                                self.epgshortlist.reverse()
                                self["epg_short_list"].setList(self.epgshortlist)
                                duplicatecheck = []

                                if self["epg_short_list"].getCurrent():
                                    glob.catchupdata = [str(self["epg_short_list"].getCurrent()[0]), str(self["epg_short_list"].getCurrent()[3])]
                                instance = self["epg_short_list"].master.master.instance
                                instance.setSelectionEnable(1)

                                self.selectedlist = self["epg_short_list"]
                                self.displayShortEPG()
                            else:
                                self.session.open(MessageBox, _("Catchup currently not available. Missing EPG data"), type=MessageBox.TYPE_INFO, timeout=5)
        return

    def reverse(self):
        self.epgshortlist.reverse()
        self["epg_short_list"].setList(self.epgshortlist)


def buildEPGListEntry(index, title, epgNowTime, epgNowTitle, epgNowDesc, epgNextTime, epgNextTitle, epgNextDesc, hidden, direct_source):
    return (title, index, epgNowTime, epgNowTitle, epgNowDesc, epgNextTime, epgNextTitle, epgNextDesc, hidden, direct_source)


def buildShortEPGListEntry(date_all, time_all, title, description, index, start_datetime, end_datetime):
    return (title, date_all, time_all, description, index, start_datetime, end_datetime)


def buildCategoryList(index, title, category_id, hidden):
    png = LoadPixmap(common_path + "more.png")
    return (title, png, index, category_id, hidden)


def buildLiveStreamList(index, name, stream_id, stream_icon, next_url, favourite, watching, hidden, direct_source):
    png = LoadPixmap(common_path + "play.png")
    if favourite:
        png = LoadPixmap(common_path + "favourite.png")
    if watching:
        png = LoadPixmap(common_path + "watching.png")
    return (name, png, index, next_url, stream_id, stream_icon, hidden, direct_source)


def buildVodStreamList(index, title, stream_id, stream_icon, added, rating, next_url, favourite, container_extension, hidden, direct_source):
    png = LoadPixmap(common_path + "play.png")
    if favourite:
        png = LoadPixmap(common_path + "favourite.png")
    return (title, png, index, next_url, stream_id, stream_icon, added, rating, container_extension, hidden, direct_source)


def buildSeriesTitlesList(index, title, series_id, cover, plot, cast, director, genre, releaseDate, rating, lastmodified, next_url, hidden):
    png = LoadPixmap(common_path + "more.png")
    return (title, png, index, next_url, series_id, cover, plot, cast, director, genre, releaseDate, rating, lastmodified, hidden)


def buildSeriesSeasonsList(index, title, series_id, cover, plot, cast, director, genre, airDate, rating, season_number, next_url, lastmodified, hidden):
    png = LoadPixmap(common_path + "more.png")
    return (title, png, index, next_url, series_id, cover, plot, cast, director, genre, airDate, rating, season_number, lastmodified, hidden)


def buildSeriesEpisodesList(index, title, series_id, cover, plot, cast, director, genre, releaseDate, rating, duration, container_extension, tmdb_id, next_url, shorttitle, lastmodified, hidden, direct_source):
    png = LoadPixmap(common_path + "play.png")
    return (title, png, index, next_url, series_id, cover, plot, cast, director, genre, releaseDate, rating, duration, container_extension, tmdb_id, shorttitle, lastmodified, hidden, direct_source)


def buildCatchupStreamList(index, title, stream_id, stream_icon, epg_channel_id, added, next_url, hidden):
    png = LoadPixmap(common_path + "more.png")
    return (title, png, index, next_url, stream_id, stream_icon, epg_channel_id, added, hidden)


def buildCatchupEPGListEntry(date_all, time_all, title, description, start, duration, index):
    return (title, date_all, time_all, description, start, duration, index)
