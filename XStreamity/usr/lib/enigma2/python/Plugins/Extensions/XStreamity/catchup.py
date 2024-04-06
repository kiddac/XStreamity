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

try:
    from http.client import HTTPConnection
    HTTPConnection.debuglevel = 0
except ImportError:
    from httplib import HTTPConnection
    HTTPConnection.debuglevel = 0


try:
    from urlparse import urlparse
except ImportError:
    from urllib.parse import urlparse

from PIL import Image, ImageFile, PngImagePlugin
from itertools import cycle, islice

try:
    from requests.adapters import HTTPAdapter, Retry
except ImportError:
    HTTPAdapter = Retry = None

try:
    from twisted.web.client import downloadPage
except ImportError:
    downloadPage = None

from requests.exceptions import RequestException

from Components.ActionMap import ActionMap
from Components.Pixmap import Pixmap
from Components.ProgressBar import ProgressBar
from Components.Sources.List import List

from Screens.MessageBox import MessageBox
from Screens.Screen import Screen
from Screens.VirtualKeyBoard import VirtualKeyBoard
from Tools.LoadPixmap import LoadPixmap

from enigma import eTimer, eServiceReference

from . import _
from . import streamplayer
from . import xstreamity_globals as glob
from .plugin import skin_directory, screenwidth, hdr, cfg, common_path, dir_tmp, downloads_json, pythonVer
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

epgimporter = os.path.isdir("/usr/lib/enigma2/python/Plugins/Extensions/EPGImport")


