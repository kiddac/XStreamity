#!/usr/bin/python
# -*- coding: utf-8 -*-

from . import _
from . import streamplayer
from . import xstreamity_globals as glob

from .plugin import skin_path, screenwidth, hdr, cfg, common_path, dir_tmp, json_file
from .xStaticText import StaticText
from collections import Counter
from Components.ActionMap import ActionMap
from Components.config import config, ConfigClock, NoSave, ConfigText
from Components.Pixmap import Pixmap
from Components.ProgressBar import ProgressBar
from Components.Sources.List import List
from datetime import datetime, timedelta, date
from enigma import eTimer, eServiceReference, eEPGCache
from os import system
from PIL import Image, ImageChops, ImageFile, PngImagePlugin
from requests.adapters import HTTPAdapter
from RecordTimer import RecordTimerEntry
from Screens.MessageBox import MessageBox
from Screens.Screen import Screen
from Screens.VirtualKeyBoard import VirtualKeyBoard
from ServiceReference import ServiceReference
from time import localtime, strftime, time
from Tools.LoadPixmap import LoadPixmap
from twisted.web.client import downloadPage


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
import xml.etree.cElementTree as ET

_simple_palette = re.compile(b"^\xff*\x00\xff*$")


def mycall(self, cid, pos, length):
    if cid.decode("ascii") == "tRNS":
        return self.chunk_TRNS(pos, length)
    else:
        return getattr(self, "chunk_" + cid.decode("ascii"))(pos, length)


def mychunk_TRNS(self, pos, length):
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


try:
    pythonVer = sys.version_info.major
except:
    pythonVer = 2

if pythonVer != 2:
    PngImagePlugin.ChunkStream.call = mycall
    PngImagePlugin.PngStream.chunk_TRNS = mychunk_TRNS

# https twisted client hack #
try:
    from twisted.internet import ssl
    from twisted.internet._sslverify import ClientTLSOptions
    sslverify = True
except:
    sslverify = False

if sslverify:
    try:
        from urlparse import urlparse
    except:
        from urllib.parse import urlparse

    class SNIFactory(ssl.ClientContextFactory):
        def __init__(self, hostname=None):
            self.hostname = hostname

        def getContext(self):
            ctx = self._contextFactory(self.method)
            if self.hostname:
                ClientTLSOptions(self.hostname, ctx)
            return ctx

epgimporter = False
if os.path.isdir('/usr/lib/enigma2/python/Plugins/Extensions/EPGImport'):
    epgimporter = True

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


