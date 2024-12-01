#!/usr/bin/python
# -*- coding: utf-8 -*-

from __future__ import division

# Standard library imports
import base64
import codecs
import json
import math
import os
import re
import tempfile
import time
from datetime import datetime, timedelta
from itertools import cycle, islice

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

try:
    from xml.dom import minidom
except ImportError:
    pass

# Third-party imports
import requests
from PIL import Image, ImageFile, PngImagePlugin
from requests.adapters import HTTPAdapter, Retry
from twisted.web.client import downloadPage

# Enigma2 components
from Components.ActionMap import ActionMap
# from Components.Label import Label
from Components.Pixmap import Pixmap
from Components.ProgressBar import ProgressBar
from Components.Sources.List import List
from Components.config import ConfigClock, ConfigText, NoSave
from RecordTimer import RecordTimerEntry
from Screens.MessageBox import MessageBox
from Screens.Screen import Screen
from Screens.VirtualKeyBoard import VirtualKeyBoard
from ServiceReference import ServiceReference
from Tools.LoadPixmap import LoadPixmap
from enigma import eEPGCache, eServiceReference, eTimer

# Local application/library-specific imports
from . import _
from . import liveplayer
from . import xstreamity_globals as glob
from .plugin import cfg, common_path, dir_tmp, playlists_json, pythonVer, screenwidth, skin_directory
from .xStaticText import StaticText

# HTTPS twisted client hack
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

hdr = {
    'User-Agent': str(cfg.useragent.value),
    'Connection': 'keep-alive',
    'Accept-Encoding': 'gzip, deflate'
}


