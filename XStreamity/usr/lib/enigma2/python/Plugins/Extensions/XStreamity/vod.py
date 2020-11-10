#!/usr/bin/python
# -*- coding: utf-8 -*-

# for localized messages
from . import _

from . import streamplayer
from . import xstreamity_globals as glob

from .plugin import skin_path, screenwidth, hdr, cfg, common_path, dir_tmp
from .xStaticText import StaticText

from collections import OrderedDict
from Components.ActionMap import ActionMap
from Components.AVSwitch import AVSwitch
from Components.config import config
from Components.Pixmap import Pixmap
from Components.ProgressBar import ProgressBar
from Components.Sources.List import List
from datetime import datetime, timedelta
from enigma import eTimer, eServiceReference, ePicLoad
from requests.adapters import HTTPAdapter
from Screens.Screen import Screen
from Screens.VirtualKeyBoard import VirtualKeyBoard
from Tools.LoadPixmap import LoadPixmap
from twisted.web.client import downloadPage

try:
    from urllib import unquote
except:
    from urllib.parse import unquote

import base64
import re
import json
import math
import os
import requests
import sys
import zlib
import codecs

from os import system

try:
    pythonVer = sys.version_info.major
except:
    pythonVer = 2

# https twisted client hack #
try:
    from OpenSSL import SSL
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
        self.main_title = (_("Vod"))

        nexturl = str(glob.current_playlist['playlist_info']['player_api']) + "&action=get_vod_categories"

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

        self["epg_picon"] = Pixmap()
        self["epg_picon"].hide()

        self["downloading"] = Pixmap()
        self["downloading"].hide()

        self["progress"] = ProgressBar()
        self["progress"].hide()

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
        self.pin = False

        self.protocol = glob.current_playlist['playlist_info']['protocol']
        self.domain = glob.current_playlist['playlist_info']['domain']
        self.host = glob.current_playlist['playlist_info']['host']
        self.vodtype = glob.current_playlist['player_info']['vodtype']
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

        self.tempstreamtype = ''
        self.tempstream_url = ''

        self.token = "ZUp6enk4cko4ZzBKTlBMTFNxN3djd25MOHEzeU5Zak1Bdkd6S3lPTmdqSjhxeUxMSTBNOFRhUGNBMjBCVmxBTzlBPT0K"

        self.timerEPG = eTimer()
        self.timerBusy = eTimer()
        self.timerVOD = eTimer()
        self.timerVODBusy = eTimer()

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
            'epg': self.imdb,
            'info': self.imdb,
            'text': self.imdb,
            "left": self.pageUp,
            "right": self.pageDown,
            "up": self.goUp,
            "down": self.goDown,
            "channelUp": self.pageUp,
            "channelDown": self.pageDown,
            "rec": self.downloadVideo,
            "0": self.reset,
        }, -1)

        self["channel_actions"].setEnabled(False)

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
        # print("*** createSetup ***")

        if self.level == 1:  # category list
            url = glob.nextlist[-1]['playlist_url']

            # load category list from stored list
            response = glob.current_playlist['data']['vod_categories']
            self.processData(response, url)

        elif self.level == 2:  # channel list
            self.downloadData()

    def downloadData(self):
        # print("*** downloadData ***")
        url = glob.nextlist[-1]["playlist_url"]
        levelpath = str(dir_tmp) + 'level' + str(self.level) + '.xml'

        if not os.path.exists(levelpath):
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

                    self.processData(content, url)
            except Exception as e:
                print(e)
        else:
            with codecs.open(levelpath, 'r', encoding='utf-8') as f:
                self.processData(json.load(f), url)

    def processData(self, response, url):
        # print("*** process data ***")
        index = 0

        if self.level == 1:
            self.list1 = []
            currentCategoryList = response
            hidden = False
            next_url = str(glob.current_playlist['playlist_info']['player_api']) + "&action=get_vod_streams&category_id=0"

            if "0" in glob.current_playlist['player_info']['vodhidden']:
                hidden = True
            self.list1.append([index, _("All"), next_url, "0", hidden])
            index += 1

            for item in currentCategoryList:
                hidden = False
                category_name = item['category_name']
                category_id = item['category_id']

                next_url = str(glob.current_playlist['playlist_info']['player_api']) + "&action=get_vod_streams&category_id=" + str(category_id)

                if category_id in glob.current_playlist['player_info']['vodhidden']:
                    hidden = True

                self.list1.append([index, str(category_name), str(next_url), str(category_id), hidden])
                index += 1

            glob.originalChannelList1 = self.list1[:]

        elif self.level == 2:
            self.list2 = []
            currentChannelList = response

            for item in currentChannelList:
                name = ''
                stream_id = ''
                stream_icon = ''
                added = ''
                container_extension = 'mp4'
                rating = ''

                if 'name' in item:
                    name = item['name']

                if 'stream_id' in item:
                    stream_id = item['stream_id']

                if 'stream_icon' in item and item['stream_icon']:
                    if item['stream_icon'].startswith("http"):
                        stream_icon = item['stream_icon']

                        if stream_icon.startswith("https://image.tmdb.org/t/p/") or stream_icon.startswith("http://image.tmdb.org/t/p/"):
                            dimensions = stream_icon.partition("/p/")[2].partition("/")[0]
                            if screenwidth.width() <= 1280:
                                stream_icon = stream_icon.replace(dimensions, "w300")
                            else:
                                stream_icon = stream_icon.replace(dimensions, "w400")

                if 'added' in item:
                    added = item['added']

                if 'container_extension' in item:
                    container_extension = item['container_extension']

                if 'rating' in item:
                    rating = item['rating']

                next_url = "%s/movie/%s/%s/%s.%s" % (self.host, self.username, self.password, stream_id, container_extension)

                self.list2.append([index, str(name), str(stream_id), str(stream_icon), str(added), str(rating), str(next_url)])
                index += 1

            glob.originalChannelList2 = self.list2[:]
        self.buildLists()

    def buildLists(self):
        # print("*** buildlists ***")

        if self.level == 1:
            self["key_menu"].setText(_("Hide/Show"))
            self["key_rec"].setText('')

            self.channelList = []

            if self.list1:
                self.channelList = [buildCategoryList(x[0], x[1], x[2], x[3], x[4]) for x in self.list1 if x[4] is False]

        elif self.level == 2:
            self["key_menu"].setText('')
            self["key_rec"].setText(_("Download"))
            self.channelList = []

            if self.list2:
                self.channelList = [buildVodStreamList(x[0], x[1], x[2], x[3], x[4], x[5], x[6]) for x in self.list2]

        self["channel_list"].setList(self.channelList)

        if self["channel_list"].getCurrent():

            if glob.nextlist[-1]['index'] != 0:
                self["channel_list"].setIndex(glob.nextlist[-1]['index'])

                channeltitle = self["channel_list"].getCurrent()[0]
                self["channel"].setText(self.main_title + ": " + str(channeltitle))

            if not glob.nextlist[-1]['filter']:
                self["key_blue"].setText(_('Search'))
            else:
                self["key_blue"].setText(_('Reset Search'))

            if glob.nextlist[-1]['filter']:
                self["key_yellow"].setText('')
                if self.level == 1:
                    self["key_menu"].setText('')
            else:
                self["key_yellow"].setText(_(glob.nextlist[-1]['sort']))
                if self.level == 1:
                    self["key_menu"].setText(_("Hide/Show"))

            if self.level == 1:
                self.hideVod()
            elif self.level == 2:
                self.showVod()

        self.selectionChanged()

    def hideVod(self):
        # print("*** hideVod ***")
        self["vod_background"].hide()
        self["vod_cover"].hide()
        self["vod_title"].setText('')
        self["vod_description"].setText('')
        self["vod_video_type_label"].setText('')
        self["vod_duration_label"].setText('')
        self["vod_genre_label"].setText('')
        self["vod_rating_label"].setText('')
        self["vod_country_label"].setText('')
        self["vod_release_date_label"].setText('')
        self["vod_director_label"].setText('')
        self["vod_cast_label"].setText('')
        self["vod_video_type"].setText('')
        self["vod_duration"].setText('')
        self["vod_genre"].setText('')
        self["vod_rating"].setText('')
        self["vod_country"].setText('')
        self["vod_release_date"].setText('')
        self["vod_director"].setText('')
        self["vod_cast"].setText('')

    def showVod(self):
        # print("*** showVod ***")
        self["vod_cover"].show()
        self["vod_background"].show()
        self["vod_video_type_label"].setText(_('Video Type:'))
        self["vod_rating_label"].setText(_('Rating:'))
        self["vod_genre_label"].setText(_('Genre:'))
        self["vod_duration_label"].setText(_('Duration:'))
        self["vod_release_date_label"].setText(_('Release Date:'))
        self["vod_cast_label"].setText(_('Cast:'))
        self["vod_director_label"].setText(_('Director:'))
        self["vod_country_label"].setText(_('Country:'))

    def playStream(self):
        # print("*** playStream ***")
        # exit button back to playing stream
        if self["channel_list"].getCurrent():

            if self.session.nav.getCurrentlyPlayingServiceReference():
                if self.session.nav.getCurrentlyPlayingServiceReference().toString() == glob.currentPlayingServiceRefString:
                    self.back()
                else:
                    ref = str(self.session.nav.getCurrentlyPlayingServiceReference().toString())
                    self.tempstreamtype = ref.partition(':')[0]
                    self.tempstream_url = unquote(ref.split(':')[10]).decode('utf8')
                    self.source = "exit"
                    self.pin = True

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

            self.position = currentindex + 1
            self.positionall = len(self.channelList)
            self.page = int(math.ceil(float(self.position) / float(self.itemsperpage)))
            self.pageall = int(math.ceil(float(self.positionall) / float(self.itemsperpage)))

            self["page"].setText('Page: ' + str(self.page) + " of " + str(self.pageall))
            self["listposition"].setText(str(self.position) + "/" + str(self.positionall))

            self["channel"].setText(self.main_title + ": " + str(channeltitle))

            if self.level == 2:
                self.timerVOD = eTimer()
                try:
                    self.timerVOD.callback.append(self.downloadVodData)
                except:
                    self.timerVOD_conn = self.timerVOD.timeout.connect(self.downloadVodData)
                self.timerVOD.start(50, True)

    def downloadVodData(self):
        # print("*** downloadVodData ***")
        if self["channel_list"].getCurrent():
            stream_id = self["channel_list"].getCurrent()[4]
            url = str(glob.current_playlist['playlist_info']['player_api']) + "&action=get_vod_info&vod_id=" + str(stream_id)
            try:
                r = requests.get(url, headers=hdr, stream=True, timeout=10, verify=False)
                r.raise_for_status()
                if r.status_code == requests.codes.ok:
                    content = r.json()

                if "info" in content and content["info"]:
                    self.info = content["info"]

                    if "name" not in self.info:
                        self.info["name"] = content["movie_data"]["name"]

                elif "movie_data" in content and content["movie_data"]:
                    self.info = content["movie_data"]
                else:
                    self.info = None

                if cfg.refreshTMDB.value is True:
                    self.downloadImage()
                    self.displayVod()
                    self.getTMDB()
                else:
                    self.downloadImage()
                    self.displayVod()

            except requests.exceptions.ConnectionError as e:
                print(("Error Connecting: %s" % e))

            except requests.exceptions.RequestException as e:
                print(e)

    def downloadImage(self):
        # print("*** downloadImage ***")
        if self["channel_list"].getCurrent():
            try:
                os.remove(str(dir_tmp) + 'original.jpg')
            except:
                pass

            size = [267, 400]
            if screenwidth.width() > 1280:
                size = [400, 600]

            original = str(dir_tmp) + 'original.jpg'
            desc_image = ''

            try:
                desc_image = self["channel_list"].getCurrent()[5]

                if self.info:  # tmbdb
                    if 'cover_big' in self.info and self.info["cover_big"] and self.info["cover_big"] != "null":
                        desc_image = str(self.info["cover_big"]).strip()
                    else:
                        self.loadDefaultImage()
                        return

                if desc_image and desc_image != "n/A":
                    if pythonVer == 3:
                        desc_image = desc_image.encode()

                    if desc_image.startswith("https") and sslverify:
                        parsed_uri = urlparse(desc_image)
                        domain = parsed_uri.hostname
                        sniFactory = SNIFactory(domain)
                        downloadPage(desc_image, original, sniFactory, timeout=5).addCallback(self.resizeImage, size).addErrback(self.loadDefaultImage)
                    else:
                        downloadPage(desc_image, original, timeout=5).addCallback(self.resizeImage, size).addErrback(self.loadDefaultImage)
                else:
                    self.loadDefaultImage()

            except Exception as e:
                print(("* image error ** %s" % e))

    def loadDefaultImage(self):
        # print("*** loadDefaultImage ***")
        if self["vod_cover"].instance:
            self["vod_cover"].instance.setPixmapFromFile(skin_path + "images/vod_cover.png")

    def resizeImage(self, data, size):
        # print("*** resizeImage ***")
        if self["channel_list"].getCurrent():
            if self["vod_cover"].instance:
                preview = str(dir_tmp) + 'original.jpg'
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
        if ptr is not None:
            self["vod_cover"].instance.setPixmap(ptr)
            self["vod_cover"].instance.show()

    def displayVod(self):
        # print("*** displayVod ***")
        if self["channel_list"].getCurrent():
            stream_url = self["channel_list"].getCurrent()[3]

            if "name" in self.info:
                self["vod_title"].setText(str(self.info["name"]).strip())
            elif "o_name" in self.info:
                self["vod_title"].setText(str(self.info["o_name"]).strip())
            else:
                self["vod_title"].setText('')

            if 'description' in self.info:
                self["vod_description"].setText(str(self.info["description"]).strip())
            elif 'plot' in self.info:
                self["vod_description"].setText(str(self.info["plot"]).strip())
            else:
                self["vod_description"].setText('')

            try:
                if self["channel_list"].getCurrent():
                    self["vod_video_type"].setText(stream_url.split('.')[-1])
            except:
                self["vod_video_type"].setText('')

            if 'duration' in self.info:
                self["vod_duration"].setText(str(self.info["duration"]).strip())
            else:
                self["vod_duration"].setText('')

            if 'genre' in self.info:
                self["vod_genre"].setText(str(self.info["genre"]).strip())
            else:
                self["vod_genre"].setText('')

            if 'rating' in self.info:
                self["vod_rating"].setText(str(self.info["rating"]).strip())
            else:
                self["vod_rating"].setText('')

            if 'country' in self.info:
                self["vod_country"].setText(str(self.info["country"]).strip())
            else:
                self["vod_country"].setText('')

            if 'releasedate' in self.info and self.info["releasedate"]:
                try:
                    self["vod_release_date"].setText(datetime.strptime(self.info["releasedate"], "%Y-%m-%d").strftime("%d-%m-%Y"))
                except:
                    self["vod_release_date"].setText('')
            else:
                self["vod_release_date"].setText('')

            if 'director' in self.info:
                self["vod_director"].setText(str(self.info["director"]).strip())
            else:
                self["vod_director"].setText('')

            if 'cast' in self.info:
                self["vod_cast"].setText(str(self.info["cast"]).strip())
            elif 'actors' in self.info:
                self["vod_cast"].setText(str(self.info["actors"]).strip())
            else:
                self["vod_cast"].setText('')

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
        # print("*** reset ***")
        self.selectedlist.setIndex(0)
        self.selectionChanged()

    def sort(self):
        # print("*** sort ***")

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

        self.buildLists()

    def search(self):
        # print("*** search ***")

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
            activelist = self.list1[:]
            activeoriginal = glob.originalChannelList1[:]

        elif self.level == 2:
            activelist = self.list2[:]
            activeoriginal = glob.originalChannelList2[:]

        activelist = activeoriginal

        if self.level == 1:
            self.list1 = activelist

        elif self.level == 2:
            self.list2 = activelist

        self.filterresult = ""
        glob.nextlist[-1]["filter"] = self.filterresult

        self.buildLists()

    def pinEntered(self, result):
        # print("*** pinEntered ***")
        from Screens.MessageBox import MessageBox
        if not result:
            self.pin = False
            self.session.open(MessageBox, _("Incorrect pin code."), type=MessageBox.TYPE_ERROR, timeout=5)
        self.next()

    def parentalCheck(self):
        # print("*** parentalCheck ***")
        self.pin = True
        if self.level == 1:
            if cfg.parental.getValue() is True:
                adult = "all,", "+18", "adult", "18+", "18 rated", "xxx", "sex", "porn", "pink", "blue"
                if any(s in str(self["channel_list"].getCurrent()[0]).lower() for s in adult):
                    from Screens.InputBox import PinInput
                    self.session.openWithCallback(self.pinEntered, PinInput, pinList=[config.ParentalControl.setuppin.value], triesEntry=config.ParentalControl.retries.servicepin, title=_("Please enter the parental control pin code"), windowTitle=_("Enter pin code"))
        self.next()

    def next(self):
        # print("*** next ***")
        if self.pin is False:
            return

        if self["channel_list"].getCurrent():
            currentindex = self["channel_list"].getIndex()
            next_url = self["channel_list"].getCurrent()[3]
            glob.nextlist[-1]['index'] = currentindex
            glob.currentchannelist = self.channelList[:]
            glob.currentchannelistindex = currentindex

            exitbutton = False
            callingfunction = sys._getframe().f_back.f_code.co_name
            if callingfunction == "playStream":
                exitbutton = True

            if exitbutton:
                if self.tempstream_url:
                    next_url = str(self.tempstream_url)

            if self.level == 1:
                self.level += 1
                self["channel_list"].setIndex(0)
                self["category_actions"].setEnabled(False)
                self["channel_actions"].setEnabled(True)

                self["key_yellow"].setText(_('Sort: A-Z'))
                glob.nextlist.append({"playlist_url": next_url, "index": 0, "level": self.level, "sort": self["key_yellow"].getText(), "filter": ""})
                self.createSetup()

            elif self.level == 2:
                streamtype = glob.current_playlist["player_info"]["vodtype"]

                if exitbutton:
                    if self.tempstreamtype:
                        streamtype = str(self.tempstreamtype)

                self.reference = eServiceReference(int(streamtype), 0, next_url)
                self.session.openWithCallback(self.setIndex, streamplayer.XStreamity_VodPlayer, str(next_url), str(streamtype))

    def setIndex(self):
        # print("*** set index ***")
        self["channel_list"].setIndex(glob.currentchannelistindex)
        self.selectionChanged()

    def back(self):
        # print("*** back ***")
        del glob.nextlist[-1]

        if len(glob.nextlist) == 0:
            self.stopStream()
            self.close()

        else:
            self.tempstreamtype = ''
            self.tempstream_url = ''
            self["key_rec"].setText('')

            if cfg.stopstream.value:
                self.stopStream()

            levelpath = str(dir_tmp) + 'level' + str(self.level) + '.xml'
            try:
                os.remove(levelpath)
            except:
                pass
            self.level -= 1

            self["category_actions"].setEnabled(True)
            self["channel_actions"].setEnabled(False)
            self.buildLists()

    def imdb(self):
        if self["channel_list"].getCurrent():
            if self["key_rec"].getText() != '':
                self.openIMDb()

    def showHiddenList(self):
        # print("*** showHiddenList ***")
        if self["key_menu"].getText() != '':
            from . import hidden
            if self["channel_list"].getCurrent():
                self.session.openWithCallback(self.createSetup, hidden.XStreamity_HiddenCategories, "vod", self.list1)

    # record button download video file
    def downloadVideo(self):
        from Screens.MessageBox import MessageBox
        if self["channel_list"].getCurrent():
            stream_url = self["channel_list"].getCurrent()[3]
            extension = str(os.path.splitext(stream_url)[-1])
            title = self["channel_list"].getCurrent()[0]
            fileTitle = re.sub(r'[\<\>\:\"\/\\\|\?\*\[\]]', '', title)

            if pythonVer == 3:
                stream_url = stream_url.encode()

            try:
                if stream_url.startswith("https") and sslverify:
                    parsed_uri = urlparse(stream_url)
                    domain = parsed_uri.hostname
                    sniFactory = SNIFactory(domain)
                    downloadPage(stream_url, str(cfg.downloadlocation.getValue()) + str(fileTitle) + str(extension), sniFactory).addErrback(self.printError)
                else:
                    downloadPage(stream_url, str(cfg.downloadlocation.getValue()) + str(fileTitle) + str(extension)).addErrback(self.printError)
                self.session.open(MessageBox, _('Downloading \n\n' + title + "\n\n" + str(cfg.downloadlocation.getValue()) + str(fileTitle) + str(extension)), MessageBox.TYPE_INFO)
            except Exception as e:
                print(("download vod %s" % e))

            except:
                self.session.open(MessageBox, _('Download Failed\n\n' + title + "\n\n" + str(cfg.downloadlocation.getValue()) + str(fileTitle) + str(extension)), MessageBox.TYPE_WARNING)

    def getTMDB(self):
        try:
            os.remove(str(dir_tmp) + 'search.txt')
        except:
            pass

        isIMDB = False

        if self["channel_list"].getCurrent():

            next_url = self["channel_list"].getCurrent()[3]

            if next_url != 'None' and "/movie/" in next_url:
                title = self["channel_list"].getCurrent()[0]

                if self.info:
                    if "name" in self.info and self.info['name']:
                        title = self.info['name']
                    elif "o_name" in self.info and self.info['o_name']:
                        title = self.info['o_name']

                    if 'tmdb_id' in self.info and self.info['tmdb_id']:
                        if str(self.info['tmdb_id'])[:1].isdigit():
                            self.getTMDBDetails(self.info["tmdb_id"])
                            return
                        else:
                            isIMDB = True

                searchtitle = title.lower()

                # if title ends in 'the', move 'the' to the beginning
                if searchtitle.endswith("the"):
                    searchtitle.rsplit(' ', 1)[0]
                    searchtitle = searchtitle.rsplit(' ', 1)[0]
                    searchtitle = "the " + str(searchtitle)

                bad_chars = ["sd", "hd", "fhd", "uhd", "4k", "vod", "1080p", "720p", "blueray", "x264", "aac", "ozlem", "hindi", "hdrip", "(cache)", "(kids)", "[3d-en]", "[iran-dubbed]", "imdb", "top250", "multi-audio",
                             "multi-subs", "multi-sub", "[audio-pt]", "[nordic-subbed]", "[nordic-subbeb]",

                             "ae:", "al:", "ar:", "at:", "ba:", "be:", "bg:", "br:", "cg:", "ch:", "cz:", "da:", "de:", "dk:", "ee:", "en:", "es:", "ex-yu:", "fi:", "fr:", "gr:", "hr:", "hu:", "in:", "ir:", "it:", "lt:", "mk:",
                             "mx:", "nl:", "no:", "pl:", "pt:", "ro:", "rs:", "ru:", "se:", "si:", "sk:", "tr:", "uk:", "us:", "yu:",

                             "[ae]", "[al]", "[ar]", "[at]", "[ba]", "[be]", "[bg]", "[br]", "[cg]", "[ch]", "[cz]", "[da]", "[de]", "[dk]", "[ee]", "[en]", "[es]", "[ex-yu]", "[fi]", "[fr]", "[gr]", "[hr]", "[hu]", "[in]", "[ir]", "[it]", "[lt]", "[mk]",
                             "[mx]", "[nl]", "[no]", "[pl]", "[pt]", "[ro]", "[rs]", "[ru]", "[se]", "[si]", "[sk]", "[tr]", "[uk]", "[us]", "[yu]",

                             "-ae-", "-al-", "-ar-", "-at-", "-ba-", "-be-", "-bg-", "-br-", "-cg-", "-ch-", "-cz-", "-da-", "-de-", "-dk-", "-ee-", "-en-", "-es-", "-ex-yu-", "-fi-", "-fr-", "-gr-", "-hr-", "-hu-", "-in-", "-ir-", "-it-", "-lt-", "-mk-",
                             "-mx-", "-nl-", "-no-", "-pl-", "-pt-", "-ro-", "-rs-", "-ru-", "-se-", "-si-", "-sk-", "-tr-", "-uk-", "-us-", "-yu-",

                             "|ae|", "|al|", "|ar|", "|at|", "|ba|", "|be|", "|bg|", "|br|", "|cg|", "|ch|", "|cz|", "|da|", "|de|", "|dk|", "|ee|", "|en|", "|es|", "|ex-yu|", "|fi|", "|fr|", "|gr|", "|hr|", "|hu|", "|in|", "|ir|", "|it|", "|lt|", "|mk|",
                             "|mx|", "|nl|", "|no|", "|pl|", "|pt|", "|ro|", "|rs|", "|ru|", "|se|", "|si|", "|sk|", "|tr|", "|uk|", "|us|", "|yu|",

                             "(", ")", "[", "]", "u-", "3d", "'", "#", "/"]

                for j in range(1900, 2025):
                    bad_chars.append(str(j))

                for i in bad_chars:
                    searchtitle = searchtitle.replace(i, '')

                bad_suffix = [' de', ' al', ' nl', ' pt', ' pl', ' ru', ' ar', ' ro', ' gr', ' fi', ' no', ' rs', ' ba', ' si', ' mk', ' ex-yu', ' hr', ' yu', ' fr', ' da', ' es', ' sw', ' swe', ' tr', ' en', ' uk']

                for i in bad_suffix:
                    if searchtitle.endswith(i):
                        suffixlength = len(i)
                        searchtitle = searchtitle[:-suffixlength]

                searchtitle = searchtitle.replace('_', ' ')
                searchtitle = searchtitle.replace('  ', ' ')
                searchtitle = searchtitle.replace(' ', '%20')
                searchtitle = searchtitle.strip()

                if isIMDB is False:
                    searchurl = 'http://api.themoviedb.org/3/search/movie?api_key=' + str(self.check(self.token)) + '&query=%22' + str(searchtitle) + '%22'
                else:
                    searchurl = 'http://api.themoviedb.org/3/find/' + str(self.info["tmdb_id"]) + '?api_key=' + str(self.check(self.token)) + '&external_source=imdb_id'
                if pythonVer == 3:
                    searchurl = searchurl.encode()

                try:
                    downloadPage(searchurl, str(dir_tmp) + 'search.txt', timeout=10).addCallback(self.processTMDB, isIMDB).addErrback(self.printError)
                except Exception as e:
                    print(("download TMDB %s" % e))
                except:
                    pass

    def processTMDB(self, result, IMDB):
        with codecs.open(str(dir_tmp) + 'search.txt', 'r', encoding='utf-8') as f:
            response = f.read()

        if response != '':
            try:
                self.searchresult = json.loads(response)
                if IMDB is False:
                    if 'results' in self.searchresult and self.searchresult['results']:
                        if 'id' in self.searchresult['results'][0]:
                            resultid = self.searchresult['results'][0]['id']
                        else:
                            return
                else:
                    if 'movie_results' in self.searchresult and self.searchresult['movie_results']:
                        if 'id' in self.searchresult['movie_results'][0]:
                            resultid = self.searchresult['movie_results'][0]['id']
                        else:
                            return

                self.getTMDBDetails(resultid)
            except:
                pass

    def getTMDBDetails(self, resultid):
        try:
            os.remove(str(dir_tmp) + 'movie.txt')
        except:
            pass

        language = "en"

        if cfg.refreshTMDB.value is True:
            language = cfg.TMDBLanguage.value

        detailsurl = "http://api.themoviedb.org/3/movie/" + str(resultid) + "?api_key=" + str(self.check(self.token)) + "&append_to_response=credits&language=" + str(language)
        if pythonVer == 3:
            detailsurl = detailsurl.encode()
        try:
            downloadPage(detailsurl, str(dir_tmp) + 'movie.txt', timeout=10).addCallback(self.processTMDBDetails).addErrback(self.printError)
        except Exception as e:
            print(("download TMDB details %s" % e))
        except:
            pass

    def processTMDBDetails(self, result):
        valid = False
        response = ''

        self.detailsresult = []
        genre = []
        country = []
        director = []
        cast = []

        with codecs.open(str(dir_tmp) + 'movie.txt', 'r', encoding='utf-8') as f:
            response = f.read()

        if response != '':
            valid = False
            try:
                self.detailsresult = json.loads(response, object_pairs_hook=OrderedDict)

                valid = True
            except:
                pass

            if not self.info:
                self.info = {}

            if valid:
                if "poster_path" in self.detailsresult and self.detailsresult["poster_path"]:
                    if screenwidth.width() <= 1280:
                        self.info["cover_big"] = "http://image.tmdb.org/t/p/w300" + str(self.detailsresult["poster_path"])
                    else:
                        self.info["cover_big"] = "http://image.tmdb.org/t/p/w400" + str(self.detailsresult["poster_path"])

                if "title" in self.detailsresult and self.detailsresult["title"]:
                    self.info["name"] = str(self.detailsresult["title"])

                if "original_title" in self.detailsresult and self.detailsresult["original_title"]:
                    self.info["o_name"] = str(self.detailsresult["original_title"])

                if "overview" in self.detailsresult and self.detailsresult["overview"]:
                    self.info["description"] = str(self.detailsresult["overview"])

                if "runtime" in self.detailsresult and self.detailsresult["runtime"] and self.detailsresult["runtime"] != 0:
                    self.info['duration'] = str(timedelta(minutes=self.detailsresult["runtime"]))

                if "vote_average" in self.detailsresult and self.detailsresult["vote_average"] and self.detailsresult["vote_average"] != 0:
                    self.info['rating'] = str(self.detailsresult["vote_average"])

                if "genres" in self.detailsresult and self.detailsresult["genres"]:
                    for genreitem in self.detailsresult["genres"]:
                        genre.append(str(genreitem["name"]))
                    genre = " / ".join(map(str, genre))
                    self.info['genre'] = genre

                if "production_countries" in self.detailsresult and self.detailsresult["production_countries"]:
                    for pcountry in self.detailsresult["production_countries"]:
                        country.append(str(pcountry["name"]))
                    country = ", ".join(map(str, country))
                    self.info['country'] = country

                if "release_date" in self.detailsresult and self.detailsresult["release_date"]:
                    self.info['releasedate'] = str(self.detailsresult["release_date"])

                if "credits" in self.detailsresult:
                    if "cast" in self.detailsresult["credits"]:
                        for actor in self.detailsresult["credits"]["cast"]:
                            if "character" in actor:
                                cast.append(str(actor["name"]))
                        cast = ", ".join(map(str, cast))
                        self.info['cast'] = cast

                if "credits" in self.detailsresult and "crew" in self.detailsresult["credits"]:
                    for actor in self.detailsresult["credits"]["crew"]:
                        if "job" in actor:
                            director.append(str(actor["name"]))

                    director = ", ".join(map(str, director))
                    self.info['director'] = director

                self.downloadImage()
                self.displayVod()

    def printError(self, failure):
        print(("********* error ******** %s" % failure))
        pass

    def openIMDb(self):
        from Screens.MessageBox import MessageBox
        try:
            from Plugins.Extensions.IMDb.plugin import IMDB
            try:
                name = self["channel_list"].getCurrent()[0]
            except:
                name = ''
            self.session.open(IMDB, name, False)
        except ImportError:
            self.session.open(MessageBox, _('The IMDb plugin is not installed!\nPlease install it.'), type=MessageBox.TYPE_INFO, timeout=10)

    def check(self, token):
        result = base64.b64decode(token)
        result = zlib.decompress(base64.b64decode(result))
        result = base64.b64decode(result).decode()
        return result


def buildCategoryList(index, title, next_url, category_id, hidden):
    png = LoadPixmap(common_path + "more.png")
    return (title, png, index, next_url, category_id, hidden)


def buildVodStreamList(index, title, stream_id, stream_icon, added, rating, next_url):
    png = LoadPixmap(common_path + "play.png")
    return (title, png, index, next_url, stream_id, stream_icon, added, rating)
