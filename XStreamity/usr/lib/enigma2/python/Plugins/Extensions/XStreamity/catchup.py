#!/usr/bin/python
# -*- coding: utf-8 -*-

from . import _
from . import streamplayer
from . import xstreamity_globals as glob

from .plugin import skin_path, screenwidth, hdr, cfg, common_path, dir_tmp, downloads_json
from .xStaticText import StaticText

from Components.ActionMap import ActionMap
from Components.Sources.List import List
from Components.Pixmap import Pixmap
from Components.config import config
from datetime import datetime, timedelta
from enigma import eTimer, eServiceReference
from PIL import Image, ImageChops, ImageFile, PngImagePlugin
from requests.adapters import HTTPAdapter
from Screens.MessageBox import MessageBox
from Screens.Screen import Screen
from Tools.LoadPixmap import LoadPixmap
from twisted.internet import ssl
from twisted.internet._sslverify import ClientTLSOptions
from twisted.web.client import downloadPage

try:
    from urlparse import urlparse
except:
    from urllib.parse import urlparse


import base64
import json
import math
import os
import re
import requests
import sys
import time

try:
    pythonVer = sys.version_info.major
except:
    pythonVer = 2


class SNIFactory(ssl.ClientContextFactory):
    def __init__(self, hostname=None):
        self.hostname = hostname

    def getContext(self):
        ctx = self._contextFactory(self.method)
        if self.hostname:
            ClientTLSOptions(self.hostname, ctx)
        return ctx


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


