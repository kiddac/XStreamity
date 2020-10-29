#!/usr/bin/python
# -*- coding: utf-8 -*-

# for localized messages
from . import _

from . import streamplayer
from . import xstreamity_globals as glob

from .plugin import skin_path, screenwidth, hdr, cfg, common_path, dir_tmp
from .xStaticText import StaticText

from Components.ActionMap import ActionMap
from Components.AVSwitch import AVSwitch
from Components.config import config, ConfigClock, NoSave, ConfigText
from Components.Pixmap import Pixmap
from Components.ProgressBar import ProgressBar
from Components.Sources.List import List
from datetime import datetime, timedelta, date
from enigma import eTimer, eServiceReference, ePicLoad
from PIL import Image, ImageChops
from requests.adapters import HTTPAdapter
from RecordTimer import RecordTimerEntry
from Screens.Screen import Screen
from Screens.VirtualKeyBoard import VirtualKeyBoard
from ServiceReference import ServiceReference
from Tools.LoadPixmap import LoadPixmap
from twisted.web.client import downloadPage

try:
    from urllib import unquote
except:
    from urllib.parse import unquote

from Screens.MessageBox import MessageBox

import xml.etree.cElementTree as ET

import base64
import re
import json
import math
import os
import requests
import sys
import time
import threading
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
    from twisted.internet import ssl, reactor
    from twisted.internet._sslverify import ClientTLSOptions
    sslverify = True
except:
    sslverify = False

