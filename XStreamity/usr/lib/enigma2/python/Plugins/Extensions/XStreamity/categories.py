#!/usr/bin/python
# -*- coding: utf-8 -*-

# for localized messages
from . import _

from collections import OrderedDict

from Components.ActionMap import ActionMap
from Components.AVSwitch import AVSwitch
from Components.config import config, ConfigClock, NoSave, ConfigText
from Components.Pixmap import Pixmap
from Components.ProgressBar import ProgressBar
from Components.Sources.List import List
from datetime import datetime, timedelta, date
from enigma import eTimer, eServiceReference, ePicLoad
from plugin import skin_path, screenwidth, hdr, cfg, common_path, dir_tmp
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

from xStaticText import StaticText
from Screens.MessageBox import MessageBox

import xml.etree.cElementTree as ET

import base64
import re
import json
import math
import os
import requests
import streamplayer
import imagedownload
import sys
import time
import xstreamity_globals as glob
import threading

from os import system


class XStreamity_Categories(Screen):

    def __init__(self, session, category):
        Screen.__init__(self, session)
        self.session = session

        self.searchString = ''

        skin = skin_path + 'categories.xml'
        if os.path.exists('/var/lib/dpkg/status'):
            skin = skin_path + 'DreamOS/categories.xml'

        with open(skin, 'r') as f:
            self.skin = f.read()

        self.setup_title = (_('Categories'))

        if category == 0:
            self.main_title = "Live Streams"
            url = str(glob.current_playlist['playlist_info']['player_api']) + "&action=get_live_categories"

        if category == 1:
            self.main_title = "Vod"
            url = str(glob.current_playlist['playlist_info']['player_api']) + "&action=get_vod_categories"
        if category == 2:
            self.main_title = "TV Series"
            url = str(glob.current_playlist['playlist_info']['player_api']) + "&action=get_series_categories"

        self.level = 1
        self.category = category
        self.currentAction = "categories"

        glob.nextlist = []
        glob.nextlist.append({"playlist_url": url, "index": 0, "level": self.level})

        self["channel"] = StaticText(self.main_title)

        self.list = []
        self.channelList = []
        self["channel_list"] = List(self.channelList, enableWrapAround=True)

        self.selectedlist = self["channel_list"]

        self.listAll = []
        self.channelListAll = []

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

        self.PicLoad = ePicLoad()
        self.Scale = AVSwitch().getFramebufferScale()

        try:
            self.PicLoad.PictureData.get().append(self.DecodePicture)
        except:
            self.PicLoad_conn = self.PicLoad.PictureData.connect(self.DecodePicture)

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

        self["progress"] = ProgressBar()
        self["progress"].hide()

        self["key_red"] = StaticText(_('Back'))
        self["key_green"] = StaticText(_('OK'))
        self["key_yellow"] = StaticText(_('Sort: A-Z'))
        self["key_blue"] = StaticText(_('Search'))
        self["key_epg"] = StaticText('')
        self["key_rec"] = StaticText('')

        self["key_menu"] = StaticText('')

        self.sorted = False
        self.isStream = False
        self.filtered = False

        self.pin = False

        self.protocol = glob.current_playlist['playlist_info']['protocol']
        self.domain = glob.current_playlist['playlist_info']['domain']
        self.host = glob.current_playlist['playlist_info']['host']
        self.livetype = glob.current_playlist['player_info']['livetype']
        self.vodtype = glob.current_playlist['player_info']['vodtype']

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

        self.showingshortEPG = False
        self.epgchecklist = []

        self.token = "ZUp6enk4cko4ZzBKTlBMTFNxN3djd25MOHEzeU5Zak1Bdkd6S3lPTmdqSjhxeUxMSTBNOFRhUGNBMjBCVmxBTzlBPT0K"

        self.timerEPG = eTimer()
        self.timerBusy = eTimer()
        self.timerVOD = eTimer()
        self.timerVODBusy = eTimer()

        self.epgdownloading = False

        self.listType = ''

        # self.xmltv_exists = False
        # self.epgdownloaded = False
        self.xmltvdownloaded = False

        self["actions"] = ActionMap(["XStreamityActions"], {
            'cancel': self.back,
            'red': self.playStream,
            'ok':  self.__next__,
            'green': self.__next__,
            'yellow': self.sort,
            'blue': self.search,
            'epg': self.nownext,
            "epg_long": self.shortEPG,
            'info': self.nownext,
            "info_long": self.shortEPG,
            'text': self.nownext,
            "left": self.pageUp,
            "right": self.pageDown,
            "up": self.goUp,
            "down": self.goDown,
            "channelUp": self.pageUp,
            "channelDown": self.pageDown,
            "rec": self.downloadVideo,
            "0": self.reset,
            "menu": self.showHiddenList,
            }, -1)

        self["actions"].csel = self

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
        self.epg_path = cfg.location.getValue() + "epg/"
        self.epg_file_name = "epg_%s.xml" % (glob.current_playlist['playlist_info']['domain'].replace(".", "_"))
        self.epg_full_path = self.epg_path + self.epg_file_name

        try:
            if config.misc.epgcachepath:
                self.epg_path = config.misc.epgcachepath.getValue() + "epg/"
                if not os.path.exists(self.epg_path):
                    os.makedirs(self.epg_path)
                self.epg_file_name = "epg_%s.xml" % (glob.current_playlist['playlist_info']['domain'].replace(".", "_"))
                self.epg_full_path = self.epg_path + self.epg_file_name
        except:
            pass

        try:
            os.remove(str(dir_tmp) + "liveepg.xml")
        except:
            pass

        self.epgchecklist = []

        self.sorted = False

        if self.filtered:
            self.resetSearch()

        self["epg_title"].setText('')
        self["epg_description"].setText('')
        self["key_rec"].setText('')

        if self.level == 1:
            self["key_menu"].setText(_("Hide/Show"))
            self["key_epg"].setText('')

            url = glob.nextlist[-1]['playlist_url']

            if self.category == 0:
                response = glob.current_playlist['data']['live_categories']
            if self.category == 1:
                response = glob.current_playlist['data']['vod_categories']
            if self.category == 2:
                response = glob.current_playlist['data']['series_categories']

            self.processData(response, url)

        else:
            self["key_menu"].setText('')
            self.downloadData()


    def downloadData(self):
        url = glob.nextlist[-1]["playlist_url"]
        levelpath = dir_tmp + 'level' + str(self.level) + '.xml'

        if not os.path.exists(levelpath):
            adapter = HTTPAdapter(max_retries=0)
            http = requests.Session()
            http.mount("http://", adapter)
            try:
                r = http.get(url, headers=hdr, stream=True, timeout=10, verify=False)
                r.raise_for_status()
                if r.status_code == requests.codes.ok:

                    content = r.json()
                    with open(levelpath, 'wb') as f:
                        f.write(json.dumps(content))

                    self.processData(content, url)

            except requests.exceptions.ConnectionError as e:
                print("Error Connecting: %s" % e)
                pass

            except requests.exceptions.RequestException as e:
                print(e)
                pass
        else:
            # print("******* using file data ******")
            with open(levelpath, "rb") as f:
                self.processData(json.load(f), url)


    # code for natural sorting of numbers in string
    def atoi(self, text):
        return int(text) if text.isdigit() else text


    def natural_keys(self, text):
        return [self.atoi(c) for c in re.split(r'(\d+)', text[1])]


    def clear_caches(self):
        try:
            system("echo 1 > /proc/sys/vm/drop_caches")
            system("echo 2 > /proc/sys/vm/drop_caches")
            system("echo 3 > /proc/sys/vm/drop_caches")
        except:
            pass


    def processData(self, response, url):

        self.channelList = []
        currentCategory = ''
        index = 0
        indexAll = 0

        # ~~~~~~~~~~~~~~~ level 1 ~~~~~~~~~~~~~~~ #

        if "&action=get_live_categories" or "&action=get_vod_categories" or "&action=get_series_categories" in url:
            self.isStream = False
            self.listType = "category"

        if "&action=get_live_categories" in url:
            currentCategory = glob.current_playlist['data']['live_categories']
            nextAction = "&action=get_live_streams&category_id="

        elif "&action=get_vod_categories" in url:
            currentCategory = glob.current_playlist['data']['vod_categories']
            nextAction = "&action=get_vod_streams&category_id="

        elif "&action=get_series_categories" in url:
            currentCategory = glob.current_playlist['data']['series_categories']
            nextAction = "&action=get_series&category_id="

        # ~~~~~~~~~~~~~~~ level 2 ~~~~~~~~~~~~~~~ #

        elif "&action=get_live_streams" in url:
            currentCategory = response
            nextAction = ''
            self.isStream = True
            self.listType = "live_streams"

        elif "&action=get_vod_streams" in url:
            currentCategory = response
            nextAction = ''
            self.isStream = True
            self.listType = "vod_streams"

        elif "&action=get_series&category_id" in url:
            currentCategory = response
            nextAction = '&action=get_series_info&series_id='
            self.isStream = False
            self.listType = "series_titles"

        # ~~~~~~~~~~~~~~~ level 3 ~~~~~~~~~~~~~~~ #

        if "&action=get_series_info" in url and self.level == 3:
            currentCategory = response
            nextAction = '&action=get_series_info&series_id='
            self.isStream = False
            self.listType = "series_seasons"

        # ~~~~~~~~~~~~~~~ level 4 ~~~~~~~~~~~~~~~ #

        if "&action=get_series_info" in url and self.level == 4:
            currentCategory = response
            nextAction = ''
            self.isStream = True
            self.listType = "series_episodes"

        # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ #

        self.list = []
        self.listAll = []

        if self.listType == "category":
            hidden = False
            # add an ALL Category
            next_url = "%s%s%s" % (glob.current_playlist['playlist_info']['player_api'], nextAction, 0)
            if "get_live_streams" in next_url and "0" in glob.current_playlist['player_info']['livehidden']:
                hidden = True

            elif "get_vod_streams" in next_url and "0" in glob.current_playlist['player_info']['vodhidden']:
                hidden = True

            elif "get_series" in next_url and "0" in glob.current_playlist['player_info']['serieshidden']:
                hidden = True

            if hidden is False:
                self.list.append([index, _("All"), "%s%s%s" % (glob.current_playlist['playlist_info']['player_api'], nextAction, 0), "0"])
                self.listAll.append([index, _("All"), "%s%s%s" % (glob.current_playlist['playlist_info']['player_api'], nextAction, 0), "0"])
                index += 1
                indexAll += 1

            for item in currentCategory:
                hidden = False
                category_name = item['category_name']
                category_id = item['category_id']

                next_url = "%s%s%s" % (glob.current_playlist['playlist_info']['player_api'], nextAction, category_id)

                if "get_live_streams" in next_url and category_id in glob.current_playlist['player_info']['livehidden']:
                    hidden = True

                elif "get_vod_streams" in next_url and category_id in glob.current_playlist['player_info']['vodhidden']:
                    hidden = True

                elif "get_series" in next_url and category_id in glob.current_playlist['player_info']['serieshidden']:
                    hidden = True

                if hidden is False:
                    self.list.append([index, str(category_name), str(next_url), str(category_id)])
                    index += 1

                self.listAll.append([indexAll, str(category_name), str(next_url), str(category_id)])
                indexAll += 1

            self.epgchecklist = []

        elif self.listType == "live_streams":
            for item in currentCategory:

                name = item['name']
                stream_id = item['stream_id']
                stream_icon = item['stream_icon']
                epg_channel_id = item['epg_channel_id']
                added = item['added']

                if stream_icon:
                    if stream_icon.startswith("https://vignette.wikia.nocookie.net/tvfanon6528"):
                        stream_icon = stream_icon.replace("https", "http")
                        if "scale-to-width-down" not in stream_icon:
                            stream_icon = str(stream_icon) + "/revision/latest/scale-to-width-down/220"

                epgnowtitle = epgnowtime = epgnowdescription = epgnexttitle = epgnexttime = epgnextdescription = ''

                next_url = "%s/live/%s/%s/%s.%s" % (self.host, self.username, self.password, stream_id, self.output)

                self.list.append([
                    index, str(name), str(stream_id), str(stream_icon), str(epg_channel_id), str(added), str(next_url),
                    epgnowtime, epgnowtitle, epgnowdescription, epgnexttime, epgnexttitle, epgnextdescription
                ])
                index += 1

        elif self.listType == "vod_streams":
            for item in currentCategory:
                name = item['name']
                stream_id = item['stream_id']
                stream_icon = item['stream_icon']
                added = item['added']
                container_extension = item['container_extension']
                rating = item['rating']

                if stream_icon:
                    if stream_icon.startswith("https://image.tmdb.org/t/p/") or stream_icon.startswith("http://image.tmdb.org/t/p/"):
                        dimensions = stream_icon.partition("/p/")[2].partition("/")[0]
                        if screenwidth.width() <= 1280:
                            stream_icon = stream_icon.replace(dimensions, "w300")
                        else:
                            stream_icon = stream_icon.replace(dimensions, "w400")

                next_url = "%s/movie/%s/%s/%s.%s" % (self.host, self.username, self.password, stream_id, container_extension)

                self.list.append([index, str(name), str(stream_id), str(stream_icon), str(added), str(rating), str(next_url)])
                index += 1

        elif self.listType == "series_titles":
            for item in currentCategory:
                name = item['name']
                series_id = item['series_id']
                cover = item['cover']
                plot = item['plot']
                cast = item['cast']
                director = item['director']
                genre = item['genre']
                releaseDate = item['releaseDate']
                rating = item['rating']
                last_modified = item['last_modified']

                if cover:
                    if cover.startswith("https://image.tmdb.org/t/p/") or cover.startswith("http://image.tmdb.org/t/p/"):
                        dimensions = cover.partition("/p/")[2].partition("/")[0]
                        if screenwidth.width() <= 1280:
                            cover = cover.replace(dimensions, "w300")
                        else:
                            cover = cover.replace(dimensions, "w400")

                next_url = "%s%s%s" % (glob.current_playlist['playlist_info']['player_api'], nextAction, series_id)

                self.list.append([index, str(name), str(series_id), str(cover), str(plot), str(cast), str(director), str(genre), str(releaseDate), str(rating), str(last_modified), str(next_url)])
                index += 1

        elif self.listType == "series_seasons":
            if "info" in currentCategory:
                name = currentCategory['info']['name']
                cover = currentCategory['info']['cover']
                overview = currentCategory['info']['plot']
                cast = currentCategory['info']['cast']
                director = currentCategory['info']['director']
                genre = currentCategory['info']['genre']
                airdate = currentCategory['info']['releaseDate']
                rating = currentCategory['info']['rating']

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

                            if isdict:
                                season_number = currentCategory["episodes"][str(season)][0]['season']
                            else:
                                season_number = currentCategory["episodes"][season][0]['season']

                            series_id = 0

                            if "seasons" in currentCategory:
                                if currentCategory['seasons']:
                                    for item in currentCategory['seasons']:
                                        if item['season_number'] == season_number:
                                            if "airdate" in item:
                                                if item['airdate'] != "":
                                                    airdate = item['airdate']

                                            if "name" in item:
                                                if item['name'] != "":
                                                    name = item['name']

                                            if "overview" in item:
                                                if item['overview'] != "":
                                                    overview = item['overview']

                                            if "cover" in item:
                                                cover = item['cover']

                                            if "cover_big" in item:
                                                cover = item['cover_big']

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

        elif self.listType == "series_episodes":
            if "info" in currentCategory:

                shorttitle = currentCategory['info']['name']
                cover = currentCategory['info']['cover']
                plot = currentCategory['info']['plot']
                cast = currentCategory['info']['cast']
                director = currentCategory['info']['director']
                genre = currentCategory['info']['genre']
                releasedate = currentCategory['info']['releaseDate']
                rating = currentCategory['info']['rating']

            if "episodes" in currentCategory:
                if currentCategory["episodes"]:
                    season_number = str(self.season_number)

                    try:
                        seasonlist = list(currentCategory['episodes'].keys())
                    except:
                        season_number = int(self.season_number)

                    for item in currentCategory['episodes'][season_number]:

                        stream_id = item['id']
                        title = item['title'].replace(str(shorttitle) + " - ", "")
                        container_extension = item['container_extension']
                        try:
                            tmdb_id = item['info']['tmdb_id']
                        except:
                            tmdb_id = ''
                            pass

                        try:
                            releasedate = item['info']['releasedate']
                        except:
                            pass

                        try:
                            plot = item['info']['plot']
                        except:
                            pass

                        try:
                            duration = item['info']['duration']
                        except:
                            duration = ''
                            pass

                        try:
                            rating = item['info']['rating']
                        except:
                            pass

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
            if self.listType == "category":
                self.channelList = []
                self.channelList = [buildCategoryList(x[0], x[1], x[2], x[3]) for x in self.list]
                self["channel_list"].setList(self.channelList)

                self.channelListAll = []
                self.channelListAll = [buildCategoryList(x[0], x[1], x[2], x[3]) for x in self.listAll]

                if self.category == 0:
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
                                    self.doDownload()

                                except:
                                    pass

                                """
                            duration = datenow - last_modified
                            duration_in_s = duration.total_seconds()
                            days = divmod(duration_in_s, 86400)

                            if days[0] >= 1:
                                try:
                                    os.remove(self.epg_full_path)
                                    self.xmltvdownloaded = False
                                    self.doDownload()

                                except:
                                    pass
                                    """
                        else:
                            self.doDownload()

            elif self.listType == "live_streams":
                self.epglist = []

                self.epglist = [buildEPGListEntry(x[0], x[1], x[7], x[8], x[9], x[10], x[11], x[12]) for x in self.list]
                self["epg_list"].setList(self.epglist)

                self.channelList = []
                self.channelList = [buildLiveStreamList(x[0], x[1], x[2], x[3], x[4], x[5], x[6]) for x in self.list]
                self["channel_list"].setList(self.channelList)

                instance = self["epg_list"].master.master.instance
                instance.setSelectionEnable(0)

                if glob.current_playlist['player_info']['epgtype'] == "1":
                    if self.sorted is False and self.filtered is False:
                        self.downloadEnigma2EPGList()

            elif self.listType == "vod_streams":
                self.channelList = []
                self.channelList = [buildVodStreamList(x[0], x[1], x[2], x[3], x[4], x[5], x[6]) for x in self.list]
                self["channel_list"].setList(self.channelList)

            elif self.listType == "series_titles":
                self.channelList = []
                self.channelList = [buildSeriesTitlesList(x[0], x[1], x[2], x[3], x[4], x[5], x[6], x[7], x[8], x[9], x[10], x[11]) for x in self.list]
                self["channel_list"].setList(self.channelList)

            elif self.listType == "series_seasons":
                self.channelList = []
                self.channelList = [buildSeriesSeasonsList(x[0], x[1], x[2], x[3], x[4], x[5], x[6], x[7], x[8], x[9], x[10], x[11]) for x in self.list]
                self["channel_list"].setList(self.channelList)

            elif self.listType == "series_episodes":
                self.channelList = []
                self.channelList = [buildSeriesEpisodesList(x[0], x[1], x[2], x[3], x[4], x[5], x[6], x[7], x[8], x[9], x[10], x[11], x[12], x[13], x[14]) for x in self.list]
                self["channel_list"].setList(self.channelList)

        if self["channel_list"].getCurrent():
            next_url = self["channel_list"].getCurrent()[3]
            if glob.nextlist[-1]['index'] != 0:
                self["channel_list"].setIndex(glob.nextlist[-1]['index'])
                channeltitle = self["channel_list"].getCurrent()[0]
                self["channel"].setText(self.main_title + ": " + str(channeltitle))

            if not self.isStream:
                self.hideEPG()
                self.hideVod()
            else:
                if next_url != 'None' and "/live/" in next_url:
                    self.showEPGElements()
                    self.hideVod()
                else:
                    self.hideEPG()
                if next_url != 'None' and ("/movie/" in next_url):
                    self.showVodElements()

            if "&action=get_series_info" in next_url or self.level == 4:
                self.showVodElements()

        self.selectionChanged()


    def back(self):

        # self.epgdownloaded = False

        if self.listType == "live_streams":
            try:
                os.remove(str(dir_tmp) + "liveepg.xml")
            except:
                pass

        if self.selectedlist == self["epg_short_list"]:
            self.shortEPG()
            return
        else:
            del glob.nextlist[-1]

            if len(glob.nextlist) == 0:
                self.close()

            else:
                self.tempstreamtype = ''
                self.tempstream_url = ''

                self.sorted = False
                self["key_yellow"].setText(_('Sort: A-Z'))
                self["key_rec"].setText('')

                # if cfg.stopstream.value == True:
                self.stopStream()

                levelpath = str(dir_tmp) + 'level' + str(self.level) + '.xml'
                try:
                    os.remove(levelpath)
                except:
                    pass
                self.level -= 1

                # self.resetSearch()
                self.createSetup()


    def pinEntered(self, result):
        from Screens.MessageBox import MessageBox
        if not result:
            self.pin = False
            self.session.open(MessageBox, _("Incorrect pin code."), type=MessageBox.TYPE_ERROR, timeout=5)
        self.next2()


    def __next__(self):
        if self.level == 1:
            self.pin = True
            if cfg.parental.getValue() is True:
                adult = "all,", "+18", "adult", "18+", "18 rated", "xxx", "sex", "porn", "pink", "blue"
                if any(s in str(self["channel_list"].getCurrent()[0]).lower() for s in adult):
                    from Screens.InputBox import PinInput
                    self.session.openWithCallback(self.pinEntered, PinInput, pinList=[config.ParentalControl.setuppin.value], triesEntry=config.ParentalControl.retries.servicepin, title=_("Please enter the parental control pin code"), windowTitle=_("Enter pin code"))
                else:
                    self.pin = True
                    self.next2()
            else:
                self.pin = True
                self.next2()
        else:
            self.pin = True
            self.next2()


    def next2(self):
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

            if not self.isStream:
                if "&action=get_series_info" in next_url:
                    if self.level == 2:
                        self.seasons_url = self["channel_list"].getCurrent()[3]
                    if self.level == 3:
                        self.season_number = self["channel_list"].getCurrent()[12]

                glob.nextlist.append({"playlist_url": next_url, "index": 0})
                self.level += 1
                self["channel_list"].setIndex(0)
                self.createSetup()
            else:

                if next_url != 'None' and "/live/" in next_url:
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

                elif next_url != 'None' and ("/movie/" in next_url or "/series/" in next_url):

                    streamtype = glob.current_playlist["player_info"]["vodtype"]

                    self.reference = eServiceReference(int(streamtype), 0, next_url)
                    self.session.openWithCallback(self.setIndex, streamplayer.XStreamity_VodPlayer, str(next_url), str(streamtype))


    def setIndex(self):
        self["channel_list"].setIndex(glob.currentchannelistindex)
        self["epg_list"].setIndex(glob.currentchannelistindex)


    def playStream(self):
        # exit button back to playing stream
        if self["channel_list"].getCurrent():

            if self.session.nav.getCurrentlyPlayingServiceReference():
                if not self.isStream or self.session.nav.getCurrentlyPlayingServiceReference().toString() == glob.currentPlayingServiceRefString or self.selectedlist == self["epg_short_list"]:
                    self.back()
                else:
                    ref = str(self.session.nav.getCurrentlyPlayingServiceReference().toString())
                    self.tempstreamtype = ref.partition(':')[0]
                    self.tempstream_url = unquote(ref.split(':')[10]).decode('utf8')
                    self.source = "exit"
                    self.pin = True

                    self["channel_list"].setIndex(glob.nextlist[-1]['index'])
                    self.next2()
            else:
                self.back()


    def stopStream(self):
        if glob.currentPlayingServiceRefString != glob.newPlayingServiceRefString:
            if glob.newPlayingServiceRefString != '':
                if self.session.nav.getCurrentlyPlayingServiceReference():
                    self.session.nav.stopService()
                self.session.nav.playService(eServiceReference(glob.currentPlayingServiceRefString))


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

            if next_url != 'None':
                if "/live/" in next_url:

                    if not self.showingshortEPG:
                        self["key_rec"].setText('')
                        self["epg_list"].setIndex(currentindex)

                        self.refreshEPGInfo()
                        self.timerpicon = eTimer()
                        try:
                            self.timerpicon.callback.append(self.downloadPicon)
                        except:
                            self.timerpicon_conn = self.timerpicon.timeout.connect(self.downloadPicon)
                        self.timerpicon.start(300, True)

                    if glob.current_playlist['player_info']['epgtype'] == "2":
                        if self.listType == "live_streams" and self.xmltvdownloaded and self.sorted is False and self.filtered is False:
                            self.getChannelChunk()

                elif "/movie/" in next_url:
                    self["key_rec"].setText(_("Download"))
                    self.timerVOD = eTimer()
                    try:
                        self.timerVOD.callback.append(self.downloadVodData)
                    except:
                        self.timerVOD_conn = self.timerVOD.timeout.connect(self.downloadVodData)
                    self.timerVOD.start(500, True)

                elif "&action=get_series_info" in next_url or self.level == 4:
                    self.timerSeries = eTimer()
                    try:
                        self.timerSeries.callback.append(self.displaySeriesData)
                    except:
                        self.timerSeries_conn = self.timerSeries.timeout.connect(self.displaySeriesData)
                    self.timerSeries.start(50, True)

                if self.level == 4:
                    self["key_rec"].setText(_("Download"))


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

        # print "********* threadname ********"
        # print(threading.currentThread().getName())
        self["epg_list"].setList(self.epglist)

        instance = self["epg_list"].master.master.instance
        instance.setSelectionEnable(0)

        glob.originalChannelList = self.list[:]

        if self.listType == "live_streams" and not self.showingshortEPG:
            self.refreshEPGInfo()


    def displaySeriesData(self):
        self.info = {}
        self.downloadCover()
        if self.listType == "series_titles":
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

        if self.listType == "series_seasons":
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

        if self.listType == "series_episodes":
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


    def downloadPicon(self):
        if self["channel_list"].getCurrent():
            next_url = self["channel_list"].getCurrent()[3]
            if next_url != 'None' and "/live/" in next_url:
                try:
                    os.remove(str(dir_tmp) + 'original.png')
                except:
                    pass

                url = ''
                size = []
                if self["channel_list"].getCurrent():

                    desc_image = ''
                    try:
                        desc_image = self["channel_list"].getCurrent()[5]
                    except Exception as e:
                        print("* picon error ** %s" % e)
                        pass

                    self.loadDefaultImage()
                    imagetype = "picon"
                    url = desc_image
                    size = [147, 88]
                    if screenwidth.width() > 1280:
                        size = [220, 130]

                    if url != '' and url != "n/A" and url is not None:
                        original = dir_tmp + 'original.png'

                        if url.startswith('https'):
                            url = url.replace('https', 'http')

                        downloadPage(url, original, timeout=5).addCallback(self.checkdownloaded, size, imagetype).addErrback(self.ebPrintError)

                    else:
                        self.loadDefaultImage()


    def downloadCover(self):
        if self["channel_list"].getCurrent():
            next_url = self["channel_list"].getCurrent()[3]
            if next_url != 'None' and ("/movie/" in next_url or "&action=get_series_info" in next_url):
                try:
                    os.remove(str(dir_tmp) + 'original.jpg')
                except:
                    pass

                url = ''
                size = []
                desc_image = ''
                try:
                    desc_image = self["channel_list"].getCurrent()[5]
                except Exception as e:
                    print("* vod cover error ** %s" % e)
                    pass

                self.loadDefaultImage()
                imagetype = "cover"

                url = desc_image
                if self.info:
                    if 'cover_big' in self.info:
                        url = str(self.info["cover_big"]).strip()

                size = [267, 400]
                if screenwidth.width() > 1280:
                    size = [400, 600]

                if url != '' and url != "n/A" and url is not None:
                    original = dir_tmp + 'original.jpg'
                    if url.startswith('https'):
                        url = url.replace('https', 'http')

                    downloadPage(url, original, timeout=5).addCallback(self.checkdownloaded, size, imagetype).addErrback(self.ebPrintError)

                else:
                    self.loadDefaultImage()


    def ebPrintError(self, failure):
        print("********* error ******** %s" % failure)
        self.loadDefaultImage()
        pass


    def PrintError(self, failure):
        print("********* error ******** %s" % failure)
        pass


    def loadDefaultImage(self):
        if self["vod_cover"].instance:
            self["vod_cover"].instance.setPixmapFromFile(skin_path + "images/vod_cover.png")

        if self["epg_picon"].instance:
            self["epg_picon"].instance.setPixmapFromFile(common_path + "picon.png")


    def checkdownloaded(self, data, piconSize, imageType):
        if self["channel_list"].getCurrent():
            if imageType == "picon":
                original = dir_tmp + 'original.png'
                if os.path.exists(original):
                    try:
                        imagedownload.updatePreview(piconSize, imageType, original)
                        self.displayImage()
                    except Exception as e:
                        print("* error ** %s" % e)
                        pass
                    except:
                        pass
                else:
                    self.loadDefaultImage()

            elif imageType == "cover":
                if self["vod_cover"].instance:
                    self.displayVodImage()


    def displayImage(self):
        preview = dir_tmp + 'original.png'
        if self["epg_picon"].instance:
            self["epg_picon"].instance.setPixmapFromFile(preview)


    def displayVodImage(self):
        preview = dir_tmp + 'original.jpg'
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


    def showEPGElements(self):
        self["epg_picon"].show()
        self["epg_bg"].show()


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

            self.displayProgress()


    def displayProgress(self):
        start = ''
        end = ''
        percent = 0

        if self["epg_list"].getCurrent():

            start = self["epg_list"].getCurrent()[2]
            end = self["epg_list"].getCurrent()[5]

        if start != '' and end != '':
            self["progress"].show()
            start_time = datetime.strptime(start, "%H:%M")
            end_time = datetime.strptime(end, "%H:%M")
            if end_time < start_time:
                end_time = datetime.strptime(end, "%H:%M") + timedelta(hours=24)

            total_time = end_time - start_time
            duration = 0
            if total_time.total_seconds() > 0:
                duration = total_time.total_seconds()/60

            now = datetime.now().strftime("%H:%M")
            current_time = datetime.strptime(now, "%H:%M")
            elapsed = current_time - start_time

            if elapsed.days < 0:
                elapsed = timedelta(days=0, seconds=elapsed.seconds)

            elapsedmins = 0
            if elapsed.total_seconds() > 0:
                elapsedmins = elapsed.total_seconds()/60

            if duration > 0:
                percent = int(elapsedmins / duration * 100)
            else:
                percent = 100

            self["progress"].setValue(percent)
        else:
            self["progress"].hide()


    def hideEPG(self):
        self["epg_list"].setList([])
        self["epg_picon"].hide()
        self["epg_bg"].hide()
        self["epg_title"].setText('')
        self["epg_description"].setText('')
        self["progress"].hide()


    def shortEPG(self):
        self.showingshortEPG = not self.showingshortEPG
        if self.showingshortEPG:
            self["epg_list"].setList([])

            if self["channel_list"].getCurrent():
                next_url = self["channel_list"].getCurrent()[3]

                if next_url != 'None':
                    if "/live/" in next_url:
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
                            print("Error Connecting: %s" % e)
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

                                    if 'title' in listing:
                                        epg_title = base64.b64decode(listing['title']).decode('utf-8')

                                    if 'description' in listing:
                                        epg_description = base64.b64decode(listing['description']).decode('utf-8')

                                    shift = 0

                                    if "epgshift" in glob.current_playlist["player_info"]:
                                        shift = int(glob.current_playlist["player_info"]["epgshift"])

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


    def nownext(self):
        if self["channel_list"].getCurrent():
            next_url = self["channel_list"].getCurrent()[3]

            if next_url != 'None':
                if "/live/" in next_url:
                    if self["key_epg"].getText() != '' and self["epg_list"].getCurrent():
                        startnowtime = self["epg_list"].getCurrent()[2]
                        titlenow = self["epg_list"].getCurrent()[3]
                        descriptionnow = self["epg_list"].getCurrent()[4]

                        startnexttime = self["epg_list"].getCurrent()[5]
                        titlenext = self["epg_list"].getCurrent()[6]
                        descriptionnext = self["epg_list"].getCurrent()[7]

                        if self["key_epg"].getText() != '' or None:
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

                elif "/movie/" in next_url:
                    if self["key_rec"].getText() != '':
                        self.openIMDb()


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


    def downloadVodData(self):
        vod_info_url = glob.current_playlist['playlist_info']['player_api']
        action = "&action=get_vod_info&vod_id="
        stream_id = self["channel_list"].getCurrent()[4]
        url = str(vod_info_url) + str(action) + str(stream_id)

        try:
            r = requests.get(url, headers=hdr, stream=True, timeout=10, verify=False)
            r.raise_for_status()
            if r.status_code == requests.codes.ok:
                content = r.json()
                self.processVod(content)

        except requests.exceptions.ConnectionError as e:
            print("Error Connecting: %s" % e)

        except requests.exceptions.RequestException as e:
            print(e)


    def processVod(self, content):
        if self["channel_list"].getCurrent():

            if "info" in content and content["info"]:
                self.info = content["info"]

                if "name" not in self.info:
                    self.info["name"] = content["movie_data"]["name"]

            elif "movie_data" in content and content["movie_data"]:
                self.info = content["movie_data"]
            else:
                self.info = None

            if cfg.refreshTMDB.value is True:
                self.loadDefaultImage()
                self.displayVod()
                self.getTMDB()
            else:
                self.downloadCover()
                self.displayVod()


    def displayVod(self):
        if self["channel_list"].getCurrent():
            stream_url = self["channel_list"].getCurrent()[3]

            if self.info and "/movie/" in stream_url:

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
                    pass

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

                if 'releasedate' in self.info:
                    if self["vod_release_date"] != "":
                        try:
                            self["vod_release_date"].setText(datetime.strptime(self.info["releasedate"], "%Y-%m-%d").strftime("%d-%m-%Y"))
                        except:
                            self["vod_release_date"].setText('')
                            pass
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


    # record button download video file
    def downloadVideo(self):
        if self["channel_list"].getCurrent():
            stream_url = self["channel_list"].getCurrent()[3]
            extension = str(os.path.splitext(stream_url)[-1])

            if self["key_rec"].getText() == _('Download'):
                from Screens.MessageBox import MessageBox

                title = self["channel_list"].getCurrent()[0]
                if "/series/" in stream_url:
                    title = str(self["channel_list"].getCurrent()[15]) + " " + str(self["channel_list"].getCurrent()[0])

                fileTitle = re.sub(r'[\<\>\:\"\/\\\|\?\*\[\]]', '', title)

                try:
                    downloadPage(stream_url, str(cfg.downloadlocation.getValue()) + str(fileTitle) + str(extension)).addErrback(self.ebPrintError)
                    self.session.open(MessageBox, _('Downloading \n\n' + title + "\n\n" + str(cfg.downloadlocation.getValue()) + str(fileTitle) + str(extension)), MessageBox.TYPE_INFO)
                except Exception as e:
                    print("download vod %s" % e)
                    pass
                except:
                    self.session.open(MessageBox, _('Download Failed\n\n' + title + "\n\n" + str(cfg.downloadlocation.getValue()) + str(fileTitle) + str(extension)), MessageBox.TYPE_WARNING)
                    pass

            elif "/live/" in stream_url:
                    self.IPTVstartInstantRecording()

            else:
                return


    def IPTVstartInstantRecording(self, limitEvent=True):
        import record

        currentindex = self["channel_list"].getIndex()

        if self.epglist[currentindex][3]:
            name = self.epglist[currentindex][3]
        else:
            name = self.list[currentindex][1]
        self.name = NoSave(ConfigText(default=name, fixed_size=False))

        begin = int(time.time())
        end = begin + 3600

        dt_now = datetime.now()

        if self.epglist[currentindex][5]:
            end_dt = datetime.strptime(str(self.epglist[currentindex][5]), "%H:%M")
            end_dt = end_dt.replace(year=dt_now.year, month=dt_now.month, day=dt_now.day)
            end = int(time.mktime(end_dt.timetuple()))

        self.date = time.time()
        self.starttime = NoSave(ConfigClock(default=begin))
        self.endtime = NoSave(ConfigClock(default=end))

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


    def RecordDateInputClosed(self, ret=None):
        if ret:
            begin = ret[1]
            end = ret[2]
            name = ret[3]

            currentindex = self["channel_list"].getIndex()
            streamurl = self["channel_list"].getCurrent()[3]

            description = ''

            if self.epglist[currentindex][4]:
                description = self.epglist[currentindex][4]

            if self.showingshortEPG:
                currentindex = self["epg_short_list"].getIndex()
                if self.epgshortlist[currentindex][2]:
                    description = str(self.epgshortlist[currentindex][2])

            eventid = int(streamurl.rpartition('/')[-1].partition('.')[0])
            self.reference = eServiceReference(1, 0, streamurl)

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

        self.stopStream()
        return


    def sort(self):
        if self["channel_list"].getCurrent():
            self["channel_list"].setIndex(0)
            # current_selected =  self["channel_list"].getCurrent()[2]
            current_sort = self["key_yellow"].getText()

            if current_sort == (_('Sort: A-Z')):
                self["key_yellow"].setText(_('Sort: Z-A'))
                self.list.sort(key=lambda x: x[1], reverse=False)
                self.sorted = True

            elif current_sort == (_('Sort: Z-A')):
                if self.listType == "live_streams" or self.listType == "vod_streams" or self.listType == "series_titles":
                    self["key_yellow"].setText(_('Sort: Newest'))
                else:
                    self["key_yellow"].setText(_('Sort: Original'))
                self.list.sort(key=lambda x: x[1], reverse=True)
                self.sorted = True

            elif current_sort == (_('Sort: Newest')):
                if self.listType == "live_streams":
                    self.list.sort(key=lambda x: x[5], reverse=True)
                if self.listType == "vod_streams":
                    self.list.sort(key=lambda x: x[4], reverse=True)
                if self.listType == "series_titles":
                    self.list.sort(key=lambda x: x[10], reverse=True)
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


    def check(self, token):
        result = base64.b64decode((base64.b64decode(base64.b64decode(token)).decode('zlib').decode('utf-8')))
        return result


    def showHiddenList(self):
        if self["key_menu"].getText() != '':
            import hidden
            if self["channel_list"].getCurrent():
                next_url = self["channel_list"].getCurrent()[3]
                if "get_live_streams" in next_url:
                    self.session.openWithCallback(self.createSetup, hidden.XStreamity_HiddenCategories, "live", self.channelListAll)
                if "get_vod_streams" in next_url:
                    self.session.openWithCallback(self.createSetup, hidden.XStreamity_HiddenCategories, "vod", self.channelListAll)
                if "get_series" in next_url:
                    self.session.openWithCallback(self.createSetup, hidden.XStreamity_HiddenCategories, "series", self.channelListAll)


    def getTMDB(self):
        try:
            os.remove(dir_tmp + 'search.txt')
        except:
            pass

        isIMDB = False

        if self["channel_list"].getCurrent():

            next_url = self["channel_list"].getCurrent()[3]

            if next_url != 'None' and "/movie/" in next_url:
                title = self["channel_list"].getCurrent()[0]

                if self.info:
                    if "name" in self.info:
                        if self.info['name'] != '':
                            title = self.info['name']
                    elif "o_name" in self.info:
                        if self.info['o_name'] != '':
                            title = self.info['o_name']

                    if 'tmdb_id' in self.info:
                        if self.info['tmdb_id'] != '':

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
                "multi-subs",  "multi-sub",

                 "[audio-pt]", "[nordic-subbed]", "[nordic-subbeb]",

                "ae:", "al:", "ar:", "at:", "ba:", "be:", "bg:", "br:", "cg:", "ch:", "cz:", "da:", "de:", "dk:", "ee:", "en:", "es:", "ex-yu:", "fi:", "fr:", "gr:", "hr:", "hu:", "in:", "ir:", "it:", "lt:", "mk:",
                "mx:", "nl:", "no:", "pl:", "pt:",  "ro:", "rs:", "ru:", "se:",  "si:", "sk:", "tr:", "uk:", "us:",  "yu:",

                "[ae]", "[al]", "[ar]", "[at]", "[ba]", "[be]", "[bg]", "[br]", "[cg]", "[ch]", "[cz]", "[da]", "[de]", "[dk]", "[ee]", "[en]", "[es]", "[ex-yu]", "[fi]", "[fr]", "[gr]", "[hr]", "[hu]", "[in]", "[ir]", "[it]", "[lt]", "[mk]",
                "[mx]", "[nl]", "[no]", "[pl]", "[pt]",  "[ro]", "[rs]", "[ru]", "[se]",  "[si]", "[sk]", "[tr]", "[uk]", "[us]",  "[yu]",

                "-ae-", "-al-", "-ar-", "-at-", "-ba-", "-be-", "-bg-", "-br-", "-cg-", "-ch-", "-cz-", "-da-", "-de-", "-dk-", "-ee-", "-en-", "-es-", "-ex-yu-", "-fi-", "-fr-", "-gr-", "-hr-", "-hu-", "-in-", "-ir-", "-it-", "-lt-", "-mk-",
                "-mx-", "-nl-", "-no-", "-pl-", "-pt-",  "-ro-", "-rs-", "-ru-", "-se-",  "-si-", "-sk-", "-tr-", "-uk-", "-us-",  "-yu-",

                "|ae|", "|al|", "|ar|", "|at|", "|ba|", "|be|", "|bg|", "|br|", "|cg|", "|ch|", "|cz|", "|da|", "|de|", "|dk|", "|ee|", "|en|", "|es|", "|ex-yu|", "|fi|", "|fr|", "|gr|", "|hr|", "|hu|", "|in|", "|ir|", "|it|", "|lt|", "|mk|",
                "|mx|", "|nl|", "|no|", "|pl|", "|pt|",  "|ro|", "|rs|", "|ru|", "|se|",  "|si|", "|sk|", "|tr|", "|uk|", "|us|",  "|yu|",

                "(", ")", "[", "]", "u-", "3d", "-", "'", ]

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

                try:
                    downloadPage(searchurl, dir_tmp + 'search.txt', timeout=10).addCallback(self.processTMDB, isIMDB).addErrback(self.PrintError)
                except Exception as e:
                    print("download TMDB %s" % e)
                    pass
                except:
                    pass


    def processTMDB(self, result, IMDB):
        with open(dir_tmp + 'search.txt', "r") as f:
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
            os.remove(dir_tmp + 'movie.txt')
        except:
            pass

        language = "en"

        if cfg.refreshTMDB.value is True:
            language = cfg.TMDBLanguage.value

        detailsurl = "http://api.themoviedb.org/3/movie/" + str(resultid) + "?api_key=" + str(self.check(self.token)) + "&append_to_response=credits&language=" + str(language)

        try:
            downloadPage(detailsurl, dir_tmp + 'movie.txt', timeout=10).addCallback(self.processTMDBDetails).addErrback(self.PrintError)
        except Exception as e:
            print("download TMDB details %s" % e)
            pass
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

        with open(dir_tmp + 'movie.txt', "r") as f:
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
                if "poster_path" in self.detailsresult:
                    if self.detailsresult["poster_path"]:
                        if self.detailsresult["poster_path"] is not None:
                            if screenwidth.width() <= 1280:
                                self.info["cover_big"] = "http://image.tmdb.org/t/p/w300" + str(self.detailsresult["poster_path"])
                            else:
                                self.info["cover_big"] = "http://image.tmdb.org/t/p/w400" + str(self.detailsresult["poster_path"])

                if "title" in self.detailsresult:
                    if self.detailsresult["title"]:
                        self.info["name"] = str(self.detailsresult["title"])

                if "original_title" in self.detailsresult:
                    if self.detailsresult["original_title"]:
                        self.info["o_name"] = str(self.detailsresult["original_title"])

                if "overview" in self.detailsresult:
                    if self.detailsresult["overview"]:
                        self.info["description"] = str(self.detailsresult["overview"])

                if "runtime" in self.detailsresult:
                    if self.detailsresult["runtime"] and self.detailsresult["runtime"] != 0:
                        self.info['duration'] = str(timedelta(minutes=self.detailsresult["runtime"]))
                    else:
                        self.info['duration'] = ''


                if "vote_average" in self.detailsresult:
                    if self.detailsresult["vote_average"]:
                        if self.detailsresult["vote_average"] != 0:
                            self.info['rating'] = str(self.detailsresult["vote_average"])

                if "genres" in self.detailsresult:
                    if self.detailsresult["genres"]:
                        for genreitem in self.detailsresult["genres"]:
                            genre.append(str(genreitem["name"]))
                        genre = " / ".join(map(str, genre))
                        self.info['genre'] = genre

                if "production_countries" in self.detailsresult:
                    if self.detailsresult["production_countries"]:
                        for pcountry in self.detailsresult["production_countries"]:
                            country.append(str(pcountry["name"]))
                        country = ", ".join(map(str, country))
                        self.info['country'] = country

                if "release_date" in self.detailsresult:
                    if self.detailsresult["release_date"]:
                        self.info['release_date'] = str(self.detailsresult["release_date"])

                if "credits" in self.detailsresult:
                    if "cast" in self.detailsresult["credits"]:
                        for actor in self.detailsresult["credits"]["cast"]:
                            if "character" in actor:
                                cast.append(str(actor["name"]))
                        cast = ", ".join(map(str, cast))
                        self.info['cast'] = cast

                if "credits" in self.detailsresult:
                    if "crew" in self.detailsresult["credits"]:
                        for actor in self.detailsresult["credits"]["crew"]:
                            if "job" in actor:
                                director.append(str(actor["name"]))

                        director = ", ".join(map(str, director))
                        self.info['director'] = director

                self.downloadCover()
                self.displayVod()


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


    def doDownload(self):
        self["downloading"].show()
        url = str(glob.current_playlist['playlist_info']['xmltv_api']) + "&next_days=1"
        downloadPage(url, self.epg_full_path, headers=hdr).addCallback(self.downloadcomplete).addErrback(self.downloadFail)


    def downloadFail(self, failure):
        print("[EPG] download failed:", failure)
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



    def downloadEnigma2EPGList(self):

        url = glob.nextlist[-1]["playlist_url"]
        urlcategory = url.rsplit("=")[-1]
        url = str(glob.current_playlist['playlist_info']['enigma2_api']) + "&type=get_live_streams&cat_id=" + str(urlcategory)

        if not os.path.exists(str(dir_tmp) + "liveepg.xml"):
            downloadPage(url, str(dir_tmp) + "liveepg.xml", timeout=10).addCallback(self.processEnigma2EPG).addErrback(self.epgError)
        else:
            self.processEnigma2EPG()


    def epgError(self, failure):
        print("********* error ******** %s" % failure)
        pass


    def processEnigma2EPG(self, data=None):
        if os.path.exists(str(dir_tmp) + "liveepg.xml"):
            with open(str(dir_tmp) + "liveepg.xml", "r") as f:
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


def buildVodStreamList(index, title, stream_id, stream_icon, added, rating, next_url):
    png = LoadPixmap(common_path + "play.png")
    return (title, png, index, next_url, stream_id, stream_icon, added, rating)


def buildSeriesTitlesList(index, title, series_id, cover, plot, cast, director, genre, releaseDate, rating, lastmodified, next_url):
    png = LoadPixmap(common_path + "more.png")
    return (title, png, index, next_url, series_id, cover, plot, cast, director, genre, releaseDate, rating, lastmodified)


def buildSeriesSeasonsList(index, title, series_id, cover, plot, cast, director, genre, airDate, rating, season_number, next_url):
    png = LoadPixmap(common_path + "more.png")
    return (title, png, index, next_url, series_id, cover, plot, cast, director, genre, airDate, rating, season_number)


def buildSeriesEpisodesList(index, title, series_id, cover, plot, cast, director, genre, releaseDate, rating, duration, container_extension, tmdb_id, next_url, shorttitle):
    png = LoadPixmap(common_path + "play.png")
    return (title, png, index, next_url, series_id, cover, plot, cast, director, genre, releaseDate, rating, duration, container_extension, tmdb_id, shorttitle)