class XStreamity_Categories(Screen):
    ALLOW_SUSPEND = True

    def __init__(self, session):
        # print("*** live init ***")
        Screen.__init__(self, session)
        self.session = session
        glob.categoryname = "live"

        self.skin_path = os.path.join(skin_directory, cfg.skin.value)
        skin = os.path.join(self.skin_path, "live_categories.xml")
        if os.path.exists("/var/lib/dpkg/status"):
            skin = os.path.join(self.skin_path, "DreamOS/live_categories.xml")

        with codecs.open(skin, "r", encoding="utf-8") as f:
            self.skin = f.read()

        self.setup_title = _("Live Categories")
        self.main_title = _("Live Streams")

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
        self.itemsperpage = 10

        # self.lastviewed_url = ""
        # self.lastviewed_id = ""
        # self.lastviewed_index = 0

        self.searchString = ""
        self.filterresult = ""

        self.showingshortEPG = False

        self.chosen_category = ""

        self.pin = False

        self.sortindex = 0
        self.sortText = _("Sort: A-Z")

        self.epgtimeshift = 0
        self.level = 1

        self.selectedlist = self["main_list"]

        self.host = glob.active_playlist["playlist_info"]["host"]
        self.username = glob.active_playlist["playlist_info"]["username"]
        self.password = glob.active_playlist["playlist_info"]["password"]
        self.output = glob.active_playlist["playlist_info"]["output"]
        self.name = glob.active_playlist["playlist_info"]["name"]

        self.player_api = glob.active_playlist["playlist_info"]["player_api"]

        self.liveStreamsData = []

        next_url = str(self.player_api) + "&action=get_live_categories"

        full_url = glob.active_playlist["playlist_info"]["full_url"]

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
            "red": self.back,
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
            if glob.active_playlist["data"]["customsids"] is True:
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
        self.list1 = []
        self.prelist = []

        currentPlaylist = glob.active_playlist
        currentCategoryList = currentPlaylist.get("data", {}).get("live_categories", [])
        currentHidden = set(currentPlaylist.get("player_info", {}).get("livehidden", []))

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

    def getLevel2(self):
        # print("*** getLevel2 ***")
        response = ""
        if self.chosen_category == "favourites":
            response = glob.active_playlist["player_info"].get("livefavourites", [])
        elif self.chosen_category == "recents":
            response = glob.active_playlist["player_info"].get("liverecents", [])
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
                if "stream_type" in channel and channel["stream_type"] and channel["stream_type"] != "live":
                    pattern = re.compile(r"[^\w\s()\[\]]", re.U)
                    name = re.sub(r"_", "", re.sub(pattern, "", name))
                    name = "** " + str(name) + " **"

                stream_id = channel.get("stream_id", "")
                if not stream_id:
                    continue

                hidden = str(stream_id) in glob.active_playlist["player_info"]["channelshidden"]

                stream_icon = str(channel.get("stream_icon", ""))

                if stream_icon and stream_icon.startswith("http"):
                    if stream_icon.startswith("https://vignette.wikia.nocookie.net/tvfanon6528"):
                        if "scale-to-width-down" not in stream_icon:
                            stream_icon = str(stream_icon) + "/revision/latest/scale-to-width-down/220"
                else:
                    stream_icon = ""

                epg_channel_id = str(channel.get("epg_channel_id", ""))
                if epg_channel_id and "&" in epg_channel_id:
                    epg_channel_id = epg_channel_id.replace("&", "&amp;")

                added = str(channel.get("added", "0"))

                category_id = str(channel.get("category_id", ""))
                if self.chosen_category == "all" and str(category_id) in glob.active_playlist["player_info"]["livehidden"]:
                    continue

                try:
                    bouquet_id1 = int(stream_id) // 65535
                    bouquet_id2 = int(stream_id) - int(bouquet_id1 * 65535)
                except:
                    continue

                service_ref = "1:0:1:" + str(format(bouquet_id1, "x")) + ":" + str(format(bouquet_id2, "x")) + ":" + str(format(self.unique_ref, "x")) + ":0:0:0:0:" + "http%3a//example.m3u8"

                custom_sid = str(channel.get("custom_sid", ""))
                if custom_sid and custom_sid not in {"null", "None", "0"}:
                    if channel["custom_sid"][0].isdigit():
                        channel["custom_sid"] = "1" + channel["custom_sid"][1:]

                    elif str(channel["custom_sid"]).startswith(":0"):
                        channel["custom_sid"] = "1" + channel["custom_sid"]

                    service_ref = str(":".join(channel["custom_sid"].split(":")[:7])) + ":0:0:0:" + "http%3a//example.m3u8"
                    custom_sid = channel["custom_sid"]

                next_url = "{}/live/{}/{}/{}.{}".format(self.host, self.username, self.password, stream_id, self.output)

                favourite = False
                if "livefavourites" in glob.active_playlist["player_info"]:
                    for fav in glob.active_playlist["player_info"]["livefavourites"]:
                        if str(stream_id) == str(fav["stream_id"]):
                            favourite = True
                            break
                else:
                    glob.active_playlist["player_info"]["livefavourites"] = []

                """
                0 = index
                1 = name
                2 = stream_id
                3 = stream_icon
                4 = epg_channel_id
                5 = add
                6 = category_id
                7 = custom_sid
                8 = service_ref
                9 = nowtime
                10 = nowTitle
                11 = nowDescription
                12 = nexttime
                13 = nextTitle
                14 = nextDesc
                15 = next_url
                16 = favourite
                17 = watched
                18 = hidden
                19 = nowunixtime
                20 = nextunixtime
                """

                self.list2.append([index, str(name), str(stream_id), str(stream_icon), str(epg_channel_id), str(added), str(category_id), str(custom_sid), str(service_ref),
                                  "", "", "", "", "", "", str(next_url), favourite, False, hidden, None, None])

        glob.originalChannelList2 = self.list2[:]

    def downloadApiData(self, url):
        # print("*** downloadApiData ***")
        try:
            retries = Retry(total=3, backoff_factor=1)
            adapter = HTTPAdapter(max_retries=retries)

            with requests.Session() as http:  # Use 'with' to ensure the session is closed
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

    def xmltvCheckData(self):
        # print("*** xmltvCheckData ***")
        safeName = re.sub(r'[\<\>\:\"\/\\\|\?\*]', "_", str(glob.active_playlist["playlist_info"]["name"]))
        safeName = re.sub(r" +", "_", safeName)  # Combine multiple spaces into one underscore
        safeName = re.sub(r"_+", "_", safeName)  # Replace multiple underscores with a single underscore

        filepath = "/etc/epgimport/"
        filename = "xstreamity.sources.xml"
        sourcepath = os.path.join(filepath, filename)
        epgfilename = "xstreamity.{}.channels.xml".format(safeName)
        channelpath = os.path.join(filepath, epgfilename)

        if (not os.path.exists(sourcepath)) or (not os.path.exists(channelpath)):
            self.downloadXMLTVdata()

        else:
            # check file creation times - refresh if older than 4 hours.
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

        if self["key_blue"].getText() != _("Reset Search"):
            self.pre_list = [buildCategoryList(x[0], x[1], x[2], x[3]) for x in self.prelist if not x[3]]
        else:
            self.pre_list = []

        self.main_list = [buildCategoryList(x[0], x[1], x[2], x[3]) for x in self.list1 if not x[3]]

        self["main_list"].setList(self.pre_list + self.main_list)

        if self["main_list"].getCurrent() and glob.nextlist[-1]["index"] != 0:
            self["main_list"].setIndex(glob.nextlist[-1]["index"])

    def buildList2(self):
        # print("*** buildlist2 ***")
        self.main_list = []
        self.epglist = []
        # index = 0, name = 1, stream_id = 2, stream_icon = 3, epg_channel_id = 4, added = 5, category_id = 6, custom_sid = 7, nowtime = 9
        # nowTitle = 10, nowDesc = 11, nexttime = 12, nextTitle = 13, nextDesc = 14, next_url = 15, favourite = 16, watching = 17, hidden = 18, nowunixtime = 19, nowunixtime = 20
        if self.chosen_category == "favourites":
            self.main_list = [buildLiveStreamList(x[0], x[1], x[2], x[3], x[15], x[16], x[17], x[18]) for x in self.list2 if x[16] is True]
            self.epglist = [buildEPGListEntry(x[0], x[2], x[9], x[10], x[11], x[12], x[13], x[14], x[18], x[19], x[20]) for x in self.list2 if x[16] is True]
        else:
            self.main_list = [buildLiveStreamList(x[0], x[1], x[2], x[3], x[15], x[16], x[17], x[18]) for x in self.list2 if x[18] is False]
            self.epglist = [buildEPGListEntry(x[0], x[2], x[9], x[10], x[11], x[12], x[13], x[14], x[18], x[19], x[20]) for x in self.list2 if x[18] is False]

        self["main_list"].setList(self.main_list)
        self["epg_list"].setList(self.epglist)
        if self.main_list:
            self.showEPG()

        if self["main_list"].getCurrent() and glob.nextlist[-1]["index"] != 0:
            self["main_list"].setIndex(glob.nextlist[-1]["index"])

    def buttons(self):
        # print("*** buttons ***")
        if glob.nextlist[-1]["filter"]:
            self["key_yellow"].setText("")
            self["key_blue"].setText(_("Reset Search"))
            self["key_menu"].setText("")
        else:
            if self.chosen_category == "recents":
                self["key_blue"].setText(_("Delete"))
            else:
                self["key_blue"].setText(_("Search"))

            if not glob.nextlist[-1]["sort"]:
                self.sortText = _("Sort: A-Z")
                glob.nextlist[-1]["sort"] = self.sortText

            self["key_yellow"].setText(_(glob.nextlist[-1]["sort"]))

            self["key_menu"].setText("+/-")

            if self.chosen_category == "favourites" or self.chosen_category == "recent":
                self["key_menu"].setText("")

    def stopStream(self):
        # print("*** stop stream ***")
        current_playing_ref = glob.currentPlayingServiceRefString
        new_playing_ref = glob.newPlayingServiceRefString

        if current_playing_ref and new_playing_ref and current_playing_ref != new_playing_ref:
            currently_playing_service = self.session.nav.getCurrentlyPlayingServiceReference()
            if currently_playing_service:
                self.session.nav.stopService()
            self.session.nav.playService(eServiceReference(current_playing_ref))
            glob.newPlayingServiceRefString = current_playing_ref

    def selectionChanged(self):
        # print("*** selectionchanged ***")
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

            self.loadBlankImage()

            if self.level == 2:

                if not self.showingshortEPG:
                    self["epg_list"].setIndex(current_index)

                    if not self.xmltvdownloaded and os.path.isfile(self.epgjsonfile):
                        self.xmltvdownloaded = True
                        self.addEPG()
                    else:
                        self.refreshEPGInfo()
                    self.timerimage = eTimer()
                    try:
                        self.timerimage.stop()
                    except:
                        pass

                if cfg.channelpicons.value:
                    try:
                        self.timerimage.callback.append(self.downloadImage)
                    except:
                        self.timerimage_conn = self.timerimage.timeout.connect(self.downloadImage)
                    self.timerimage.start(250, True)
        else:
            position = 0
            position_all = 0
            page = 0
            page_all = 0

            self["page"].setText(_("Page: ") + "{}/{}".format(page, page_all))
            self["listposition"].setText("{}/{}".format(position, position_all))
            self["key_yellow"].setText("")
            self["key_blue"].setText("")

    def downloadImage(self):
        # print("*** downloadimage ***")
        if self["main_list"].getCurrent():
            try:
                for filename in ["original.png", "temp.png"]:
                    file_path = os.path.join(dir_tmp, filename)
                    if os.path.exists(file_path):
                        os.remove(file_path)
            except Exception:
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
                except Exception:
                    self.loadDefaultImage()
            else:
                self.loadDefaultImage()

    def loadBlankImage(self, data=None):
        # print("*** loadblankimage ***")
        if self["picon"].instance:
            self["picon"].instance.setPixmapFromFile(os.path.join(common_path, "picon_blank.png"))

    def loadDefaultImage(self, data=None):
        # print("*** loaddefaultimage ***")
        if self["picon"].instance:
            self["picon"].instance.setPixmapFromFile(os.path.join(common_path, "picon.png"))

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
                        im.thumbnail(size, Image.Resampling.LANCZOS)
                    except:
                        im.thumbnail(size, Image.ANTIALIAS)

                    # Create blank RGBA image
                    bg = Image.new("RGBA", size, (255, 255, 255, 0))

                    # Calculate position for centering

                    left = (size[0] - im.size[0]) // 2
                    top = (size[1] - im.size[1]) // 2

                    # Paste resized image onto blank image
                    bg.paste(im, (left, top), mask=im)

                    # Save as PNG
                    bg.save(original, "PNG")

                    # Set pixmap for picon instance
                    if self["picon"].instance:
                        self["picon"].instance.setPixmapFromFile(original)

                except Exception as e:
                    print("Error resizing image:", e)
                    self.loadDefaultImage()
            else:
                self.loadDefaultImage()

    def goUp(self):
        # print("*** goup ***")
        instance = self.selectedlist.master.master.instance
        instance.moveSelection(instance.moveUp)
        self.selectionChanged()

    def goDown(self):
        # print("*** godown ***")
        instance = self.selectedlist.master.master.instance
        instance.moveSelection(instance.moveDown)
        self.selectionChanged()

    def pageUp(self):
        # print("*** pageup ***")
        instance = self.selectedlist.master.master.instance
        instance.moveSelection(instance.pageUp)
        self.selectionChanged()

    def pageDown(self):
        # print("*** pagedown ***")
        instance = self.selectedlist.master.master.instance
        instance.moveSelection(instance.pageDown)
        self.selectionChanged()

    # button 0
    def reset(self):
        # print("*** reset ***")
        self.selectedlist.setIndex(0)
        self.selectionChanged()

    def sort(self):
        # print("*** sort ***")

        current_sort = self["key_yellow"].getText()
        if not current_sort or current_sort == _("Reverse"):
            return

        activelist = self.list1 if self.level == 1 else self.list2

        sortlist = [_("Sort: A-Z"), _("Sort: Z-A")]
        if self.level == 1:
            sortlist.append(_("Sort: Original"))
        else:
            sortlist.extend([_("Sort: Added"), _("Sort: Original")])

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
            if self.level != 1:
                activelist.sort(key=lambda x: x[1].lower(), reverse=False)
                activelist.sort(key=lambda x: (x[5] or ""), reverse=True)

        elif current_sort == _("Sort: Original"):
            activelist.sort(key=lambda x: x[0], reverse=False)

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

            del glob.active_playlist["player_info"]['liverecents'][current_index]
            self.hideEPG()

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
        # print("*** filterchannels ***")
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
        # print("*** resetsearch ***")
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
        # print("*** pinentered ***")
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
            current_index = self["main_list"].getIndex()
            glob.nextlist[-1]["index"] = current_index
            glob.currentchannellist = self.main_list[:]
            glob.currentchannellistindex = current_index

            if self.level == 1:
                if self.list1:
                    category_id = self["main_list"].getCurrent()[3]

                    next_url = "{0}&action=get_live_streams&category_id={1}".format(self.player_api, category_id)
                    self.chosen_category = ""

                    if category_id == "0":
                        next_url = "{0}&action=get_live_streams".format(self.player_api)
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
                    glob.currentepglist = self.epglist[:]

                    if self.selectedlist == self["epg_short_list"]:
                        self.shortEPG()

                    streamtype = glob.active_playlist["player_info"]["livetype"]
                    next_url = self["main_list"].getCurrent()[3]
                    stream_id = self["main_list"].getCurrent()[4]

                    if str(os.path.splitext(next_url)[-1]) == ".m3u8":
                        if streamtype == "1":
                            streamtype = "4097"

                    self.reference = eServiceReference(int(streamtype), 0, next_url)

                    self.reference.setName(glob.currentchannellist[glob.currentchannellistindex][0])

                    if self.session.nav.getCurrentlyPlayingServiceReference():

                        if self.session.nav.getCurrentlyPlayingServiceReference().toString() != self.reference.toString() and cfg.livepreview.value is True:
                            try:
                                self.session.nav.stopService()
                            except Exception as e:
                                print(e)

                            try:
                                self.session.nav.playService(self.reference)
                            except Exception as e:
                                print(e)

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
                            for channel in self.list2:
                                if channel[2] == stream_id:
                                    channel[17] = True  # set watching icon
                                else:
                                    channel[17] = False

                            self.buildLists()

                            try:
                                self.session.nav.stopService()
                            except:
                                pass

                            self.session.openWithCallback(self.setIndex, liveplayer.XStreamity_StreamPlayer, str(next_url), str(streamtype), stream_id)
                    else:
                        try:
                            self.session.nav.stopService()
                        except:
                            pass

                        self.session.openWithCallback(self.setIndex, liveplayer.XStreamity_StreamPlayer, str(next_url), str(streamtype), stream_id)

                    self["category_actions"].setEnabled(False)

                else:
                    self.createSetup()

    def setIndex(self, data=None):
        # print("*** setindex ***")
        if self["main_list"].getCurrent():
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

        if not glob.nextlist:
            self.stopStream()
            self.close()
        else:
            # self.lastviewed_url = ""
            # self.lastviewed_id = ""
            # self.lastviewed_index = 0

            self["x_title"].setText("")
            self["x_description"].setText("")

            if cfg.stopstream.value or not cfg.livepreview.value:
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
                self.xmltvdownloaded = False
                self.session.openWithCallback(self.createSetup, hidden.XStreamity_HiddenCategories, "live", current_list, self.level)

    def favourite(self):
        # print("*** favourite ***")
        if not self["main_list"].getCurrent():
            return

        current_index = self["main_list"].getIndex()
        favExists = False
        favStream_id = ""

        for fav in glob.active_playlist["player_info"]["livefavourites"]:
            if self["main_list"].getCurrent()[4] == fav["stream_id"]:
                favExists = True
                favStream_id = fav["stream_id"]
                break

        self.list2[current_index][16] = not self.list2[current_index][16]

        if favExists:
            glob.active_playlist["player_info"]["livefavourites"] = [x for x in glob.active_playlist["player_info"]["livefavourites"] if str(x["stream_id"]) != str(favStream_id)]
        else:
            newfavourite = {
                "name": self.list2[current_index][1],
                "stream_id": self.list2[current_index][2],
                "stream_icon": self.list2[current_index][3],
                "epg_channel_id": self.list2[current_index][4],
                "added": self.list2[current_index][5],
                "category_id": self.list2[current_index][6],
                "custom_sid": self.list2[current_index][7]
            }

            glob.active_playlist["player_info"]["livefavourites"].insert(0, newfavourite)
            # self.hideEPG()

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
            del self.list2[current_index]

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

                                    entry[0] = int(entry[0]) + (int(glob.active_playlist["player_info"]["epgoffset"]) * 3600)
                                    entry[1] = int(entry[1]) + (int(glob.active_playlist["player_info"]["epgoffset"]) * 3600)

                                    if int(entry[0]) < now and int(entry[1]) > now:

                                        channel[9] = str(time.strftime("%H:%M", time.localtime(int(entry[0]))))
                                        channel[10] = str(entry[2])
                                        channel[11] = str(entry[3])
                                        channel[19] = int(entry[0])

                                        channel[12] = str(time.strftime("%H:%M", time.localtime(int(entry[1]))))
                                        channel[13] = str(next_el[2])
                                        channel[14] = str(next_el[3])
                                        channel[20] = int(entry[1])

                                        break
                        else:
                            self.eventslist = []
                            serviceref = channel[8]

                            events = ["IBDTEX", (serviceref, -1, -1, -1)]  # search next 12 hours
                            self.eventslist = [] if self.epgcache is None else self.epgcache.lookupEvent(events)

                            for i in range(len(self.eventslist)):
                                if self.eventslist[i][1] is not None:
                                    self.eventslist[i] = (self.eventslist[i][0], self.eventslist[i][1], self.eventslist[i][2], self.eventslist[i][3], self.eventslist[i][4])

                            if self.eventslist:
                                if len(self.eventslist) > 0:
                                    try:
                                        # start time
                                        if self.eventslist[0][1]:
                                            channel[9] = str(time.strftime("%H:%M", time.localtime(self.eventslist[0][1])))
                                            channel[19] = int(self.eventslist[0][1])

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
                                        channel[20] = int(self.eventslist[1][1])

                                    # next title
                                    if self.eventslist[1][3]:
                                        channel[13] = str(self.eventslist[1][3])

                                    # next description
                                    if self.eventslist[1][4]:
                                        channel[14] = str(self.eventslist[1][4])
                                except Exception as e:
                                    print(e)

                    self.epglist = [buildEPGListEntry(x[0], x[1], x[9], x[10], x[11], x[12], x[13], x[14], x[18], x[19], x[20]) for x in self.list2 if x[18] is False]
                    self["epg_list"].updateList(self.epglist)

                    instance = self["epg_list"].master.master.instance
                    instance.setSelectionEnable(0)
                    self.xmltvdownloaded = True
                    self.refreshEPGInfo()
                except Exception as e:
                    print(e)

    def hideEPG(self):
        # print("*** hideEPG ***")
        self["epg_list"].setList([])
        self["picon"].hide()
        self["epg_bg"].hide()
        self["x_title"].setText("")
        self["x_description"].setText("")
        self["progress"].hide()

    def showEPG(self):
        # print("*** showEPG ***")
        self["picon"].show()
        self["epg_bg"].show()
        self["progress"].show()

    def refreshEPGInfo(self):
        # print("*** refreshEPG ***")
        current_item = self["epg_list"].getCurrent()
        if not current_item:
            return

        instance = self["epg_list"].master.master.instance
        instance.setSelectionEnable(1)

        titlenow = current_item[3]
        descriptionnow = current_item[4]
        startnowtime = current_item[2]
        startnexttime = current_item[5]
        startnowunixtime = current_item[9]
        startnextunixtime = current_item[10]

        if titlenow:
            nowTitle = "{} - {}  {}".format(startnowtime, startnexttime, titlenow)
            self["key_epg"].setText(_("Next Info"))
        else:
            nowTitle = ""
            self["key_epg"].setText("")
            instance.setSelectionEnable(0)

        self["x_title"].setText(nowTitle)
        self["x_description"].setText(descriptionnow)

        percent = 0

        if startnowunixtime and startnextunixtime:
            self["progress"].show()

            now = int(time.time())
            total_time = startnextunixtime - startnowunixtime
            elapsed = now - startnowunixtime

            percent = int(elapsed / total_time * 100) if total_time > 0 else 0

            self["progress"].setValue(percent)
        else:
            self["progress"].hide()

    def nownext(self):
        # print("*** nownext ***")
        current_item = self["main_list"].getCurrent()
        if not current_item:
            return

        if self.level == 2 and self["key_epg"].getText() and self["epg_list"].getCurrent():
            startnowtime = self["epg_list"].getCurrent()[2]
            titlenow = self["epg_list"].getCurrent()[3]
            descriptionnow = self["epg_list"].getCurrent()[4]

            startnexttime = self["epg_list"].getCurrent()[5]
            titlenext = self["epg_list"].getCurrent()[6]
            descriptionnext = self["epg_list"].getCurrent()[7]

            if self["key_epg"].getText() == _("Next Info"):
                nextTitle = "Next {}: {}".format(startnexttime, titlenext)
                self["x_title"].setText(nextTitle)
                self["x_description"].setText(descriptionnext)
                self["key_epg"].setText(_("Now Info"))
            else:
                nowTitle = "{} - {}  {}".format(startnowtime, startnexttime, titlenow)
                self["x_title"].setText(nowTitle)
                self["x_description"].setText(descriptionnow)
                self["key_epg"].setText(_("Next Info"))

    def parse_datetime(self, datetime_str):
        time_formats = ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H-%M-%S", "%Y-%m-%d-%H:%M:%S", "%Y- %m-%d %H:%M:%S"]

        for time_format in time_formats:
            try:
                return datetime.strptime(datetime_str, time_format)
            except ValueError:
                pass
        return ""  # Return None if none of the formats match

    def shortEPG(self):
        # print("*** shortEPG ***")
        if self["main_list"].getCurrent():
            self.showingshortEPG = not self.showingshortEPG

            if self.showingshortEPG:
                self["key_menu"].setText("")

                current_index = self["main_list"].getIndex()
                glob.nextlist[-1]["index"] = current_index

                self["epg_list"].setList([])
                next_url = self["main_list"].getCurrent()[3]

                if self.level == 2:
                    try:
                        stream_id = next_url.rpartition("/")[-1].partition(".")[0]

                        url = "{}&action=get_simple_data_table&stream_id={}".format(self.player_api, stream_id)

                        retries = Retry(total=3, backoff_factor=1)
                        adapter = HTTPAdapter(max_retries=retries)

                        with requests.Session() as http:  # Use 'with' to ensure the session is closed
                            http.mount("http://", adapter)
                            http.mount("https://", adapter)

                            try:
                                r = http.get(url, headers=hdr, timeout=(10, 20), verify=False)
                                r.raise_for_status()

                                if r.status_code == requests.codes.ok:
                                    response = r.json()
                            except Exception as e:
                                print("Error fetching short EPG:", e)

                        if response:
                            now = datetime.now()
                            self.epgshortlist = []
                            duplicatecheck = []

                            if "epg_listings" in response and response["epg_listings"]:
                                for index, listing in enumerate(response["epg_listings"]):
                                    try:
                                        title = base64.b64decode(listing.get("title", "")).decode("utf-8")
                                        description = base64.b64decode(listing.get("description", "")).decode("utf-8")
                                        shift = int(glob.active_playlist["player_info"].get("serveroffset", 0))
                                        start = listing.get("start", "")
                                        end = listing.get("end", listing.get("stop", ""))

                                        start_timestamp = int(listing.get("start_timestamp", 0))
                                        stop_timestamp = int(listing.get("stop_timestamp", 0))

                                        start_timestamp += (3600 * shift)
                                        stop_timestamp += (3600 * shift)

                                        start_datetime = self.parse_datetime(start)
                                        end_datetime = self.parse_datetime(end)

                                        if start_datetime and end_datetime:
                                            start_datetime += timedelta(hours=shift)
                                            end_datetime += timedelta(hours=shift)
                                            epg_date_all = start_datetime.strftime("%a %d/%m")
                                            epg_time_all = "{} - {}".format(start_datetime.strftime("%H:%M"), end_datetime.strftime("%H:%M"))

                                            if [epg_date_all, epg_time_all] not in duplicatecheck and end_datetime >= now:
                                                duplicatecheck.append([epg_date_all, epg_time_all])
                                                self.epgshortlist.append(buildShortEPGListEntry(str(epg_date_all), str(epg_time_all), str(title), str(description), index, start_datetime, end_datetime, start_timestamp, stop_timestamp))
                                    except Exception as e:
                                        print("Error processing short EPG data:", e)

                            self["epg_short_list"].setList(self.epgshortlist)
                            instance = self["epg_short_list"].master.master.instance
                            instance.setSelectionEnable(1)

                            self["progress"].hide()
                            self["key_yellow"].setText("")
                            self["key_blue"].setText("")
                            self["key_epg"].setText("")

                            self.selectedlist = self["epg_short_list"]
                            # self.displayShortEPG()
                    except Exception as e:
                        print("Error fetching short EPG:", e)
            else:
                self["epg_short_list"].setList([])
                self.selectedlist = self["main_list"]
                self.buildLists()

    def displayShortEPG(self):
        # print("*** displayshortEPG ***")
        if self["epg_short_list"].getCurrent():
            title = str(self["epg_short_list"].getCurrent()[0])
            description = str(self["epg_short_list"].getCurrent()[3])
            timeall = str(self["epg_short_list"].getCurrent()[2])
            self["x_title"].setText(timeall + " " + title)
            self["x_description"].setText(description)

    # record button download video file
    def downloadStream(self, limitEvent=True):
        # print("*** downloadstream ***")
        from . import record
        current_index = self["main_list"].getIndex()
        begin = int(time.time())
        end = begin + 3600
        self.date = time.time()

        if len(self.epgshortlist) > current_index:

            if self.epglist[current_index][3]:
                name = self.epglist[current_index][3]
            else:
                name = self.epglist[current_index][0]

            if self.epglist[current_index][10]:
                end = self.epglist[current_index][10]

            if self.showingshortEPG:
                current_index = self["epg_short_list"].getIndex()

                if self.epgshortlist[current_index][0]:
                    name = self.epgshortlist[current_index][0]

                if self.epgshortlist[current_index][1]:
                    self.date = self.epgshortlist[current_index][7]

                if self.epgshortlist[current_index][2]:
                    begin = self.epgshortlist[current_index][7]
                    end = self.epgshortlist[current_index][8]

        self.name = NoSave(ConfigText(default=name, fixed_size=False))
        self.starttime = NoSave(ConfigClock(default=begin))
        self.endtime = NoSave(ConfigClock(default=end))

        self.session.openWithCallback(self.RecordDateInputClosed, record.RecordDateInput, self.name, self.date, self.starttime, self.endtime)

    def RecordDateInputClosed(self, data=None):
        # print("*** recorddateinputclosed ***")
        if data:
            begin = data[1]
            end = data[2]
            name = data[3]

            current_index = self["main_list"].getIndex()
            description = ""
            streamurl = self["main_list"].getCurrent()[3]
            streamtype = 1

            if self.epglist[current_index][4]:
                description = self.epglist[current_index][4]

            if self.showingshortEPG:
                current_index = self["epg_short_list"].getIndex()
                if self.epgshortlist[current_index][3]:
                    description = str(self.epgshortlist[current_index][3])

            eventid = int(streamurl.rpartition("/")[-1].partition(".")[0])

            if streamurl.endswith("m3u8"):
                streamtype = 4097

            self.reference = eServiceReference(streamtype, 0, streamurl)

            # switch channel to prevent multi active users
            if self.session.nav.getCurrentlyPlayingServiceReference().toString() != self.reference.toString():
                self.session.nav.stopService()
                self.session.nav.playService(self.reference)

                if self.session.nav.getCurrentlyPlayingServiceReference():
                    glob.newPlayingServiceRef = self.session.nav.getCurrentlyPlayingServiceReference()
                    glob.newPlayingServiceRefString = glob.newPlayingServiceRef.toString()

            if isinstance(self.reference, eServiceReference):
                serviceref = ServiceReference(self.reference)

            recording = RecordTimerEntry(serviceref, begin, end, name, description, eventid, dirname=str(cfg.downloadlocation.value))
            recording.dontSave = False

            simulTimerList = self.session.nav.RecordTimer.record(recording)

            if simulTimerList is None:  # no conflict
                recording.autoincrease = False
                self.session.open(MessageBox, _("Recording Timer Set."), MessageBox.TYPE_INFO, timeout=5)
            else:
                self.session.open(MessageBox, _("Recording Failed."), MessageBox.TYPE_WARNING)
        return

    def downloadXMLTVdata(self):
        # print("*** downloadxmltvdata ***")
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
        print(("[EPG] download failed:", failure))

    def downloadComplete(self, data=None, filename=None):
        # print("*** downloadcomplete ***")
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
        # print("*** buildxmltv ***")
        safeName = re.sub(r'[\<\>\:\"\/\\\|\?\*]', "_", str(glob.active_playlist["playlist_info"]["name"]))
        safeName = re.sub(r" +", "_", safeName)
        safeName = re.sub(r"_+", "_", safeName)

        filepath = "/etc/epgimport/"
        epgfilename = "xstreamity." + str(safeName) + ".channels.xml"
        channelpath = os.path.join(filepath, epgfilename)

        # if xmltv file doesn't already exist, create file and build.
        if not os.path.isfile(channelpath):
            with open(channelpath, "a") as f:
                pass

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

            tree = ET.parse(sourcefile, parser=ET.XMLParser(encoding="utf-8"))
            root = tree.getroot()
            sourcecat = root.find("sourcecat")

            exists = any(channelpath in sourceitem.attrib["channels"] for sourceitem in sourcecat)

            if not exists:
                source = ET.SubElement(sourcecat, "source", type="gen_xmltv", nocheck="1", channels=channelpath)
                description = ET.SubElement(source, "description")
                description.text = str(safeName)

                url = ET.SubElement(source, "url")
                url.text = str(glob.active_playlist["playlist_info"]["xmltv_api"])

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

            for i, channel in enumerate(self.xmltv_channel_list):
                channelid = str(channel.get("epg_channel_id", ""))
                if channelid and "&" in channelid:
                    channelid = channelid.replace("&", "&amp;")

                stream_id = int(channel.get("stream_id", 0))
                try:
                    bouquet_id1 = int(stream_id) // 65535
                    bouquet_id2 = int(stream_id) - int(bouquet_id1 * 65535)
                except:
                    continue

                service_ref = "1:0:1:" + str(format(bouquet_id1, "x")) + ":" + str(format(bouquet_id2, "x")) + ":" + str(format(self.unique_ref, "x")) + ":0:0:0:0:" + "http%3a//example.m3u8"

                custom_sid = str(channel.get("custom_sid", ""))
                if custom_sid and custom_sid not in {"null", "None", "0"}:
                    if channel["custom_sid"][0].isdigit():
                        channel["custom_sid"] = "1" + channel["custom_sid"][1:]

                    elif str(channel["custom_sid"]).startswith(":0"):
                        channel["custom_sid"] = "1" + channel["custom_sid"]

                    service_ref = str(":".join(channel["custom_sid"].split(":")[:7])) + ":0:0:0:" + "http%3a//example.m3u8"

                self.xmltv_channel_list[i]["serviceref"] = str(service_ref)
                name = self.xmltv_channel_list[i]["name"]

                if channelid and channelid != "None":
                    xml_str += '\t<channel id="' + str(channelid) + '">' + str(service_ref) + '</channel><!-- ' + str(name) + ' -->\n'

            xml_str += '</channels>\n'
            f.write(xml_str)

        # self.buildLists()

    def epgminus(self):
        # print("*** epgminus ***")
        self.epgtimeshift -= 1
        if self.epgtimeshift <= 0:
            self.epgtimeshift = 0
        self.addEPG()

    def epgplus(self):
        # print("*** epgplus ***")
        self.epgtimeshift += 1
        self.addEPG()

    def epgreset(self):
        # print("*** epg reset ***")
        self.epgtimeshift = 0
        self.addEPG()


def buildEPGListEntry(index, title, epgNowTime, epgNowTitle, epgNowDesc, epgNextTime, epgNextTitle, epgNextDesc, hidden, epgNowUnixTime, epgNextUnixTime):
    return (title, index, epgNowTime, epgNowTitle, epgNowDesc, epgNextTime, epgNextTitle, epgNextDesc, hidden, epgNowUnixTime, epgNextUnixTime)


def buildShortEPGListEntry(date_all, time_all, title, description, index, start_datetime, end_datetime, start_timestamp, stop_timestamp):
    return (title, date_all, time_all, description, index, start_datetime, end_datetime, start_timestamp, stop_timestamp)


def buildCategoryList(index, title, category_id, hidden):
    png = LoadPixmap(os.path.join(common_path, "more.png"))
    return (title, png, index, category_id, hidden)


def buildLiveStreamList(index, name, stream_id, stream_icon, next_url, favourite, watching, hidden):
    png = LoadPixmap(os.path.join(common_path, "play.png"))
    if favourite:
        png = LoadPixmap(os.path.join(common_path, "favourite.png"))
    if watching:
        png = LoadPixmap(os.path.join(common_path, "watching.png"))
    return (name, png, index, next_url, stream_id, stream_icon, hidden)