if sslverify:
    try:
        from urlparse import urlparse, parse_qs
    except:
        from urllib.parse import urlparse, parse_qs

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
        self.main_title = (_("Live Streams"))

        nexturl = str(glob.current_playlist['playlist_info']['player_api']) + "&action=get_live_categories"

        self.level = 1
        glob.nextlist = []
        glob.nextlist.append({"playlist_url": nexturl, "index": 0, "level": self.level})

        self["channel"] = StaticText(self.main_title)

        self.list = []  # original category/programme list
        self.channelList = []  # amended category/programme list
        self["channel_list"] = List(self.channelList, enableWrapAround=True)
        self.selectedlist = self["channel_list"]

        self.listAll = []  # all original categories combined into 1
        self.channelListAll = []  # amended all categories/programmes list

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
        self.epgchecklist = []
        self.epgdownloading = False

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

        self.sorted = False
        self.isStream = False
        self.filtered = False
        self.pin = False

        self.protocol = glob.current_playlist['playlist_info']['protocol']
        self.domain = glob.current_playlist['playlist_info']['domain']
        self.host = glob.current_playlist['playlist_info']['host']
        self.livetype = glob.current_playlist['player_info']['livetype']
        self.username = glob.current_playlist['playlist_info']['username']
        self.password = glob.current_playlist['playlist_info']['password']
        self.output = glob.current_playlist['playlist_info']['output']

        self.simpledatatable = str(glob.current_playlist['playlist_info']['player_api']) + "&action=get_simple_data_table&stream_id="

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

        self.xmltvdownloaded = False

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
            "left": self.pageUp,
            "right": self.pageDown,
            "up": self.goUp,
            "down": self.goDown,
            "channelUp": self.pageUp,
            "channelDown": self.pageDown,
            "rec": self.downloadStream,
            "0": self.reset,
        }, -1)

        self["channel_actions"].setEnabled(False)

        self.onFirstExecBegin.append(self.createSetup)
        self.onLayoutFinish.append(self.__layoutFinished)

    def __layoutFinished(self):
        self.setTitle(self.setup_title)

    def check(self, token):
        result = base64.b64decode(token)
        result = zlib.decompress(base64.b64decode(result))
        result = base64.b64decode(result).decode()
        return result

    def createSetup(self):
        # resets
        self.epgchecklist = []
        self.sorted = False

        if self.filtered:
            self.resetSearch()

        # enigma2_api quick epg location
        try:
            os.remove(str(dir_tmp) + "liveepg.xml")
        except:
            pass

        # where full epg is saved
        self.epg_path = cfg.location.getValue() + "epg/"
        if not os.path.exists(self.epg_path):
            os.makedirs(self.epg_path)

        # if external media - override above and write to external
        try:
            if config.misc.epgcachepath:
                if config.misc.epgcachepath.getValue() != "/etc/enigma2/":
                    self.epg_path = config.misc.epgcachepath.getValue() + "epg/"
                    if not os.path.exists(self.epg_path):
                        os.makedirs(self.epg_path)
        except:
            pass

        self.epg_file_name = "epg_%s.xml" % (glob.current_playlist['playlist_info']['domain'].replace(".", "_"))
        self.epg_full_path = self.epg_path + self.epg_file_name

        # buttons
        self["epg_title"].setText('')
        self["epg_description"].setText('')
        self["key_rec"].setText('')

        if self.level == 1:  # category list
            self["key_menu"].setText(_("Hide/Show"))
            self["key_epg"].setText('')
            url = glob.nextlist[-1]['playlist_url']

            # load category list from stored list
            response = glob.current_playlist['data']['live_categories']
            self.processData(response, url)

        else:  # channel list
            self["key_menu"].setText('')
            self.downloadData()

    def downloadData(self):
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

            except requests.exceptions.ConnectionError as e:
                print(("Error Connecting: %s" % e))

            except requests.exceptions.RequestException as e:
                print(e)
        else:
            with codecs.open(levelpath, 'r', encoding='utf-8') as f:
                self.processData(json.load(f), url)

        if glob.current_playlist['player_info']['epgtype'] == "1":
            if self.sorted is False and self.filtered is False:
                self.downloadQuickEPGList()

    def processData(self, response, url):
        self.channelList = []
        currentCategoryList = ''
        index = 0
        indexAll = 0

        self.list = []
        self.listAll = []

        if self.level == 1:
            currentCategoryList = glob.current_playlist['data']['live_categories']
            hidden = False

            # add an ALL Category
            next_url = str(glob.current_playlist['playlist_info']['player_api']) + "&action=get_live_streams&category_id=0"

            # Dont add if not required
            if "0" in glob.current_playlist['player_info']['livehidden']:
                hidden = True

            if hidden is False:
                self.list.append([index, _("All"), next_url, "0"])
                self.listAll.append([index, _("All"), next_url, "0"])
                index += 1
                indexAll += 1

            for item in currentCategoryList:
                hidden = False
                category_name = item['category_name']
                category_id = item['category_id']

                next_url = str(glob.current_playlist['playlist_info']['player_api']) + "&action=get_live_streams&category_id=" + str(category_id)

                if category_id in glob.current_playlist['player_info']['livehidden']:
                    hidden = True

                if hidden is False:
                    # not hidden list
                    self.list.append([index, str(category_name), str(next_url), str(category_id)])
                    index += 1

                # full list
                self.listAll.append([indexAll, str(category_name), str(next_url), str(category_id)])
                indexAll += 1

                self.epgchecklist = []

        elif self.level == 2:
            currentChannelList = response
            nextAction = ""

            for item in currentChannelList:

                name = ''
                stream_id = ''
                stream_icon = ''
                epg_channel_id = ''
                added = ''

                if 'name' in item:
                    name = item['name']

                # restyle bouquet markers
                if 'stream_type' in item:
                    if item['stream_type'] != "live":
                        pattern = re.compile(r'[^\w\s()\[\]]', re.U)
                        name = re.sub(r'_', '', re.sub(pattern, '', name))
                        name = "** " + str(name) + " **"

                if 'stream_id' in item:
                    stream_id = item['stream_id']

                if 'stream_icon' in item:
                    if item['stream_icon'].startswith("http"):
                        stream_icon = item['stream_icon']

                # fix some bad picons
                if stream_icon:
                    if stream_icon.startswith("https://vignette.wikia.nocookie.net/tvfanon6528"):
                        # stream_icon = stream_icon.replace("https", "http")
                        if "scale-to-width-down" not in stream_icon:
                            stream_icon = str(stream_icon) + "/revision/latest/scale-to-width-down/220"

                if 'epg_channel_id' in item:
                    epg_channel_id = item['epg_channel_id']

                if 'added' in item:
                    added = item['added']

                next_url = "%s/live/%s/%s/%s.%s" % (self.host, self.username, self.password, stream_id, self.output)

                self.list.append([index, str(name), str(stream_id), str(stream_icon), str(epg_channel_id), str(added), str(next_url), '', '', '', '', '', ''])
                index += 1

        glob.originalChannelList = self.list[:]
        self.buildLists()

    def buildLists(self):
        if self.list:
            if self.level == 1:
                self.channelList = []
                self.channelList = [buildCategoryList(x[0], x[1], x[2], x[3]) for x in self.list]
                self["channel_list"].setList(self.channelList)

                self.channelListAll = []
                self.channelListAll = [buildCategoryList(x[0], x[1], x[2], x[3]) for x in self.listAll]

                # full epg download

                if glob.current_playlist['player_info']['epgtype'] == "2":
                    if os.path.isfile(self.epg_full_path):
                        self.xmltvdownloaded = True

                        if self["downloading"].instance:
                            self["downloading"].hide()
                        last_modified = datetime.fromtimestamp(int(os.path.getmtime(self.epg_full_path)))
                        datenow = datetime.now()

                        if last_modified.date() < datenow.date():
                            try:
                                os.remove(self.epg_full_path)
                                self.xmltvdownloaded = False

                                self.timer = eTimer()
                                try:
                                    self.timer_conn = self.timer.timeout.connect(self.doXMLTVDownload)
                                except:
                                    try:
                                        self.timer.callback.append(self.doXMLTVDownload)
                                    except:
                                        self.createSetup()
                                self.timer.start(5, True)

                            except:
                                pass
                    else:
                        self.timer = eTimer()
                        try:
                            self.timer_conn = self.timer.timeout.connect(self.doXMLTVDownload)
                        except:
                            try:
                                self.timer.callback.append(self.doXMLTVDownload)
                            except:
                                self.createSetup()
                        self.timer.start(5, True)

            elif self.level == 2:
                # build empty epg list
                self.epglist = []
                self.epglist = [buildEPGListEntry(x[0], x[1], x[7], x[8], x[9], x[10], x[11], x[12]) for x in self.list]
                self["epg_list"].setList(self.epglist)

                self.channelList = []
                self.channelList = [buildLiveStreamList(x[0], x[1], x[2], x[3], x[4], x[5], x[6]) for x in self.list]
                self["channel_list"].setList(self.channelList)

                # disable epg panel selection
                instance = self["epg_list"].master.master.instance
                instance.setSelectionEnable(0)

        if self["channel_list"].getCurrent():
            next_url = self["channel_list"].getCurrent()[3]

            if glob.nextlist[-1]['index'] != 0:
                self["channel_list"].setIndex(glob.nextlist[-1]['index'])

                channeltitle = self["channel_list"].getCurrent()[0]
                self["channel"].setText(self.main_title + ": " + str(channeltitle))

            if self.level == 1:
                self.hideEPG()
            elif self.level == 2:
                self.showEPGElements()

        self.selectionChanged()

    def hideEPG(self):
        self["epg_list"].setList([])
        self["epg_picon"].hide()
        self["epg_bg"].hide()
        self["epg_title"].setText('')
        self["epg_description"].setText('')
        self["progress"].hide()

    def showEPGElements(self):
        self["epg_picon"].show()
        self["epg_bg"].show()

    def playStream(self):
        # exit button back to playing stream
        if self["channel_list"].getCurrent():

            if self.session.nav.getCurrentlyPlayingServiceReference():
                if self.session.nav.getCurrentlyPlayingServiceReference().toString() == glob.currentPlayingServiceRefString or self.selectedlist == self["epg_short_list"]:
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
        if glob.currentPlayingServiceRefString != glob.newPlayingServiceRefString:
            if glob.newPlayingServiceRefString != '':
                if self.session.nav.getCurrentlyPlayingServiceReference():
                    self.session.nav.stopService()
                self.session.nav.playService(eServiceReference(glob.currentPlayingServiceRefString))
                glob.newPlayingServiceRefString = glob.currentPlayingServiceRefString

    def selectionChanged(self):
        if self["channel_list"].getCurrent():
            channeltitle = self["channel_list"].getCurrent()[0]
            next_url = self["channel_list"].getCurrent()[3]
            currentindex = self["channel_list"].getIndex()

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

                if glob.current_playlist['player_info']['epgtype'] == "2":
                    if self.level == 2 and self.xmltvdownloaded and self.sorted is False and self.filtered is False:
                        self.getChannelChunk()

    def downloadImage(self):
        if self["channel_list"].getCurrent():
            try:
                os.remove(str(dir_tmp) + 'original.png')
            except:
                pass

            # self.loadDefaultImage()

            size = []
            desc_image = ''

            try:
                desc_image = self["channel_list"].getCurrent()[5]
            except Exception as e:
                print(("* image error ** %s" % e))

            size = [147, 88]
            if screenwidth.width() > 1280:
                size = [220, 130]

            if desc_image and desc_image != "n/A":
                original = str(dir_tmp) + 'original.png'

                """
                if desc_image.startswith('https'):
                    desc_image = desc_image.replace('https', 'http')
                    """

                if pythonVer == 3:
                    desc_image = desc_image.encode()

                if desc_image.startswith("https") and sslverify:
                    parsed_uri = urlparse(desc_image)
                    domain = parsed_uri.hostname
                    sniFactory = SNIFactory(domain)
                    downloadPage(desc_image, original, sniFactory, timeout=5).addCallback(self.resizeImage, size).addErrback(self.imageError)
                else:
                    downloadPage(desc_image, original, timeout=5).addCallback(self.resizeImage, size).addErrback(self.imageError)

    def loadDefaultImage(self):
        if self["epg_picon"].instance:
            self["epg_picon"].instance.setPixmapFromFile(common_path + "picon.png")

    def imageError(self, failure):
        print(("********* image error ******** %s" % failure))
        self.loadDefaultImage()

    def resizeImage(self, data, size):
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
        # print "********* threadname ********"
        # print(threading.currentThread().getName())

        if self["epg_list"].getCurrent():
            instance = self["epg_list"].master.master.instance
            instance.setSelectionEnable(1)

            startnowtime = self["epg_list"].getCurrent()[2]
            titlenow = self["epg_list"].getCurrent()[3]
            descriptionnow = self["epg_list"].getCurrent()[4]
            startnexttime = self["epg_list"].getCurrent()[5]

            if titlenow:
                nowtitle = "%s - %s  %s" % (startnowtime, startnexttime, titlenow)
                self["key_epg"].setText(_("Next Info"))

            else:
                nowtitle = ""
                self["key_epg"].setText('')
                instance.setSelectionEnable(0)

            self["epg_title"].setText(nowtitle)
            self["epg_description"].setText(descriptionnow)

            # display progress bar
            start = ''
            end = ''
            percent = 0
            
            if self["epg_list"].getCurrent():
                start = self["epg_list"].getCurrent()[2]
                end = self["epg_list"].getCurrent()[5]

            if startnowtime and startnexttime:
                self["progress"].show()

                start_time = datetime.strptime(startnowtime, "%H:%M")
                end_time = datetime.strptime(startnexttime, "%H:%M")
                
                if end_time < start_time:
                    end_time = datetime.strptime(end, "%H:%M") + timedelta(hours=24)

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
        try:
            system("echo 1 > /proc/sys/vm/drop_caches")
            system("echo 2 > /proc/sys/vm/drop_caches")
            system("echo 3 > /proc/sys/vm/drop_caches")
        except:
            pass

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
        if self["channel_list"].getCurrent():
            self["channel_list"].setIndex(0)
            current_sort = self["key_yellow"].getText()

            if current_sort == (_('Sort: A-Z')):
                self["key_yellow"].setText(_('Sort: Z-A'))
                self.list.sort(key=lambda x: x[1], reverse=False)
                self.sorted = True

            elif current_sort == (_('Sort: Z-A')):
                if self.level == 2:
                    self["key_yellow"].setText(_('Sort: Newest'))
                else:
                    self["key_yellow"].setText(_('Sort: Original'))
                self.list.sort(key=lambda x: x[1], reverse=True)
                self.sorted = True

            elif current_sort == (_('Sort: Newest')):
                if self.level == 2:
                    self.list.sort(key=lambda x: x[5], reverse=True)
                self.sorted = True

                self["key_yellow"].setText(_('Sort: Original'))

            elif current_sort == (_('Sort: Original')):
                self["key_yellow"].setText(_('Sort: A-Z'))
                self.list = glob.originalChannelList
                self.sorted = False
                self.createSetup()

            self.epgchecklist = []
            self.buildLists()

    def search(self):
        current_filter = self["key_blue"].getText()
        if current_filter != (_('Reset Search')):
            self.session.openWithCallback(self.filterChannels, VirtualKeyBoard, title=_("Filter this category..."), text=self.searchString)
        else:
            self.resetSearch()

    def filterChannels(self, result):
        if result:
            self.searchString = result
            self["key_blue"].setText(_('Reset Search'))
            self["key_yellow"].setText('')
            self.list = [channel for channel in self.list if str(result).lower() in str(channel[1]).lower()]
            self.epgchecklist = []
            self.filtered = True
            self.buildLists()

    def resetSearch(self):
        self["key_blue"].setText(_('Search'))
        self["key_yellow"].setText(_('Sort: A-Z'))
        self.list = glob.originalChannelList
        self.filtered = False
        self.sorted = False
        self.createSetup()

    def pinEntered(self, result):
        from Screens.MessageBox import MessageBox
        if not result:
            self.pin = False
            self.session.open(MessageBox, _("Incorrect pin code."), type=MessageBox.TYPE_ERROR, timeout=5)
        self.next()

    def parentalCheck(self):
        self.pin = True
        if self.level == 1:
            if cfg.parental.getValue() is True:
                adult = "all,", "+18", "adult", "18+", "18 rated", "xxx", "sex", "porn", "pink", "blue"
                if any(s in str(self["channel_list"].getCurrent()[0]).lower() for s in adult):
                    from Screens.InputBox import PinInput
                    self.session.openWithCallback(self.pinEntered, PinInput, pinList=[config.ParentalControl.setuppin.value], triesEntry=config.ParentalControl.retries.servicepin, title=_("Please enter the parental control pin code"), windowTitle=_("Enter pin code"))
        self.next()

    def next(self):
        if self.pin is False:
            return

        self["key_yellow"].setText(_('Sort: A-Z'))

        if self["channel_list"].getCurrent():
            currentindex = self["channel_list"].getIndex()
            next_url = self["channel_list"].getCurrent()[3]
            glob.nextlist[-1]['index'] = currentindex

            self.list = glob.originalChannelList

            glob.currentchannelist = self.channelList[:]
            glob.currentchannelistindex = currentindex
            glob.currentepglist = self.epglist[:]

            exitbutton = False
            callingfunction = sys._getframe().f_back.f_code.co_name
            if callingfunction == "playStream":
                exitbutton = True

            if exitbutton:
                if self.tempstream_url:
                    next_url = str(self.tempstream_url)

            if self.level == 1:
                glob.nextlist.append({"playlist_url": next_url, "index": 0})
                self.level += 1
                self["channel_list"].setIndex(0)
                self["category_actions"].setEnabled(False)
                self["channel_actions"].setEnabled(True)
                self.createSetup()

            elif self.level == 2:
                streamtype = glob.current_playlist["player_info"]["livetype"]

                if exitbutton:
                    if self.tempstreamtype:
                        streamtype = str(self.tempstreamtype)

                self.reference = eServiceReference(int(streamtype), 0, next_url)

                if self.session.nav.getCurrentlyPlayingServiceReference():
                    # live preview
                    if self.session.nav.getCurrentlyPlayingServiceReference().toString() != self.reference.toString() and cfg.livepreview.value is True:
                        self.session.nav.stopService()
                        self.session.nav.playService(self.reference)

                        if self.session.nav.getCurrentlyPlayingServiceReference():
                            glob.newPlayingServiceRef = self.session.nav.getCurrentlyPlayingServiceReference()
                            glob.newPlayingServiceRefString = glob.newPlayingServiceRef.toString()
                    else:
                        self.session.openWithCallback(self.setIndex, streamplayer.XStreamity_StreamPlayer, str(next_url), str(streamtype))
                else:
                    self.session.openWithCallback(self.setIndex, streamplayer.XStreamity_StreamPlayer, str(next_url), str(streamtype))

    def setIndex(self):
        self["channel_list"].setIndex(glob.currentchannelistindex)
        self["epg_list"].setIndex(glob.currentchannelistindex)

    def back(self):
        try:
            os.remove(str(dir_tmp) + "liveepg.xml")
        except:
            pass

        if self.selectedlist == self["epg_short_list"]:
            self.shortEPG()
            return

        del glob.nextlist[-1]

        if len(glob.nextlist) == 0:
            self.stopStream()
            self.close()

        else:
            self.tempstreamtype = ''
            self.tempstream_url = ''

            self.sorted = False
            self["key_yellow"].setText(_('Sort: A-Z'))
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

            self.createSetup()

    def downloadQuickEPGList(self):
        # download enigma2_api EPG
        url = glob.nextlist[-1]["playlist_url"]
        urlcategory = url.rsplit("=")[-1]
        quickEPG = str(glob.current_playlist['playlist_info']['enigma2_api']) + "&type=get_live_streams&cat_id=" + str(urlcategory)
        if pythonVer == 3:
            quickEPG = quickEPG.encode()

        if not os.path.exists(str(dir_tmp) + "liveepg.xml"):

            if quickEPG.startswith("https") and sslverify:
                parsed_uri = urlparse(quickEPG)
                domain = parsed_uri.hostname
                sniFactory = SNIFactory(domain)
                downloadPage(quickEPG, str(dir_tmp) + "liveepg.xml", sniFactory, timeout=5).addCallback(self.processQuickEPG).addErrback(self.QuickEPGError)
            else:
                downloadPage(quickEPG, str(dir_tmp) + "liveepg.xml", timeout=5).addCallback(self.processQuickEPG).addErrback(self.QuickEPGError)
        else:
            self.processQuickEPG()

    def QuickEPGError(self, failure):
        print(("********* Quick EPG Error ******** %s " % failure))
        pass

    def processQuickEPG(self, data=None):
        if os.path.exists(str(dir_tmp) + "liveepg.xml"):
            with codecs.open(str(dir_tmp) + "liveepg.xml", 'r', encoding='utf-8') as f:
                content = f.read()

        if content:
            root = ET.fromstring(content)
            index = 0
            for channel in root.findall('channel'):
                nowtitle = nowdescription = nowstarttime = nowendtime = ''
                nexttitle = nextdescription = ''

                description = base64.b64decode(channel.findtext('description')).decode('utf-8')
                try:
                    description = ''.join(chr(ord(c)) for c in description).decode('utf8')
                except:
                    pass

                if description:
                    lines = re.split("\n", description)
                    newdescription = []

                    # use string manipulation rather than regex for speed.
                    for line in lines:
                        if line.startswith("[") or line.startswith("("):
                            newdescription.append(line)

                    try:
                        nowstarttime = newdescription[0].partition(" ")[0].lstrip("[").rstrip("]")
                    except:
                        pass

                    try:
                        nowtitle = newdescription[0].partition(" ")[-1].strip()
                    except:
                        pass

                    try:
                        nowdescription = newdescription[1].lstrip("(").rstrip(")").strip()
                    except:
                        pass

                    try:
                        nowendtime = newdescription[2].partition(" ")[0].lstrip("[").rstrip("]")
                    except:
                        pass

                    try:
                        nexttitle = newdescription[2].partition(" ")[-1].strip()
                    except:
                        pass

                    try:
                        nextdescription = newdescription[3].lstrip("(").rstrip(")").strip()
                    except:
                        pass

                    shift = 0
                    if "epgquickshift" in glob.current_playlist["player_info"]:
                        shift = int(glob.current_playlist["player_info"]["epgquickshift"])

                    if nowstarttime != "":
                        nowstarttime = str(date.today()) + " " + str(nowstarttime)
                        time = datetime.strptime(nowstarttime, "%Y-%m-%d %H:%M")
                        nowshifttime = time + timedelta(hours=shift)
                        nowstarttime = format(nowshifttime, '%H:%M')

                    if nowendtime:
                        nowendtime = str(date.today()) + " " + str(nowendtime)
                        time = datetime.strptime(nowendtime, "%Y-%m-%d %H:%M")
                        nextshifttime = time + timedelta(hours=shift)
                        nowendtime = format(nextshifttime, '%H:%M')

                self.list[index][7] = str(nowstarttime)
                self.list[index][8] = str(nowtitle)
                self.list[index][9] = str(nowdescription)
                self.list[index][10] = str(nowendtime)
                self.list[index][11] = str(nexttitle)
                self.list[index][12] = str(nextdescription)

                index += 1

            self.epglist = []
            self.epglist = [buildEPGListEntry(x[0], x[1], x[7], x[8], x[9], x[10], x[11], x[12]) for x in self.list]

            self["epg_list"].setList(self.epglist)

            instance = self["epg_list"].master.master.instance
            instance.setSelectionEnable(0)

            self.refreshEPGInfo()

    def nownext(self):
        if self["channel_list"].getCurrent():
            if self.level == 2:
                if self["key_epg"].getText() and self["epg_list"].getCurrent():
                    startnowtime = self["epg_list"].getCurrent()[2]
                    titlenow = self["epg_list"].getCurrent()[3]
                    descriptionnow = self["epg_list"].getCurrent()[4]

                    startnexttime = self["epg_list"].getCurrent()[5]
                    titlenext = self["epg_list"].getCurrent()[6]
                    descriptionnext = self["epg_list"].getCurrent()[7]

                    current_epg = self["key_epg"].getText()
                    if current_epg == (_("Next Info")):
                        nexttitle = "Next %s:  %s" % (startnexttime, titlenext)
                        self["epg_title"].setText(nexttitle)
                        self["epg_description"].setText(descriptionnext)
                        self["key_epg"].setText(_("Now Info"))
                    else:
                        nowtitle = "%s - %s  %s" % (startnowtime, startnexttime, titlenow)
                        self["epg_title"].setText(nowtitle)
                        self["epg_description"].setText(descriptionnow)
                        self["key_epg"].setText(_("Next Info"))

    def shortEPG(self):
        self.showingshortEPG = not self.showingshortEPG
        if self.showingshortEPG:
            if self["channel_list"].getCurrent():
                self["epg_list"].setList([])
                next_url = self["channel_list"].getCurrent()[3]

                if self.level == 2:
                    response = ''
                    player_api = str(glob.current_playlist["playlist_info"]["player_api"])
                    stream_id = next_url.rpartition("/")[-1].partition(".")[0]

                    shortEPGJson = []

                    url = str(player_api) + "&action=get_short_epg&stream_id=" + str(stream_id) + "&limit=50"
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

                                if "epgshift" in glob.current_playlist["player_info"]:
                                    shift = int(glob.current_playlist["player_info"]["epgshift"])

                                if listing['start'] and listing['end']:
                                    start = listing['start']
                                    end = listing['end']

                                    start_datetime = datetime.strptime(start, "%Y-%m-%d %H:%M:%S") + timedelta(hours=shift)
                                    end_datetime = datetime.strptime(end, "%Y-%m-%d %H:%M:%S") + timedelta(hours=shift)

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

            self["key_green"].setText(_('OK'))
            self["key_yellow"].setText(_('Sort: A-Z'))
            self["key_blue"].setText(_('Search'))
            self["key_epg"].setText(_('Next Info'))
        return

    def displayShortEPG(self):
        if self["epg_short_list"].getCurrent():
            title = str(self["epg_short_list"].getCurrent()[0])
            description = str(self["epg_short_list"].getCurrent()[3])
            timeall = str(self["epg_short_list"].getCurrent()[2])
            self["epg_title"].setText(timeall + " " + title)
            self["epg_description"].setText(description)
            self["key_rec"].setText(_('Record'))

    def showHiddenList(self):
        from . import hidden
        if self["channel_list"].getCurrent():
            self.session.openWithCallback(self.createSetup, hidden.XStreamity_HiddenCategories, "live", self.channelListAll)

    # record button download video file
    def downloadStream(self, limitEvent=True):
        from . import record

        currentindex = self["channel_list"].getIndex()

        begin = int(time.time())
        end = begin + 3600
        dt_now = datetime.now()
        self.date = time.time()

        # recordng name - programme title = fallback channel name
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

            # self.stopStream()
        return

    def getChannelChunk(self):

        if self["channel_list"].getCurrent():

            currentindex = self["channel_list"].getIndex()
            startindex = currentindex // self.itemsperpage * self.itemsperpage

            if startindex in self.epgchecklist:
                return
            else:
                self.epgchecklist.append(startindex)

            items = len(self.list) - startindex

            if items > self.itemsperpage:
                items = self.itemsperpage

            if items > len(self.list):
                items = len(self.list)

            self.xmlchannellist = []
            for i in range(0, items):
                index = startindex + i

                if self.list[index][7] == '':

                    channelid = self.channelList[startindex + i][6]
                    channelindex = self.channelList[startindex + i][2]
                    self.xmlchannellist.append([str(channelid), int(channelindex)])

            self.timerepg = eTimer()
            try:
                self.timerepg.callback.append(self.processXmltv)
            except:
                self.timerepg_conn = self.timerepg.timeout.connect(self.processXmltv)
            self.timerepg.start(20, True)

    def processXmltv(self):
        self.xmlfail = False
        t = threading.Thread(target=self.processXmltvEPG2, args=())
        t.daemon = True
        t.start()
        t.join()

        self.epglist = []
        self.epglist = [buildEPGListEntry(x[0], x[1], x[7], x[8], x[9], x[10], x[11], x[12]) for x in self.list]

        self["epg_list"].setList(self.epglist)

        instance = self["epg_list"].master.master.instance
        instance.setSelectionEnable(0)

        glob.originalChannelList = self.list[:]

        if self.level == 2 and not self.showingshortEPG:
            self.refreshEPGInfo()

    def processXmltvEPG2(self):
        now = datetime.now()
        nowdict = {}

        if os.path.isfile(self.epg_full_path):

            shift = 0
            if "epgshift" in glob.current_playlist["player_info"]:
                shift = int(glob.current_playlist["player_info"]["epgshift"])

            try:

                for event, elem in ET.iterparse(self.epg_full_path):
                    if elem.tag == 'programme':
                        channel = elem.get('channel')

                        if channel in nowdict:
                            if 'nextstart' in nowdict[str(channel)]:
                                elem.clear()
                                continue

                        if channel in (item for sublist in self.xmlchannellist for item in sublist):

                            try:
                                title = elem.find('title').text
                            except:
                                title = ''

                            try:
                                desc = elem.find('desc').text
                            except:
                                desc = ''

                            try:
                                start = elem.get('start')
                                startstruct = time.struct_time((int(start[0:4]), int(start[4:6]), int(start[6:8]), int(start[8:10]), int(start[10:12]), 0, -1, -1, 0))
                                startdatetime = datetime(*startstruct[:6])
                                startdatetime = startdatetime + timedelta(hours=shift)
                                startTime = startdatetime.time()

                                stop = elem.get('stop')
                                stopstruct = time.struct_time((int(stop[0:4]), int(stop[4:6]), int(stop[6:8]), int(stop[8:10]), int(stop[10:12]), 0, -1, -1, 0))
                                stopdatetime = datetime(*stopstruct[:6])
                                stopdatetime = stopdatetime + timedelta(hours=shift)
                                stopTime = stopdatetime.time()

                                if stopdatetime < now:
                                    elem.clear()
                                    continue

                                if self.isNowInTimePeriod(startdatetime, stopdatetime, now):
                                    nowdict[str(channel)] = dict([
                                        ("nowstart", str(startTime)[:5]),
                                        ("nowstop", str(stopTime)[:5]),
                                        ("nowtitle", str(title)),
                                        ("nowdesc", str(desc))
                                    ])

                                if channel in nowdict:
                                    if str(startTime)[:5] == nowdict[str(channel)]['nowstop']:
                                        nowdict[str(channel)].update({
                                            ("nextstart", str(startTime)[:5]),
                                            ("nextstop", str(stopTime)[:5]),
                                            ("nextitle", str(title)),
                                            ("nextdesc", str(desc))
                                        })
                            except:
                                elem.clear()
                                continue

                            elem.clear()

                    elif elem.tag == 'channel':
                        elem.clear()
                        continue
            except:
                print("********** xml error *********")
                return
                pass

        for item in nowdict:
            for x in self.xmlchannellist:
                if item == x[0]:
                    index = x[1]
                    if 'nowstart' in nowdict[item]:
                        self.list[index][7] = str(nowdict[item]['nowstart'])
                        self.list[index][8] = str(nowdict[item]['nowtitle'])
                        self.list[index][9] = str(nowdict[item]['nowdesc'])
                    if 'nextstart' in nowdict[item]:
                        self.list[index][10] = str(nowdict[item]['nextstart'])
                        self.list[index][11] = str(nowdict[item]['nextitle'])
                        self.list[index][12] = str(nowdict[item]['nextdesc'])

    def isNowInTimePeriod(self, startTime, endTime, nowTime):
        if startTime < endTime:
            return nowTime >= startTime and nowTime <= endTime

    def doXMLTVDownload(self):
        self["downloading"].show()
        url = str(glob.current_playlist['playlist_info']['xmltv_api']) + "&next_days=1"
        if pythonVer == 3:
            url = url.encode()

        if url.startswith("https") and sslverify:
            parsed_uri = urlparse(url)
            domain = parsed_uri.hostname
            sniFactory = SNIFactory(domain)
            downloadPage(url, self.epg_full_path, sniFactory).addCallback(self.downloadcomplete).addErrback(self.downloadFail)
        else:
            downloadPage(url, self.epg_full_path).addCallback(self.downloadcomplete).addErrback(self.downloadFail)

    def downloadFail(self, failure):
        print(("[EPG] download failed:", failure))
        if self["downloading"].instance:
            self["downloading"].hide()
        if self.session:
            self.session.open(MessageBox, _("EPG Error. Failed to download XMLTV file.\nTry Quick EPG in Edit Server"), type=MessageBox.TYPE_ERROR)

    def downloadcomplete(self, data=None):
        if self["downloading"].instance:
            self["downloading"].hide()

        self.xmltvdownloaded = True

        if os.stat(self.epg_full_path).st_size <= 100:
            if self.session:
                self.session.open(MessageBox, _("EPG Error. Failed to download XMLTV file.\nTry Quick EPG in Edit Server"), type=MessageBox.TYPE_ERROR)
        self.clear_caches()
        self.buildLists()


def buildEPGListEntry(index, title, epgnowtime, epgnowtitle, epgnowdescription, epgnexttime, epgnexttitle, epgnextdescription):
    return (title, index, epgnowtime, epgnowtitle, epgnowdescription, epgnexttime, epgnexttitle, epgnextdescription)


def buildShortEPGListEntry(date_all, time_all, title, description, index):
    return (title, date_all, time_all, description, index)


def buildCategoryList(index, title, next_url, category_id):
    png = LoadPixmap(common_path + "more.png")
    return (title, png, index, next_url, category_id)


def buildLiveStreamList(index, title, stream_id, stream_icon, epg_channel_id, added, next_url):
    png = LoadPixmap(common_path + "play.png")
    return (title, png, index, next_url, stream_id, stream_icon, epg_channel_id, added)