class XStreamity_Categories(Screen):

    def __init__(self, session):
        Screen.__init__(self, session)
        self.session = session

        self.searchString = ''

        skin = skin_path + 'categories.xml'
        if os.path.exists('/var/lib/dpkg/status'):
            skin = skin_path + 'DreamOS/categories.xml'

        with codecs.open(skin, 'r', encoding='utf-8') as f:
            self.skin = f.read()

        self.setup_title = (_('Categories'))
        self.main_title = (_("Live Streams"))

        nexturl = str(glob.current_playlist['playlist_info']['player_api']) + "&action=get_live_categories"

        self.level = 1
        glob.nextlist = []
        glob.nextlist.append({"playlist_url": nexturl, "index": 0, "level": self.level, "sort": "Sort: A-Z", "filter": ""})

        self["channel"] = StaticText(self.main_title)

        self.channelList = []  # displayed list
        self["channel_list"] = List(self.channelList, enableWrapAround=True)

        self.selectedlist = self["channel_list"]

        # epg variables
        self["epg_bg"] = Pixmap()
        self["epg_bg"].hide()

        self["epg_title"] = StaticText()
        self["epg_description"] = StaticText()

        self.epglist = []
        self["epg_list"] = List(self.epglist)

        self.epgshortlist = []
        self["epg_short_list"] = List(self.epgshortlist, enableWrapAround=True)
        self["epg_short_list"].onSelectionChanged.append(self.displayShortEPG)

        self["epg_picon"] = Pixmap()
        self["epg_picon"].hide()

        self["downloading"] = Pixmap()
        self["downloading"].hide()

        self["progress"] = ProgressBar()
        self["progress"].hide()

        self.showingshortEPG = False

        self.xmltvdownloaded = False
        self.e2epgdownloaded = False

        self.epgchecklist = []
        self.epgdownloading = False
        self.epg_channel_list = []
        self.xmltvcategorydownloaded = False
        self.enigma2epgcategorydownloaded = False
        self.favourites_category = False

        # vod variables
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
        self["vod_title"] = StaticText()
        self["vod_description"] = StaticText()
        self["vod_video_type"] = StaticText()
        self["vod_duration"] = StaticText()
        self["vod_genre"] = StaticText()
        self["vod_rating"] = StaticText()
        self["vod_country"] = StaticText()
        self["vod_release_date"] = StaticText()
        self["vod_director"] = StaticText()
        self["vod_cast"] = StaticText()

        self.isStream = False
        self.filterresult = ""
        self.pin = False

        self.protocol = glob.current_playlist['playlist_info']['protocol']
        self.domain = glob.current_playlist['playlist_info']['domain']
        self.host = glob.current_playlist['playlist_info']['host']
        self.livetype = glob.current_playlist['player_info']['livetype']
        self.username = glob.current_playlist['playlist_info']['username']
        self.password = glob.current_playlist['playlist_info']['password']
        self.output = glob.current_playlist['playlist_info']['output']

        self["page"] = StaticText('')
        self["listposition"] = StaticText('')
        self.page = 0
        self.pageall = 0
        self.position = 0
        self.positionall = 0
        self.itemsperpage = 10

        self.lastviewed_url = ''
        self.lastviewed_id = ''
        self.lastviewed_index = 0

        self.timerEPG = eTimer()
        self.timerBusy = eTimer()

        self.editmode = False

        try:
            config.plugins.epgimport.import_onlybouquet.value = False
            config.plugins.epgimport.import_onlybouquet.save()
        except:
            pass

        self["key_red"] = StaticText(_('Back'))
        self["key_green"] = StaticText(_('OK'))
        self["key_yellow"] = StaticText(_('Sort: A-Z'))
        self["key_blue"] = StaticText(_('Search'))
        self["key_epg"] = StaticText('')
        self["key_rec"] = StaticText('')
        self["key_menu"] = StaticText('')

        self["category_actions"] = ActionMap(["XStreamityActions"], {
            'cancel': self.back,
            'red': self.back,
            'ok': self.parentalCheck,
            'green': self.parentalCheck,
            'yellow': self.sort,
            'blue': self.search,
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
            'cancel': self.back,
            'red': self.playStream,
            'ok': self.parentalCheck,
            'green': self.parentalCheck,
            'yellow': self.sort,
            'blue': self.search,
            'epg': self.nownext,
            'info': self.nownext,
            'text': self.nownext,
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
            "tv": self.favourite,
            "stop": self.favourite,
            "0": self.reset,
            "menu": self.showHiddenList,
        }, -1)

        self["favourites_actions"] = ActionMap(["XStreamityActions"], {
            'cancel': self.back,
            'red': self.playStream,
            'ok': self.parentalCheck,
            'green': self.parentalCheck,
            'yellow': self.sort,
            'blue': self.search,
            'epg': self.nownext,
            'info': self.nownext,
            'text': self.nownext,
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
            "tv": self.favourite,
            "stop": self.favourite,
            "0": self.reset,
            "menu": self.editfav,
        }, -1)

        self["channel_actions"].setEnabled(False)
        self["favourites_actions"].setEnabled(False)

        self.onFirstExecBegin.append(self.createSetup)
        self.onLayoutFinish.append(self.__layoutFinished)

    def __layoutFinished(self):
        self.setTitle(self.setup_title)

    def createSetup(self):
        # print("*** createSetup ***")
        self["epg_title"].setText('')
        self["epg_description"].setText('')

        if self.level == 1:  # category list
            self.processCategories()

        elif self.level == 2:  # channel list
            self.downloadChannels()

    def processCategories(self):
        # print("*** processCategories ***")
        index = 0
        self.list1 = []
        currentCategoryList = glob.current_playlist['data']['live_categories']

        next_url = str(glob.current_playlist['playlist_info']['player_api']) + "&action=get_live_streams&category_id=0"

        # add FAVOURITES category to list
        hidden = False
        if "-1" in glob.current_playlist['player_info']['livehidden']:
            hidden = True
        self.list1.append([index, _("FAVOURITES"), next_url + "0", "-1", hidden])
        index += 1

        # add ALL category to list
        hidden = False
        if "0" in glob.current_playlist['player_info']['livehidden']:
            hidden = True
        self.list1.append([index, _("ALL"), next_url, "0", hidden])
        index += 1

        for item in currentCategoryList:
            hidden = False
            category_name = item['category_name']
            category_id = item['category_id']

            next_url = str(glob.current_playlist['playlist_info']['player_api']) + "&action=get_live_streams&category_id=" + str(category_id)

            if category_id in glob.current_playlist['player_info']['livehidden']:
                hidden = True

            self.list1.append([index, str(category_name), str(next_url), str(category_id), hidden])
            index += 1

        glob.originalChannelList1 = self.list1[:]

        cleanName = re.sub(r'[\<\>\:\"\/\\\|\?\*]', '_', str(glob.current_playlist['playlist_info']['name']))
        cleanName = re.sub(r' ', '_', cleanName)
        cleanName = re.sub(r'_+', '_', cleanName)

        filepath = '/etc/epgimport/'
        filename = 'xstreamity.' + str(cleanName) + '.sources.xml'
        sourcepath = filepath + filename
        epgfilename = 'xstreamity.' + str(cleanName) + '.channels.xml'
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

        self.buildLists()

    def downloadChannels(self):
        # print("*** downloadChannels ***")
        url = glob.nextlist[-1]["playlist_url"]

        self.favourites_category = False
        if url.endswith("00"):
            self.favourites_category = True

        levelpath = str(dir_tmp) + 'level' + str(self.level) + '.json'

        if self.favourites_category:
            self.processChannels(glob.current_playlist['player_info']['livefavourites'])

        elif os.path.exists(levelpath):
            with codecs.open(levelpath, 'r', encoding='utf-8') as f:
                self.processChannels(json.load(f))
        else:
            adapter = HTTPAdapter(max_retries=0)
            http = requests.Session()
            http.mount("http://", adapter)
            try:
                r = http.get(url, headers=hdr, stream=True, timeout=10, verify=False)
                r.raise_for_status()
                if r.status_code == requests.codes.ok:
                    content = r.json()
                    with codecs.open(levelpath, 'w', encoding='utf-8') as f:
                        f.write(json.dumps(content))

                    self.processChannels(content)
            except Exception as e:
                print(e)

    def processChannels(self, response):
        # print("*** processChannels ***")
        index = 0
        self.category_id = ""

        self.list2 = []
        currentChannelList = response
        for item in currentChannelList:
            name = ''
            stream_id = ''
            stream_icon = ''
            epg_channel_id = ''
            added = ''
            category_id = ''
            custom_sid = ''
            serviceref = ''
            nowtime = ''
            nowTitle = ''
            nowDesc = ''
            nexttime = ''
            nextTitle = ''
            nextDesc = ''

            favourite = False
            watching = False
            editmode = False
            hidden = False

            if 'name' in item:
                name = item['name']

                # restyle bouquet markers
                if 'stream_type' in item and item['stream_type'] and item['stream_type'] != "live":
                    pattern = re.compile(r'[^\w\s()\[\]]', re.U)
                    name = re.sub(r'_', '', re.sub(pattern, '', name))
                    name = "** " + str(name) + " **"

            if 'stream_id' in item:
                stream_id = item['stream_id']

                if str(stream_id) in glob.current_playlist['player_info']['channelshidden']:
                    hidden = True

            if 'stream_icon' in item and item['stream_icon']:
                if item['stream_icon'].startswith("http"):
                    stream_icon = item['stream_icon']

                if stream_icon.startswith("https://vignette.wikia.nocookie.net/tvfanon6528"):
                    if "scale-to-width-down" not in stream_icon:
                        stream_icon = str(stream_icon) + "/revision/latest/scale-to-width-down/220"

            if 'epg_channel_id' in item:
                epg_channel_id = item['epg_channel_id']

                if epg_channel_id and "&" in epg_channel_id:
                    epg_channel_id = epg_channel_id.replace("&", "&amp;")

            if 'added' in item:
                added = item['added']

            if 'category_id' in item:
                category_id = item['category_id']

            bouquet_id = 0
            calc_remainder = int(stream_id) // 65535
            bouquet_id = bouquet_id + calc_remainder
            bouquet_stream_id = int(stream_id) - int(calc_remainder * 65535)
            unique_ref = 999 + int(glob.current_playlist['playlist_info']['index'])
            serviceref = '1:0:1:' + str(format(bouquet_id, '04x')) + ":" + str(format(bouquet_stream_id, '04x')) + ":" + str(format(unique_ref, '08x')) + ":0:0:0:0:" + "http%3a//example.m3u8"

            if 'custom_sid' in item:
                custom_sid = item['custom_sid']

                if custom_sid and custom_sid != "None":
                    if custom_sid.startswith(":"):
                        custom_sid = "1" + str(custom_sid)
                    serviceref = str(':'.join(custom_sid.split(":")[:7])) + ":0:0:0:" + "http%3a//example.m3u8"

            next_url = "%s/live/%s/%s/%s.%s" % (self.host, self.username, self.password, stream_id, self.output)

            if 'livefavourites' in glob.current_playlist['player_info']:
                for fav in glob.current_playlist['player_info']['livefavourites']:
                    if str(stream_id) == str(fav['stream_id']):
                        favourite = True
                        break
            else:
                glob.current_playlist['player_info']['livefavourites'] = []

            self.list2.append([index, str(name), str(stream_id), str(stream_icon), str(epg_channel_id), str(added), str(category_id), str(custom_sid), str(serviceref),
                              str(nowtime), str(nowTitle), str(nowDesc), str(nexttime), str(nextTitle), str(nextDesc), str(next_url), favourite, watching, editmode, hidden])

            index += 1

        glob.originalChannelList2 = self.list2[:]

        self.buildLists()

    def downloadXMLTVdata(self):
        # print("*** downloadXMLTVdata ***")
        if epgimporter is False:
            return

        self["downloading"].show()
        url = str(glob.current_playlist['playlist_info']['player_api']) + "&action=get_live_streams"
        tmpfd, tempfilename = tempfile.mkstemp()

        if url.startswith("https") and sslverify:
            parsed_uri = urlparse(url)
            domain = parsed_uri.hostname
            sniFactory = SNIFactory(domain)

            if pythonVer == 3:
                url = url.encode()

            downloadPage(url, tempfilename, sniFactory).addCallback(self.downloadcomplete, tempfilename).addErrback(self.downloadFail)
        else:
            if pythonVer == 3:
                url = url.encode()
            downloadPage(url, tempfilename).addCallback(self.downloadcomplete, tempfilename).addErrback(self.downloadFail)

        os.close(tmpfd)

    def downloadFail(self, failure):
        # print("*** downloadFail ***")
        print(("[EPG] download failed:", failure))
        if self["downloading"].instance:
            self["downloading"].hide()

    def downloadcomplete(self, data, filename):
        # print("***** download complete ****")
        channellist_all = []
        with open(filename, "r+b") as f:
            try:
                channellist_all = json.load(f)
                self.epg_channel_list = []
                for channel in channellist_all:

                    self.epg_channel_list.append({"name": str(channel["name"]), "stream_id": str(channel["stream_id"]), "epg_channel_id": str(channel["epg_channel_id"]), "custom_sid": channel["custom_sid"]})
            except:
                pass

        os.remove(filename)
        self.buildXMLTV()

    def buildXMLTV(self):
        # print("***** buildXMLTV ****")
        cleanName = re.sub(r'[\<\>\:\"\/\\\|\?\*]', '_', str(glob.current_playlist['playlist_info']['name']))
        cleanName = re.sub(r' ', '_', cleanName)
        cleanName = re.sub(r'_+', '_', cleanName)

        filepath = '/etc/epgimport/'
        filename = 'xstreamity.' + str(cleanName) + '.sources.xml'
        sourcepath = filepath + filename
        epgfilename = 'xstreamity.' + str(cleanName) + '.channels.xml'
        channelpath = filepath + epgfilename

        # if xmltv file doesn't already exist, create file and build.
        if not os.path.isfile(channelpath):
            open(channelpath, 'a').close()

        # buildXMLTVSourceFile
        with open(sourcepath, 'w') as f:
            xml_str = '<?xml version="1.0" encoding="utf-8"?>\n'
            xml_str += '<sources>\n'
            xml_str += '<sourcecat sourcecatname="XStreamity ' + str(cleanName) + '">\n'
            xml_str += '<source type="gen_xmltv" nocheck="1" channels="' + channelpath + '">\n'
            xml_str += '<description>' + str(cleanName) + '</description>\n'
            if str(glob.current_playlist['player_info']['xmltv_api']) == str(glob.current_playlist['playlist_info']['xmltv_api']):
                xml_str += '<url><![CDATA[' + str(glob.current_playlist['player_info']['xmltv_api']) + '&next_days=2]]></url>\n'
            else:
                xml_str += '<url><![CDATA[' + str(glob.current_playlist['player_info']['xmltv_api']) + ']]></url>\n'
            xml_str += '</source>\n'
            xml_str += '</sourcecat>\n'
            xml_str += '</sources>\n'
            f.write(xml_str)

        # buildXMLTVChannelFile
        with open(channelpath, 'w') as f:
            xml_str = '<?xml version="1.0" encoding="utf-8"?>\n'
            xml_str += '<channels>\n'

            for i in range(len(self.epg_channel_list)):

                channelid = self.epg_channel_list[i]['epg_channel_id']
                if channelid and "&" in channelid:
                    channelid = channelid.replace("&", "&amp;")
                bouquet_id = 0

                stream_id = int(self.epg_channel_list[i]['stream_id'])
                calc_remainder = int(stream_id) // 65535
                bouquet_id = bouquet_id + calc_remainder
                stream_id = int(stream_id) - int(calc_remainder * 65535)

                unique_ref = 999 + int(glob.current_playlist['playlist_info']['index'])

                serviceref = '1:0:1:' + str(format(bouquet_id, '04x')) + ":" + str(format(stream_id, '04x')) + ":" + str(format(unique_ref, '08x')) + ":0:0:0:0:" + "http%3a//example.m3u8"

                if 'custom_sid' in self.epg_channel_list[i]:
                    if self.epg_channel_list[i]['custom_sid'] and self.epg_channel_list[i]['custom_sid'] != "None":
                        if self.epg_channel_list[i]['custom_sid'].startswith(":"):
                            self.epg_channel_list[i]['custom_sid'] = "1" + self.epg_channel_list[i]['custom_sid']
                        serviceref = str(':'.join(self.epg_channel_list[i]['custom_sid'].split(":")[:7])) + ":0:0:0:" + "http%3a//example.m3u8"

                self.epg_channel_list[i]['serviceref'] = str(serviceref)
                name = self.epg_channel_list[i]['name']

                if channelid and channelid != "None":
                    xml_str += '<channel id="' + str(channelid) + '">' + str(serviceref) + '</channel><!--' + str(name) + '-->\n'

            xml_str += '</channels>\n'
            f.write(xml_str)

        if self["downloading"].instance:
            self["downloading"].hide()

        self.xmltvdownloaded = True

        self.buildLists()

    def buildLists(self):
        # print("*** buildlists ***")

        if self.level == 1:
            self["key_menu"].setText(_("Hide/Show"))
            self["key_epg"].setText('')
            self.channelList = []

            self.channelList = [buildCategoryList(x[0], x[1], x[2], x[3], x[4]) for x in self.list1 if x[4] is False]
            self["channel_list"].setList(self.channelList)

        elif self.level == 2:
            self["key_menu"].setText("Hide/Show")
            self.channelList = []
            self.epglist = []

            # index = 0
            # name = 1
            # stream_id = 2
            # stream_icon = 3
            # epg_channel_id = 4
            # added = 5
            # category_id = 6
            # custom_sid = 7
            # serviceref = 8
            # nowtime = 9
            # nowTitle = 10
            # nowDesc = 11
            # nexttime = 12
            # nextTitle = 13
            # nextDesc = 14
            # next_url = 15
            # favourite = 16
            # watching = 17
            # editmode = 18

            if self.favourites_category:
                self.channelList = [buildLiveStreamList(x[0], x[1], x[2], x[3], x[15], x[16], x[17], x[18], x[19]) for x in self.list2 if x[16] is True]
                self.epglist = [buildEPGListEntry(x[0], x[2], x[9], x[10], x[11], x[12], x[13], x[14], x[19]) for x in self.list2 if x[16] is True]
            else:

                self.channelList = [buildLiveStreamList(x[0], x[1], x[2], x[3], x[15], x[16], x[17], x[18], x[19]) for x in self.list2 if x[19] is False]
                self.epglist = [buildEPGListEntry(x[0], x[2], x[9], x[10], x[11], x[12], x[13], x[14], x[19]) for x in self.list2 if x[19] is False]

            self["channel_list"].setList(self.channelList)

            if self.enigma2epgcategorydownloaded is False and self.list2:
                category_id = self.list2[0][6]
                self.downloadQuickEPGList(category_id)

            # print("**** displaying epg list 1 ****")
            self["epg_list"].setList(self.epglist)

            instance = self["epg_list"].master.master.instance
            instance.setSelectionEnable(0)

        if self["channel_list"].getCurrent():
            if self.editmode is False and glob.nextlist[-1]['index'] != 0:
                self["channel_list"].setIndex(glob.nextlist[-1]['index'])

                channeltitle = self["channel_list"].getCurrent()[0]
                self["channel"].setText(self.main_title + ": " + str(channeltitle))

            if glob.nextlist[-1]['filter']:
                self["key_yellow"].setText('')
                self["key_blue"].setText(_('Reset Search'))
                if self.level == 1:
                    self["key_menu"].setText('')
            else:
                self["key_blue"].setText(_('Search'))
                self["key_yellow"].setText(_(glob.nextlist[-1]['sort']))
                self["key_menu"].setText(_("Hide/Show"))

            if self.editmode:
                self["key_red"].setText('')
                self["key_green"].setText('')
                self["key_blue"].setText('')
                self["key_yellow"].setText('')
                self["key_epg"].setText('')
            else:
                self["key_red"] = StaticText(_('Back'))
                self["key_green"] = StaticText(_('OK'))

            if self.level == 1:
                self.hideEPG()
            elif self.level == 2:
                self.showEPG()

        self.selectionChanged()

    def getXMLTVEPG(self):
        # print("*** getXMLTVEPG **")

        if self["channel_list"].getCurrent():

            self.epgcache = eEPGCache.getInstance()

            offset = int(glob.current_playlist["player_info"]["epgshift"]) * 3600

            for channel in self.list2:
                self.eventslist = []

                serviceref = channel[8]

                events = ['IBDTEX', (serviceref, -1, -1, -1)]  # search next 12 hours
                self.eventslist = [] if self.epgcache is None else self.epgcache.lookupEvent(events)

                for i in range(len(self.eventslist)):
                    if self.eventslist[i][1] is not None:
                        self.eventslist[i] = (self.eventslist[i][0], self.eventslist[i][1] + offset, self.eventslist[i][2], self.eventslist[i][3], self.eventslist[i][4])

                if self.eventslist:
                    if len(self.eventslist) > 0:
                        try:
                            # start time
                            if self.eventslist[0][1]:
                                channel[9] = str(strftime("%H:%M", (localtime(self.eventslist[0][1]))))

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
                                channel[12] = str(strftime("%H:%M", (localtime(self.eventslist[1][1]))))

                            # next title
                            if self.eventslist[1][3]:
                                channel[13] = str(self.eventslist[1][3])

                            # next description
                            if self.eventslist[1][4]:
                                channel[14] = str(self.eventslist[1][4])
                        except Exception as e:
                            print(e)

            self.xmltvcategorydownloaded = True

            self.epglist = []
            self.epglist = [buildEPGListEntry(x[0], x[1], x[9], x[10], x[11], x[12], x[13], x[14], x[19]) for x in self.list2 if x[19] is False]

            # print("**** displaying epg list 2 ****")
            self["epg_list"].setList(self.epglist)

            instance = self["epg_list"].master.master.instance
            instance.setSelectionEnable(0)

            self.refreshEPGInfo()
            # self.buildLists()

    def hideEPG(self):
        # print("*** hide EPG ***")
        self["epg_list"].setList([])
        self["epg_picon"].hide()
        self["epg_bg"].hide()
        self["epg_title"].setText('')
        self["epg_description"].setText('')
        self["progress"].hide()

    def showEPG(self):
        # print("*** showEPGElements ***")
        self["epg_picon"].show()
        self["epg_bg"].show()
        self["progress"].show()

    def playStream(self):
        # print("*** playStream ***")
        # back button back to playing stream
        if self["channel_list"].getCurrent():
            if self.session.nav.getCurrentlyPlayingServiceReference():
                if self.session.nav.getCurrentlyPlayingServiceReference().toString() == glob.currentPlayingServiceRefString:
                    self.back()
                elif self.selectedlist == self["epg_short_list"]:
                    self.back()
                else:
                    self["channel_list"].setIndex(glob.nextlist[-1]['index'])
                    self.next()
            else:
                self.back()

    def stopStream(self):
        # print("*** stopStream ***")
        if glob.currentPlayingServiceRefString != glob.newPlayingServiceRefString:
            if glob.newPlayingServiceRefString != '':
                if self.session.nav.getCurrentlyPlayingServiceReference():
                    self.session.nav.stopService()
                self.session.nav.playService(eServiceReference(glob.currentPlayingServiceRefString))
                glob.newPlayingServiceRefString = glob.currentPlayingServiceRefString

    def selectionChanged(self):
        # print("*** selectionChanged ***")
        if self["channel_list"].getCurrent():

            channeltitle = self["channel_list"].getCurrent()[0]
            currentindex = self["channel_list"].getIndex()

            if self.editmode:
                glob.nextlist[-1]['index'] = currentindex

            self.position = currentindex + 1
            self.positionall = len(self.channelList)
            self.page = int(math.ceil(float(self.position) / float(self.itemsperpage)))
            self.pageall = int(math.ceil(float(self.positionall) / float(self.itemsperpage)))

            self["page"].setText('Page: ' + str(self.page) + " of " + str(self.pageall))
            self["listposition"].setText(str(self.position) + "/" + str(self.positionall))

            self["channel"].setText(self.main_title + ": " + str(channeltitle))

            if self.level == 2:
                if not self.showingshortEPG:
                    self["key_rec"].setText('')
                    self["epg_list"].setIndex(currentindex)

                    self.refreshEPGInfo()
                    self.timerimage = eTimer()
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

            self["page"].setText('Page: ' + str(self.page) + " of " + str(self.pageall))
            self["listposition"].setText(str(self.position) + "/" + str(self.positionall))

            self["key_yellow"].setText('')
            self["key_blue"].setText('')

    def downloadImage(self):
        # print("*** downloadImage ***")
        if self["channel_list"].getCurrent():
            try:
                os.remove(str(dir_tmp) + 'original.png')
            except:
                pass

            size = [147, 88]
            if screenwidth.width() > 1280:
                size = [220, 130]

            original = str(dir_tmp) + 'original.png'
            desc_image = ''

            try:
                desc_image = self["channel_list"].getCurrent()[5]

                if desc_image and desc_image != "n/A":
                    if desc_image.startswith("https") and sslverify:
                        parsed_uri = urlparse(desc_image)
                        domain = parsed_uri.hostname
                        sniFactory = SNIFactory(domain)
                        if pythonVer == 3:
                            desc_image = desc_image.encode()
                        downloadPage(desc_image, original, sniFactory, timeout=5).addCallback(self.resizeImage, size).addErrback(self.loadDefaultImage)
                    else:
                        if pythonVer == 3:
                            desc_image = desc_image.encode()
                        downloadPage(desc_image, original, timeout=5).addCallback(self.resizeImage, size).addErrback(self.loadDefaultImage)
                else:
                    self.loadDefaultImage()
            except Exception as e:
                print("* image error ** %s" % e)

    def loadDefaultImage(self, default=None):
        # print("*** loadDefaultImage ***")
        if self["epg_picon"].instance:
            self["epg_picon"].instance.setPixmapFromFile(common_path + "picon.png")

    def resizeImage(self, data, size):
        # print("*** resizeImage ***")
        if self["channel_list"].getCurrent():
            original = str(dir_tmp) + 'original.png'

            if os.path.exists(original):
                try:
                    im = Image.open(original).convert('RGBA')
                    im.thumbnail(size, Image.ANTIALIAS)

                    # crop and center image
                    bg = Image.new('RGBA', size, (255, 255, 255, 0))

                    imagew, imageh = im.size
                    im_alpha = im.convert('RGBA').split()[-1]
                    bgwidth, bgheight = bg.size
                    bg_alpha = bg.convert('RGBA').split()[-1]
                    temp = Image.new('L', (bgwidth, bgheight), 0)
                    temp.paste(im_alpha, (int((bgwidth - imagew) / 2), int((bgheight - imageh) / 2)), im_alpha)
                    bg_alpha = ImageChops.screen(bg_alpha, temp)
                    bg.paste(im, (int((bgwidth - imagew) / 2), int((bgheight - imageh) / 2)))
                    im = bg

                    im.save(original, 'PNG')

                    if self["epg_picon"].instance:
                        self["epg_picon"].instance.setPixmapFromFile(original)

                except Exception as e:
                    print("******* picon resize failed *******")
                    print(e)
            else:
                self.loadDefaultImage()

    def refreshEPGInfo(self):
        # print("*** refreshEPGInfo ***")

        if self["epg_list"].getCurrent():
            instance = self["epg_list"].master.master.instance
            instance.setSelectionEnable(1)

            startnowtime = self["epg_list"].getCurrent()[2]
            titlenow = self["epg_list"].getCurrent()[3]
            descriptionnow = self["epg_list"].getCurrent()[4]
            startnexttime = self["epg_list"].getCurrent()[5]

            if titlenow and not self.editmode:
                nowTitle = "%s - %s  %s" % (startnowtime, startnexttime, titlenow)
                self["key_epg"].setText(_("Next Info"))

            else:
                nowTitle = ""
                self["key_epg"].setText('')
                instance.setSelectionEnable(0)

            self["epg_title"].setText(nowTitle)
            self["epg_description"].setText(descriptionnow)

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

    def clear_caches(self):
        # print("*** clear_caches ***")
        try:
            system("echo 1 > /proc/sys/vm/drop_caches")
            system("echo 2 > /proc/sys/vm/drop_caches")
            system("echo 3 > /proc/sys/vm/drop_caches")
        except:
            pass

    def goUp(self):
        # print("*** goUp ***")
        if self.editmode:
            if self["channel_list"].getCurrent():

                x = 0
                for fav in glob.current_playlist['player_info']['livefavourites']:
                    if self["channel_list"].getCurrent()[4] == fav['stream_id']:
                        currentindex = x
                        break
                    x += 1

                swapindex = currentindex - 1
                if swapindex < 0:
                    return

                glob.current_playlist['player_info']['livefavourites'][currentindex], glob.current_playlist['player_info']['livefavourites'][swapindex] = \
                    glob.current_playlist['player_info']['livefavourites'][swapindex], glob.current_playlist['player_info']['livefavourites'][currentindex]

        instance = self.selectedlist.master.master.instance
        instance.moveSelection(instance.moveUp)
        self.selectionChanged()

        if self.editmode:
            self.downloadChannels()
            if self["channel_list"].getCurrent():
                currentindex = self["channel_list"].getIndex()
                self.list2[currentindex][18] = not self.list2[currentindex][18]
                self.buildLists()

    def goDown(self):
        if self.editmode:
            if self["channel_list"].getCurrent():

                x = 0
                for fav in glob.current_playlist['player_info']['livefavourites']:
                    if self["channel_list"].getCurrent()[4] == fav['stream_id']:
                        currentindex = x
                        break
                    x += 1

                swapindex = currentindex + 1
                if swapindex > len(self.channelList) - 1:
                    return

                glob.current_playlist['player_info']['livefavourites'][currentindex], glob.current_playlist['player_info']['livefavourites'][swapindex] = glob.current_playlist['player_info']['livefavourites'][swapindex], glob.current_playlist['player_info']['livefavourites'][currentindex]

        # print("*** goDown ***")
        instance = self.selectedlist.master.master.instance
        instance.moveSelection(instance.moveDown)
        self.selectionChanged()

        if self.editmode:
            self.downloadChannels()
            if self["channel_list"].getCurrent():
                currentindex = self["channel_list"].getIndex()
                self.list2[currentindex][18] = not self.list2[currentindex][18]
                self.buildLists()

    def pageUp(self):
        if self.editmode:
            return
        else:
            # print("*** pageUp ***")
            instance = self.selectedlist.master.master.instance
            instance.moveSelection(instance.pageUp)
            self.selectionChanged()

    def pageDown(self):
        if self.editmode:
            return
        else:
            # print("*** pageDown ***")
            instance = self.selectedlist.master.master.instance
            instance.moveSelection(instance.pageDown)
            self.selectionChanged()

    # button 0
    def reset(self):
        # print("*** reset ***")
        if self.editmode:
            return
        else:

            self.selectedlist.setIndex(0)
            self.selectionChanged()

    def sort(self):
        # print("*** sort ***")
        if self.editmode:
            return
        else:
            if not self["key_yellow"].getText():
                return

            if self.level == 1:
                activelist = self.list1[:]
                activeoriginal = glob.originalChannelList1[:]

            elif self.level == 2:
                activelist = self.list2[:]
                activeoriginal = glob.originalChannelList2[:]

            if self["channel_list"].getCurrent():
                self["channel_list"].setIndex(0)
                current_sort = self["key_yellow"].getText()

                if current_sort == (_('Sort: A-Z')):
                    self["key_yellow"].setText(_('Sort: Z-A'))
                    activelist.sort(key=lambda x: x[1], reverse=False)

                elif current_sort == (_('Sort: Z-A')):
                    if self.level == 2:
                        self["key_yellow"].setText(_('Sort: Newest'))
                    else:
                        self["key_yellow"].setText(_('Sort: Original'))
                    activelist.sort(key=lambda x: x[1], reverse=True)

                elif current_sort == (_('Sort: Newest')):
                    if self.level == 2:
                        activelist.sort(key=lambda x: x[5], reverse=True)

                    self["key_yellow"].setText(_('Sort: Original'))

                elif current_sort == (_('Sort: Original')):
                    self["key_yellow"].setText(_('Sort: A-Z'))
                    activelist = activeoriginal

                if current_sort:
                    glob.nextlist[-1]["sort"] = self["key_yellow"].getText()

            if self.level == 1:
                self.list1 = activelist

            elif self.level == 2:
                self.list2 = activelist

            self.epgchecklist = []
            self.buildLists()

    def search(self):
        # print("*** search ***")
        if self.editmode:
            return
        else:
            if not self["key_blue"].getText():
                return

            current_filter = self["key_blue"].getText()
            if current_filter != (_('Reset Search')):
                self.session.openWithCallback(self.filterChannels, VirtualKeyBoard, title=_("Filter this category..."), text=self.searchString)
            else:
                self.resetSearch()

    def filterChannels(self, result):
        # print("*** filterChannels ***")
        if result or self.filterresult:
            self.filterresult = result
            glob.nextlist[-1]["filter"] = self.filterresult

            if self.level == 1:
                activelist = self.list1[:]

            elif self.level == 2:
                activelist = self.list2[:]

            self.searchString = result
            self["key_blue"].setText(_('Reset Search'))
            self["key_yellow"].setText('')
            activelist = [channel for channel in activelist if str(result).lower() in str(channel[1]).lower()]
            self.epgchecklist = []

            if self.level == 1:
                self.list1 = activelist

            elif self.level == 2:
                self.list2 = activelist

            self.buildLists()

    def resetSearch(self):
        # print("*** resetSearch ***")
        self["key_blue"].setText(_('Search'))
        self["key_yellow"].setText(_('Sort: A-Z'))

        if self.level == 1:
            activeoriginal = glob.originalChannelList1[:]

        elif self.level == 2:
            activeoriginal = glob.originalChannelList2[:]

        if self.level == 1:
            self.list1 = activeoriginal

        elif self.level == 2:
            self.list2 = activeoriginal

        self.filterresult = ""
        glob.nextlist[-1]["filter"] = self.filterresult

        self.buildLists()

    def pinEntered(self, result):
        # print("*** pinEntered ***")
        if not result:
            self.pin = False
            self.session.open(MessageBox, _("Incorrect pin code."), type=MessageBox.TYPE_ERROR, timeout=5)

        if self.pin is True:
            self.next()
        else:
            return

    def parentalCheck(self):
        # print("*** parentalCheck ***")
        if self.editmode is False:
            self.pin = True
            if self.level == 1:
                if cfg.parental.getValue() is True:
                    adult = "all", "+18", "adult", "18+", "18 rated", "xxx", "sex", "porn", "pink", "blue"
                    if any(s in str(self["channel_list"].getCurrent()[0]).lower() for s in adult):
                        from Screens.InputBox import PinInput
                        self.session.openWithCallback(self.pinEntered, PinInput, pinList=[config.ParentalControl.setuppin.value], triesEntry=config.ParentalControl.retries.servicepin, title=_("Please enter the parental control pin code"), windowTitle=_("Enter pin code"))
                    else:
                        self.next()
                else:
                    self.next()
            else:
                self.next()

    def next(self):
        # print("*** next ***")

        if self["channel_list"].getCurrent():
            currentindex = self["channel_list"].getIndex()
            next_url = self["channel_list"].getCurrent()[3]
            stream_id = self["channel_list"].getCurrent()[4]

            # name = self["channel_list"].getCurrent()[0]
            glob.nextlist[-1]['index'] = currentindex
            glob.currentchannelist = self.channelList[:]
            glob.currentchannelistindex = currentindex
            glob.currentepglist = self.epglist[:]

            if self.level == 1:
                self.level += 1
                self["channel_list"].setIndex(0)
                self["category_actions"].setEnabled(False)

                if self.favourites_category:
                    self["channel_actions"].setEnabled(False)
                    self["favourites_actions"].setEnabled(True)

                else:
                    self["channel_actions"].setEnabled(True)
                    self["favourites_actions"].setEnabled(False)

                self["key_yellow"].setText(_('Sort: A-Z'))
                glob.nextlist.append({"playlist_url": next_url, "index": 0, "level": self.level, "sort": self["key_yellow"].getText(), "filter": ""})
                self.createSetup()

            elif self.level == 2:

                streamtype = glob.current_playlist["player_info"]["livetype"]
                self.reference = eServiceReference(int(streamtype), 0, next_url)

                if self.session.nav.getCurrentlyPlayingServiceReference():
                    # live preview
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
                        # print("callingfunction %s" % callingfunction)
                        if callingfunction == "playStream":
                            next_url = str(self.lastviewed_url)
                            stream_id = str(self.lastviewed_id)
                            self["channel_list"].setIndex(self.lastviewed_index)
                            self.reference = eServiceReference(int(streamtype), 0, next_url)
                            glob.newPlayingServiceRef = self.reference
                            glob.newPlayingServiceRefString = self.reference.toString()
                            glob.currentchannelistindex = self.lastviewed_index

                        else:
                            self.lastviewed_url = next_url
                            self.lastviewed_id = stream_id
                            self.lastviewed_index = self["channel_list"].getIndex()

                        for channel in self.list2:
                            if channel[2] == stream_id:
                                channel[17] = True  # set watching icon
                            else:
                                channel[17] = False
                        self.buildLists()

                        self.session.openWithCallback(self.setIndex, streamplayer.XStreamity_StreamPlayer, str(next_url), str(streamtype))
                else:
                    self.session.openWithCallback(self.setIndex, streamplayer.XStreamity_StreamPlayer, str(next_url), str(streamtype))

                self["category_actions"].setEnabled(False)

    def setIndex(self):
        # print("*** set index ***")
        self["channel_list"].setIndex(glob.currentchannelistindex)
        self["epg_list"].setIndex(glob.currentchannelistindex)
        self.selectionChanged()
        self.xmltvcategorydownloaded = False
        self.enigma2epgcategorydownloaded = False
        self.buildLists()

    def back(self):
        # print("*** back ***")
        if self.editmode:
            return

        if self.selectedlist == self["epg_short_list"]:
            self.shortEPG()
            return

        del glob.nextlist[-1]

        try:
            os.remove(str(dir_tmp) + "liveepg.xml")
        except:
            pass

        if len(glob.nextlist) == 0:
            self.stopStream()
            self.close()
        else:
            self.lastviewed_url = ''
            self.lastviewed_id = ''
            self.lastviewed_index = 0

            self["epg_title"].setText('')
            self["epg_description"].setText('')
            self["key_rec"].setText('')

            if cfg.stopstream.value:
                self.stopStream()

            levelpath = str(dir_tmp) + 'level' + str(self.level) + '.json'
            try:
                os.remove(levelpath)
            except:
                pass

            self.level -= 1

            self["category_actions"].setEnabled(True)
            self["channel_actions"].setEnabled(False)
            self["favourites_actions"].setEnabled(False)

            self.xmltvcategorydownloaded = False
            self.enigma2epgcategorydownloaded = False

            self.buildLists()

    def nownext(self):
        # print("*** nownext ***")
        if self["channel_list"].getCurrent():
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
                        self["epg_title"].setText(nextTitle)
                        self["epg_description"].setText(descriptionnext)
                        self["key_epg"].setText(_("Now Info"))
                    else:
                        nowTitle = "%s - %s  %s" % (startnowtime, startnexttime, titlenow)
                        self["epg_title"].setText(nowTitle)
                        self["epg_description"].setText(descriptionnow)
                        self["key_epg"].setText(_("Next Info"))

    def shortEPG(self):
        # print("*** shortEPG ***")
        self.showingshortEPG = not self.showingshortEPG
        if self.showingshortEPG:
            self["key_menu"].setText("")

            if self["channel_list"].getCurrent():
                currentindex = self["channel_list"].getIndex()
                glob.nextlist[-1]['index'] = currentindex

                self["epg_list"].setList([])
                next_url = self["channel_list"].getCurrent()[3]

                if self.level == 2:

                    response = ''
                    player_api = str(glob.current_playlist["playlist_info"]["player_api"])
                    stream_id = next_url.rpartition("/")[-1].partition(".")[0]

                    shortEPGJson = []

                    url = str(player_api) + "&action=get_short_epg&stream_id=" + str(stream_id) + "&limit=1000"
                    adapter = HTTPAdapter(max_retries=0)
                    http = requests.Session()
                    http.mount("http://", adapter)

                    try:
                        r = http.get(url, headers=hdr, stream=True, timeout=10, verify=False)
                        r.raise_for_status()
                        if r.status_code == requests.codes.ok:
                            try:
                                response = r.json()
                            except:
                                response = ''

                    except requests.exceptions.ConnectionError as e:
                        print(("Error Connecting: %s" % e))
                        response = ''

                    except requests.exceptions.RequestException as e:
                        print(e)
                        response = ''

                    if response != '':
                        shortEPGJson = response
                        index = 0

                        self.epgshortlist = []

                        if "epg_listings" in shortEPGJson:
                            for listing in shortEPGJson["epg_listings"]:

                                epg_title = ""
                                epg_description = ""
                                epg_date_all = ""
                                epg_time_all = ""
                                start = ""
                                end = ""

                                if 'title' in listing:
                                    epg_title = base64.b64decode(listing['title']).decode('utf-8')

                                if 'description' in listing:
                                    epg_description = base64.b64decode(listing['description']).decode('utf-8')

                                shift = 0

                                if "serveroffset" in glob.current_playlist["player_info"]:
                                    shift = int(glob.current_playlist["player_info"]["serveroffset"])

                                if listing['start'] and listing['end']:
                                    start = listing['start']
                                    end = listing['end']

                                    start_datetime = datetime.strptime(start, "%Y-%m-%d %H:%M:%S") + timedelta(hours=shift)
                                    try:
                                        end_datetime = datetime.strptime(end, "%Y-%m-%d %H:%M:%S") + timedelta(hours=shift)
                                    except:
                                        try:
                                            end = listing['stop']
                                            end_datetime = datetime.strptime(end, "%Y-%m-%d %H:%M:%S") + timedelta(hours=shift)
                                        except:
                                            return

                                    epgstarttime = str(start_datetime)[11:16]
                                    epgendtime = str(end_datetime)[11:16]
                                    epg_day = start_datetime.strftime("%a")
                                    epg_start_date = start_datetime.strftime("%d/%m")
                                    epg_date_all = "%s %s" % (epg_day, epg_start_date)
                                    epg_time_all = "%s - %s" % (epgstarttime, epgendtime)

                                    self.epgshortlist.append(buildShortEPGListEntry(str(epg_date_all), str(epg_time_all), str(epg_title), str(epg_description), index))

                                    index += 1

                            self["epg_short_list"].setList(self.epgshortlist)

                            instance = self["epg_short_list"].master.master.instance
                            instance.setSelectionEnable(1)

                            self["progress"].hide()
                            self["key_green"].setText('')
                            self["key_yellow"].setText('')
                            self["key_blue"].setText('')
                            self["key_epg"].setText('')

                            self.selectedlist = self["epg_short_list"]
                            self.displayShortEPG()

        else:
            self["epg_short_list"].setList([])

            self.selectedlist = self["channel_list"]
            self.buildLists()
        return

    def displayShortEPG(self):
        # print("*** displayShortEPG ***")
        if self["epg_short_list"].getCurrent():
            title = str(self["epg_short_list"].getCurrent()[0])
            description = str(self["epg_short_list"].getCurrent()[3])
            timeall = str(self["epg_short_list"].getCurrent()[2])
            self["epg_title"].setText(timeall + " " + title)
            self["epg_description"].setText(description)
            self["key_rec"].setText(_('Record'))

    def showHiddenList(self):
        # print("*** showHiddenList ***")

        from . import hidden
        if self["channel_list"].getCurrent():
            if self.level == 1:
                self.session.openWithCallback(self.createSetup, hidden.XStreamity_HiddenCategories, "live", self.list1, self.level)
            if self.level == 2 and not self.favourites_category:
                self.session.openWithCallback(self.createSetup, hidden.XStreamity_HiddenCategories, "live", self.list2, self.level)

    # record button download video file
    def downloadStream(self, limitEvent=True):
        # print("*** downloadStream ***")
        from . import record

        currentindex = self["channel_list"].getIndex()

        begin = int(time.time())
        end = begin + 3600
        dt_now = datetime.now()
        self.date = time.time()

        # recording name - programme title = fallback channel name
        if self.epglist[currentindex][3]:
            name = self.epglist[currentindex][3]
        else:
            name = self.epglist[currentindex][1]

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

            currentindex = self["channel_list"].getIndex()
            description = ''
            streamurl = self["channel_list"].getCurrent()[3]
            streamtype = 1

            if self.epglist[currentindex][4]:
                description = self.epglist[currentindex][4]

            if self.showingshortEPG:
                currentindex = self["epg_short_list"].getIndex()
                if self.epgshortlist[currentindex][2]:
                    description = str(self.epgshortlist[currentindex][2])

            eventid = int(streamurl.rpartition('/')[-1].partition('.')[0])

            if streamurl.endswith('m3u8'):
                streamtype = 4097

            self.reference = eServiceReference(streamtype, 0, streamurl)

            # switch channel to prevent mutli active users
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
                self.session.open(MessageBox, _('Recording Timer Set.'), MessageBox.TYPE_INFO, timeout=5)
            else:
                self.session.open(MessageBox, _('Recording Failed.'), MessageBox.TYPE_WARNING)
        return

    def favourite(self):
        # print("**** favourite ***")
        if self["channel_list"].getCurrent():
            currentindex = self["channel_list"].getIndex()

            favExists = False

            for fav in glob.current_playlist['player_info']['livefavourites']:
                if self["channel_list"].getCurrent()[4] == fav['stream_id']:
                    favExists = True
                    favStream_id = fav['stream_id']
                    break

            if favExists:
                glob.current_playlist['player_info']['livefavourites'][:] = [x for x in glob.current_playlist['player_info']['livefavourites'] if str(x['stream_id']) != str(favStream_id)]
            else:
                self.list2[currentindex][16] = not self.list2[currentindex][16]
                glob.current_playlist['player_info']['livefavourites'].append(dict([
                    ("name", self.list2[currentindex][1]),
                    ("stream_id", self.list2[currentindex][2]),
                    ("stream_icon", self.list2[currentindex][3]),
                    ("epg_channel_id", self.list2[currentindex][4]),
                    ("added", self.list2[currentindex][5]),
                    ("category_id", self.list2[currentindex][6]),
                    ("custom_sid", self.list2[currentindex][7]),
                ]))

            with open(json_file, "r") as f:
                try:
                    self.playlists_all = json.load(f)
                except:
                    os.remove(json_file)

            if self.playlists_all:
                x = 0
                for playlists in self.playlists_all:
                    if playlists["playlist_info"]["domain"] == glob.current_playlist["playlist_info"]["domain"] and playlists["playlist_info"]["username"] == glob.current_playlist["playlist_info"]["username"] and playlists["playlist_info"]["password"] == glob.current_playlist["playlist_info"]["password"]:
                        self.playlists_all[x] = glob.current_playlist
                        break
                    x += 1
            with open(json_file, 'w') as f:
                json.dump(self.playlists_all, f)

            self.xmltvcategorydownloaded = False
            self.enigma2epgcategorydownloaded = False
            self.createSetup()

    def editfav(self):
        if self.favourites_category:
            self.editmode = not self.editmode
            if self.editmode is False:
                self.getXMLTVEPG()

                with open(json_file, "r") as f:
                    try:
                        self.playlists_all = json.load(f)
                    except:
                        os.remove(json_file)

                if self.playlists_all:
                    x = 0
                    for playlists in self.playlists_all:
                        if playlists["playlist_info"]["domain"] == glob.current_playlist["playlist_info"]["domain"] and playlists["playlist_info"]["username"] == glob.current_playlist["playlist_info"]["username"] and playlists["playlist_info"]["password"] == glob.current_playlist["playlist_info"]["password"]:
                            self.playlists_all[x] = glob.current_playlist
                            break
                        x += 1
                with open(json_file, 'w') as f:
                    json.dump(self.playlists_all, f)

                glob.nextlist[-1]['index'] = 0

            if self["channel_list"].getCurrent():
                currentindex = self["channel_list"].getIndex()
                self.list2[currentindex][18] = not self.list2[currentindex][18]

        else:
            return
        self.buildLists()

    def downloadQuickEPGList(self, category):
        # print("*** downloadQuickEPGList ***")
        # self["downloading"].show()

        quickEPG = str(glob.current_playlist['playlist_info']['enigma2_api']) + "&type=get_live_streams&cat_id=" + str(category)

        if quickEPG.startswith("https") and sslverify:
            parsed_uri = urlparse(quickEPG)
            domain = parsed_uri.hostname
            sniFactory = SNIFactory(domain)

            if pythonVer == 3:
                quickEPG = quickEPG.encode()
            downloadPage(quickEPG, str(dir_tmp) + "liveepg.xml", sniFactory, timeout=20).addCallback(self.dictQuickEPG).addErrback(self.QuickEPGError)
        else:
            if pythonVer == 3:
                quickEPG = quickEPG.encode()
            downloadPage(quickEPG, str(dir_tmp) + "liveepg.xml", timeout=20).addCallback(self.dictQuickEPG).addErrback(self.QuickEPGError)

    def QuickEPGError(self, failure):
        # print("*** QuickEPGError ***")
        print(("********* Quick EPG Error ******** %s " % failure))
        if epgimporter and self.xmltvcategorydownloaded is False:
            self.getXMLTVEPG()

    def dictQuickEPG(self, data=None):
        self.enigma2epgcategorydownloaded = True

        # print("*** dictQuickEPG ***")
        try:
            os.remove(str(dir_tmp) + "quickepg.json")
        except:
            pass

        if os.path.exists(str(dir_tmp) + "liveepg.xml"):
            with codecs.open(str(dir_tmp) + "liveepg.xml", 'r', encoding='utf-8') as f:
                content = f.read()

        quickepgdict = []
        xmllist = []

        if content:
            root = ET.fromstring(content)
            for channel in root.findall('channel'):
                title = ''
                description = ''
                nowTitle = ''
                nowDesc = ''
                nowStart = ''
                nowEnd = ''
                nextTitle = ''
                nextDesc = ''

                title = base64.b64decode(channel.findtext('title')).decode('utf-8')
                try:
                    title = ''.join(chr(ord(c)) for c in title).decode('utf8')
                except:
                    pass

                title = title.partition("[")[0].strip()

                description = base64.b64decode(channel.findtext('description')).decode('utf-8')
                try:
                    description = ''.join(chr(ord(c)) for c in description).decode('utf8')
                except:
                    pass

                if description:
                    # long winded way of reading the lines that may be split with \n :(

                    lines = re.split("\n", description)

                    line1 = ""
                    line2 = ""
                    line3 = ""
                    line4 = ""
                    time1 = False
                    desc1 = False

                    for line in lines:
                        if line.startswith("[") and time1 is False:
                            line1 = line
                            time1 = True

                        elif not line.startswith("[") and desc1 is False:
                            line2 += line + " "

                        elif line.startswith("[") and time1:
                            desc1 = True
                            line3 = line

                        elif not line.startswith("[") and desc1:
                            line4 += line + " "

                    try:
                        nowStart = re.compile(r"\[(\d+:\d+)\]").search(line1).group(1).strip()
                        try:
                            nowTitle = re.compile("] (.*)").search(line1).group(1).strip()
                        except:
                            pass
                    except:
                        pass

                    try:
                        nowDesc = line2.strip().lstrip("(").rstrip(")").strip()
                    except:
                        pass

                    try:
                        nowEnd = re.compile(r"\[(\d+:\d+)\]").search(line3).group(1).strip()
                        try:
                            nextTitle = re.compile("] (.*)").search(line3).group(1).strip()
                        except:
                            pass
                    except:
                        pass

                    try:
                        nextDesc = line4.strip().lstrip("(").rstrip(")").strip()
                    except:
                        pass

                    xmllist.append([str(title), str(nowStart), str(nowTitle), str(nowDesc), str(nowEnd), str(nextTitle), str(nextDesc)])

            # print("xmllist %s" % xmllist)

            # shiftList = []
            # c = ""

            timeOffset = int(glob.current_playlist["player_info"]["serveroffset"])

            for channel in xmllist:

                nowStart = ''
                nowEnd = ''
                nowStartLong = ""
                nowEndLong = ""
                yesterday = False
                # mostCommon = 0
                # mostCommon2 = 0
                # timeOffset = 0

                if channel[1]:  # start time
                    nowStart = channel[1]

                    nowStartLong = datetime.strptime(str(date.today()) + " " + str(nowStart), "%Y-%m-%d %H:%M")

                    if int(datetime.now().hour) < int(nowStartLong.hour):
                        yesterday = True
                        nowStartLong -= timedelta(hours=24)

                    nowStartLong += timedelta(hours=timeOffset)
                    nowStart = format(nowStartLong, '%H:%M')

                if channel[4]:  # end time
                    nowEnd = channel[4]
                    nowEndLong = datetime.strptime(str(date.today()) + " " + str(nowEnd), "%Y-%m-%d %H:%M")

                    if yesterday:
                        nowEndLong -= timedelta(hours=24)

                    if nowEndLong < nowStartLong:
                        nowEndLong += timedelta(hours=24)

                    nowEndLong += timedelta(hours=timeOffset)
                    nowEnd = format(nowEndLong, '%H:%M')

                channel[1] = nowStart
                channel[4] = nowEnd

                title = channel[0]
                nowTitle = channel[2]
                nowDesc = channel[3]
                nextTitle = channel[5]
                nextDesc = channel[6]

                if datetime.now() > nowStartLong and datetime.now() < nowEndLong:
                    quickepgdict.append(dict([
                        ("title", str(title)),
                        ("nowTitle", str(nowTitle)),
                        ("nowDesc", str(nowDesc)),
                        ("nowStart", str(nowStart)),
                        ("nowEnd", str(nowEnd)),
                        ("nextTitle", str(nextTitle)),
                        ("nextDesc", str(nextDesc)),
                    ]))
                else:
                    quickepgdict.append(dict([
                        ("title", ""),
                        ("nowTitle", ""),
                        ("nowDesc", ""),
                        ("nowStart", ""),
                        ("nowEnd", ""),
                        ("nextTitle", ""),
                        ("nextDesc", ""),
                    ]))

            with open(str(dir_tmp) + "quickepg.json", 'w') as f:
                json.dump(quickepgdict, f)

        self.getE2EPG()
        # self.buildLists()

    def getE2EPG(self):
        # print("*** getE2EPG **")
        with open(str(dir_tmp) + "quickepg.json", 'r') as f:
            quickepglist = json.load(f)

        if self["channel_list"].getCurrent():
            for channel in self.list2:
                for epgentry in quickepglist:

                    if str(channel[1]) == str(epgentry['title']):
                        channel[9] = str(epgentry['nowStart'])
                        channel[10] = str(epgentry['nowTitle'])
                        channel[11] = str(epgentry['nowDesc'])
                        channel[12] = str(epgentry['nowEnd'])
                        channel[13] = str(epgentry['nextTitle'])
                        channel[14] = str(epgentry['nextDesc'])
                        break

            self.epglist = []
            self.epglist = [buildEPGListEntry(x[0], x[1], x[9], x[10], x[11], x[12], x[13], x[14], x[19]) for x in self.list2 if x[19] is False]

            self.refreshEPGInfo()

            self["epg_list"].setList(self.epglist)

            instance = self["epg_list"].master.master.instance
            instance.setSelectionEnable(0)

            if epgimporter and self.xmltvcategorydownloaded is False:
                self.getXMLTVEPG()


def buildEPGListEntry(index, title, epgNowTime, epgNowTitle, epgNowDesc, epgNextTime, epgNextTitle, epgNextDesc, hidden):
    return (title, index, epgNowTime, epgNowTitle, epgNowDesc, epgNextTime, epgNextTitle, epgNextDesc, hidden)


def buildShortEPGListEntry(date_all, time_all, title, description, index):
    return (title, date_all, time_all, description, index)


def buildCategoryList(index, title, next_url, category_id, hidden):
    png = LoadPixmap(common_path + "more.png")
    return (title, png, index, next_url, category_id, hidden)


def buildLiveStreamList(index, name, stream_id, stream_icon, next_url, favourite, watching, editmode, hidden):
    png = LoadPixmap(common_path + "play.png")
    if favourite:
        png = LoadPixmap(common_path + "favourite.png")
    if watching:
        png = LoadPixmap(common_path + "watching.png")
    if editmode:
        png = LoadPixmap(common_path + "edit.png")
    return (name, png, index, next_url, stream_id, stream_icon, hidden)