class XStreamity_Catchup(Screen):

    def __init__(self, session):
        Screen.__init__(self, session)
        self.session = session

        skin = skin_path + 'catchup.xml'

        with open(skin, 'r') as f:
            self.skin = f.read()

        self.setup_title = (_('Catch Up TV'))
        self.main_title = (_('Catch Up TV'))

        url = str(glob.current_playlist['playlist_info']['player_api']) + "&action=get_live_categories"

        self.level = 1

        glob.nextlist = []
        glob.nextlist.append({"playlist_url": url, "index": 0, "level": self.level})

        self["channel"] = StaticText(self.main_title)

        self.list = []
        self.channelList = []
        self["channel_list"] = List(self.channelList, enableWrapAround=True)
        self.selectedlist = self["channel_list"]

        # epg variables
        self["epg_bg"] = Pixmap()
        self["epg_bg"].hide()

        self["epg_title"] = StaticText()
        self["epg_description"] = StaticText()

        self.epgshortlist = []
        self["epg_short_list"] = List(self.epgshortlist, enableWrapAround=True)
        self["epg_short_list"].onSelectionChanged.append(self.displayShortEPG)

        self["epg_picon"] = Pixmap()
        self["epg_picon"].hide()

        self["key_red"] = StaticText(_('Back'))
        self["key_green"] = StaticText(_('OK'))
        self["key_yellow"] = StaticText('')
        self["key_rec"] = StaticText('')

        self.isStream = False
        self.pin = False

        self.protocol = glob.current_playlist['playlist_info']['protocol']
        self.domain = glob.current_playlist['playlist_info']['domain']
        self.host = glob.current_playlist['playlist_info']['host']
        self.livetype = glob.current_playlist['player_info']['livetype']
        self.username = glob.current_playlist['playlist_info']['username']
        self.password = glob.current_playlist['playlist_info']['password']
        self.output = glob.current_playlist['playlist_info']['output']

        self.live_categories = str(glob.current_playlist['playlist_info']['player_api']) + "&action=get_live_categories"
        self.live_streams = str(glob.current_playlist['playlist_info']['player_api']) + "&action=get_live_streams"
        self.simpledatatable = str(glob.current_playlist['playlist_info']['player_api']) + "&action=get_simple_data_table&stream_id="

        self["page"] = StaticText('')
        self["listposition"] = StaticText('')
        self.page = 0
        self.pageall = 0
        self.position = 0
        self.positionall = 0
        self.itemsperpage = 10

        self.showingshortEPG = False

        self.listType = ''

        self["actions"] = ActionMap(["XStreamityActions"], {
            'red': self.back,
            'cancel': self.back,
            'ok': self.parentalCheck,
            'green': self.parentalCheck,
            'yellow': self.reverse,
            "left": self.pageUp,
            "right": self.pageDown,
            "up": self.goUp,
            "down": self.goDown,
            "channelUp": self.pageUp,
            "channelDown": self.pageDown,
            "0": self.reset,
            "rec": self.downloadVideo,
        }, -2)

        self.onFirstExecBegin.append(self.createSetup)
        self.onLayoutFinish.append(self.__layoutFinished)

    def __layoutFinished(self):
        self.setTitle(self.setup_title)

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

    def reset(self):
        self.selectedlist.setIndex(0)
        self.selectionChanged()

    def createSetup(self):
        self["epg_title"].setText('')
        self["epg_description"].setText('')

        self.downloadLiveStreams()

        if self.level == 1:
            url = glob.nextlist[-1]['playlist_url']
            response = glob.current_playlist['data']['live_categories']

            self.processData(response, url)
        else:
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
                    with open(levelpath, 'w') as f:
                        f.write(json.dumps(content))

                    self.processData(content, url)

            except Exception as e:
                print(e)
        else:
            with open(levelpath, "r") as f:
                content = f.read()
                self.processData(json.loads(content), url)

    def processData(self, response, url):
        self.channelList = []
        currentCategory = ''
        index = 0

        # ~~~~~~~~~~~~~~~ level 1 ~~~~~~~~~~~~~~~ #
        if "&action=get_live_categories" in url:
            self.isStream = False
            self.listType = "category"
            currentCategory = glob.current_playlist['data']['live_categories']

            nextAction = "&action=get_live_streams&category_id="

        # ~~~~~~~~~~~~~~~ level 2 ~~~~~~~~~~~~~~~ #
        elif "&action=get_live_streams" in url:
            currentCategory = response
            nextAction = ''
            self.isStream = True
            self.listType = "live_streams"

        self.list = []

        if self.listType == "category":
            for item in currentCategory:

                for archive in self.live_list_archive:
                    category_id = ''
                    category_name = ''
                    if "category_id" in item:
                        if item['category_id'] == archive['category_id']:
                            if 'category_name' in item:
                                category_name = item['category_name']
                            category_id = item['category_id']
                            next_url = "%s%s%s" % (glob.current_playlist['playlist_info']['player_api'], nextAction, category_id)
                            if category_id not in glob.current_playlist['player_info']['livehidden']:
                                self.list.append([index, str(category_name), str(next_url), str(category_id)])
                            index += 1
                            break
            self.buildLists()

        elif self.listType == "live_streams":
            for item in currentCategory:
                name = ''
                stream_id = ''
                stream_icon = ''
                epg_channel_id = ''
                added = ''

                if 'tv_archive' in item and 'tv_archive_duration' in item:
                    if item['tv_archive'] == 1 and item['tv_archive_duration'] != "0":

                        if 'name' in item and item['name']:
                            name = item['name']
                        if 'stream_id' in item and item['stream_id']:
                            stream_id = item['stream_id']
                        if 'stream_icon' in item and item['stream_icon']:
                            if item['stream_icon'].startswith("http"):
                                stream_icon = item['stream_icon']
                        if 'epg_channel_id' in item and item['epg_channel_id']:
                            epg_channel_id = item['epg_channel_id']

                            if epg_channel_id and "&" in epg_channel_id:
                                epg_channel_id = epg_channel_id.replace("&", "&amp;")
                        if 'added' in item and item['added']:
                            added = item['added']
                        epgnowtitle = epgnowtime = epgnowdescription = epgnexttitle = epgnexttime = epgnextdescription = ''

                        next_url = "%s/live/%s/%s/%s.%s" % (self.host, self.username, self.password, stream_id, self.output)
                        self.list.append([
                            index, str(name), str(stream_id), str(stream_icon), str(epg_channel_id), str(added), str(next_url),
                            epgnowtime, epgnowtitle, epgnowdescription, epgnexttime, epgnexttitle, epgnextdescription
                        ])

                        index += 1

            self.buildLists()

        if self["channel_list"].getCurrent():
            if glob.nextlist[-1]['index'] != 0:
                self["channel_list"].setIndex(glob.nextlist[-1]['index'])

            if not self.isStream:
                self.hideEPG()
                pass

    def buildLists(self):
        if self.listType == "category":
            self.channelList = []
            self.channelList = [buildCategoryList(x[0], x[1], x[2], x[3]) for x in self.list]
            self["channel_list"].setList(self.channelList)
            self.selectionChanged()

        elif self.listType == "live_streams":
            self.channelList = []
            self.channelList = [buildLiveStreamList(x[0], x[1], x[2], x[3], x[4], x[5], x[6]) for x in self.list]
            self["channel_list"].setList(self.channelList)
            self.selectionChanged()

    def downloadLiveStreams(self):
        url = self.live_streams

        self.streams = ''
        self.live_list_archive = []

        adapter = HTTPAdapter(max_retries=0)
        http = requests.Session()
        http.mount("http://", adapter)

        try:
            r = http.get(url, headers=hdr, stream=True, timeout=10, verify=False)
            r.raise_for_status()
            if r.status_code == requests.codes.ok:
                self.streams = r.json()

        except Exception as e:
            print(e)

        if self.streams:
            for item in self.streams:
                if "tv_archive" and "tv_archive_duration" in item:
                    if int(item["tv_archive"]) == 1 and int(item["tv_archive_duration"]) > 0:
                        self.live_list_archive.append(item)
        else:
            self.close()

    def back(self):
        self.hideEPG()
        self["key_rec"].setText("")

        if self.selectedlist == self["epg_short_list"]:

            instance = self["epg_short_list"].master.master.instance
            instance.setSelectionEnable(0)
            self.catchup_all = []
            self['epg_short_list'].setList(self.catchup_all)

            instance = self["channel_list"].master.master.instance
            instance.setSelectionEnable(1)
            self.selectedlist = self["channel_list"]
        else:

            del glob.nextlist[-1]

            if len(glob.nextlist) == 0:
                self.close()
            else:

                self.stopStream()

                levelpath = str(dir_tmp) + 'level' + str(self.level) + '.xml'
                try:
                    os.remove(levelpath)
                except:
                    pass
                self.level -= 1
                self.createSetup()

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
        self.pin = True
        if self.level == 1:

            if cfg.parental.getValue() is True and int(time.time()) - int(glob.pintime) > 900:
                adult = _("all"), "all", "+18", "adult", "18+", "18 rated", "xxx", "sex", "porn", "pink", "blue"
                if any(s in str(self["channel_list"].getCurrent()[0]).lower() and str(self["channel_list"].getCurrent()[0]).lower() != "Allgemeines" for s in adult):
                    from Screens.InputBox import PinInput
                    self.session.openWithCallback(self.pinEntered, PinInput, pinList=[config.ParentalControl.setuppin.value], triesEntry=config.ParentalControl.retries.servicepin, title=_("Please enter the parental control pin code"), windowTitle=_("Enter pin code"))
                else:
                    self.next()
            else:
                self.next()
        else:
            self.next()

    def next(self):
        if self["channel_list"].getCurrent():
            self.currentindex = self["channel_list"].getCurrent()[2]
            next_url = self["channel_list"].getCurrent()[3]

            glob.nextlist[-1]['index'] = self.currentindex
            glob.currentchannellist = self.channelList
            glob.currentchannellistindex = self.currentindex

            if self.level == 1:
                glob.nextlist.append({"playlist_url": next_url, "index": 0})
                self["epg_picon"].hide()
                self.level += 1
                self["channel_list"].setIndex(0)
                self.createSetup()
            else:

                self["epg_picon"].show()
                if self.selectedlist == self["channel_list"]:
                    self.shortEPG()
                else:
                    self.playCatchup()

    def shortEPG(self):
        if self["channel_list"].getCurrent():
            next_url = self["channel_list"].getCurrent()[3]

            if next_url != 'None':
                if "/live/" in next_url:
                    stream_id = next_url.rpartition("/")[-1].partition(".")[0]
                    response = ''
                    shortEPGJson = []

                    url = str(self.simpledatatable) + str(stream_id)

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

                    except Exception as e:
                        print(e)
                        response = ''

                    if response != '':
                        shortEPGJson = response
                        index = 0
                        self.epgshortlist = []
                        duplicatecheck = []

                        if "epg_listings" in shortEPGJson:
                            if shortEPGJson["epg_listings"]:
                                for listing in shortEPGJson["epg_listings"]:
                                    if 'has_archive' in listing and listing['has_archive'] == 1:

                                        epg_title = ""
                                        epg_description = ""
                                        epg_date_all = ""
                                        epg_time_all = ""
                                        start = ""
                                        end = ""

                                        catchupstart = int(cfg.catchupstart.getValue())
                                        catchupend = int(cfg.catchupend.getValue())

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

                                            start_datetime_original = datetime.strptime(start, "%Y-%m-%d %H:%M:%S")
                                            start_datetime_offset = datetime.strptime(start, "%Y-%m-%d %H:%M:%S") + timedelta(hours=shift)
                                            start_datetime_margin = datetime.strptime(start, "%Y-%m-%d %H:%M:%S") + timedelta(hours=shift) - timedelta(minutes=catchupstart)

                                            try:
                                                # end_datetime_original = datetime.strptime(end, "%Y-%m-%d %H:%M:%S")
                                                end_datetime_offset = datetime.strptime(end, "%Y-%m-%d %H:%M:%S") + timedelta(hours=shift)
                                                end_datetime_margin = datetime.strptime(end, "%Y-%m-%d %H:%M:%S") + timedelta(hours=shift) + timedelta(minutes=catchupend)
                                            except:
                                                try:
                                                    end = listing['stop']
                                                    # end_datetime_original = datetime.strptime(end, "%Y-%m-%d %H:%M:%S")
                                                    end_datetime_offset = datetime.strptime(end, "%Y-%m-%d %H:%M:%S") + timedelta(hours=shift)
                                                    end_datetime_margin = datetime.strptime(end, "%Y-%m-%d %H:%M:%S") + timedelta(hours=shift) + timedelta(minutes=catchupend)
                                                except:
                                                    return

                                            epg_date_all = start_datetime_offset.strftime('%a %d/%m')
                                            epg_time_all = str(start_datetime_offset.strftime('%H:%M')) + " - " + str(end_datetime_offset.strftime('%H:%M'))

                                        epg_duration = int((end_datetime_margin - start_datetime_margin).total_seconds() / 60.0)

                                        url_datestring = str(start_datetime_original.strftime('%Y-%m-%d:%H-%M'))

                                        if [epg_date_all, epg_time_all] not in duplicatecheck:
                                            duplicatecheck.append([epg_date_all, epg_time_all])
                                            self.epgshortlist.append(buildShortEPGListEntry(str(epg_date_all), str(epg_time_all), str(epg_title), str(epg_description), str(url_datestring), str(epg_duration), index))

                                            index += 1

                                self.epgshortlist.reverse()
                                self["epg_short_list"].setList(self.epgshortlist)
                                duplicatecheck = []

                                if self["epg_short_list"].getCurrent():
                                    glob.catchupdata = [str(self["epg_short_list"].getCurrent()[0]), str(self["epg_short_list"].getCurrent()[3])]
                                instance = self["epg_short_list"].master.master.instance
                                instance.setSelectionEnable(1)

                                self.selectedlist = self["epg_short_list"]
                                self["key_rec"].setText(_("Download"))
                                self.displayShortEPG()
                            else:
                                self.session.open(MessageBox, _("Catchup currently not available. Missing EPG data"), type=MessageBox.TYPE_INFO, timeout=5)
        return

    def displayShortEPG(self):
        if self["epg_short_list"].getCurrent():
            title = str(self["epg_short_list"].getCurrent()[0])
            description = str(self["epg_short_list"].getCurrent()[3])
            timeall = str(self["epg_short_list"].getCurrent()[2])
            self["epg_title"].setText(timeall + " " + title)
            self["epg_description"].setText(description)
            self.showEPGElements()

    def playCatchup(self):
        next_url = self["channel_list"].getCurrent()[3]
        stream = next_url.rpartition('/')[-1]

        date = str(self["epg_short_list"].getCurrent()[4])

        duration = str(self["epg_short_list"].getCurrent()[5])

        playurl = "%s/timeshift/%s/%s/%s/%s/%s" % (self.host, self.username, self.password, duration, date, stream)

        if next_url != 'None' and "/live/" in next_url:
            streamtype = "4097"
            self.reference = eServiceReference(int(streamtype), 0, str(playurl))
            glob.catchupdata = [str(self["epg_short_list"].getCurrent()[0]), str(self["epg_short_list"].getCurrent()[3])]
            self.session.openWithCallback(self.createSetup, streamplayer.XStreamity_CatchupPlayer, str(playurl), str(streamtype))
        else:
            from Screens.MessageBox import MessageBox
            self.session.open(MessageBox, _('Catchup error. No data for this slot'), MessageBox.TYPE_WARNING, timeout=5)

    def stopStream(self):
        if glob.currentPlayingServiceRefString != glob.newPlayingServiceRefString:
            if glob.newPlayingServiceRefString != '':
                if self.session.nav.getCurrentlyPlayingServiceReference():
                    self.session.nav.stopService()
                self.session.nav.playService(eServiceReference(glob.currentPlayingServiceRefString))

    def selectionChanged(self):
        if self["channel_list"].getCurrent():
            channeltitle = self["channel_list"].getCurrent()[0]
            currentindex = self["channel_list"].getIndex()

            self.position = currentindex + 1
            self.positionall = len(self.channelList)
            self.page = int(math.ceil(float(self.position) / float(self.itemsperpage)))
            self.pageall = int(math.ceil(float(self.positionall) / float(self.itemsperpage)))

            self["page"].setText(_('Page: ') + str(self.page) + _(" of ") + str(self.pageall))
            self["listposition"].setText(str(self.position) + "/" + str(self.positionall))

            self["channel"].setText(self.main_title + ": " + str(channeltitle))
            if self.level >= 2:
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

            self["page"].setText(_('Page: ') + str(self.page) + _(" of ") + str(self.pageall))
            self["listposition"].setText(str(self.position) + "/" + str(self.positionall))

    def downloadImage(self):
        if self["channel_list"].getCurrent():
            try:
                os.remove(str(dir_tmp) + 'original.png')
                os.remove(str(dir_tmp) + 'temp.png')
            except:
                pass

            try:
                desc_image = self["channel_list"].getCurrent()[5]
            except:
                desc_image = ''

            if desc_image and desc_image != "n/A":
                temp = dir_tmp + 'temp.png'
                try:
                    parsed = urlparse(desc_image)
                    domain = parsed.hostname
                    scheme = parsed.scheme

                    if pythonVer == 3:
                        desc_image = desc_image.encode()

                    if scheme == "https":
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
        if data:
            print(data)
        if self["epg_picon"].instance:
            self["epg_picon"].instance.setPixmapFromFile(common_path + "picon.png")

    def resizeImage(self, data=None):
        # print("*** resizeImage ***")
        if self["channel_list"].getCurrent():
            original = str(dir_tmp) + 'temp.png'

            size = [147, 88]
            if screenwidth.width() > 1280:
                size = [220, 130]

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

    def showEPGElements(self):
        self["epg_picon"].show()
        self["epg_bg"].show()
        self["key_yellow"].setText(_('Reverse'))

    def hideEPG(self):
        self["epg_short_list"].setList([])
        self["epg_picon"].hide()
        self["epg_bg"].hide()
        self["epg_title"].setText('')
        self["epg_description"].setText('')
        self["key_yellow"].setText('')

    # record button download video file

    def downloadVideo(self):
        # load x-downloadlist.json file
        if self["key_rec"].getText() != '':

            if self["channel_list"].getCurrent():

                next_url = self["channel_list"].getCurrent()[3]
                stream = next_url.rpartition('/')[-1]
                date = str(self["epg_short_list"].getCurrent()[4])
                duration = str(self["epg_short_list"].getCurrent()[5])
                playurl = "%s/timeshift/%s/%s/%s/%s/%s" % (self.host, self.username, self.password, duration, date, stream)

                date_all = str(self["epg_short_list"].getCurrent()[1]).strip()
                time_all = str(self["epg_short_list"].getCurrent()[2]).strip()
                time_start = time_all.partition(" - ")[0].strip()
                current_year = int(datetime.now().year)
                date = str(datetime.strptime(str(current_year) + str(date_all) + str(time_start), "%Y%a %d/%m%H:%M")).replace("-", "").replace(":", "")[:-2]

                otitle = str(self["epg_short_list"].getCurrent()[0])
                channel = str(self["channel_list"].getCurrent()[0])
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
                    downloads_all.append([_("Catch-up"), title, playurl, _("Not Started"), 0, 0])

                    with open(downloads_json, 'w') as f:
                        json.dump(downloads_all, f)

                    self.session.open(MessageBox, _(title) + "\n\n" + _("Added to download manager"), MessageBox.TYPE_INFO, timeout=5)
                else:
                    self.session.open(MessageBox, _(title) + "\n\n" + _("Already added to download manager"), MessageBox.TYPE_ERROR, timeout=5)

    def reverse(self):
        self.epgshortlist.reverse()
        self["epg_short_list"].setList(self.epgshortlist)


def buildCategoryList(index, title, next_url, category_id):
    png = LoadPixmap(common_path + "more.png")
    return (title, png, index, next_url, category_id)


def buildLiveStreamList(index, title, stream_id, stream_icon, epg_channel_id, added, next_url):
    png = LoadPixmap(common_path + "more.png")
    return (title, png, index, next_url, stream_id, stream_icon, epg_channel_id, added)


def buildShortEPGListEntry(date_all, time_all, title, description, start, duration, index):
    return (title, date_all, time_all, description, start, duration, index)
