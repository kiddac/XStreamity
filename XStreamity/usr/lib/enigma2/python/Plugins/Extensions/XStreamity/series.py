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
from Components.config import config, ConfigClock, NoSave, ConfigText
from Components.Pixmap import Pixmap
from Components.ProgressBar import ProgressBar
from Components.Sources.List import List
from datetime import datetime, timedelta, date
from enigma import eTimer, eServiceReference, ePicLoad
from PIL import Image
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
        self.main_title = (_("Vod"))

        nexturl = str(glob.current_playlist['playlist_info']['player_api']) + "&action=get_vod_categories"

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

        self.sorted = False
        self.isStream = False
        self.filtered = False
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

    def check(self, token):
        result = base64.b64decode(token)
        result = zlib.decompress(base64.b64decode(result))
        result = base64.b64decode(result).decode()
        return result

    def createSetup(self):
        # resets
        self.sorted = False

        if self.filtered:
            self.resetSearch()

        self["key_rec"].setText('')

        if self.level == 1:  # category list
            self["key_menu"].setText(_("Hide/Show"))
            self["key_epg"].setText('')
            url = glob.nextlist[-1]['playlist_url']

            # load category list from stored list
            response = glob.current_playlist['data']['series_categories']
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

    # code for natural sorting of numbers in string
    def atoi(self, text):
        return int(text) if text.isdigit() else text

    def natural_keys(self, text):
        return [self.atoi(c) for c in re.split(r'(\d+)', text[1])]

    def processData(self, response, url):
        self.channelList = []
        currentCategoryList = ''
        index = 0
        indexAll = 0

        self.list = []
        self.listAll = []

        if self.level == 1:  # categories
            currentCategoryList = glob.current_playlist['data']['series_categories']
            hidden = False

            # add an ALL Category
            next_url = str(glob.current_playlist['playlist_info']['player_api']) + "&action=get_series&category_id=0"

            # Dont add if not required
            if "0" in glob.current_playlist['player_info']['serieshidden']:
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

                next_url = str(glob.current_playlist['playlist_info']['player_api']) + "&action=get_series&category_id=" + str(category_id)

                if category_id in glob.current_playlist['player_info']['serieshidden']:
                    hidden = True

                if hidden is False:
                    # not hidden list
                    self.list.append([index, str(category_name), str(next_url), str(category_id)])
                    index += 1

                # full list
                self.listAll.append([indexAll, str(category_name), str(next_url), str(category_id)])
                indexAll += 1

        elif self.level == 2:  # titles
            currentCategory = response
            for item in currentCategory:

                name = ''
                series_id = ''
                cover = ''
                plot = ''
                cast = ''
                director = ''
                genre = ''
                releaseDate = ''
                rating = ''
                last_modified = ''

                if 'name' in item:
                    name = item['name']

                if 'series_id' in item:
                    series_id = item['series_id']

                if 'cover' in item:
                    cover = item['cover']

                if 'plot' in item:
                    plot = item['plot']

                if 'cast' in item:
                    cast = item['cast']

                if 'director' in item:
                    director = item['director']

                if 'genre' in item:
                    genre = item['genre']

                if 'releaseDate' in item:
                    releaseDate = item['releaseDate']

                if 'rating' in item:
                    rating = item['rating']

                if 'last_modified' in item:
                    last_modified = item['last_modified']

                if cover:
                    if cover.startswith("https://image.tmdb.org/t/p/") or cover.startswith("http://image.tmdb.org/t/p/"):
                        dimensions = cover.partition("/p/")[2].partition("/")[0]
                        if screenwidth.width() <= 1280:
                            cover = cover.replace(dimensions, "w300")
                        else:
                            cover = cover.replace(dimensions, "w400")
                next_url = str(glob.current_playlist['playlist_info']['player_api']) + "&action=get_series_info&series_id=" + str(series_id)

                self.list.append([index, str(name), str(series_id), str(cover), str(plot), str(cast), str(director), str(genre), str(releaseDate), str(rating), str(last_modified), str(next_url)])

                index += 1

        elif self.level == 3:  # seasons
            currentCategory = response
            name = ''
            cover1 = ''
            overview1 = ''
            cast1 = ''
            director1 = ''
            genre1 = ''
            airdate1 = ''
            rating1 = ''

            if "info" in currentCategory:
                if 'name' in currentCategory['info']:
                    name = currentCategory['info']['name']

                if 'cover' in currentCategory['info']:
                    cover1 = currentCategory['info']['cover']

                if 'plot' in currentCategory['info']:
                    overview1 = currentCategory['info']['plot']

                if 'cast' in currentCategory['info']:
                    cast1 = currentCategory['info']['cast']

                if 'director' in currentCategory['info']:
                    director1 = currentCategory['info']['director']

                if 'genre' in currentCategory['info']:
                    genre1 = currentCategory['info']['genre']

                if 'releaseDate' in currentCategory['info']:
                    airdate1 = currentCategory['info']['releaseDate']

                if 'rating' in currentCategory['info']:
                    rating1 = currentCategory['info']['rating']

            if "episodes" in currentCategory:
                if currentCategory["episodes"]:

                    seasonlist = []
                    isdict = True
                    try:
                        seasonlist = list(currentCategory['episodes'].keys())

                    except:
                        isdict = False
                        x = 0
                        for item in currentCategory["episodes"]:
                            seasonlist.append(x)
                            x += 1

                    if seasonlist:
                        for season in seasonlist:

                            name = _("Season ") + str(season)
                            cover = cover1
                            overview = overview1
                            cast = cast1
                            director = director1
                            genre = genre1
                            airdate = airdate1
                            rating = rating1

                            if isdict:
                                season_number = currentCategory["episodes"][str(season)][0]['season']
                            else:
                                season_number = currentCategory["episodes"][season][0]['season']

                            series_id = 0

                            if "seasons" in currentCategory:
                                if currentCategory['seasons']:
                                    for item in currentCategory['seasons']:
                                        if 'season_number' in item:
                                            if item['season_number'] == season_number:

                                                if "airdate" in item:
                                                    if item['airdate']:
                                                        airdate = item['airdate']
                                                    else:
                                                        airdate = airdate1

                                                if "name" in item:
                                                    if item['name']:
                                                        name = item['name']

                                                if "overview" in item:
                                                    if item['overview']:
                                                        overview = item['overview']
                                                    else:
                                                        overview = overview1

                                                if "cover_big" in item:
                                                    if item['cover_big']:
                                                        cover = item['cover_big']
                                                    else:
                                                        cover = cover1

                                                elif "cover" in item:
                                                    if item['cover']:
                                                        cover = item['cover']
                                                    else:
                                                        cover = cover1
                                                else:
                                                    cover = cover1
                            if cover:
                                if cover.startswith("https://image.tmdb.org/t/p/") or cover.startswith("http://image.tmdb.org/t/p/"):
                                    dimensions = cover.partition("/p/")[2].partition("/")[0]
                                    if screenwidth.width() <= 1280:
                                        cover = cover.replace(dimensions, "w300")
                                    else:
                                        cover = cover.replace(dimensions, "w400")

                            next_url = self.seasons_url
                            self.list.append([index, str(name), str(series_id), str(cover), str(overview), str(cast), str(director), str(genre), str(airdate), str(rating), season_number, str(next_url)])

                self.list.sort(key=self.natural_keys)

        elif self.level == 4:  # episodes
            currentCategory = response

            shorttitle1 = ''
            cover1 = ''
            plot1 = ''
            cast1 = ''
            director1 = ''
            genre1 = ''
            releasedate1 = ''
            rating1 = ''

            if "info" in currentCategory:

                if 'name' in currentCategory['info']:
                    shorttitle1 = currentCategory['info']['name']

                if 'cover' in currentCategory['info']:
                    cover1 = currentCategory['info']['cover']

                if 'plot' in currentCategory['info']:
                    plot1 = currentCategory['info']['plot']

                if 'cast' in currentCategory['info']:
                    cast1 = currentCategory['info']['cast']

                if 'director' in currentCategory['info']:
                    director1 = currentCategory['info']['director']

                if 'genre' in currentCategory['info']:
                    genre1 = currentCategory['info']['genre']

                if 'releaseDate' in currentCategory['info']:
                    releasedate1 = currentCategory['info']['releaseDate']

                if 'rating' in currentCategory['info']:
                    rating1 = currentCategory['info']['rating']

            if "episodes" in currentCategory:
                if currentCategory["episodes"]:
                    season_number = str(self.season_number)

                    try:
                        seasonlist = list(currentCategory['episodes'].keys())
                    except:
                        season_number = int(self.season_number)

                    for item in currentCategory['episodes'][season_number]:
                        shorttitle = shorttitle1
                        title = ''
                        cover = cover1
                        plot = plot1
                        cast = cast1
                        director = director1
                        genre = genre1
                        releasedate = releasedate1
                        rating = rating1
                        stream_id = ''
                        container_extension = 'mp4'
                        tmdb_id = ''
                        duration = ''

                        if 'id' in item:
                            stream_id = item['id']

                        if 'title' in item:
                            title = item['title'].replace(str(shorttitle) + " - ", "")

                        if 'container_extension' in item:
                            container_extension = item['container_extension']

                        if 'tmdb_id' in item:
                            tmdb_id = item['info']['tmdb_id']

                        if 'releasedate' in item['info']:
                            releasedate = item['info']['releasedate']

                        if 'plot' in item['info']:
                            plot = item['info']['plot']

                        if 'duration' in item['info']:
                            duration = item['info']['duration']

                        if 'rating' in item['info']:
                            rating = item['info']['rating']

                        if "seasons" in currentCategory:
                            if currentCategory['seasons']:
                                for season in currentCategory['seasons']:
                                    if int(season['season_number']) == int(season_number):
                                        if "cover" in season:
                                            cover = season['cover']

                                        if "cover_big" in season:
                                            cover = season['cover_big']
                                        break

                        if cover:
                            if cover.startswith("https://image.tmdb.org/t/p/") or cover.startswith("http://image.tmdb.org/t/p/"):
                                dimensions = cover.partition("/p/")[2].partition("/")[0]
                                if screenwidth.width() <= 1280:
                                    cover = cover.replace(dimensions, "w300")
                                else:
                                    cover = cover.replace(dimensions, "w400")

                        next_url = "%s/series/%s/%s/%s.%s" % (self.host, self.username, self.password, stream_id, container_extension)
                        self.list.append([index, str(title), str(stream_id), str(cover), str(plot), str(cast), str(director), str(genre), str(releasedate), str(rating), str(duration), str(container_extension), str(tmdb_id), str(next_url), str(shorttitle)])
                        index += 1

        glob.originalChannelList = self.list[:]
        self.buildLists()

    def buildLists(self):
        if self.list:
            if self.level == 1:
                self.channelList = []
                self.channelList = [buildCategoryList(x[0], x[1], x[2], x[3]) for x in self.list]

                self.channelListAll = []
                self.channelListAll = [buildCategoryList(x[0], x[1], x[2], x[3]) for x in self.listAll]

            elif self.level == 2:
                self.channelList = []
                self.channelList = [buildSeriesTitlesList(x[0], x[1], x[2], x[3], x[4], x[5], x[6], x[7], x[8], x[9], x[10], x[11]) for x in self.list]

            elif self.level == 3:
                self.channelList = []
                self.channelList = [buildSeriesSeasonsList(x[0], x[1], x[2], x[3], x[4], x[5], x[6], x[7], x[8], x[9], x[10], x[11]) for x in self.list]

            elif self.level == 4:
                self.channelList = []
                self.channelList = [buildSeriesEpisodesList(x[0], x[1], x[2], x[3], x[4], x[5], x[6], x[7], x[8], x[9], x[10], x[11], x[12], x[13], x[14]) for x in self.list]

            self["channel_list"].setList(self.channelList)

        if self["channel_list"].getCurrent():
            next_url = self["channel_list"].getCurrent()[3]

            if glob.nextlist[-1]['index'] != 0:
                self["channel_list"].setIndex(glob.nextlist[-1]['index'])

                channeltitle = self["channel_list"].getCurrent()[0]
                self["channel"].setText(self.main_title + ": " + str(channeltitle))

            if self.level != 1:
                self.showVodElements()
            else:
                self.hideVod()

        self.selectionChanged()

    def hideVod(self):
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

    def showVodElements(self):
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

            if self.level != 1:
                self.timerSeries = eTimer()
                try:
                    self.timerSeries.callback.append(self.displaySeriesData)
                except:
                    self.timerSeries_conn = self.timerSeries.timeout.connect(self.displaySeriesData)
                self.timerSeries.start(50, True)

            if self.level == 4:
                self["key_rec"].setText(_("Download"))

    def displaySeriesData(self):
        if self.level == 2 or self.level == 3:
            self.downloadImage()
        if self.level == 2:
            if self["channel_list"].getCurrent():
                current = self["channel_list"].getCurrent()
                self["vod_title"].setText(current[0])
                self["vod_description"].setText(current[6])
                self["vod_genre"].setText(current[9])
                self["vod_rating"].setText(current[11])
                try:
                    self["vod_release_date"].setText(datetime.strptime(current[10], "%Y-%m-%d").strftime("%d-%m-%Y"))
                except:
                    self["vod_release_date"].setText('')
                    pass
                self["vod_director"].setText(current[8])
                self["vod_cast"].setText(current[7])

        elif self.level == 3:
            if self["channel_list"].getCurrent():
                current = self["channel_list"].getCurrent()
                self["vod_title"].setText(current[0])
                self["vod_description"].setText(current[6])
                self["vod_genre"].setText(current[9])
                self["vod_rating"].setText(current[11])

                try:
                    self["vod_release_date"].setText(datetime.strptime(current[10], "%Y-%m-%d").strftime("%d-%m-%Y"))
                except:
                    self["vod_release_date"].setText('')
                    pass
                self["vod_director"].setText(current[8])
                self["vod_cast"].setText(current[7])

        elif self.level == 4:
            if self["channel_list"].getCurrent():
                current = self["channel_list"].getCurrent()

                self["vod_title"].setText(current[0])
                self["vod_description"].setText(current[6])
                self["vod_genre"].setText(current[9])
                self["vod_rating"].setText(current[11])

                try:
                    self["vod_release_date"].setText(datetime.strptime(current[10], "%Y-%m-%d").strftime("%d-%m-%Y"))
                except:
                    self["vod_release_date"].setText('')
                    pass

                self["vod_director"].setText(current[8])
                self["vod_cast"].setText(current[7])
                self["vod_duration"].setText(current[12])
                self["vod_video_type"].setText(current[13])

    def downloadImage(self):
        if self["channel_list"].getCurrent():

            try:
                os.remove(str(dir_tmp) + 'original.jpg')
            except:
                pass

            size = [267, 400]
            if screenwidth.width() > 1280:
                size = [400, 600]

            desc_image = ''

            try:
                desc_image = self["channel_list"].getCurrent()[5]
            except Exception as e:
                print(("* image error ** %s" % e))

            if desc_image and desc_image != "n/A":
                original = str(dir_tmp) + 'original.jpg'

                if pythonVer == 3:
                    desc_image = desc_image.encode()

                if desc_image.startswith("https") and sslverify:
                    parsed_uri = urlparse(desc_image)
                    domain = parsed_uri.hostname
                    sniFactory = SNIFactory(domain)
                    downloadPage(desc_image, original, sniFactory, timeout=5).addCallback(self.resizeImage, size).addErrback(self.loadDefaultImage)
                else:
                    downloadPage(desc_image, original, timeout=5).addCallback(self.resizeImage, size).addErrback(self.loadDefaultImage)

    def loadDefaultImage(self):
        if self["vod_cover"].instance:
            self["vod_cover"].instance.setPixmapFromFile(skin_path + "images/vod_cover.png")

    def resizeImage(self, data, size):
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
        ptr = self.PicLoad.getData()
        if ptr is not None:
            self["vod_cover"].instance.setPixmap(ptr)
            self["vod_cover"].instance.show()

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
                    self.list.sort(key=lambda x: x[10], reverse=True)
                self.sorted = True

                self["key_yellow"].setText(_('Sort: Original'))

            elif current_sort == (_('Sort: Original')):
                self["key_yellow"].setText(_('Sort: A-Z'))
                self.list = glob.originalChannelList
                self.sorted = False
                self.createSetup()

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

            exitbutton = False
            callingfunction = sys._getframe().f_back.f_code.co_name
            if callingfunction == "playStream":
                exitbutton = True

            if exitbutton:
                if self.tempstream_url:
                    next_url = str(self.tempstream_url)

            if self.level != 4:
                if "&action=get_series_info" in next_url:
                    if self.level == 2:
                        self.seasons_url = self["channel_list"].getCurrent()[3]
                    if self.level == 3:
                        self.season_number = self["channel_list"].getCurrent()[12]

                glob.nextlist.append({"playlist_url": next_url, "index": 0})
                self.level += 1
                self["channel_list"].setIndex(0)
                self["category_actions"].setEnabled(False)
                self["channel_actions"].setEnabled(True)
                self.createSetup()

            elif self.level == 4:
                streamtype = glob.current_playlist["player_info"]["vodtype"]
                self.reference = eServiceReference(int(streamtype), 0, next_url)
                self.session.openWithCallback(self.setIndex, streamplayer.XStreamity_VodPlayer, str(next_url), str(streamtype))

    def setIndex(self):
        self["channel_list"].setIndex(glob.currentchannelistindex)

    def back(self):
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

    def showHiddenList(self):
        if self["key_menu"].getText() != '':
            from . import hidden
            if self["channel_list"].getCurrent():
                self.session.openWithCallback(self.createSetup, hidden.XStreamity_HiddenCategories, "series", self.channelListAll)

    # record button download video file
    def downloadVideo(self):
        if self.level == 4:
            from Screens.MessageBox import MessageBox
            if self["channel_list"].getCurrent():
                stream_url = self["channel_list"].getCurrent()[3]
                extension = str(os.path.splitext(stream_url)[-1])
                title = self["channel_list"].getCurrent()[0]
                if "/series/" in stream_url:
                    title = str(self["channel_list"].getCurrent()[15]) + " " + str(self["channel_list"].getCurrent()[0])

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
                    print(("download series %s" % e))

                except:
                    self.session.open(MessageBox, _('Download Failed\n\n' + title + "\n\n" + str(cfg.downloadlocation.getValue()) + str(fileTitle) + str(extension)), MessageBox.TYPE_WARNING)

    def printError(self, failure):
        print(("********* error ******** %s" % failure))
        pass


def buildCategoryList(index, title, next_url, category_id):
    png = LoadPixmap(common_path + "more.png")
    return (title, png, index, next_url, category_id)


def buildSeriesTitlesList(index, title, series_id, cover, plot, cast, director, genre, releaseDate, rating, lastmodified, next_url):
    png = LoadPixmap(common_path + "more.png")
    return (title, png, index, next_url, series_id, cover, plot, cast, director, genre, releaseDate, rating, lastmodified)


def buildSeriesSeasonsList(index, title, series_id, cover, plot, cast, director, genre, airDate, rating, season_number, next_url):
    png = LoadPixmap(common_path + "more.png")
    return (title, png, index, next_url, series_id, cover, plot, cast, director, genre, airDate, rating, season_number)


def buildSeriesEpisodesList(index, title, series_id, cover, plot, cast, director, genre, releaseDate, rating, duration, container_extension, tmdb_id, next_url, shorttitle):
    png = LoadPixmap(common_path + "play.png")
    return (title, png, index, next_url, series_id, cover, plot, cast, director, genre, releaseDate, rating, duration, container_extension, tmdb_id, shorttitle)
