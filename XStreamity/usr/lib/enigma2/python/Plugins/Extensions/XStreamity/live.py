#!/usr/bin/python
# -*- coding: utf-8 -*-

from . import _
from . import streamplayer
from . import xstreamity_globals as glob

from .plugin import skin_directory, screenwidth, hdr, cfg, common_path, dir_tmp, playlists_json, pythonVer
from .xStaticText import StaticText

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
from datetime import datetime, timedelta
from enigma import eTimer, eServiceReference, eEPGCache
from requests.adapters import HTTPAdapter, Retry
from twisted.web.client import downloadPage
from itertools import cycle, islice
try:
    from xml.dom import minidom
except:
    pass

try:
    from urlparse import urlparse
except:
    from urllib.parse import urlparse

import base64
import codecs
import json
import math
import os
import re
import requests
import sys
import tempfile
import time

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


class XStreamity_Categories(Screen):
    ALLOW_SUSPEND = True

    def __init__(self, session):
        # print("*** init ***")
        Screen.__init__(self, session)
        self.session = session
        glob.categoryname = "live"

        self.skin_path = os.path.join(skin_directory, cfg.skin.getValue())
        skin = os.path.join(self.skin_path, "live_categories.xml")
        if os.path.exists("/var/lib/dpkg/status"):
            skin = os.path.join(self.skin_path, "DreamOS/live_categories.xml")

        with codecs.open(skin, "r", encoding="utf-8") as f:
            self.skin = f.read()

        self.setup_title = (_("Live Categories"))
        self.main_title = (_("Live Streams"))

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

        self.sortindex = 0
        self.sortText = (_("Sort: A-Z"))

        self.epgtimeshift = 0
        self.level = 1

        self.selectedlist = self["main_list"]

        self.host = glob.current_playlist["playlist_info"]["host"]
        self.username = glob.current_playlist["playlist_info"]["username"]
        self.password = glob.current_playlist["playlist_info"]["password"]
        self.output = glob.current_playlist["playlist_info"]["output"]
        self.name = glob.current_playlist["playlist_info"]["name"]

        self.player_api = glob.current_playlist["playlist_info"]["player_api"]

        self.liveStreamsData = []

        next_url = str(self.player_api) + "&action=get_live_categories"

        full_url = glob.current_playlist["playlist_info"]["full_url"]

        self.unique_ref = 0

        for j in str(full_url):
            value = ord(j)
            self.unique_ref += value

        epglocation = str(cfg.epglocation.value)
        self.epgfolder = os.path.join(epglocation, str(self.name))
        self.epgjsonfile = os.path.join(self.epgfolder, "epg.json")

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

        glob.nextlist = []
        glob.nextlist.append({"next_url": next_url, "index": 0, "level": self.level, "sort": self.sortText, "filter": ""})

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
            if glob.current_playlist["data"]["customsids"] is True:
                self.timer = eTimer()
                try:
                    self.timer_conn = self.timer.timeout.connect(self.xmltvCheckData)
                except:
                    try:
                        self.timer.callback.append(self.xmltvCheckData)
                    except:
                        self.xmltvCheckData()
                self.timer.start(50, True)

        else:
            self.getLevel2()

        self.buildLists()

    def buildLists(self):
        # print("*** buildLists ***")
        if self.level == 1:
            self.buildList1()
        else:
            self.buildList2()

        self.buttons()
        self.selectionChanged()

    def getCategories(self):
        # print("*** getCategories **")
        index = 0
        self.list1 = []
        self.prelist = []

        currentCategoryList = glob.current_playlist["data"]["live_categories"]
        currentHidden = glob.current_playlist["player_info"]["livehidden"]

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

    def getLevel2(self):
        # print("*** getLevel2 ***")

        response = self.downloadApiData(glob.nextlist[-1]["next_url"])

        if self.favourites_category:
            response = glob.current_playlist["player_info"]["livefavourites"]

        elif self.recents_category:
            response = glob.current_playlist["player_info"]["liverecents"]

        index = 0

        self.list2 = []
        currentChannelList = response
        for channel in currentChannelList:
            name = ""
            stream_id = ""
            stream_icon = ""
            epg_channel_id = ""
            added = ""
            category_id = ""
            custom_sid = ""
            service_ref = ""
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

            if "name" in channel and channel["name"]:
                name = channel["name"]

                # restyle bouquet markers
                if "stream_type" in channel and channel["stream_type"] and channel["stream_type"] != "live":
                    pattern = re.compile(r"[^\w\s()\[\]]", re.U)
                    name = re.sub(r"_", "", re.sub(pattern, "", name))
                    name = "** " + str(name) + " **"

            if "stream_id" in channel and channel["stream_id"]:
                stream_id = channel["stream_id"]

                if str(stream_id) in glob.current_playlist["player_info"]["channelshidden"]:
                    hidden = True
            else:
                continue

            if "stream_icon" in channel and channel["stream_icon"]:
                if channel["stream_icon"].startswith("http"):
                    stream_icon = channel["stream_icon"]

                if stream_icon.startswith("https://vignette.wikia.nocookie.net/tvfanon6528"):
                    if "scale-to-width-down" not in stream_icon:
                        stream_icon = str(stream_icon) + "/revision/latest/scale-to-width-down/220"

            if "epg_channel_id" in channel and channel["epg_channel_id"]:
                epg_channel_id = channel["epg_channel_id"]

                if epg_channel_id and "&" in epg_channel_id:
                    epg_channel_id = epg_channel_id.replace("&", "&amp;")

            if "added" in channel and channel["added"]:
                added = channel["added"]

            if "category_id" in channel and channel["category_id"]:
                category_id = channel["category_id"]

            if "direct_source" in channel and channel["direct_source"]:
                direct_source = channel["direct_source"]

            bouquet_id1 = 0
            calc_remainder = int(stream_id) // 65535
            bouquet_id1 = bouquet_id1 + calc_remainder
            bouquet_id2 = int(stream_id) - int(calc_remainder * 65535)

            service_ref = "1:0:1:" + str(format(bouquet_id1, "x")) + ":" + str(format(bouquet_id2, "x")) + ":" + str(format(self.unique_ref, "x")) + ":0:0:0:0:" + "http%3a//example.m3u8"

            if "custom_sid" in channel and channel["custom_sid"]:
                if channel["custom_sid"] != "null" and channel["custom_sid"] != "None" and channel["custom_sid"] is not None and channel["custom_sid"] != "0":
                    if channel["custom_sid"][0].isdigit():
                        channel["custom_sid"] = "1" + channel["custom_sid"][1:]

                    service_ref = str(":".join(channel["custom_sid"].split(":")[:7])) + ":0:0:0:" + "http%3a//example.m3u8"
                    custom_sid = channel["custom_sid"]

            next_url = "%s/live/%s/%s/%s.%s" % (self.host, self.username, self.password, stream_id, self.output)

            if "livefavourites" in glob.current_playlist["player_info"]:
                for fav in glob.current_playlist["player_info"]["livefavourites"]:
                    if str(stream_id) == str(fav["stream_id"]):
                        favourite = True
                        break
            else:
                glob.current_playlist["player_info"]["livefavourites"] = []

            self.list2.append([index, str(name), str(stream_id), str(stream_icon), str(epg_channel_id), str(added), str(category_id), str(custom_sid), str(service_ref),
                              str(nowtime), str(nowTitle), str(nowDesc), str(nexttime), str(nextTitle), str(nextDesc), str(next_url), favourite, watching, hidden, str(direct_source)])
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

    def xmltvCheckData(self):
        # print("*** xmltvCheckData ***")
        safeName = re.sub(r'[\<\>\:\"\/\\\|\?\*]', "_", str(glob.current_playlist["playlist_info"]["name"]))
        safeName = re.sub(r" ", "_", safeName)
        safeName = re.sub(r"_+", "_", safeName)

        filepath = "/etc/epgimport/"
        filename = "xstreamity" + ".sources.xml"
        sourcepath = os.path.join(filepath, filename)
        epgfilename = "xstreamity." + str(safeName) + ".channels.xml"
        channelpath = os.path.join(filepath, epgfilename)

        if not os.path.exists(sourcepath) or not os.path.exists(channelpath):
            self.downloadXMLTVdata()

        else:
            # check file creation times - refresh if older than 24 hours.
            try:
                nowtime = time.time()
                channelmodified = os.path.getctime(channelpath)
                if (int(nowtime) - int(channelmodified)) > 14400:
                    self.downloadXMLTVdata()
            except Exception as e:
                print(e)

    def buildList1(self):
        # print("*** buildlist1 ***")
        self["key_epg"].setText("")
        self.hideEPG()
        self.xmltvdownloaded = False

        self.pre_list = []
        if self["key_blue"].getText() != (_("Reset Search")):
            self.pre_list = [buildCategoryList(x[0], x[1], x[2], x[3]) for x in self.prelist if x[3] is False]

        self.main_list = []
        self.main_list = [buildCategoryList(x[0], x[1], x[2], x[3]) for x in self.list1 if x[3] is False]

        self.combined_list = []
        self.combined_list.extend(self.pre_list + self.main_list)

        self["main_list"].setList(self.combined_list)

        if self["main_list"].getCurrent():
            if glob.nextlist[-1]["index"] != 0:
                self["main_list"].setIndex(glob.nextlist[-1]["index"])

    def buildList2(self):
        # print("*** buildlist2 ***")
        self.main_list = []
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

        if self["main_list"].getCurrent():
            if glob.nextlist[-1]["index"] != 0:
                self["main_list"].setIndex(glob.nextlist[-1]["index"])

    def buttons(self):
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

            self.loadBlankImage()

            if self.level == 2:
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
                os.remove(os.path.join(dir_tmp, "original.png"))
                os.remove(os.path.join(dir_tmp, "temp.png"))
            except:
                pass

            desc_image = ""
            try:
                desc_image = self["main_list"].getCurrent()[5]
            except:
                pass

            if desc_image and desc_image != "n/A":
                temp = os.path.join(dir_tmp, "temp.png")

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

    def loadBlankImage(self, data=None):
        # print("*** loadDefaultImage ***")
        if self["picon"].instance:
            self["picon"].instance.setPixmapFromFile(os.path.join(common_path, "picon_blank.png"))

    def loadDefaultImage(self, data=None):
        # print("*** loadDefaultImage ***")
        if self["picon"].instance:
            self["picon"].instance.setPixmapFromFile(os.path.join(common_path, "picon.png"))

    def resizeImage(self, data=None):
        # print("*** resizeImage ***")
        if self["main_list"].getCurrent():
            original = os.path.join(dir_tmp, "temp.png")

            if screenwidth.width() == 2560:
                size = [294, 176]
            elif screenwidth.width() > 1280:
                size = [220, 130]
            else:
                size = [147, 88]

            if os.path.exists(original):
                try:
                    im = Image.open(original).convert("RGBA")
                    try:
                        im.thumbnail(size, Image.Resampling.LANCZOS)
                    except:
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
            sortlist = [(_("Sort: A-Z")), (_("Sort: Z-A")), (_("Sort: Added")), (_("Sort: Original"))]

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
            activelist.sort(key=lambda x: x[5], reverse=True)

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

            del glob.current_playlist["player_info"]['liverecents'][currentindex]
            self.hideEPG()

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
            adult = "adult", "+18", "18+", "18 rated", "xxx", "sex", "porn", "voksen", "volwassen", "aikuinen", "Erwachsene", "dorosly", "взрослый", "vuxen", "£дорослий"

            if str(self["main_list"].getCurrent()[0]).lower() == _("all") or str(self["main_list"].getCurrent()[0]).lower() == "all":
                glob.adultChannel = True

            elif "sport" in str(self["main_list"].getCurrent()[0]).lower():
                glob.adultChannel = False

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
            glob.currentepglist = self.epglist[:]

            if self.level == 1:
                if self.list1:
                    category_id = self["main_list"].getCurrent()[3]

                    if category_id == "0":
                        next_url = str(self.player_api) + "&action=get_live_streams"

                    else:
                        next_url = str(self.player_api) + "&action=get_live_streams&category_id=" + str(category_id)

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

                    if glob.current_playlist["player_info"]["directsource"] == "Direct Source":
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
                                if glob.current_playlist["player_info"]["directsource"] == "Direct Source":
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

                            self.session.openWithCallback(self.setIndex, streamplayer.XStreamity_StreamPlayer, str(next_url), str(streamtype), str(direct_source), stream_id)
                    else:
                        self.session.openWithCallback(self.setIndex, streamplayer.XStreamity_StreamPlayer, str(next_url), str(streamtype), str(direct_source), stream_id)

                    self["category_actions"].setEnabled(False)

                else:
                    self.createSetup()

    def setIndex(self, data=None):
        # print("*** set index ***")
        self["main_list"].setIndex(glob.currentchannellistindex)
        self["epg_list"].setIndex(glob.currentchannellistindex)
        self.xmltvdownloaded = False
        self.createSetup()

    def back(self, data=None):
        # print("*** back ***")
        if self.selectedlist == self["epg_short_list"]:
            self.shortEPG()
            return

        try:
            os.remove(os.path.join(dir_tmp, "liveepg.xml"))
        except:
            pass

        del glob.nextlist[-1]

        if len(glob.nextlist) == 0:
            self.stopStream()
            self.close()
        else:
            self.lastviewed_url = ""
            self.lastviewed_id = ""
            self.lastviewed_index = 0

            self["x_title"].setText("")
            self["x_description"].setText("")

            if cfg.stopstream.value or cfg.livepreview.value is False:
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
                    self.session.openWithCallback(self.createSetup, hidden.XStreamity_HiddenCategories, "live", self.prelist + self.list1, self.level)
                elif self.level == 2 and not self.favourites_category and not self.recents_category:
                    self.session.openWithCallback(self.createSetup, hidden.XStreamity_HiddenCategories, "live", self.list2, self.level)

    def favourite(self):
        # print("**** favourite ***")
        if self["main_list"].getCurrent():
            currentindex = self["main_list"].getIndex()
            favExists = False
            favStream_id = None

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

                                    if next_el == entry:
                                        next_el = self.epgJson[epg_channel_id][index + 2]

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
        self["progress"].hide()

    def showEPG(self):
        # print("*** showEPGElements ***")
        self["picon"].show()
        self["epg_bg"].show()
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
                    stream_id = next_url.rpartition("/")[-1].partition(".")[0]

                    shortEPGJson = []

                    # url = str(self.player_api) + "&action=get_short_epg&stream_id=" + str(stream_id) + "&limit=1000"
                    url = str(self.player_api) + "&action=get_simple_data_table&stream_id=" + str(stream_id)
                    retries = Retry(total=3, backoff_factor=1)
                    adapter = HTTPAdapter(max_retries=retries)
                    http = requests.Session()
                    http.mount("http://", adapter)
                    http.mount("https://", adapter)
                    response = ""
                    try:
                        r = http.get(url, headers=hdr, timeout=(10, 20), verify=False)
                        r.raise_for_status()
                        if r.status_code == requests.codes.ok:
                            try:
                                response = r.json()
                            except Exception as e:
                                print(e)

                    except Exception as e:
                        print(e)
                        response = ""

                    if response:
                        shortEPGJson = response
                        index = 0
                        now = datetime.now()

                        self.epgshortlist = []
                        duplicatecheck = []

                        if "epg_listings" in shortEPGJson and shortEPGJson["epg_listings"]:
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
                                    if [epg_date_all, epg_time_all] not in duplicatecheck and end_datetime >= now:
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
            if glob.current_playlist["player_info"]["directsource"] == "Direct Source":
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

        url = str(self.player_api) + "&action=get_live_streams"
        tmpfd, tempfilename = tempfile.mkstemp()

        parsed = urlparse(url)
        domain = parsed.hostname
        scheme = parsed.scheme

        if pythonVer == 3:
            url = url.encode()

        if scheme == "https" and sslverify:
            sniFactory = SNIFactory(domain)
            downloadPage(url, tempfilename, sniFactory).addCallback(self.downloadComplete, tempfilename).addErrback(self.downloadFail)
        else:
            downloadPage(url, tempfilename).addCallback(self.downloadComplete, tempfilename).addErrback(self.downloadFail)

        os.close(tmpfd)

    def downloadFail(self, failure=None):
        # print("*** downloadFail ***")
        print(("[EPG] download failed:", failure))

    def downloadComplete(self, data=None, filename=None):
        channellist_all = []
        with open(filename, "r+b") as f:
            try:
                channellist_all = json.load(f)
                self.xmltv_channel_list = []
                for channel in channellist_all:
                    self.xmltv_channel_list.append({"name": str(channel["name"]).strip("-"), "stream_id": str(channel["stream_id"]), "epg_channel_id": str(channel["epg_channel_id"]), "custom_sid": channel["custom_sid"]})
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
        channelpath = os.path.join(filepath, epgfilename)

        # if xmltv file doesn't already exist, create file and build.
        if not os.path.isfile(channelpath):
            with open(channelpath, "a") as f:
                f.close()

        # buildXMLTVSourceFile

        sourcefile = "/etc/epgimport/xstreamity.sources.xml"
        if not os.path.isfile(sourcefile) or os.stat(sourcefile).st_size == 0:
            with open(sourcefile, "w") as f:
                xml_str = '<?xml version="1.0" encoding="utf-8"?>\n'
                xml_str += '<sources>\n'
                xml_str += '<sourcecat sourcecatname="XStreamity EPG">\n'
                xml_str += '</sourcecat>\n'
                xml_str += '</sources>\n'
                f.write(xml_str)

        try:
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
        except Exception as e:
            print(e)

        try:
            with open(sourcefile, "r+") as f:
                xml_str = f.read()
                f.seek(0)
                doc = minidom.parseString(xml_str)
                xml_output = doc.toprettyxml(encoding="utf-8", indent="\t")
                try:
                    xml_output = os.linesep.join([s for s in xml_output.splitlines() if s.strip()])
                except:
                    xml_output = os.linesep.join([s for s in xml_output.decode().splitlines() if s.strip()])
                f.write(xml_output)
        except Exception as e:
            print(e)

        # buildXMLTVChannelFile
        with open(channelpath, "w") as f:
            xml_str = '<?xml version="1.0" encoding="utf-8"?>\n'
            xml_str += '<channels>\n'

            for i in range(len(self.xmltv_channel_list)):

                channelid = self.xmltv_channel_list[i]["epg_channel_id"]
                if channelid and "&" in channelid:
                    channelid = channelid.replace("&", "&amp;")

                stream_id = int(self.xmltv_channel_list[i]["stream_id"])

                bouquet_id1 = 0
                calc_remainder = int(stream_id) // 65535
                bouquet_id1 = bouquet_id1 + calc_remainder
                bouquet_id2 = int(stream_id) - int(calc_remainder * 65535)

                service_ref = "1:0:1:" + str(format(bouquet_id1, "x")) + ":" + str(format(bouquet_id2, "x")) + ":" + str(format(self.unique_ref, "x")) + ":0:0:0:0:" + "http%3a//example.m3u8"

                if "custom_sid" in self.xmltv_channel_list[i] and self.xmltv_channel_list[i]["custom_sid"]:
                    if self.xmltv_channel_list[i]["custom_sid"] and self.xmltv_channel_list[i]["custom_sid"] != "None" and self.xmltv_channel_list[i]["custom_sid"] is not None and self.xmltv_channel_list[i]["custom_sid"] != "0":
                        if self.xmltv_channel_list[i]["custom_sid"][0].isdigit():
                            self.xmltv_channel_list[i]["custom_sid"] = "1" + self.xmltv_channel_list[i]["custom_sid"][1:]

                        service_ref = str(":".join(self.xmltv_channel_list[i]["custom_sid"].split(":")[:7])) + ":0:0:0:" + "http%3a//example.m3u8"

                self.xmltv_channel_list[i]["serviceref"] = str(service_ref)
                name = self.xmltv_channel_list[i]["name"]

                if channelid and channelid != "None":
                    xml_str += '\t<channel id="' + str(channelid) + '">' + str(service_ref) + '</channel><!-- ' + str(name) + ' -->\n'

            xml_str += '</channels>\n'
            f.write(xml_str)

        # self.buildLists()

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


def buildEPGListEntry(index, title, epgNowTime, epgNowTitle, epgNowDesc, epgNextTime, epgNextTitle, epgNextDesc, hidden, direct_source):
    return (title, index, epgNowTime, epgNowTitle, epgNowDesc, epgNextTime, epgNextTitle, epgNextDesc, hidden, direct_source)


def buildShortEPGListEntry(date_all, time_all, title, description, index, start_datetime, end_datetime):
    return (title, date_all, time_all, description, index, start_datetime, end_datetime)


def buildCategoryList(index, title, category_id, hidden):
    png = LoadPixmap(os.path.join(common_path, "more.png"))
    return (title, png, index, category_id, hidden)


def buildLiveStreamList(index, name, stream_id, stream_icon, next_url, favourite, watching, hidden, direct_source):
    png = LoadPixmap(os.path.join(common_path, "play.png"))
    if favourite:
        png = LoadPixmap(os.path.join(common_path, "favourite.png"))
    if watching:
        png = LoadPixmap(os.path.join(common_path, "watching.png"))
    return (name, png, index, next_url, stream_id, stream_icon, hidden, direct_source)
