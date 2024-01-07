#!/usr/bin/python
# -*- coding: utf-8 -*-

from . import _
from . import streamplayer
from . import xstreamity_globals as glob

from .plugin import skin_directory, screenwidth, hdr, cfg, common_path, dir_tmp, downloads_json, pythonVer
from .xStaticText import StaticText

from Components.ActionMap import ActionMap
from Components.Pixmap import Pixmap
from Components.ProgressBar import ProgressBar
from Components.Sources.List import List
from PIL import Image, ImageChops, ImageFile, PngImagePlugin
from Screens.MessageBox import MessageBox
from Screens.Screen import Screen
from Screens.VirtualKeyBoard import VirtualKeyBoard
from Tools.LoadPixmap import LoadPixmap
from datetime import datetime, timedelta
from enigma import eTimer, eServiceReference
from requests.adapters import HTTPAdapter, Retry
from twisted.web.client import downloadPage
from itertools import cycle, islice

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
        glob.categoryname = "catchup"

        self.skin_path = os.path.join(skin_directory, cfg.skin.getValue())
        skin = os.path.join(self.skin_path, "live_categories.xml")
        if os.path.exists("/var/lib/dpkg/status"):
            skin = os.path.join(self.skin_path, "DreamOS/live_categories.xml")

        with codecs.open(skin, "r", encoding="utf-8") as f:
            self.skin = f.read()

        self.setup_title = (_("Catch Up Categories"))
        self.main_title = (_("Catch Up TV"))
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

        self.liveStreamsData = []

        self.liveStreamsUrl = str(self.player_api) + "&action=get_live_streams"
        self.simpledatatable = str(self.player_api) + "&action=get_simple_data_table&stream_id="

        next_url = str(self.player_api) + "&action=get_live_categories"

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
        }, -1)

        self["channel_actions"].setEnabled(False)

        glob.nextlist = []
        glob.nextlist.append({"next_url": next_url, "index": 0, "level": self.level, "sort": self.sortText, "filter": ""})

        self.onFirstExecBegin.append(self.createSetup)
        self.onLayoutFinish.append(self.__layoutFinished)

    def __layoutFinished(self):
        self.setTitle(self.setup_title)

    def createSetup(self):
        # print("*** createSetup ***")
        self["x_title"].setText("")
        self["x_description"].setText("")

        if self.level == 1:
            self.getCategories()
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
        currentHidden = glob.current_playlist["player_info"]["catchuphidden"]

        hidden = False

        if "0" in currentHidden:
            hidden = True

        self.prelist.append([index, _("ALL"), "0", hidden])
        index += 1

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
                        else:
                            continue
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

    def buildList1(self):
        # print("*** buildlist1 ***")
        self["picon"].hide()

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

        self.main_list = [buildCatchupStreamList(x[0], x[1], x[2], x[3], x[4], x[5], x[6], x[13]) for x in self.list2 if x[13] is False]
        self["main_list"].setList(self.main_list)
        self["picon"].show()

        if self["main_list"].getCurrent():
            if glob.nextlist[-1]["index"] != 0:
                self["main_list"].setIndex(glob.nextlist[-1]["index"])

    def buttons(self):
        if glob.nextlist[-1]["filter"]:
            self["key_yellow"].setText("")
            self["key_blue"].setText(_("Reset Search"))
            self["key_menu"].setText("")
        else:

            if self.selectedlist == self["epg_short_list"]:
                self["key_blue"].setText("")
                self["key_yellow"].setText(_("Reverse"))
                self["key_menu"].setText("+/-")

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
        # print("*** self.level ***", self.level)
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

            size = [147, 88]
            if screenwidth.width() > 1280:
                size = [220, 130]

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

        if self.selectedlist == self["epg_short_list"]:
            self.reverse()
            return

        if not self["key_yellow"].getText() or self["key_yellow"].getText() == _("Reverse"):
            return

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

        if self.level == 1:
            adult = _("all"), "all", "+18", "adult", "adults", "18+", "18 rated", "xxx", "sex", "porn", "pink", "blue", "الكل", "vše", "alle", "kõik", "kaikki", "tout", "tutto", "alles", "wszystko", "todos", "všetky", "të gjitha", "sve", "allt", "hepsi", "所有"
            if any(s in str(self["main_list"].getCurrent()[0]).lower() and str(self["main_list"].getCurrent()[0]).lower() != "Allgemeines" for s in adult):
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
                        next_url = str(self.player_api) + "&action=get_live_streams"

                    else:
                        next_url = str(self.player_api) + "&action=get_live_streams&category_id=" + str(category_id)

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
                    if self.selectedlist == self["main_list"]:
                        self.catchupEPG()
                        self.buttons()
                    else:
                        self.playCatchup()
                else:
                    self.createSetup()

    def setIndex(self):
        # print("*** set index ***")
        self["main_list"].setIndex(glob.currentchannellistindex)
        self.createSetup()

    def back(self, data=None):
        # print("*** back ***")

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
                self.level -= 1
                self.createSetup()

    def showHiddenList(self):
        # print("*** showHiddenList ***")
        if self["key_menu"].getText() != "":
            from . import hidden
            if self["main_list"].getCurrent():
                if self.level == 1:
                    self.session.openWithCallback(self.createSetup, hidden.XStreamity_HiddenCategories, "catchup", self.prelist + self.list1, self.level)
                elif self.level == 2:
                    self.session.openWithCallback(self.createSetup, hidden.XStreamity_HiddenCategories, "catchup", self.list2, self.level)

    def hideEPG(self):
        # print("*** hide EPG ***")
        self["picon"].hide()
        self["epg_bg"].hide()
        self["x_title"].setText("")
        self["x_description"].setText("")

    def showEPG(self):
        # print("*** showEPGElements ***")
        self["picon"].show()
        self["epg_bg"].show()

    def displayShortEPG(self):
        # print("*** displayShortEPG ***")
        if self["epg_short_list"].getCurrent():
            title = str(self["epg_short_list"].getCurrent()[0])
            description = str(self["epg_short_list"].getCurrent()[3])
            timeall = str(self["epg_short_list"].getCurrent()[2])
            self["x_title"].setText(timeall + " " + title)
            self["x_description"].setText(description)
            self.showEPG()

    def downloadVideo(self):
        # print("*** downloadVideo ***")

        if self.selectedlist != self["epg_short_list"]:
            return

        if self["main_list"].getCurrent():

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

                if playurl == url:
                    exists = True

            if exists is False:
                downloads_all.append([_("Catch-up"), title, playurl, "Not Started", 0, 0])

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

    def failed(self, data=None):
        # print("*** failed ***")
        if data:
            print(data)

    def playCatchup(self):
        # print("*** playCatchup ***")
        next_url = self["main_list"].getCurrent()[3]
        stream = next_url.rpartition("/")[-1]

        date = str(self["epg_short_list"].getCurrent()[4])

        duration = str(self["epg_short_list"].getCurrent()[5])

        playurl = "%s/timeshift/%s/%s/%s/%s/%s" % (self.host, self.username, self.password, duration, date, stream)
        if next_url != "None" and "/live/" in next_url:
            streamtype = glob.current_playlist["player_info"]["vodtype"]
            self.reference = eServiceReference(int(streamtype), 0, str(playurl))
            glob.catchupdata = [str(self["epg_short_list"].getCurrent()[0]), str(self["epg_short_list"].getCurrent()[3])]
            self.session.openWithCallback(self.setIndex, streamplayer.XStreamity_CatchupPlayer, str(playurl), str(streamtype))
        else:
            from Screens.MessageBox import MessageBox
            self.session.open(MessageBox, _("Catchup error. No data for this slot"), MessageBox.TYPE_WARNING, timeout=5)

    def catchupEPG(self):
        # print("*** catchupEPG ***")
        if self["main_list"].getCurrent():
            next_url = self["main_list"].getCurrent()[3]

            if next_url != "None":
                if "/live/" in next_url:
                    stream_id = next_url.rpartition("/")[-1].partition(".")[0]
                    response = ""
                    shortEPGJson = []

                    url = str(self.simpledatatable) + str(stream_id)

                    retries = Retry(total=3, backoff_factor=1)
                    adapter = HTTPAdapter(max_retries=retries)
                    http = requests.Session()
                    http.mount("http://", adapter)
                    http.mount("https://", adapter)
                    response = ""
                    try:
                        r = http.get(url, headers=hdr, timeout=(10, 60), verify=False)
                        r.raise_for_status()
                        if r.status_code == requests.codes.ok:
                            try:
                                response = r.json()
                            except Exception as e:
                                print(e)

                    except Exception as e:
                        print(e)

                    if response:
                        shortEPGJson = response
                        index = 0
                        self.epgshortlist = []
                        duplicatecheck = []

                        if "epg_listings" not in shortEPGJson or not shortEPGJson["epg_listings"]:
                            self.session.open(MessageBox, _("Catchup currently not available. Missing EPG data"), type=MessageBox.TYPE_INFO, timeout=5)
                            return

                        else:
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
                                            end_datetime_offset = datetime.strptime(end, "%Y-%m-%d %H:%M:%S") + timedelta(hours=shift)
                                            end_datetime_margin = datetime.strptime(end, "%Y-%m-%d %H:%M:%S") + timedelta(hours=shift) + timedelta(minutes=catchupend)
                                        except:
                                            try:
                                                end = listing["stop"]
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


def buildCategoryList(index, title, category_id, hidden):
    png = LoadPixmap(os.path.join(common_path, "more.png"))
    return (title, png, index, category_id, hidden)


def buildCatchupStreamList(index, title, stream_id, stream_icon, epg_channel_id, added, next_url, hidden):
    png = LoadPixmap(os.path.join(common_path, "more.png"))
    return (title, png, index, next_url, stream_id, stream_icon, epg_channel_id, added, hidden)


def buildCatchupEPGListEntry(date_all, time_all, title, description, start, duration, index):
    return (title, date_all, time_all, description, start, duration, index)