class XStreamity_Categories(Screen):
    ALLOW_SUSPEND = True

    def __init__(self, session):
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

    def createSetup(self, data=None):
        self["x_title"].setText("")
        self["x_description"].setText("")

        if self.level == 1:
            self.getCategories()
        else:
            self.getLevel2()

        self.buildLists()

    def buildLists(self):
        if self.level == 1:
            self.buildList1()
        else:
            self.buildList2()

        self.buttons()
        self.selectionChanged()

    def getCategories(self):
        index = 0
        self.list1 = []
        self.prelist = []
        self.pre_list = []

        currentCategoryList = glob.current_playlist["data"]["live_categories"]
        currentHidden = set(glob.current_playlist["player_info"]["catchuphidden"])

        hidden = "0" in currentHidden

        self.prelist.append(
            [index, _("ALL"), "0", hidden]
        )
        index += 1

        if not self.liveStreamsData:
            self.liveStreamsData = self.downloadApiData(self.liveStreamsUrl)

        archivelist = [
            x for x in self.liveStreamsData
            if "tv_archive" in x and x["tv_archive"] == 1
            and "tv_archive_duration" in x
            and x["tv_archive_duration"] != "0"
            and x["tv_archive_duration"] != 0
            and x["category_id"] not in glob.current_playlist["player_info"]["livehidden"]
        ]

        for item in currentCategoryList:
            for archive in archivelist:
                if "category_id" in item and "category_ids" in archive:
                    if item["category_id"] == archive["category_id"] or item["category_id"] in archive["category_ids"]:
                        self.list1.append(
                            [
                                index,
                                str(item["category_name"] if "category_name" in item else "No category"),
                                str(item["category_id"] if "category_id" in item else "999999"),
                                item["category_id"] in currentHidden
                            ]
                        )
                        index += 1
                        break

        glob.originalChannelList1 = self.list1[:]

    def getLevel2(self):
        response = self.downloadApiData(glob.nextlist[-1]["next_url"])

        index = 0
        self.list2 = []

        if response:
            catchup_hidden_channels = set(glob.current_playlist["player_info"]["catchupchannelshidden"])

            for item in response:
                if item.get("tv_archive") == 1 and item.get("tv_archive_duration") != "0" and item.get("tv_archive_duration") != 0:
                    name = item.get("name", "")
                    stream_id = item.get("stream_id", "")
                    stream_icon = item.get("stream_icon", "") if item.get("stream_icon", "").startswith("http") else ""
                    epg_channel_id = item.get("epg_channel_id", "").replace("&", "&amp;")
                    added = item.get("added", "")
                    hidden = str(stream_id) in catchup_hidden_channels

                    if stream_id:
                        next_url = "{}/live/{}/{}/{}.{}".format(self.host, self.username, self.password, stream_id, self.output)
                        self.list2.append([
                            index, str(name), str(stream_id), str(stream_icon), str(epg_channel_id), str(added),
                            str(next_url), "", "", "", "", "", "", hidden
                        ])
                        index += 1

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
        except RequestException as e:
            print("Error occurred during API data download:", e)

        self.session.openWithCallback(self.back, MessageBox, _("Server error or invalid link."), MessageBox.TYPE_ERROR, timeout=3)

    def buildList1(self):
        self["picon"].hide()

        if self["key_blue"].getText() != (_("Reset Search")):
            self.pre_list = [buildCategoryList(x[0], x[1], x[2], x[3]) for x in self.prelist if not x[3]]
        else:
            self.pre_list = []

        self.main_list = [buildCategoryList(x[0], x[1], x[2], x[3]) for x in self.list1 if not x[3]]

        self["main_list"].setList(self.pre_list + self.main_list)

        if self["main_list"].getCurrent() and glob.nextlist[-1]["index"] != 0:
            self["main_list"].setIndex(glob.nextlist[-1]["index"])

    def buildList2(self):
        self.main_list = [
            buildCatchupStreamList(x[0], x[1], x[2], x[3], x[4], x[5], x[6], x[13])
            for x in self.list2 if not x[13]
        ]
        self["main_list"].setList(self.main_list)
        self["picon"].show()

        if self["main_list"].getCurrent() and glob.nextlist[-1]["index"] != 0:
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
                if not glob.nextlist[-1]["sort"]:
                    self.sortText = (_("Sort: A-Z"))
                    glob.nextlist[-1]["sort"] = self.sortText

                self["key_blue"].setText(_("Search"))
                self["key_yellow"].setText(_(glob.nextlist[-1]["sort"]))
                self["key_menu"].setText("+/-")

    def playStream(self):
        if self["main_list"].getCurrent():
            currently_playing_ref = self.session.nav.getCurrentlyPlayingServiceReference()
            if currently_playing_ref:
                if currently_playing_ref.toString() == glob.currentPlayingServiceRefString or self.selectedlist == self["epg_short_list"]:
                    self.back()
                else:
                    self["main_list"].setIndex(glob.nextlist[-1]["index"])
                    self.next()
            else:
                self.back()

    def stopStream(self):
        if glob.currentPlayingServiceRefString != glob.newPlayingServiceRefString != "":
            if self.session.nav.getCurrentlyPlayingServiceReference():
                self.session.nav.stopService()
            self.session.nav.playService(eServiceReference(glob.currentPlayingServiceRefString))
            glob.newPlayingServiceRefString = glob.currentPlayingServiceRefString

    def selectionChanged(self):
        if self["main_list"].getCurrent():
            channel_title = self["main_list"].getCurrent()[0]
            current_index = self["main_list"].getIndex() + 1

            self.position = current_index
            if self.level == 1:
                self.positionall = len(self.pre_list) + len(self.main_list)
            else:
                self.positionall = len(self.main_list)
            self.page = (self.position - 1) // self.itemsperpage + 1
            self.pageall = (self.positionall - 1) // self.itemsperpage + 1

            self["page"].setText(_("Page: ") + str(self.page) + _(" of ") + str(self.pageall))
            self["listposition"].setText("{}/{}".format(self.position, self.positionall))

            self["main_title"].setText(self.main_title + ": " + str(channel_title))

            self.loadBlankImage()

            if self.level == 2 and cfg.channelpicons.value:
                self.timerimage = eTimer()
                try:
                    self.timerimage.stop()
                except:
                    pass

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
            self["listposition"].setText("{}/{}".format(self.position, self.positionall))

            self["key_yellow"].setText("")
            self["key_blue"].setText("")

    def downloadImage(self):
        if self["main_list"].getCurrent():
            try:
                for filename in ["original.png", "temp.png"]:
                    file_path = os.path.join(dir_tmp, filename)
                    if os.path.exists(file_path):
                        os.remove(file_path)
            except Exception:
                pass

            desc_image = self["main_list"].getCurrent()[5] if self["main_list"].getCurrent() else ""
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
                except Exception:
                    self.loadDefaultImage()
            else:
                self.loadDefaultImage()

    def loadBlankImage(self, data=None):
        pixmap_path = os.path.join(common_path, "picon_blank.png")
        self.setPixmap(pixmap_path)

    def loadDefaultImage(self, data=None):
        pixmap_path = os.path.join(common_path, "picon.png")
        self.setPixmap(pixmap_path)

    def setPixmap(self, pixmap_path):
        if self["picon"].instance:
            self["picon"].instance.setPixmapFromFile(pixmap_path)

    def resizeImage(self, data=None):
        # print("*** resizeImage ***")
        current_item = self["main_list"].getCurrent()
        if current_item:
            original = os.path.join(dir_tmp, "temp.png")

            # Determine the target size based on screen width
            if screenwidth.width() == 2560:
                size = [294, 176]
            elif screenwidth.width() > 1280:
                size = [220, 130]
            else:
                size = [147, 88]

            if os.path.exists(original):
                try:
                    im = Image.open(original)

                    # Convert to RGBA if not already
                    if im.mode != "RGBA":
                        im = im.convert("RGBA")

                    # Resize image with Lanczos resampling if available, otherwise use ANTIALIAS
                    try:
                        im.thumbnail(size, Image.LANCZOS)
                    except:
                        im.thumbnail(size, Image.ANTIALIAS)

                    # Create blank RGBA image
                    bg = Image.new("RGBA", size, (255, 255, 255, 0))

                    # Calculate position for centering
                    left = (size[0] - im.width) // 2
                    top = (size[1] - im.height) // 2

                    # Paste resized image onto blank image
                    bg.paste(im, (left, top), mask=im)

                    # Save as PNG
                    bg.save(original, "PNG")

                    # Set pixmap for picon instance
                    self.setPixmap(original)

                except Exception as e:
                    print("Error resizing image:", e)
                    self.loadDefaultImage()
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
        if self.selectedlist == self["epg_short_list"]:
            self.reverse()
            return

        current_sort = self["key_yellow"].getText()
        if not current_sort or current_sort == _("Reverse"):
            return

        activelist = self.list1 if self.level == 1 else self.list2
        activeoriginal = glob.originalChannelList1 if self.level == 1 else glob.originalChannelList2

        sortlist = [(_("Sort: A-Z")), (_("Sort: Z-A"))]
        if self.level == 1:
            sortlist.append(_("Sort: Original"))
        else:
            sortlist.extend([(_("Sort: Added")), (_("Sort: Original"))])

        for index, item in enumerate(sortlist):
            if str(item) == str(self.sortText):
                self.sortindex = index
                break

        if self["main_list"].getCurrent():
            self["main_list"].setIndex(0)

        if current_sort == (_("Sort: A-Z")):
            activelist.sort(key=lambda x: x[1], reverse=False)

        elif current_sort == (_("Sort: Z-A")):
            activelist.sort(key=lambda x: x[1], reverse=True)

        elif current_sort == (_("Sort: Added")):
            if self.level != 1:
                activelist.sort(key=lambda x: x[5], reverse=True)

        elif current_sort == (_("Sort: Original")):
            activelist[:] = activeoriginal

        next_sort_type = next(islice(cycle(sortlist), self.sortindex + 1, None))
        self.sortText = str(next_sort_type)

        self["key_yellow"].setText(self.sortText)
        glob.nextlist[-1]["sort"] = self["key_yellow"].getText()

        if self.level == 1:
            self.list1 = activelist
        else:
            self.list2 = activelist

        self.buildLists()

    def search(self, result=None):
        if not self["key_blue"].getText():
            return

        current_filter = self["key_blue"].getText()

        if current_filter == (_("Reset Search")):
            self.resetSearch()
        else:
            self.session.openWithCallback(self.filterChannels, VirtualKeyBoard, title=_("Filter this category..."), text=self.searchString)

    def filterChannels(self, result=None):
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

                self.buildLists()

    def resetSearch(self):
        self["key_blue"].setText(_("Search"))
        self["key_yellow"].setText(self.sortText)

        if self.level == 1:
            activelist = glob.originalChannelList1[:]
        else:
            activelist = glob.originalChannelList2[:]

        if self.level == 1:
            self.list1 = activelist
        else:
            self.list2 = activelist

        self.filterresult = ""
        glob.nextlist[-1]["filter"] = self.filterresult

        self.buildLists()

    def pinEntered(self, result=None):
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
        self.pin = True
        nowtime = int(time.mktime(datetime.now().timetuple())) if pythonVer == 2 else int(datetime.timestamp(datetime.now()))

        if self.level == 1 and self["main_list"].getCurrent():
            adult_keywords = {"adult", "+18", "18+", "18 rated", "xxx", "sex", "porn", "voksen", "volwassen", "aikuinen", "Erwachsene", "dorosly", "взрослый", "vuxen", "£дорослий"}
            current_title_lower = str(self["main_list"].getCurrent()[0]).lower()

            if current_title_lower in {"all", _("all")}:
                glob.adultChannel = True
            elif "sport" in current_title_lower:
                glob.adultChannel = False
            elif any(keyword in current_title_lower for keyword in adult_keywords):
                glob.adultChannel = True
            else:
                glob.adultChannel = False

            if cfg.adult.value and nowtime - int(glob.pintime) > 900:
                if glob.adultChannel:
                    from Screens.InputBox import PinInput
                    self.session.openWithCallback(self.pinEntered, PinInput, pinList=[cfg.adultpin.value], triesEntry=cfg.retries.adultpin, title=_("Please enter the parental control pin code"), windowTitle=_("Enter pin code"))
                else:
                    self.next()
            else:
                self.next()
        else:
            self.next()

    def next(self):
        if self["main_list"].getCurrent():
            current_index = self["main_list"].getIndex()
            glob.nextlist[-1]["index"] = current_index
            glob.currentchannellist = self.main_list[:]
            glob.currentchannellistindex = current_index

            if self.level == 1:
                if self.list1:
                    category_id = self["main_list"].getCurrent()[3]
                    next_url = "{0}&action=get_live_streams&category_id={1}".format(self.player_api, category_id) if category_id != "0" else "{0}&action=get_live_streams".format(self.player_api)
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

    def setIndex(self, data=None):
        self["main_list"].setIndex(glob.currentchannellistindex)
        self.createSetup()

    def back(self, data=None):
        self.hideEPG()

        if self.selectedlist == self["epg_short_list"]:
            epg_instance = self["epg_short_list"].master.master.instance
            epg_instance.setSelectionEnable(0)
            self.catchup_all = []
            self["epg_short_list"].setList(self.catchup_all)
            main_instance = self["main_list"].master.master.instance
            main_instance.setSelectionEnable(1)
            self.selectedlist = self["main_list"]
            self.buttons()
        else:
            del glob.nextlist[-1]

            if not glob.nextlist:
                self.close()
            else:
                self.stopStream()
                self.level -= 1
                self.createSetup()

    def showHiddenList(self):
        if self["key_menu"].getText():
            from . import hidden

            current_list = self.prelist + self.list1 if self.level == 1 else self.list2

            if current_list and self["main_list"].getCurrent():
                self.session.openWithCallback(self.createSetup, hidden.XStreamity_HiddenCategories, "catchup", current_list, self.level)

    def hideEPG(self):
        self["picon"].hide()
        self["epg_bg"].hide()
        self["x_title"].setText("")
        self["x_description"].setText("")

    def showEPG(self):
        self["picon"].show()
        self["epg_bg"].show()

    def displayShortEPG(self):
        current_item = self["epg_short_list"].getCurrent()

        if current_item:
            title = str(current_item[0])
            description = str(current_item[3])
            timeall = str(current_item[2])

            self["x_title"].setText("{} {}".format(timeall, title))
            self["x_description"].setText(description)
            self.showEPG()

    def downloadVideo(self):
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
        if data:
            print(data)

    def playCatchup(self):
        current_main_list_item = self["main_list"].getCurrent()
        if current_main_list_item:
            next_url = current_main_list_item[3]
            stream = next_url.rpartition("/")[-1]

            epg_short_list_current_item = self["epg_short_list"].getCurrent()
            date = str(epg_short_list_current_item[4])
            duration = str(epg_short_list_current_item[5])

            playurl = "{}/timeshift/{}/{}/{}/{}/{}".format(self.host, self.username, self.password, duration, date, stream)
            if next_url != "None" and "/live/" in next_url:
                streamtype = glob.current_playlist["player_info"]["vodtype"]
                glob.catchupdata = [str(epg_short_list_current_item[0]), str(epg_short_list_current_item[3])]
                self.session.openWithCallback(self.setIndex, streamplayer.XStreamity_CatchupPlayer, str(playurl), str(streamtype))
            else:
                from Screens.MessageBox import MessageBox
                self.session.open(MessageBox, _("Catchup error. No data for this slot"), MessageBox.TYPE_WARNING, timeout=5)

    def checkRedirect(self, url):
        # print("*** check redirect ***")
        x = ""
        retries = Retry(total=3, backoff_factor=1)
        adapter = HTTPAdapter(max_retries=retries)
        http = requests.Session()
        http.mount("http://", adapter)
        http.mount("https://", adapter)
        try:
            x = http.get(url, headers=hdr, timeout=30, verify=False, stream=True)
            url = x.url
            x.close()
            return str(url)
        except Exception as e:
            print(e)
            return str(url)

    def catchupEPG(self):
        current_item = self["main_list"].getCurrent()
        if not current_item:
            return

        next_url = current_item[3]
        if next_url == "None" or "/live/" not in next_url:
            return

        stream_id = next_url.rpartition("/")[-1].partition(".")[0]

        url = "{}{}".format(self.simpledatatable, stream_id)
        print(url)
        url = self.checkRedirect(url)
        print(url)

        try:
            with requests.Session() as http:
                retries = Retry(total=3, backoff_factor=1)
                adapter = HTTPAdapter(max_retries=retries)
                http.mount("http://", adapter)
                http.mount("https://", adapter)

                response = http.get(url, headers=hdr, timeout=(10, 60), verify=False)
                response.raise_for_status()
                if response.status_code == requests.codes.ok:
                    shortEPGJson = response.json()

        except Exception as e:
            print("Error fetching catchup EPG:", e)
            return

        if "epg_listings" not in shortEPGJson or not shortEPGJson["epg_listings"]:
            self.session.open(MessageBox, _("Catchup currently not available. Missing EPG data"), type=MessageBox.TYPE_INFO, timeout=5)
            return

        index = 0
        self.epgshortlist = []
        duplicatecheck = set()

        shift = int(glob.current_playlist["player_info"].get("serveroffset", 0))
        catchupstart = int(cfg.catchupstart.getValue())
        catchupend = int(cfg.catchupend.getValue())

        for listing in shortEPGJson["epg_listings"]:
            if "has_archive" in listing and listing["has_archive"] == 1 or "now_playing" in listing and listing["now_playing"] == 1:
                title = base64.b64decode(listing.get("title", "")).decode("utf-8")
                description = base64.b64decode(listing.get("description", "")).decode("utf-8")

                start = listing.get("start", "")
                end = listing.get("end", "")
                stop = listing.get("stop", "")

                if start:
                    try:
                        start_datetime_original = datetime.strptime(start, "%Y-%m-%d %H:%M:%S")
                        start_datetime = datetime.strptime(start, "%Y-%m-%d %H:%M:%S") + timedelta(hours=shift)
                    except Exception as e:
                        print("Error parsing start datetime:", e)
                        continue

                if end:
                    end_datetime = datetime.strptime(end, "%Y-%m-%d %H:%M:%S") + timedelta(hours=shift)
                elif stop:
                    end_datetime = datetime.strptime(stop, "%Y-%m-%d %H:%M:%S") + timedelta(hours=shift)
                else:
                    print("Error: Missing end or stop time")
                    continue

                start_datetime_margin = start_datetime - timedelta(minutes=catchupstart)
                end_datetime_margin = end_datetime + timedelta(minutes=catchupend)

                epg_date_all = start_datetime.strftime("%a %d/%m")
                epg_time_all = "{} - {}".format(start_datetime.strftime("%H:%M"), end_datetime.strftime("%H:%M"))
                epg_duration = int((end_datetime_margin - start_datetime_margin).total_seconds() / 60.0)

                url_datestring = start_datetime_original.strftime("%Y-%m-%d:%H-%M")

                if (epg_date_all, epg_time_all) not in duplicatecheck:
                    duplicatecheck.add((epg_date_all, epg_time_all))
                    self.epgshortlist.append(buildCatchupEPGListEntry(epg_date_all, epg_time_all, title, description, url_datestring, str(epg_duration), index))

                    index += 1

        self.epgshortlist.reverse()
        self["epg_short_list"].setList(self.epgshortlist)

        if self["epg_short_list"].getCurrent():
            glob.catchupdata = [str(self["epg_short_list"].getCurrent()[0]), str(self["epg_short_list"].getCurrent()[3])]
        instance = self["epg_short_list"].master.master.instance
        instance.setSelectionEnable(1)

        self.selectedlist = self["epg_short_list"]
        self.displayShortEPG()

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
