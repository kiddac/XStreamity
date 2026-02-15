#!/usr/bin/python
# -*- coding: utf-8 -*-

# Standard library imports
import base64
import codecs
from datetime import datetime, timedelta
import json
import os
import re
import time
from itertools import cycle, islice
import zlib
import tempfile

try:
    from http.client import HTTPConnection
    HTTPConnection.debuglevel = 0
except ImportError:
    from httplib import HTTPConnection
    HTTPConnection.debuglevel = 0

try:
    from urllib import quote
except ImportError:
    from urllib.parse import quote

# Third-party imports
import requests
from PIL import Image
from requests.adapters import HTTPAdapter, Retry
from twisted.internet import reactor
from twisted.web.client import Agent, downloadPage, readBody
from twisted.web.http_headers import Headers

try:
    from twisted.web.client import BrowserLikePolicyForHTTPS
    contextFactory = BrowserLikePolicyForHTTPS()
except ImportError:
    from twisted.web.client import WebClientContextFactory
    contextFactory = WebClientContextFactory()

# Enigma2 components
from Components.ActionMap import ActionMap
from Components.Pixmap import Pixmap
from Components.Sources.List import List
from Screens.MessageBox import MessageBox
from Screens.Screen import Screen
from Screens.VirtualKeyBoard import VirtualKeyBoard
from Tools.LoadPixmap import LoadPixmap
from collections import OrderedDict
from enigma import ePicLoad, eServiceReference, eTimer

# Local imports
from . import _
from . import xstreamity_globals as glob
from .plugin import (cfg, common_path, dir_tmp, downloads_json, pythonVer, screenwidth, skin_directory, debugs)
from .xStaticText import StaticText

if os.path.exists("/var/lib/dpkg/status"):
    DreamOS = True
else:
    DreamOS = False

hdr = {
    'User-Agent': str(cfg.useragent.value),
    'Accept-Encoding': 'gzip, deflate'
}


if pythonVer == 3:
    superscript_to_normal = str.maketrans(
        '⁰¹²³⁴⁵⁶⁷⁸⁹ᵃᵇᶜᵈᵉᶠᵍʰⁱʲᵏˡᵐⁿᵒᵖʳˢᵗᵘᵛʷˣʸᶻ'
        'ᴬᴮᴰᴱᴳᴴᴵᴶᴷᴸᴹᴺᴼᴾᴿᵀᵁⱽᵂ⁺⁻⁼⁽⁾',
        '0123456789abcdefghijklmnoprstuvwxyz'
        'ABDEGHIJKLMNOPRTUVW+-=()'
    )


def normalize_superscripts(text):
    return text.translate(superscript_to_normal)


def clean_names(streams):
    """Clean 'name' and 'category_name' fields in each stream entry."""
    for item in streams:
        for field in ("name", "category_name"):
            if field in item and isinstance(item[field], str):
                item[field] = normalize_superscripts(item[field])
    return streams


class XStreamity_Series_Categories(Screen):
    ALLOW_SUSPEND = True

    def __init__(self, session):
        if debugs:
            print("*** init ***")

        Screen.__init__(self, session)
        self.session = session
        glob.categoryname = "series"

        self.agent = Agent(reactor, contextFactory=contextFactory)
        self.cover_download_deferred = None
        self.logo_download_deferred = None
        self.backdrop_download_deferred = None

        self.skin_path = os.path.join(skin_directory, cfg.skin.value)
        skin = os.path.join(self.skin_path, "vod_categories.xml")
        if DreamOS:
            skin = os.path.join(self.skin_path, "DreamOS/vod_categories.xml")

        with codecs.open(skin, "r", encoding="utf-8") as f:
            self.skin = f.read()

        self.playlists_json = cfg.playlists_json.value

        self.setup_title = _("Series Categories")

        self.main_title = _("Series")
        self["main_title"] = StaticText(self.main_title)

        self.group_title = ""
        self.series_group_title = ""

        self.main_list = []
        self["main_list"] = List(self.main_list, enableWrapAround=True)

        self["x_title"] = StaticText()
        self["x_description"] = StaticText()

        self["overview"] = StaticText()
        self["tagline"] = StaticText()
        self["facts"] = StaticText()

        # skin vod variables
        self["vod_cover"] = Pixmap()
        self["vod_cover"].hide()
        self["vod_backdrop"] = Pixmap()
        self["vod_backdrop"].hide()
        self["vod_logo"] = Pixmap()
        self["vod_logo"].hide()
        self["vod_director_label"] = StaticText()
        self["vod_country_label"] = StaticText()
        self["vod_cast_label"] = StaticText()
        self["vod_director"] = StaticText()
        self["vod_country"] = StaticText()
        self["vod_cast"] = StaticText()

        self["rating_text"] = StaticText()
        self["rating_percent"] = StaticText()

        # pagination variables
        self["page"] = StaticText("")
        self["listposition"] = StaticText("")
        self.itemsperpage = 10

        self.searchString = ""
        self.filterresult = ""

        self.chosen_category = ""

        self.pin = False
        self.tmdbresults = {}

        self.storedtitle = ""
        self.storedseason = ""
        self.storedepisode = ""
        self.storedyear = ""
        self.storedcover = ""
        self.storedtmdb = ""
        self.storedbackdrop = ""
        self.storedlogo = ""
        self.storeddescription = ""
        self.storedcast = ""
        self.storeddirector = ""
        self.storedgenre = ""
        self.storedreleasedate = ""
        self.storedrating = ""

        self.repeatcount = 0

        self.sortindex = 0
        self.sortText = _("Sort: A-Z")

        self.level = 1

        self.host = glob.active_playlist["playlist_info"]["host"]
        self.username = glob.active_playlist["playlist_info"]["username"]
        self.password = glob.active_playlist["playlist_info"]["password"]
        self.output = glob.active_playlist["playlist_info"]["output"]
        self.name = glob.active_playlist["playlist_info"]["name"]

        self.player_api = glob.active_playlist["playlist_info"]["player_api"]
        # self.liveStreamsData = []

        self.token = "ZUp6enk4cko4ZzBKTlBMTFNxN3djd25MOHEzeU5Zak1Bdkd6S3lPTmdqSjhxeUxMSTBNOFRhUGNBMjBCVmxBTzlBPT0K"

        next_url = str(self.player_api) + "&action=get_series_categories"

        self._vod_req_id = 0

        self._tmp_cover = None
        self._tmp_logo = None
        self._tmp_backdrop = None
        self._tmp_backdrop_src = None
        self._tmp_backdrop_out = None

        self._mask2 = None
        self._mask2_alpha = None
        self._mask2_cache = OrderedDict()
        self._mask2_cache_max = 5
        self._mask2_size = None
        self._backdrop_target_size = None

        try:
            mask_path = os.path.join(skin_directory, "common/mask2.png")
            if os.path.exists(mask_path):
                self._mask2 = Image.open(mask_path)
                self._mask2.load()  # Force load the image data
                self._mask2_size = self._mask2.size

                # Always create a reliable L alpha mask once:
                try:
                    if self._mask2.mode in ("RGBA", "LA"):
                        # For RGBA/LA, extract the alpha channel
                        if hasattr(self._mask2, 'split'):
                            bands = self._mask2.split()
                            if bands:
                                self._mask2_alpha = bands[-1]
                            else:
                                raise ValueError("split() returned empty")
                        else:
                            # Old PIL without proper split
                            self._mask2_alpha = self._mask2.convert("L")
                    else:
                        # Greyscale (or RGB etc) -> treat brightness as alpha
                        self._mask2_alpha = self._mask2.convert("L")
                except Exception as e:
                    print("Error extracting alpha, using greyscale fallback:", e)
                    self._mask2_alpha = self._mask2.convert("L")

        except Exception as e:
            print("Error loading mask2:", e)
            self._mask2 = None
            self._mask2_alpha = None
            self._mask2_size = None

        # tmdb image sizes (set once)
        self._tmdb_coversize = "w200"
        self._tmdb_backdropsize = "w1280"
        self._tmdb_logosize = "w200"
        self._cover_target_size = None
        self._logo_target_size = None

        try:
            width = screenwidth.width()

            if width <= 1280:
                self._tmdb_coversize = "w200"
                self._tmdb_backdropsize = "w1280"
                self._tmdb_logosize = "w300"

            elif width <= 1920:
                self._tmdb_coversize = "w300"
                self._tmdb_backdropsize = "w1280"
                self._tmdb_logosize = "w300"

            else:
                self._tmdb_coversize = "w400"
                self._tmdb_backdropsize = "w1280"
                self._tmdb_logosize = "w500"
        except:
            pass

        self._px_play = LoadPixmap(os.path.join(common_path, "play.png"))
        self._px_fav = LoadPixmap(os.path.join(common_path, "favourite.png"))
        self._px_watched = LoadPixmap(os.path.join(common_path, "watched.png"))
        self._px_more = LoadPixmap(os.path.join(common_path, "more.png"))

        # Precompiled regex (stripjunk)
        self._re_has_ascii = re.compile(r'[\x00-\x7F]')
        self._re_has_non_ascii = re.compile(r'[^\x00-\x7F]')

        self._re_remove_non_ascii = re.compile(r'[^\x00-\x7F]+')

        self._re_end_the = re.compile(r'\s*the$', re.IGNORECASE)
        self._re_prefix_xx_colon = re.compile(r'^\w{2}:', re.IGNORECASE)
        self._re_prefix_xx_pipe_xx = re.compile(r'^\w{2}\|\w{2}\s', re.IGNORECASE)

        self._re_leading_doublepipes = re.compile(r'^\|\|.*?\|\|')
        self._re_leading_singlepipe_block = re.compile(r'^\|.*?\|')
        self._re_any_pipe_block = re.compile(r'\|.*?\|')

        self._re_leading_doublebars = re.compile(r'^┃┃.*?┃┃')
        self._re_leading_singlebar_block = re.compile(r'^┃.*?┃')
        self._re_any_bar_block = re.compile(r'┃.*?┃')

        self._re_parens = re.compile(r'\(\(.*?\)\)|\([^()]*\)')
        self._re_brackets = re.compile(r'\[\[.*?\]\]|\[.*?\]')

        self._re_is_year_only = re.compile(r'^\d{4}$')
        self._re_trailing_year = re.compile(r'[\s\-]*(?:[\(\[\"]?\d{4}[\)\]\"]?)$')

        self._re_lang_dash_prefix = re.compile(r'^[A-Za-z0-9\-]{1,7}\s*-\s*', re.IGNORECASE)

        # Bad substrings
        bad_strings = [
            "ae|", "al|", "ar|", "at|", "ba|", "be|", "bg|", "br|", "cg|", "ch|", "cz|", "da|", "de|", "dk|",
            "ee|", "en|", "es|", "eu|", "ex-yu|", "fi|", "fr|", "gr|", "hr|", "hu|", "in|", "ir|", "it|", "lt|",
            "mk|", "mx|", "nl|", "no|", "pl|", "pt|", "ro|", "rs|", "ru|", "se|", "si|", "sk|", "sp|", "tr|",
            "uk|", "us|", "yu|",
            "1080p", "1080p-dual-lat-cine-calidad.com", "1080p-dual-lat-cine-calidad.com-1",
            "1080p-dual-lat-cinecalidad.mx", "1080p-lat-cine-calidad.com", "1080p-lat-cine-calidad.com-1",
            "1080p-lat-cinecalidad.mx", "1080p.dual.lat.cine-calidad.com", "3d", "'", "#", "(", ")", "-", "[]", "/",
            "4k", "720p", "aac", "blueray", "ex-yu:", "fhd", "hd", "hdrip", "hindi", "imdb", "multi:", "multi-audio",
            "multi-sub", "multi-subs", "multisub", "ozlem", "sd", "top250", "u-", "uhd", "vod", "x264",
            "amz", "dolby", "audio", "8k", "3840p", "50fps", "60fps", "hevc", "raw ", "vip ", "NF", "d+", "a+", "vp", "prmt", "mrvl"
        ]
        self._re_bad_strings = re.compile('|'.join(map(re.escape, bad_strings)), re.IGNORECASE)

        # Bad suffixes
        bad_suffix = [
            " al", " ar", " ba", " da", " de", " en", " es", " eu", " ex-yu", " fi", " fr", " gr", " hr", " mk",
            " nl", " no", " pl", " pt", " ro", " rs", " ru", " si", " swe", " sw", " tr", " uk", " yu"
        ]
        self._re_bad_suffix = re.compile(r'(' + '|'.join(map(re.escape, bad_suffix)) + r')$', re.IGNORECASE)

        self._re_dots_underscores = re.compile(r"[._'\*]")

        self.adult_keywords = set([
            "adult", "+18", "18+", "18 rated", "xxx", "sex", "porn",
            "voksen", "volwassen", "aikuinen", "Erwachsene", "dorosly",
            "взрослый", "vuxen", "£дорослий"
        ])

        # buttons / keys
        self["key_red"] = StaticText(_("Back"))
        self["key_green"] = StaticText(_("OK"))
        self["key_yellow"] = StaticText(self.sortText)
        self["key_blue"] = StaticText(_("Search"))
        self["key_epg"] = StaticText("")
        self["key_menu"] = StaticText("")

        self._screen_w = screenwidth.width()

        self._re_year = re.compile(r"\b\d{4}\b")

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
        }, -2)

        self["channel_actions"] = ActionMap(["XStreamityActions"], {
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
            "rec": self.downloadVideo,
            "5": self.downloadVideo,
            "0": self.reset,
            "menu": self.showHiddenList,
            "1": self.clearWatched,
            "tv": self.favourite,
            "stop": self.favourite,
        }, -2)

        self["channel_actions"].setEnabled(False)

        glob.nextlist = []
        glob.nextlist.append({"next_url": next_url, "index": 0, "level": self.level, "sort": self.sortText, "filter": ""})

        self.coverLoad = ePicLoad()
        try:
            self.coverLoad.PictureData.get().append(self.DecodeCover)
        except:
            self.coverLoad_conn = self.coverLoad.PictureData.connect(self.DecodeCover)

        self.timerSeries = eTimer()
        try:
            self.timerSeries.callback.append(self.displaySeriesData)
        except:
            self.timerSeries_conn = self.timerSeries.timeout.connect(self.displaySeriesData)

        self.onFirstExecBegin.append(self.createSetup)
        self.onLayoutFinish.append(self.__layoutFinished)

    def __layoutFinished(self):
        self.setTitle(self.setup_title)

        # cache cover target size
        try:
            if self["vod_cover"].instance:
                self._cover_target_size = (
                    self["vod_cover"].instance.size().width(),
                    self["vod_cover"].instance.size().height()
                )
        except:
            self._cover_target_size = None

        # cache logo target size
        try:
            if self["vod_logo"].instance:
                self._logo_target_size = (
                    self["vod_logo"].instance.size().width(),
                    self["vod_logo"].instance.size().height()
                )
        except:
            self._logo_target_size = None

        # cache backdrop target size (your existing code)
        try:
            if self["vod_backdrop"].instance:
                self._backdrop_target_size = (
                    self["vod_backdrop"].instance.size().width(),
                    self["vod_backdrop"].instance.size().height()
                )
        except:
            self._backdrop_target_size = None

        if not self._backdrop_target_size and self._mask2_size:
            self._backdrop_target_size = self._mask2_size

    def _stopTimerSeries(self):
        # Stop any scheduled timer fire
        try:
            if self.timerSeries:
                self.timerSeries.stop()
        except:
            pass

        # Invalidate any in-flight downloadPage callbacks (zap protection)
        try:
            self._vod_req_id += 1
        except:
            self._vod_req_id = 1

    def _new_tmp_file(self, prefix, suffix):
        fd = None
        path = None

        try:
            fd, path = tempfile.mkstemp(prefix=prefix, suffix=suffix, dir=dir_tmp)
        except:
            fd, path = tempfile.mkstemp(prefix=prefix, suffix=suffix)

        try:
            os.close(fd)
        except:
            pass

        return path

    def _safe_unlink(self, path):
        try:
            if path and os.path.exists(path):
                os.remove(path)
        except:
            pass

    def _cleanup_series_assets(self):
        self._safe_unlink(self._tmp_cover)
        self._safe_unlink(self._tmp_logo)
        self._safe_unlink(self._tmp_backdrop_src)
        self._safe_unlink(self._tmp_backdrop_out)

        self._tmp_cover = None
        self._tmp_logo = None
        self._tmp_backdrop_src = None
        self._tmp_backdrop_out = None

        if self.cover_download_deferred:
            try:
                self.cover_download_deferred.cancel()
            except:
                pass
            self.cover_download_deferred = None

        if self.logo_download_deferred:
            try:
                self.logo_download_deferred.cancel()
            except:
                pass
            self.logo_download_deferred = None

        if self.backdrop_download_deferred:
            try:
                self.backdrop_download_deferred.cancel()
            except:
                pass
            self.backdrop_download_deferred = None

    def goUp(self):
        instance = self["main_list"].master.master.instance
        instance.moveSelection(instance.moveUp)
        self.selectionChanged()

    def goDown(self):
        instance = self["main_list"].master.master.instance
        instance.moveSelection(instance.moveDown)
        self.selectionChanged()

    def pageUp(self):
        instance = self["main_list"].master.master.instance
        instance.moveSelection(instance.pageUp)
        self.selectionChanged()

    def pageDown(self):
        instance = self["main_list"].master.master.instance
        instance.moveSelection(instance.pageDown)
        self.selectionChanged()

    def reset(self):
        self["main_list"].setIndex(0)
        self.selectionChanged()

    def createSetup(self, data=None):
        if debugs:
            print("*** createSetup ***")

        self["x_title"].setText("")
        self["x_description"].setText("")

        if self.level == 1:
            self.getCategories()

        elif self.level == 2:
            self.getSeries()

        elif self.level == 3:
            self.getSeasons()

        elif self.level == 4:
            self.getEpisodes()

        self.getSortOrder()
        self.buildLists()

    def getSortOrder(self):
        if debugs:
            print("*** getSortOrder ***")

        if self.level == 1:
            self.sortText = cfg.seriescategoryorder.value
            sortlist = [_("Sort: A-Z"), _("Sort: Z-A"), _("Sort: Original")]
            activelist = self.list1
        elif self.level == 2:
            self.sortText = cfg.seriesorder.value
            sortlist = [_("Sort: A-Z"), _("Sort: Z-A"), _("Sort: Added"), _("Sort: Year"), _("Sort: Original")]
            activelist = self.list2
        else:
            return

        current_sort = self.sortText

        if not current_sort:
            return

        self.sortindex = 0

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
            activelist.sort(key=lambda x: x[1].lower(), reverse=False)
            activelist.sort(key=lambda x: (x[10] or ""), reverse=True)

        elif current_sort == _("Sort: Year"):
            activelist.sort(key=lambda x: x[1].lower(), reverse=False)
            activelist.sort(key=lambda x: (x[14] or ""), reverse=True)

        elif current_sort == _("Sort: Original"):
            activelist.sort(key=lambda x: x[0], reverse=False)

        next_sort_type = next(islice(cycle(sortlist), self.sortindex + 1, None))
        self.sortText = str(next_sort_type)

        self["key_yellow"].setText(self.sortText)
        glob.nextlist[-1]["sort"] = self["key_yellow"].getText()

        if self.level == 1:
            self.list1 = activelist

        elif self.level == 2:
            self.list2 = activelist

        elif self.level == 3:
            self.list3 = activelist

        elif self.level == 4:
            self.list4 = activelist

    def buildLists(self):
        if debugs:
            print("*** buildLists ***")

        if self.level == 1:
            self.buildCategories()

        elif self.level == 2:
            self.buildSeries()

        elif self.level == 3:
            self.buildSeasons()

        elif self.level == 4:
            self.buildEpisodes()

        self.resetButtons()
        self.selectionChanged()

    def getCategories(self):
        if debugs:
            print("*** getCategories **")

        index = 0
        self.list1 = []
        self.prelist = []

        # no need to download. Already downloaded and saved in playlist menu
        currentPlaylist = glob.active_playlist
        currentCategoryList = currentPlaylist.get("data", {}).get("series_categories", [])
        currentHidden = set(currentPlaylist.get("player_info", {}).get("serieshidden", []))

        hiddenfavourites = "-1" in currentHidden
        hidden = "0" in currentHidden

        i = 0

        self.prelist.extend([
            [i, _("FAVOURITES"), "-1", hiddenfavourites],
            [i + 1, _("ALL"), "0", hidden]
        ])

        for index, item in enumerate(currentCategoryList, start=len(self.prelist)):
            if not isinstance(item, dict):
                continue

            category_name = item.get("category_name", "No category")
            category_id = item.get("category_id", "999999")
            hidden = category_id in currentHidden
            self.list1.append([index, str(category_name), str(category_id), hidden])

        glob.originalChannelList1 = self.list1[:]

    def getSeries(self):
        if debugs:
            print("*** getSeries ***")

        response = ""

        if self.chosen_category == "favourites":
            response = glob.active_playlist["player_info"].get("seriesfavourites", [])
        else:
            response = self.downloadApiData(glob.nextlist[-1]["next_url"])

        def sanitize_false(obj):
            if isinstance(obj, dict):
                return {k: sanitize_false(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [sanitize_false(i) for i in obj]
            elif obj is False:
                return ""
            else:
                return obj

        response = sanitize_false(response)

        self.series_info = ""
        index = 0
        self.list2 = []

        self.storedtitle = ""
        self.storedseason = ""
        self.storedepisode = ""
        self.storedyear = ""
        self.storedcover = ""
        self.storedtmdb = ""
        self.storedbackdrop = ""
        self.storedlogo = ""
        self.storeddescription = ""
        self.storedcast = ""
        self.storeddirector = ""
        self.storedgenre = ""
        self.storedreleasedate = ""
        self.storedrating = ""
        self.tmdbretry = 0

        if response:
            for index, channel in enumerate(response):
                name = str(channel.get("name", ""))

                if not name or name == "None":
                    continue

                if name and '\" ' in name:
                    parts = name.split('\" ', 1)
                    if len(parts) > 1:
                        name = parts[0]

                if "stream_type" in channel and channel["stream_type"] and (channel["stream_type"] not in ["movie", "series"]):
                    continue

                series_id = channel.get("series_id", "")
                if not series_id:
                    continue

                hidden = str(series_id) in glob.active_playlist["player_info"]["seriestitleshidden"]

                cover = str(channel.get("cover", ""))
                if cover and cover.startswith("http"):
                    try:
                        cover = cover.replace(r"\/", "/")
                    except:
                        pass

                    if cover == "https://image.tmdb.org/t/p/w600_and_h900_bestv2" or cover == "https://image.tmdb.org/t/p/w500":
                        cover = ""

                    if cover.startswith("https://image.tmdb.org/t/p/") or cover.startswith("http://image.tmdb.org/t/p/"):
                        dimensions = cover.partition("/p/")[2].partition("/")[0]

                        if screenwidth.width() <= 1280:
                            cover = cover.replace(dimensions, "w200")
                        elif screenwidth.width() <= 1920:
                            cover = cover.replace(dimensions, "w300")
                        else:
                            cover = cover.replace(dimensions, "w400")
                else:
                    cover = ""

                last_modified = str(channel.get("last_modified", "0"))

                category_id = str(channel.get("category_id", ""))
                if self.chosen_category == "all" and str(category_id) in glob.active_playlist["player_info"]["serieshidden"]:
                    continue

                rating = str(channel.get("rating", ""))

                plot = str(channel.get("plot", ""))

                cast = str(channel.get("cast", ""))

                director = str(channel.get("director", ""))

                genre = str(channel.get("genre", ""))

                tmdb = channel.get("tmdb", "")

                releaseDate = (channel.get("releaseDate") or channel.get("release_date") or channel.get("releasedate") or "")
                releaseDate = str(releaseDate) if releaseDate is not None else ""

                year = str(channel.get("year", ""))

                if year == "":
                    matches = self._re_year.findall(name)
                    if matches:
                        year = str(matches[-1])

                if not year and releaseDate:
                    year_match = re.match(r'(\d{4})', releaseDate)
                    if year_match:
                        year = year_match.group(1)

                if year:
                    self.storedyear = year
                else:
                    self.storedyear = ""

                backdrop_path = channel.get("backdrop_path", "")

                if backdrop_path:
                    try:
                        backdrop_path = channel["backdrop_path"][0]
                    except:
                        pass

                favourite = False
                if "seriesfavourites" in glob.active_playlist["player_info"]:
                    for fav in glob.active_playlist["player_info"]["seriesfavourites"]:
                        if str(series_id) == str(fav["series_id"]):
                            favourite = True
                            break
                else:
                    glob.active_playlist["player_info"]["vodfavourites"] = []

                next_url = "{}&action=get_series_info&series_id={}".format(str(self.player_api), str(series_id))

                # 0 index, 1 name, 2 series_id, 3 cover, 4 plot, 5 cast, 6 director, 7 genre, 8 releaseDate, 9 rating, 10 last_modified, 11 next_url, 12 tmdb, 13 hidden, 14 year, 15 backdrop
                self.list2.append([index, str(name), str(series_id), str(cover), str(plot), str(cast), str(director), str(genre), str(releaseDate), str(rating), str(last_modified), str(next_url), str(tmdb), hidden, str(year), str(backdrop_path), favourite])

        glob.originalChannelList2 = self.list2[:]

    def getSeasons(self):
        if debugs:
            print("**** getSeasons ****")

        if not self.series_info:
            response = self.downloadApiData(glob.nextlist[-1]["next_url"])
            self.series_info = response
        else:
            response = self.series_info

        def sanitize_false(obj):
            if isinstance(obj, dict):
                return {k: sanitize_false(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [sanitize_false(i) for i in obj]
            elif obj is False:
                return ""
            else:
                return obj

        response = sanitize_false(response)

        index = 0
        self.list3 = []

        if response:
            currentChannelList = response
            if "info" in currentChannelList and currentChannelList["info"]:
                infodict = response["info"]
                if infodict:
                    tmdb = infodict.get("tmdb", self.tmdb2)
                    if tmdb:
                        self.tmdb2 = tmdb
                    name = infodict.get("name", self.title2)
                    cover = infodict.get("cover", self.cover2)
                    if not cover.startswith("http"):
                        cover = self.cover2

                    overview = infodict.get("plot", self.plot2)
                    cast = infodict.get("cast", self.cast2)
                    director = infodict.get("director", self.director2)
                    genre = infodict.get("genre", self.genre2)
                    airdate = infodict.get("releaseDate") or infodict.get("release_date") or self.releaseDate2
                    rating = infodict.get("rating", self.rating2)
                    last_modified = infodict.get("last_modified", "0")
                    backdrop_path = infodict.get("backdrop_path", self.backdrop_path2)

                    if "backdrop_path" in infodict and infodict["backdrop_path"]:
                        try:
                            backdrop_path = infodict["backdrop_path"][0]
                        except:
                            pass
            else:
                return

            if "episodes" in currentChannelList and currentChannelList["episodes"]:
                episodes = currentChannelList["episodes"]
                seasonlist = []
                self.isdict = True

                try:
                    seasonlist = list(episodes.keys())
                except Exception as e:
                    print(e)

                    self.isdict = False
                    x = 0
                    for item in episodes:
                        seasonlist.append(x)
                        x += 1

                if seasonlist:
                    parent_index = glob.nextlist[1]["index"]
                    parent_id = self.list2[parent_index][2]

                    for index, season in enumerate(seasonlist):
                        name = _("Season ") + str(season)

                        if self.isdict:
                            season_number = episodes[str(season)][0]["season"]
                        else:
                            season_number = episodes[season][0]["season"]

                        series_id = 0
                        hidden = False

                        if "seasons" in currentChannelList and currentChannelList["seasons"]:
                            for item in currentChannelList["seasons"]:
                                if "season_number" in item and str(item["season_number"]) == str(season_number):

                                    if "airdate" in item and item["airdate"]:
                                        airdate = item["airdate"]
                                    elif "air_date" in item and item["air_date"]:
                                        airdate = item["air_date"]

                                    if "name" in item and item["name"]:
                                        name = item["name"]

                                    if "overview" in item and item["overview"] and len(item["overview"]) > 50 and "http" not in item["overview"]:
                                        overview = item["overview"]

                                    if "cover_tmdb" in item and item["cover_tmdb"] and item["cover_tmdb"].startswith("http") and len(item["cover_tmdb"]) > 50:
                                        cover = item["cover_tmdb"]

                                    elif "cover_big" in item and item["cover_big"] and item["cover_big"].startswith("http") and len(item["cover_big"]) > 50:
                                        cover = item["cover_big"]

                                    elif "cover" in item and item["cover"] and item["cover"].startswith("http") and len(item["cover_big"]) > 50:
                                        cover = item["cover"]

                                    if "id" in item and item["id"]:
                                        series_id = item["id"]
                                    break

                        if str(series_id) in glob.active_playlist["player_info"]["seriesseasonshidden"]:
                            hidden = True

                        if cover and cover.startswith("http"):

                            try:
                                cover = cover.replace(r"\/", "/")
                            except:
                                pass

                            if cover == "https://image.tmdb.org/t/p/w600_and_h900_bestv2" or cover == "https://image.tmdb.org/t/p/w500":
                                cover = self.cover2

                            if cover.startswith("https://image.tmdb.org/t/p/") or cover.startswith("http://image.tmdb.org/t/p/"):
                                dimensions = cover.partition("/p/")[2].partition("/")[0]

                                if screenwidth.width() <= 1280:
                                    cover = cover.replace(dimensions, "w200")
                                elif screenwidth.width() <= 1920:
                                    cover = cover.replace(dimensions, "w300")
                                else:
                                    cover = cover.replace(dimensions, "w400")

                        next_url = self.seasons_url

                        # 0 index, 1 name, 2 series_id, 3 cover, 4 overview, 5 cast, 6 director, 7 genre, 8 airdate, 9 rating, 10 last_modified, 11 next_url, 12 tmdb, 13 hidden, 14 season_number, 15 backdrop, 16 parent_index, 17 parent_id
                        self.list3.append([index, str(name), str(series_id), str(cover), str(overview), str(cast), str(director), str(genre), str(airdate), str(rating), str(last_modified), str(next_url), tmdb, hidden, season_number, str(backdrop_path), parent_index, str(parent_id)])

                self.list3.sort(key=self.natural_keys)

            if cover:
                self.storedcover = cover

        glob.originalChannelList3 = self.list3[:]

    def getEpisodes(self):
        if debugs:
            print("**** getEpisodes ****")

        response = self.series_info
        index = 0
        self.list4 = []
        currentChannelList = response

        shorttitle = self.title2
        cover = self.storedcover

        plot = ""
        cast = self["vod_cast"].getText()
        director = self["vod_director"].getText()
        genre = ""
        releasedate = ""
        rating = ""

        tmdb_id = self.tmdb2
        last_modified = "0"

        if currentChannelList:
            if "info" in currentChannelList:
                if "name" in currentChannelList["info"] and currentChannelList["info"]["name"]:
                    shorttitle = currentChannelList["info"]["name"]

                if "cover" in currentChannelList["info"] and currentChannelList["info"]["cover"]:
                    cover = currentChannelList["info"]["cover"]

                if "plot" in currentChannelList["info"] and currentChannelList["info"]["plot"]:
                    plot = currentChannelList["info"]["plot"]

                if "cast" in currentChannelList["info"] and currentChannelList["info"]["cast"]:
                    cast = currentChannelList["info"]["cast"]

                if "director" in currentChannelList["info"] and currentChannelList["info"]["director"]:
                    director = currentChannelList["info"]["director"]

                if "genre" in currentChannelList["info"] and currentChannelList["info"]["genre"]:
                    genre = currentChannelList["info"]["genre"]

                if "releaseDate" in currentChannelList["info"] and currentChannelList["info"]["releaseDate"]:
                    releasedate = currentChannelList["info"]["releaseDate"]

                elif "release_date" in currentChannelList["info"] and currentChannelList["info"]["release_date"]:
                    releasedate = currentChannelList["info"]["release_date"]

                if "rating" in currentChannelList["info"] and currentChannelList["info"]["rating"]:
                    rating = currentChannelList["info"]["rating"]

                if "last_modified" in currentChannelList["info"] and currentChannelList["info"]["last_modified"]:
                    last_modified = currentChannelList["info"]["last_modified"]

                if "tmdb_id" in currentChannelList["info"] and currentChannelList["info"]["tmdb_id"]:
                    tmdb_id = currentChannelList["info"]["tmdb_id"]

            if "episodes" in currentChannelList:
                if currentChannelList["episodes"]:

                    season_number = str(self.storedseason)
                    if self.isdict is False:
                        season_number = int(self.storedseason)

                    parent_index = glob.nextlist[1]["index"]
                    parent_id = self.list2[parent_index][2]

                    for index, item in enumerate(currentChannelList["episodes"][season_number]):
                        title = ""
                        stream_id = ""
                        container_extension = "mp4"
                        # tmdb_id = ""
                        duration = ""
                        hidden = False

                        if "id" in item:
                            stream_id = item["id"]
                        else:
                            continue

                        if "title" in item:
                            title = item["title"].replace(str(shorttitle) + " - ", "")
                            title = re.sub(r'^.*?\.', '', title)

                        if "container_extension" in item:
                            container_extension = item["container_extension"]

                        if "episode_num" in item:
                            episode_num = item["episode_num"]

                        if "info" in item:
                            if "releaseDate" in item["info"]:
                                releasedate = item["info"]["releaseDate"]

                            elif "release_date" in item["info"]:
                                releasedate = item["info"]["release_date"]

                            elif "air_date" in item["info"]:
                                releasedate = item["info"]["air_date"]

                            if "plot" in item["info"]:
                                plot = item["info"]["plot"]

                            if "duration" in item["info"]:
                                duration = item["info"]["duration"]

                            if "rating" in item["info"]:
                                rating = item["info"]["rating"]

                            if "seasons" in currentChannelList:
                                if currentChannelList["seasons"]:
                                    for season in currentChannelList["seasons"]:
                                        if int(season["season_number"]) == int(season_number):
                                            if "cover" in season and season["cover"]:
                                                cover = season["cover"]

                                            if "cover_big" in season and season["cover_big"]:
                                                cover = season["cover_big"]
                                            break

                        if cover:
                            cover = cover.replace(r"\/", "/")
                            if cover and cover.startswith("http"):
                                if cover == "https://image.tmdb.org/t/p/w600_and_h900_bestv2" or cover == "https://image.tmdb.org/t/p/w500":
                                    cover = ""

                                if cover.startswith("https://image.tmdb.org/t/p/") or cover.startswith("http://image.tmdb.org/t/p/"):
                                    dimensions = cover.partition("/p/")[2].partition("/")[0]
                                    if screenwidth.width() <= 1280:
                                        cover = cover.replace(dimensions, "w200")
                                    elif screenwidth.width() <= 1920:
                                        cover = cover.replace(dimensions, "w300")
                                    else:
                                        cover = cover.replace(dimensions, "w400")
                            else:
                                cover = ""

                        hidden = str(stream_id) in glob.active_playlist["player_info"]["seriesepisodeshidden"]

                        next_url = "{}/series/{}/{}/{}.{}".format(self.host, self.username, self.password, stream_id, container_extension)

                        # 0 index, 1 title, 2 stream_id, 3 cover, 4 plot, 5 cast, 6 director, 7 genre, 8 releasedate, 9 rating, 10 last_modified, 11 next_url, 12 tmdb_id, 13 hidden, 14 duration, 15 container_extension, 16 shorttitle, 17 episode_num, 18 parent_index, 19 parent_id
                        self.list4.append([index, str(title), str(stream_id), str(cover), str(plot), str(cast), str(director), str(genre), str(releasedate), str(rating), str(last_modified), str(next_url), str(tmdb_id), hidden, str(duration), str(container_extension),  str(shorttitle), episode_num, parent_index, str(parent_id)])

        glob.originalChannelList4 = self.list4[:]

    def downloadApiData(self, url):
        if debugs:
            print("*** downloadApiData ***", url)

        retries = Retry(total=1, backoff_factor=1)
        adapter = HTTPAdapter(max_retries=retries)

        with requests.Session() as http:
            http.mount("http://", adapter)
            http.mount("https://", adapter)

            try:
                response = http.get(url, headers=hdr, timeout=(10, 30), verify=False)
                response.raise_for_status()

                if response.status_code == requests.codes.ok:
                    try:
                        if pythonVer == 3:
                            return clean_names(response.json())
                        else:
                            return response.json()
                    except ValueError:
                        print("JSON decoding failed.")
                        return None
            except Exception as e:
                print("Error occurred during API data download:", e)
                self.session.openWithCallback(self.back, MessageBox, _("Server error or invalid link."), MessageBox.TYPE_ERROR, timeout=3)

    def buildCategories(self):
        if debugs:
            print("*** buildCategories ***")

        self.hideVod()

        if self["key_blue"].getText() != _("Reset Search"):
            self.pre_list = [buildCategoryList(x[0], x[1], x[2], x[3], self._px_more) for x in self.prelist if not x[3]]
        else:
            self.pre_list = []

        self.main_list = [buildCategoryList(x[0], x[1], x[2], x[3], self._px_more) for x in self.list1 if not x[3]]

        self["main_list"].setList(self.pre_list + self.main_list)

        if self["main_list"].getCurrent():
            self["main_list"].setIndex(glob.nextlist[-1]["index"])

    def buildSeries(self):
        if debugs:
            print("*** buildSeries ***")

        self.main_list = []

        # 0 index, 1 name, 2 series_id, 3 cover, 4 plot, 5 cast, 6 director, 7 genre, 8 releaseDate, 9 rating, 10 last_modified, 11 next_url, 12 tmdb, 13 hidden, 14 year, 15 backdrop, 16 favourite
        self.main_list = [buildSeriesTitlesList(x[0], x[1], x[2], x[3], x[4], x[5], x[6], x[7], x[8], x[9], x[10], x[11], x[12], x[13], x[14], x[15], x[16], self._px_more, self._px_fav) for x in self.list2 if not x[13]]
        self["main_list"].setList(self.main_list)

        self.showVod()

        if self["main_list"].getCurrent():
            self["main_list"].setIndex(glob.nextlist[-1]["index"])

    def buildSeasons(self):
        if debugs:
            print("*** buildSeasons ***")

        self.main_list = []

        self.main_list = [buildSeriesSeasonsList(x[0], x[1], x[2], x[3], x[4], x[5], x[6], x[7], x[8], x[9], x[10], x[11], x[12], x[13], x[14], x[15], x[16], x[17], self._px_more) for x in self.list3 if not x[13]]
        self["main_list"].setList(self.main_list)

        if self["main_list"].getCurrent():
            self["main_list"].setIndex(glob.nextlist[-1]["index"])

    def buildEpisodes(self):
        if debugs:
            print("*** buildEpisodes ***")

        self.main_list = []

        watched_set = set(str(x) for x in glob.active_playlist["player_info"].get("serieswatched", []))

        self.main_list = [buildSeriesEpisodesList(x[0], x[1], x[2], x[3], x[4], x[5], x[6], x[7], x[8], x[9], x[10], x[11], x[12], x[13], x[14], x[15], x[16], x[17], x[18], x[19], watched_set, self._px_play, self._px_watched) for x in self.list4 if not x[13]]
        self["main_list"].setList(self.main_list)
        if self["main_list"].getCurrent():
            self["main_list"].setIndex(glob.nextlist[-1]["index"])

    def displaySeriesData(self):
        if debugs:
            print("*** displaySeriesData ***")

        if self["main_list"].getCurrent():
            if cfg.TMDB.value is True:
                if self.level != 1:
                    self.tmdbValid = True
                    self.tmdbfailedcount = 0
                    self.getTMDB()

            else:
                self.displayTMDB()

    def selectionChanged(self):
        if debugs:
            print("*** selectionChanged ***")

        self.tmdbresults = {}
        self.tmdbretry = 0

        current_item = self["main_list"].getCurrent()

        if current_item:
            channel_title = current_item[0]
            current_index = self["main_list"].getIndex()

            glob.currentchannellistindex = current_index
            glob.nextlist[-1]["index"] = current_index

            position = current_index + 1
            position_all = len(self.pre_list) + len(self.main_list) if self.level == 1 else len(self.main_list)
            page = (position - 1) // self.itemsperpage + 1
            page_all = (position_all + self.itemsperpage - 1) // self.itemsperpage

            self["page"].setText(_("Page: ") + "{}/{}".format(page, page_all))
            self["listposition"].setText("{}/{}".format(position, position_all))

            parts = []

            if self.main_title:
                parts.append(self.main_title)

            if self.group_title:
                parts.append(self.group_title)

            if self.series_group_title:
                parts.append(self.series_group_title)

            if channel_title:
                parts.append(channel_title)

            self["main_title"].setText(": ".join(parts))

            if self.level == 2:
                self.loadDefaultCover()
                self.loadDefaultBackdrop()

                self["vod_cover"].hide()
                self["vod_logo"].hide()
                self["vod_backdrop"].hide()

            if self.level == 3:
                self.loadDefaultCover()
                self["vod_cover"].hide()
                self["vod_logo"].hide()

            if self.level != 1:
                self.clearVod()
                self._stopTimerSeries()
                self._cleanup_series_assets()
                self.timerSeries.start(300, True)

        else:
            position = 0
            position_all = 0
            page = 0
            page_all = 0

            self["page"].setText(_("Page: ") + "{}/{}".format(page, page_all))
            self["listposition"].setText("{}/{}".format(position, position_all))
            self["key_yellow"].setText("")
            self["key_blue"].setText("")
            self.hideVod()

    def strip_foreign_mixed(self, text):
        has_ascii = bool(self._re_has_ascii.search(text))
        has_non_ascii = bool(self._re_has_non_ascii.search(text))

        if has_ascii and has_non_ascii:
            text = self._re_remove_non_ascii.sub('', text)

        return text

    def stripjunk(self, text, database=None):
        searchtitle = text

        # Move "the" from the end to the beginning (case-insensitive)
        if self._re_end_the.search(searchtitle.strip().lower()):
            searchtitle = "The " + searchtitle[:-3].strip()

        # remove xx: at start (case-insensitive)
        searchtitle = self._re_prefix_xx_colon.sub('', searchtitle)

        # remove xx|xx at start (case-insensitive)
        searchtitle = self._re_prefix_xx_pipe_xx.sub('', searchtitle)

        # remove all leading content between and including || or |
        searchtitle = self._re_leading_doublepipes.sub('', searchtitle)
        searchtitle = self._re_leading_singlepipe_block.sub('', searchtitle)
        searchtitle = self._re_any_pipe_block.sub('', searchtitle)

        # remove all leading content between and including ┃┃ or ┃
        searchtitle = self._re_leading_doublebars.sub('', searchtitle)
        searchtitle = self._re_leading_singlebar_block.sub('', searchtitle)
        searchtitle = self._re_leading_singlebar_block.sub('', searchtitle)
        searchtitle = self._re_any_bar_block.sub('', searchtitle)

        # remove all content between and including () unless it's all digits
        searchtitle = self._re_parens.sub('', searchtitle)

        # remove all content between and including []
        searchtitle = self._re_brackets.sub('', searchtitle)

        # remove trailing year (but not if the whole title *is* a year)
        if not self._re_is_year_only.match(searchtitle.strip()):
            searchtitle = self._re_trailing_year.sub('', searchtitle)

        # remove up to 6 characters followed by space and dash at start (e.g. "EN -", "BE-NL -")
        searchtitle = self._re_lang_dash_prefix.sub('', searchtitle)

        # Strip foreign / non-ASCII characters (only when mixed)
        searchtitle = self.strip_foreign_mixed(searchtitle)

        # Bad substrings to strip (case-insensitive)
        searchtitle = self._re_bad_strings.sub('', searchtitle)

        # Bad suffixes to remove (case-insensitive, only if at end)
        searchtitle = self._re_bad_suffix.sub('', searchtitle)

        # Replace '.', '_', "'", '*' with space
        searchtitle = self._re_dots_underscores.sub(' ', searchtitle)

        # Trim leading/trailing hyphens and whitespace
        searchtitle = searchtitle.strip(' -').strip()

        return str(searchtitle)

    def getTMDB(self):
        if debugs:
            print("**** getTMDB ***")

        current_item = self["main_list"].getCurrent()

        if current_item:
            if self.level == 2:
                title = current_item[0]
                year = current_item[13]
                tmdb = current_item[14]
                cover = current_item[5]

                backdrop = current_item[15]

                if not year:
                    # Get year from release date
                    try:
                        year = current_item[10][:4]
                    except IndexError:
                        year = ""

                if year:
                    self.storedyear = year
                else:
                    self.storedyear = ""
                if title:
                    self.storedtitle = title
                if cover:
                    self.storedcover = cover
                if backdrop:
                    self.storedbackdrop = backdrop

            else:
                title = self.storedtitle
                year = self.storedyear

                if self.level == 3:
                    tmdb = current_item[15]

                if self.level == 4:
                    tmdb = current_item[14]

            if tmdb and self.tmdbValid and tmdb != "0":
                self.getTMDBDetails(tmdb)
                return

            try:
                os.remove(os.path.join(dir_tmp, "search.txt"))
            except:
                pass

            searchtitle = self.stripjunk(title, "TMDB")
            searchtitle = quote(searchtitle, safe="")

            searchurl = 'http://api.themoviedb.org/3/search/tv?api_key={}&query={}'.format(self.check(self.token), searchtitle)
            if self.storedyear:
                searchurl = 'http://api.themoviedb.org/3/search/tv?api_key={}&first_air_date_year={}&query={}'.format(self.check(self.token), self.storedyear, searchtitle)

            if pythonVer == 3:
                searchurl = searchurl.encode()

            filepath = os.path.join(dir_tmp, "search.txt")
            try:
                downloadPage(searchurl, filepath, timeout=10).addCallback(self.processTMDB).addErrback(self.failed)
            except Exception as e:
                print("download TMDB error {}".format(e))

    def failed(self, data=None):
        if debugs:
            print("*** failed ***")

        if data:
            print(data)
            self.tmdbValid = False
            self.getTMDB()

    def processTMDB(self, result=None):
        if debugs:
            print("*** processTMDB ***")

        resultid = ""
        search_file_path = os.path.join(dir_tmp, "search.txt")
        try:
            with codecs.open(search_file_path, "r", encoding="utf-8") as f:
                response = f.read()

            if response:
                self.searchresult = json.loads(response)
                if "results" in self.searchresult and self.searchresult["results"]:
                    resultid = self.searchresult["results"][0].get("id")
                    self.tmdb2 = resultid

                    if not resultid:
                        self.displayTMDB()
                        return

                    self.getTMDBDetails(resultid)
                else:
                    self.storedyear = ""
                    self.tmdbretry += 1
                    if self.tmdbretry < 2:
                        self.getTMDB()
                    else:
                        self.tmdbretry = 0
                        self.displayTMDB()
                        return

        except Exception as e:
            print("Error processing TMDB response:", e)

    def getTMDBDetails(self, resultid=None):
        if debugs:
            print(" *** getTMDBDetails ***")

        detailsurl = ""

        try:
            os.remove(os.path.join(dir_tmp, "search.txt"))
        except OSError:
            pass

        language = cfg.TMDBLanguage2.value
        languagestr = ""

        if language:
            languagestr = "&language=" + str(language)

        if self.level == 2:
            detailsurl = "http://api.themoviedb.org/3/tv/{}?api_key={}&append_to_response=credits,images,content_ratings{}&include_image_language=en".format(
                resultid, self.check(self.token), languagestr
            )

        elif self.level == 3:
            self.storedseason = self["main_list"].getCurrent()[12]
            detailsurl = "http://api.themoviedb.org/3/tv/{}/season/{}?api_key={}&append_to_response=credits,images,content_ratings{}&include_image_language=en".format(
                resultid, self.storedseason, self.check(self.token), languagestr
            )

        elif self.level == 4:
            self.storedepisode = self["main_list"].getCurrent()[18]
            detailsurl = "http://api.themoviedb.org/3/tv/{}/season/{}/episode/{}?api_key={}&append_to_response=credits,images,content_ratings{}&include_image_language=en".format(
                resultid, self.storedseason, self.storedepisode, self.check(self.token), languagestr
            )

        if pythonVer == 3:
            detailsurl = detailsurl.encode()

        filepath = os.path.join(dir_tmp, "search.txt")

        try:
            downloadPage(detailsurl, filepath, timeout=10).addCallback(self.processTMDBDetails).addErrback(self.failed2)
        except Exception as e:
            print("download TMDB details error:", e)

    def failed2(self, data=None):
        if debugs:
            print("*** failed 2 ***")

        if data:
            print(data)
            if self.level == 2:
                self.tmdbValid = False
                if self.repeatcount == 0:
                    self.getTMDB()
                    self.repeatcount += 1

            else:
                self.displayTMDB()
                return

    def processTMDBDetails(self, result=None):
        if debugs:
            print("*** processTMDBDetails ***")

        response = ""

        self.tmdbresults = {}
        self.tmdbdetails = []
        # director = []
        # country = []
        # logos = []

        try:
            with codecs.open(os.path.join(dir_tmp, "search.txt"), "r", encoding="utf-8") as f:
                response = f.read()
        except Exception as e:
            print("Error reading TMDB response:", e)
            return

        if not response:
            return

        try:
            self.tmdbdetails = json.loads(response, object_pairs_hook=OrderedDict)
        except Exception as e:
            print("Error parsing TMDB response:", e)
            return

        if not self.tmdbdetails:
            return

        name = self.tmdbdetails.get("name", "")
        if name:
            self.tmdbresults["name"] = str(name).strip()

        overview = self.tmdbdetails.get("overview")
        if overview:
            self.tmdbresults["description"] = str(overview).strip()

        # Handle rating
        vote_average = self.tmdbdetails.get("vote_average")
        if vote_average not in (None, 0, 0.0, "0", "0.0"):
            try:
                rating = float(vote_average)
                self.tmdbresults["rating"] = "{:.1f}".format(round(rating, 1))
            except (ValueError, TypeError) as e:
                print("*** rating error ***", e)
                self.tmdbresults["rating"] = "0.0"
        else:
            self.tmdbresults["rating"] = "0.0"

        if self.level == 2:
            original_name = self.tmdbdetails.get("original_name", "")
            if original_name:
                self.tmdbresults["o_name"] = str(original_name).strip()

            runtime = 0

            try:
                episode_times = self.tmdbdetails.get("episode_run_time") or []
                if episode_times:
                    runtime = episode_times[0]
                else:
                    runtime = self.tmdbdetails.get("runtime", 0)

                if runtime and runtime != 0:
                    runtime = int(runtime)

                    self.tmdbresults["originalduration"] = runtime

                    duration_timedelta = timedelta(minutes=runtime)
                    formatted_time = "{:0d}h {:02d}m".format(
                        duration_timedelta.seconds // 3600,
                        (duration_timedelta.seconds % 3600) // 60
                    )

                    self.tmdbresults["duration"] = formatted_time

            except (TypeError, ValueError, IndexError) as e:
                print("Error processing runtime:", e)

            first_air_date = self.tmdbdetails.get("first_air_date", "")
            if first_air_date:
                self.tmdbresults["releaseDate"] = str(first_air_date).strip()

            # Handle genres
            genres = self.tmdbdetails.get("genres")
            if genres:
                try:
                    genre = " / ".join(str(g["name"]) for g in genres[:4])
                    self.tmdbresults["genre"] = genre
                except (KeyError, TypeError):
                    pass

            country = None
            origin_country = self.tmdbdetails.get("origin_country")
            if origin_country:
                try:
                    country = origin_country[0]
                    self.tmdbresults["country"] = country
                except (IndexError, TypeError):
                    pass

            if not country:
                production_countries = self.tmdbdetails.get("production_countries")
                if production_countries:
                    try:
                        country = ", ".join(str(pc["name"]) for pc in production_countries)
                        self.tmdbresults["country"] = country
                    except (KeyError, TypeError):
                        pass

        if self.level != 4:
            # Handle credits
            credits = self.tmdbdetails.get("credits")
            if credits:
                cast_list = credits.get("cast")
                if cast_list:
                    try:
                        cast = ", ".join(actor["name"] for actor in cast_list[:10])
                        self.tmdbresults["cast"] = cast
                    except (KeyError, TypeError):
                        pass

                crew_list = credits.get("crew")
                if crew_list:
                    try:
                        directors = [
                            actor["name"] for actor in crew_list
                            if actor.get("job") == "Director"
                        ]
                        if directors:
                            self.tmdbresults["director"] = ", ".join(directors)
                    except (KeyError, TypeError):
                        pass

            # Handle images - single lookups
            poster_path = self.tmdbdetails.get("poster_path", "")
            backdrop_path = self.tmdbdetails.get("backdrop_path", "")

            logo_path = ""
            images = self.tmdbdetails.get("images")
            if images:
                logos = images.get("logos")
                if logos:
                    logo_path = logos[0].get("file_path", "")

            # Build image URLs only if paths exist
            if poster_path:
                self.tmdbresults["cover_big"] = "http://image.tmdb.org/t/p/{}/{}".format(
                    self._tmdb_coversize, poster_path
                )

            if backdrop_path:
                self.tmdbresults["backdrop_path"] = "http://image.tmdb.org/t/p/{}/{}".format(
                    self._tmdb_backdropsize, backdrop_path
                )

            if logo_path:
                self.tmdbresults["logo"] = "http://image.tmdb.org/t/p/{}/{}".format(
                    self._tmdb_logosize, logo_path
                )

        if self.level != 2:
            air_date = self.tmdbdetails.get("air_date", "")
            if air_date:
                self.tmdbresults["releaseDate"] = str(air_date).strip()

        if self.level == 4:
            run_time = self.tmdbdetails.get("run_time") or []
            if run_time:
                runtime = run_time[0]
            else:
                runtime = self.tmdbdetails.get("runtime", 0)

            if runtime:
                try:
                    runtime = int(runtime)

                    duration_timedelta = timedelta(minutes=runtime)
                    formatted_time = "{:0d}h {:02d}m".format(
                        duration_timedelta.seconds // 3600,
                        (duration_timedelta.seconds % 3600) // 60
                    )

                    self.tmdbresults["duration"] = formatted_time

                except (TypeError, ValueError, IndexError):
                    pass

        # Handle certification
        def get_certification(data, language_code):
            """Extract certification for given language code with fallbacks"""
            fallback_codes = ["GB", "US"]

            release_dates = data.get("release_dates")
            if not release_dates:
                return None

            results = release_dates.get("results")
            if not results:
                return None

            # Try specified language code first
            if language_code:
                for release in results:
                    if release.get("iso_3166_1") == language_code:
                        release_dates_list = release.get("release_dates")
                        if release_dates_list:
                            return release_dates_list[0].get("certification")

            # Try fallback codes
            for fallback_code in fallback_codes:
                for release in results:
                    if release.get("iso_3166_1") == fallback_code:
                        release_dates_list = release.get("release_dates")
                        if release_dates_list:
                            cert = release_dates_list[0].get("certification")
                            if cert:  # Only return if not empty
                                return cert

            return None

        # Get language and certification
        language = cfg.TMDBLanguage2.value or "en-GB"
        language_code = language.split("-")[-1]  # Get country code

        certification = get_certification(self.tmdbdetails, language_code)
        if certification:
            self.tmdbresults["certification"] = str(certification)

        tagline = self.tmdbdetails.get("tagline")
        if tagline:
            self.tmdbresults["tagline"] = str(tagline).strip()

        self.repeatcount = 0
        self.displayTMDB()

    def displayTMDB(self):
        if debugs:
            print("*** displayTMDB ***")

        current_item = self["main_list"].getCurrent()
        if not current_item or self.level == 1:
            return

        # Initialize fields
        duration = ""
        genre = ""
        release_date = ""
        director = ""
        country = ""
        cast = ""
        certification = ""
        tagline = ""
        rating = 0
        text = ""
        stream_format = ""

        # Level-specific handling
        if self.level == 4:
            duration = current_item[12]
            try:
                time_obj = datetime.strptime(duration, "%H:%M:%S")
                duration = "{:0d}h {:02d}m".format(time_obj.hour, time_obj.minute)
            except Exception:
                pass

            stream_format = current_item[13]

        # Metadata from list
        self["x_title"].setText(current_item[0])
        self["x_description"].setText(current_item[6])
        genre = current_item[9]

        try:
            rating = float(current_item[11])
        except:
            rating = 0

        director = current_item[8]
        cast = current_item[7]
        release_date = current_item[10]
        stream_url = current_item[3]

        if self.level == 4 and stream_url:
            try:
                stream_format = stream_url.split(".")[-1]
            except:
                pass

        # Override with TMDB results
        if self.tmdbresults:
            info = self.tmdbresults

            self["x_title"].setText(str(info.get("name") or info.get("o_name") or current_item[0]).strip())
            self["x_description"].setText(str(info.get("description") or info.get("plot") or current_item[6]).strip())

            tagline = str(info.get("tagline") or "").strip()
            duration = str(info.get("duration") or duration).strip()
            genre = str(info.get("genre") or genre).strip()
            country = str(info.get("country") or country).strip()
            director = str(info.get("director") or director).strip()
            cast = str(info.get("cast") or info.get("actors") or cast).strip()

            certification = str(info.get("certification") or "").strip().upper()
            if certification:
                certification = _("Rating: ") + certification

            for key in ["releaseDate", "release_date", "releasedate"]:
                if key in info and info[key]:
                    try:
                        release_date = datetime.strptime(info[key], "%Y-%m-%d").strftime("%d-%m-%Y")
                        break
                    except:
                        pass

            try:
                rating = float(info.get("rating", rating) or rating)
            except:
                rating = 0

        # Rating text lookup
        rating_texts = {
            (0.0, 0.0): "",
            (0.1, 0.5): "",
            (0.6, 1.0): "",
            (1.1, 1.5): "",
            (1.6, 2.0): "",
            (2.1, 2.5): "",
            (2.6, 3.0): "",
            (3.1, 3.5): "",
            (3.6, 4.0): "",
            (4.1, 4.5): "",
            (4.6, 5.0): "",
            (5.1, 5.5): "",
            (5.6, 6.0): "",
            (6.1, 6.5): "",
            (6.6, 7.0): "",
            (7.1, 7.5): "",
            (7.6, 8.0): "",
            (8.1, 8.5): "",
            (8.6, 9.0): "",
            (9.1, 9.5): "",
            (9.6, 10.0): "",
        }

        for rating_range, rating_text in rating_texts.items():
            if rating_range[0] <= rating <= rating_range[1]:
                text = rating_text
                break
            else:
                text = ""

        # Percent dial
        self["rating_percent"].setText(str(text))

        try:
            rounded_rating = round(rating, 1)
            rating = "{:.1f}".format(rounded_rating)
            if self.tmdbresults:
                self.tmdbresults["rating"] = rating
        except:
            if self.tmdbresults:
                self.tmdbresults["rating"] = str(rating)

        self["rating_text"].setText(str(rating).strip())

        # Facts
        release_date_str = str(release_date).strip()
        try:
            release_date_str = datetime.strptime(release_date_str, "%Y-%m-%d").strftime("%d-%m-%Y")
        except:
            pass

        facts = self.buildFacts(str(certification), str(release_date_str), str(genre), str(duration), str(stream_format))

        # UI fields
        self["facts"].setText(str(facts))
        self["tagline"].setText(str(tagline).strip())
        self["vod_cast"].setText(str(cast).strip())
        self["vod_director"].setText(str(director).strip())
        self["vod_country"].setText(str(country).strip())
        self["vod_cast_label"].setText(_("Cast:") if cast else "")
        self["vod_director_label"].setText(_("Director:") if director else "")
        self["vod_country_label"].setText(_("Country:") if country else "")
        self["overview"].setText(_("Overview") if self["x_description"].getText() else "")

        if (self.level == 2 or self.level == 3) and cfg.channelcovers.value:
            self.downloadBackdrop()
            self.downloadCover()
            self.downloadLogo()

    def resetButtons(self):
        if debugs:
            print("*** resetButtons ***")

        if glob.nextlist[-1]["filter"]:
            self["key_yellow"].setText("")
            self["key_blue"].setText(_("Reset Search"))
            self["key_menu"].setText("")
        else:
            if not glob.nextlist[-1]["sort"]:
                self.sortText = _("Sort: A-Z")
                glob.nextlist[-1]["sort"] = self.sortText

            self["key_blue"].setText(_("Search"))
            self["key_yellow"].setText(_(glob.nextlist[-1]["sort"]))
            self["key_menu"].setText("+/-")

            if self.chosen_category == "favourites":
                self["key_menu"].setText("")

    def downloadCover(self):
        if debugs:
            print("*** downloadCover ***")

        if cfg.channelcovers.value is False:
            return

        if not self["main_list"].getCurrent():
            return

        self._safe_unlink(self._tmp_cover)
        self._tmp_cover = None

        desc_image = ""

        try:
            desc_image = self["main_list"].getCurrent()[5] or ""
        except Exception:
            desc_image = ""

        if self.tmdbresults:
            desc_image = str(self.tmdbresults.get("cover_big") or "").strip()

            if not desc_image:
                desc_image = str(self.tmdbresults.get("movie_image") or "").strip()

            if not desc_image:
                desc_image = self.storedcover or ""

        if not desc_image:
            self.loadDefaultCover()
            return

        if "http" not in desc_image:
            self.loadDefaultCover()
            return

        req_id = self._vod_req_id
        # self.redirect_count = 0

        if self.cover_download_deferred and not self.cover_download_deferred.called:
            self.cover_download_deferred.cancel()

        self.cover_download_deferred = self.agent.request(
            b'GET',
            desc_image.encode(),
            Headers({'User-Agent': [b"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"]})
        )

        self.cover_download_deferred.addCallback(self.coverResponse, req_id)
        self.cover_download_deferred.addErrback(self.coverError, req_id)

    def downloadCoverFromUrl(self, url):
        if debugs:
            print("*** downloadCoverFromUrl ***")

        req_id = self._vod_req_id

        self.cover_download_deferred = self.agent.request(
            b'GET',
            url.encode(),
            Headers({'User-Agent': [b"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"]})
        )
        self.cover_download_deferred.addCallback(self.coverFromUrlResponse, req_id)
        self.cover_download_deferred.addErrback(self.coverError, req_id)

    def coverResponse(self, response, req_id):
        if debugs:
            print("*** coverresponse ***")

        if req_id != self._vod_req_id:
            return

        if response.code == 200:
            d = readBody(response)
            d.addCallback(self.coverBody, req_id)
            return d

        elif response.code in (301, 302):
            location = response.headers.getRawHeaders('location')[0]
            self.downloadCoverFromUrl(location)
        else:
            self.coverError("HTTP error code: %s" % response.code)

    def coverFromUrlResponse(self, response, req_id):
        if req_id != self._vod_req_id:
            return

        if response.code == 200:
            d = readBody(response)
            d.addCallback(self.coverBody, req_id)
            return d

        self.coverError("HTTP error code: %s" % response.code)

    def coverBody(self, body, req_id):
        if debugs:
            print("*** coverbody ***")

        if req_id != self._vod_req_id:
            return

        temp = self._new_tmp_file("xst_vod_cover_", ".jpg")
        self._tmp_cover = temp

        try:
            with open(temp, 'wb') as f:
                f.write(body)
        except:
            self._safe_unlink(temp)
            self._tmp_cover = None
            self.loadDefaultCover()
            return

        self.resizeCover(temp)

    def coverError(self, error, req_id=None):
        if debugs:
            print("*** handle error ***")

        print(error)
        self.loadDefaultCover()

    def loadDefaultCover(self, data=None):
        if debugs:
            print("*** loadDefaultCover ***")

        if self["vod_cover"].instance:
            self["vod_cover"].instance.setPixmapFromFile(os.path.join(skin_directory, "common/blank.png"))

    def resizeCover(self, preview):
        if debugs:
            print("*** resizeCover ***", preview)

        if not (self["main_list"].getCurrent() and self["vod_cover"].instance):
            self._safe_unlink(preview)
            return

        if not os.path.isfile(preview):
            return

        try:
            if self._cover_target_size:
                width, height = self._cover_target_size
            else:
                width = self["vod_cover"].instance.size().width()
                height = self["vod_cover"].instance.size().height()

            self.coverLoad.setPara([width, height, 1, 1, 0, 1, "FF000000"])
            self.coverLoad.startDecode(preview)
        except:
            self._safe_unlink(preview)

    def DecodeCover(self, PicInfo=None):
        if debugs:
            print("*** decodecover ***")

        ptr = self.coverLoad.getData()
        if ptr is not None and self.level != 1:
            self["vod_cover"].instance.setPixmap(ptr)
            self["vod_cover"].show()
        else:
            self["vod_cover"].hide()

        self._safe_unlink(self._tmp_cover)
        self._tmp_cover = None

    def downloadLogo(self):
        if debugs:
            print("*** downloadLogo ***")

        if cfg.channelcovers.value is False:
            return

        if not self["main_list"].getCurrent():
            return

        self._safe_unlink(self._tmp_logo)
        self._tmp_logo = None

        logo_image = ""

        logo_image = self.storedlogo or ""

        if self.tmdbresults:
            tmdb_logo = str(self.tmdbresults.get("logo") or "").strip()
            if tmdb_logo:
                logo_image = tmdb_logo

        if not logo_image:
            self.loadDefaultLogo()
            return

        if "http" not in logo_image:
            self.loadDefaultLogo()
            return

        req_id = self._vod_req_id

        if self.logo_download_deferred and not self.logo_download_deferred.called:
            self.logo_download_deferred.cancel()

        self.logo_download_deferred = self.agent.request(
            b'GET',
            logo_image.encode(),
            Headers({'User-Agent': [b"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"]})
        )
        self.logo_download_deferred.addCallback(self.logoResponse, req_id)
        self.logo_download_deferred.addErrback(self.logoError, req_id)

    def logoResponse(self, response, req_id):
        if debugs:
            print("*** logoresponse ***")

        if req_id != self._vod_req_id:
            return

        if response.code == 200:
            d = readBody(response)
            d.addCallback(self.logoBody, req_id)
            return d

    def logoBody(self, body, req_id):
        if debugs:
            print("*** logobody ***")

        if req_id != self._vod_req_id:
            return

        temp = self._new_tmp_file("xst_vod_logo_", ".png")
        self._tmp_logo = temp

        try:
            with open(temp, 'wb') as f:
                f.write(body)
        except:
            self._safe_unlink(temp)
            self._tmp_logo = None
            self.loadDefaultLogo()
            return

        self.resizeLogo(temp)

    def logoError(self, error, req_id=None):
        if debugs:
            print("*** handle error ***")

        print(error)
        self.loadDefaultLogo()

    def loadDefaultLogo(self, data=None):
        if debugs:
            print("*** loadDefaultLogo ***")

        if self["vod_logo"].instance:
            self["vod_logo"].instance.setPixmapFromFile(os.path.join(skin_directory, "common/blank.png"))

    def resizeLogo(self, preview):
        if debugs:
            print("*** resizeLogo ***")

        if not (self["main_list"].getCurrent() and self["vod_logo"].instance):
            self._safe_unlink(preview)
            return

        if self._logo_target_size:
            size = self._logo_target_size
        else:
            size = (
                self["vod_logo"].instance.size().width(),
                self["vod_logo"].instance.size().height()
            )

        try:
            im = Image.open(preview)

            if im.mode != "RGBA":
                im = im.convert("RGBA")

            # Only thumbnail if image is bigger than target
            if im.size[0] > size[0] or im.size[1] > size[1]:
                try:
                    im.thumbnail(size, Image.Resampling.LANCZOS)
                except:
                    im.thumbnail(size, Image.ANTIALIAS)

            bg = Image.new("RGBA", size, (255, 255, 255, 0))

            # right-aligned logo (same as your original)
            left = size[0] - im.size[0]
            top = 0

            bg.paste(im, (left, top), mask=im)

            bg.save(preview, "PNG", compress_level=0)

            self["vod_logo"].instance.setPixmapFromFile(preview)
            self["vod_logo"].show()

        except Exception as e:
            print("Error resizing logo:", e)
            self["vod_logo"].hide()

        # cleanup tempfile
        self._safe_unlink(preview)
        self._tmp_logo = None

    def downloadBackdrop(self):
        if debugs:
            print("*** downloadBackdrop ***")

        if cfg.channelcovers.value is False:
            return

        if not self["main_list"].getCurrent():
            return

        self._safe_unlink(self._tmp_backdrop_src)
        self._tmp_backdrop_src = None

        backdrop_image = ""

        if self.level == 2:
            try:
                backdrop_image = self["main_list"].getCurrent()[15]
            except Exception:
                backdrop_image = ""

        elif self.level == 3:
            try:
                backdrop_image = self["main_list"].getCurrent()[16]
            except Exception:
                backdrop_image = ""

        if self.tmdbresults:
            backdrop_path = self.tmdbresults.get("backdrop_path")
            if backdrop_path:
                try:
                    if isinstance(backdrop_path, list):
                        tmdb_backdrop = backdrop_path[0]
                    else:
                        tmdb_backdrop = backdrop_path

                    tmdb_backdrop = str(tmdb_backdrop).strip()
                    if tmdb_backdrop:
                        backdrop_image = tmdb_backdrop

                except (TypeError, ValueError, IndexError):
                    pass

            if not backdrop_image:
                backdrop_image = self.storedcover or ""

        if not backdrop_image:
            self.loadDefaultBackdrop()
            return

        if "http" not in backdrop_image:
            self.loadDefaultBackdrop()
            return

        req_id = self._vod_req_id

        if self.backdrop_download_deferred and not self.backdrop_download_deferred.called:
            self.backdrop_download_deferred.cancel()

        self.backdrop_download_deferred = self.agent.request(
            b'GET',
            backdrop_image.encode(),
            Headers({'User-Agent': [b"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"]})
        )

        self.backdrop_download_deferred.addCallback(self.backdropResponse, req_id)
        self.backdrop_download_deferred.addErrback(self.backdropError, req_id)

    def backdropResponse(self, response, req_id):
        if debugs:
            print("*** backdropresponse ***")

        if req_id != self._vod_req_id:
            return

        if response.code == 200:
            d = readBody(response)
            d.addCallback(self.backdropBody, req_id)
            return d

    def backdropBody(self, body, req_id):
        if debugs:
            print("*** backdropbody ***")

        if req_id != self._vod_req_id:
            return

        temp = self._new_tmp_file("xst_vod_backdrop_", ".jpg")
        self._tmp_backdrop_src = temp

        try:
            with open(temp, 'wb') as f:
                f.write(body)
        except:
            self._safe_unlink(temp)
            self._tmp_backdrop_src = None
            self.loadDefaultBackdrop()
            return

        self.resizeBackdrop(temp)

    def backdropError(self, error, req_id=None):
        if debugs:
            print("*** handle error ***")

        print(error)
        self.loadDefaultBackdrop()

    def loadDefaultBackdrop(self, data=None):
        if debugs:
            print("*** loadDefaultBackdrop ***")

        if self["vod_backdrop"].instance:
            self["vod_backdrop"].instance.setPixmapFromFile(os.path.join(skin_directory, "common/blank.png"))

    def resizeBackdrop(self, preview):
        if debugs:
            print("*** resizeBackdrop ***")

        if not (self["main_list"].getCurrent() and self["vod_backdrop"].instance):
            self._safe_unlink(preview)
            return

        try:
            if not self._mask2_alpha or not self._mask2_size:
                self.loadDefaultBackdrop()
                self._safe_unlink(preview)
                return

            bd_size = self._mask2_size
            bd_width, bd_height = bd_size

            im = Image.open(preview)
            if im.mode != "RGBA":
                im = im.convert("RGBA")

            try:
                resample = Image.Resampling.LANCZOS
            except:
                resample = Image.ANTIALIAS

            # Fit inside mask size (no crop)
            if im.size != bd_size:
                im.thumbnail(bd_size, resample)

            im_w, im_h = im.size
            x_offset = (bd_width - im_w) // 2
            y_offset = 0

            # paste() mask must match im.size
            key = "%dx%d" % (im_w, im_h)
            if key in self._mask2_cache:
                alpha = self._mask2_cache[key]
            else:
                alpha = self._mask2_alpha
                if alpha.size != im.size:
                    alpha = alpha.resize(im.size, resample)

                self._mask2_cache[key] = alpha

                try:
                    while len(self._mask2_cache) > self._mask2_cache_max:
                        self._mask2_cache.popitem(last=False)
                except:
                    pass

            background = Image.new("RGBA", bd_size, (0, 0, 0, 0))
            background.paste(im, (x_offset, y_offset), alpha)

            output = self._new_tmp_file("xst_vod_backdrop_out_", ".png")
            self._tmp_backdrop_out = output

            background.save(output, "PNG", compress_level=0)
            self["vod_backdrop"].instance.setPixmapFromFile(output)
            self["vod_backdrop"].show()

        except Exception as e:
            print("Error resizing backdrop:", e)
            self["vod_backdrop"].hide()

        self._safe_unlink(preview)
        self._safe_unlink(self._tmp_backdrop_out)
        self._tmp_backdrop_src = None
        self._tmp_backdrop_out = None

    def sort(self):
        if debugs:
            print("*** sort ***")

        current_sort = self["key_yellow"].getText()
        if not current_sort:
            return

        if self.level == 1:
            activelist = self.list1

        elif self.level == 2:
            activelist = self.list2

        elif self.level == 3:
            activelist = self.list3

        elif self.level == 4:
            activelist = self.list4

        if self.level == 1:
            sortlist = [_("Sort: A-Z"), _("Sort: Z-A"), _("Sort: Original")]

        elif self.level == 2:
            sortlist = [_("Sort: A-Z"), _("Sort: Z-A"), _("Sort: Added"), _("Sort: Year"), _("Sort: Original")]
        else:
            sortlist = [_("Sort: A-Z"), _("Sort: Z-A"), _("Sort: Added"), _("Sort: Original")]

        self.sortindex = 0
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
            activelist.sort(key=lambda x: x[1].lower(), reverse=False)
            activelist.sort(key=lambda x: (x[10] or ""), reverse=True)

        elif current_sort == _("Sort: Year"):
            activelist.sort(key=lambda x: x[1].lower(), reverse=False)
            activelist.sort(key=lambda x: (x[14] or ""), reverse=True)

        elif current_sort == _("Sort: Original"):
            activelist.sort(key=lambda x: x[0], reverse=False)

        next_sort_type = next(islice(cycle(sortlist), self.sortindex + 1, None))
        self.sortText = str(next_sort_type)

        self["key_yellow"].setText(self.sortText)
        glob.nextlist[-1]["sort"] = self["key_yellow"].getText()

        if self.level == 1:
            self.list1 = activelist

        elif self.level == 2:
            self.list2 = activelist

        elif self.level == 3:
            self.list3 = activelist

        elif self.level == 4:
            self.list4 = activelist

        self.buildLists()

    def search(self, result=None):
        if debugs:
            print("*** search ***")

        if not self["key_blue"].getText():
            return

        current_filter = self["key_blue"].getText()

        if current_filter == _("Reset Search"):
            self.resetSearch()

        else:
            self.session.openWithCallback(self.filterChannels, VirtualKeyBoard, title=_("Filter this category..."), text=self.searchString)

    def filterChannels(self, result=None):
        if debugs:
            print("*** filterChannels ***")

        activelist = []

        if result:
            self.filterresult = result
            glob.nextlist[-1]["filter"] = self.filterresult

            if self.level == 1:
                activelist = self.list1

            elif self.level == 2:
                activelist = self.list2

            elif self.level == 3:
                activelist = self.list3

            elif self.level == 4:
                activelist = self.list4

            self.searchString = result
            activelist = [channel for channel in activelist if str(result).lower() in str(channel[1]).lower()]

            if not activelist:
                self.searchString = ""
                self.session.openWithCallback(self.search, MessageBox, _("No results found."), type=MessageBox.TYPE_ERROR, timeout=5)
            else:
                if self.level == 1:
                    self.list1 = activelist

                elif self.level == 2:
                    self.list2 = activelist

                elif self.level == 3:
                    self.list3 = activelist

                elif self.level == 4:
                    self.list4 = activelist

                self["key_blue"].setText(_("Reset Search"))
                self["key_yellow"].setText("")

                self.hideVod()
                self.buildLists()

    def resetSearch(self):
        if debugs:
            print("*** resetSearch ***")

        self["key_blue"].setText(_("Search"))
        self["key_yellow"].setText(self.sortText)

        if self.level == 1:
            activelist = glob.originalChannelList1[:]
            self.list1 = activelist

        elif self.level == 2:
            activelist = glob.originalChannelList2[:]
            self.list2 = activelist

        elif self.level == 3:
            activelist = glob.originalChannelList3[:]
            self.list3 = activelist

        elif self.level == 4:
            activelist = glob.originalChannelList4[:]
            self.list4 = activelist

        self.filterresult = ""
        glob.nextlist[-1]["filter"] = self.filterresult

        self.getSortOrder()
        self.buildLists()

    def pinEntered(self, result=None):
        if debugs:
            print("*** pinEntered ***")

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
            current_title = str(self["main_list"].getCurrent()[0])

            if current_title == "ALL" or current_title == _("ALL"):
                glob.adultChannel = True

            elif "sport" in current_title.lower():
                glob.adultChannel = False

            elif any(keyword in current_title.lower() for keyword in self.adult_keywords):
                glob.adultChannel = True

            else:
                glob.adultChannel = False

            if cfg.adult.value and nowtime - int(glob.pintime) > 900 and glob.adultChannel:
                from Screens.InputBox import PinInput
                self.session.openWithCallback(
                    self.pinEntered,
                    PinInput,
                    pinList=[cfg.adultpin.value],
                    triesEntry=cfg.retries.adultpin,
                    title=_("Please enter the parental control pin code"),
                    windowTitle=_("Enter pin code")
                )
            else:
                self.next()
        else:
            self.next()

    def next(self):
        if debugs:
            print("*** next ***")

        if self["main_list"].getCurrent():
            current_index = self["main_list"].getIndex()
            glob.nextlist[-1]["index"] = current_index
            glob.currentchannellist = self.main_list[:]
            glob.currentchannellistindex = current_index

            if self.level == 1:
                if self.list1:
                    category_id = self["main_list"].getCurrent()[3]
                    self.group_title = self["main_list"].getCurrent()[0]

                    next_url = "{0}&action=get_series&category_id={1}".format(self.player_api, category_id)
                    self.chosen_category = ""

                    if category_id == "0":
                        next_url = "{0}&action=get_series".format(self.player_api)
                        self.chosen_category = "all"

                    elif category_id == "-1":
                        self.chosen_category = "favourites"

                    self.level += 1
                    self["main_list"].setIndex(0)

                    self["category_actions"].setEnabled(False)
                    self["channel_actions"].setEnabled(True)
                    self["key_yellow"].setText(_("Sort: A-Z"))

                    glob.nextlist.append({"next_url": next_url, "index": 0, "level": self.level, "sort": self["key_yellow"].getText(), "filter": ""})

                    self.createSetup()
                else:
                    self.createSetup()

            elif self.level == 2:
                if self.list2:
                    self.series_group_title = self["main_list"].getCurrent()[0]
                    self.title2 = self["main_list"].getCurrent()[0]
                    self.cover2 = self["main_list"].getCurrent()[5]
                    self.plot2 = self["main_list"].getCurrent()[6]
                    self.cast2 = self["main_list"].getCurrent()[7]
                    self.director2 = self["main_list"].getCurrent()[8]
                    self.genre2 = self["main_list"].getCurrent()[9]
                    self.releaseDate2 = self["main_list"].getCurrent()[10]
                    self.rating2 = self["main_list"].getCurrent()[11]
                    self.backdrop_path2 = self["main_list"].getCurrent()[15]

                    if self["main_list"].getCurrent()[14] and self["main_list"].getCurrent()[14] != "0":
                        self.tmdb2 = self["main_list"].getCurrent()[14]
                    else:
                        self.tmdb2 = ""

                    next_url = self["main_list"].getCurrent()[3]
                    if "&action=get_series_info" in next_url:
                        self.seasons_url = self["main_list"].getCurrent()[3]

                    self.level += 1

                    self["main_list"].setIndex(0)
                    self["category_actions"].setEnabled(False)
                    self["channel_actions"].setEnabled(True)
                    self["key_yellow"].setText(_("Sort: A-Z"))

                    glob.nextlist.append({"next_url": next_url, "index": 0, "level": self.level, "sort": self["key_yellow"].getText(), "filter": ""})

                    self.createSetup()
                else:
                    self.createSetup()

            elif self.level == 3:
                if self.list3:
                    next_url = self["main_list"].getCurrent()[3]
                    self.storedseason = self["main_list"].getCurrent()[12]

                    self.level += 1
                    self["main_list"].setIndex(0)
                    self["category_actions"].setEnabled(False)
                    self["channel_actions"].setEnabled(True)
                    self["key_yellow"].setText(_("Sort: A-Z"))
                    glob.nextlist.append({"next_url": next_url, "index": 0, "level": self.level, "sort": self["key_yellow"].getText(), "filter": ""})
                    self.createSetup()
                else:
                    self.createSetup()

            elif self.level == 4:
                if self.list4:
                    from . import vodplayer
                    self.storedepisode = self["main_list"].getCurrent()[18]
                    streamtype = glob.active_playlist["player_info"]["vodtype"]
                    next_url = self["main_list"].getCurrent()[3]
                    stream_id = self["main_list"].getCurrent()[4]

                    self.reference = eServiceReference(int(streamtype), 0, next_url)
                    self.reference.setName(glob.currentchannellist[glob.currentchannellistindex][0])
                    self.session.openWithCallback(self.setIndex, vodplayer.XStreamity_VodPlayer, str(next_url), str(streamtype), stream_id)

                else:
                    self.createSetup()

    def setIndex(self, data=None):
        if debugs:
            print("*** setIndex ***")

        if self["main_list"].getCurrent():
            self["main_list"].setIndex(glob.currentchannellistindex)
            # self.createSetup()

    def back(self, data=None):
        if debugs:
            print("*** back ***")

        self.chosen_category = ""

        self._stopTimerSeries()
        self._cleanup_series_assets()

        try:
            del glob.nextlist[-1]
        except Exception as e:
            print(e)
            self.close()

        if self.level == 2:
            self.group_title = ""

        if self.level == 3:
            self.series_info = ""
            self.series_group_title = ""

        if not glob.nextlist:
            self.close()
        else:
            self["x_title"].setText("")
            self["x_description"].setText("")
            self["key_epg"].setText("")
            self.level -= 1
            if self.level == 1:
                self["category_actions"].setEnabled(True)
                self["channel_actions"].setEnabled(False)
            self.buildLists()

            self.loadDefaultCover()
            self.loadDefaultLogo()
            self.loadDefaultBackdrop()

    def showHiddenList(self):
        if debugs:
            print("*** showHiddenList ***")

        if self["key_menu"].getText() and self["main_list"].getCurrent():
            from . import hidden

            if self["main_list"].getCurrent():
                if self.level == 1:
                    self.session.openWithCallback(self.setIndex, hidden.XStreamity_HiddenCategories, "series", self.prelist + self.list1, self.level)
                elif self.level == 2 and self.chosen_category != "favourites":
                    self.session.openWithCallback(self.setIndex, hidden.XStreamity_HiddenCategories, "series", self.list2, self.level)
                elif self.level == 3 and self.chosen_category != "favourites":
                    self.session.openWithCallback(self.setIndex, hidden.XStreamity_HiddenCategories, "series", self.list3, self.level)
                elif self.level == 4 and self.chosen_category != "favourites":
                    self.session.openWithCallback(self.setIndex, hidden.XStreamity_HiddenCategories, "series", self.list4, self.level)

    def clearWatched(self):
        if debugs:
            print("*** clearWatched ***")

        if self.level == 4:
            current_id = str(self["main_list"].getCurrent()[4])
            watched_list = glob.active_playlist["player_info"].get("serieswatched", [])
            if current_id in watched_list:
                watched_list.remove(current_id)
            else:
                watched_list.append(current_id)

        with open(self.playlists_json, "r") as f:
            try:
                self.playlists_all = json.load(f)
            except:
                os.remove(self.playlists_json)
                return

            for i, playlist in enumerate(self.playlists_all):
                playlist_info = playlist.get("playlist_info", {})
                current_playlist_info = glob.active_playlist.get("playlist_info", {})
                if (playlist_info.get("domain") == current_playlist_info.get("domain") and
                        playlist_info.get("username") == current_playlist_info.get("username") and
                        playlist_info.get("password") == current_playlist_info.get("password")):
                    self.playlists_all[i] = glob.active_playlist
                    break

        with open(self.playlists_json, "w") as f:
            json.dump(self.playlists_all, f, indent=4)

        self.buildLists()

    def favourite(self):
        if debugs:
            print("*** favourite ***")
            print("*** self.level ***", self.level)

        if not self["main_list"].getCurrent():
            return

        if self.chosen_category == "favourites" and not self.level == 2:
            return

        current_index = self["main_list"].getIndex()
        favExists = False
        favStream_id = None

        if self.level == 2:
            series_id = str(self["main_list"].getCurrent()[4])
            current_index = self["main_list"].getIndex()

        elif self.level == 3:
            current_index = self["main_list"].getCurrent()[17]
            series_id = str(self["main_list"].getCurrent()[18])

        elif self.level == 4:
            current_index = self["main_list"].getCurrent()[19]
            series_id = str(self["main_list"].getCurrent()[20])

        self.list2[current_index][16] = not self.list2[current_index][16]

        for fav in glob.active_playlist["player_info"]["seriesfavourites"]:
            if str(series_id) == str(fav["series_id"]):
                favExists = True
                favStream_id = str(fav["series_id"])
                break

        # remove for glob favourites

        if favExists:
            if self.level == 2:
                glob.active_playlist["player_info"]["seriesfavourites"] = [x for x in glob.active_playlist["player_info"]["seriesfavourites"] if str(x["series_id"]) != str(favStream_id)]
        else:
            newfavourite = {
                "name": self.list2[current_index][1],
                "series_id": self.list2[current_index][2],
                "cover": self.list2[current_index][3],
                "plot": self.list2[current_index][4],
                "cast": self.list2[current_index][5],
                "director": self.list2[current_index][6],
                "genre": self.list2[current_index][7],
                "releaseDate": self.list2[current_index][8],
                "rating": self.list2[current_index][9],
                "last_modified": self.list2[current_index][10],
                "tmdb": self.list2[current_index][12],
                "year": self.list2[current_index][14],
                "backdrop": self.list2[current_index][15]
            }

            glob.active_playlist["player_info"]["seriesfavourites"].insert(0, newfavourite)

        with open(self.playlists_json, "r") as f:
            try:
                self.playlists_all = json.load(f)
            except:
                os.remove(self.playlists_json)
                self.playlists_all = []

        if self.playlists_all:
            for playlists in self.playlists_all:
                if (playlists["playlist_info"]["domain"] == glob.active_playlist["playlist_info"]["domain"]
                        and playlists["playlist_info"]["username"] == glob.active_playlist["playlist_info"]["username"]
                        and playlists["playlist_info"]["password"] == glob.active_playlist["playlist_info"]["password"]):
                    playlists.update(glob.active_playlist)
                    break

        with open(self.playlists_json, "w") as f:
            json.dump(self.playlists_all, f, indent=4)

        if self.level == 2:
            self.createSetup()
        else:
            if not favExists:
                self.session.open(MessageBox, _("Series group added to favourites."), type=MessageBox.TYPE_INFO, timeout=2)
            else:
                self.session.open(MessageBox, _("Series group removed from favourites."), type=MessageBox.TYPE_INFO, timeout=2)

    def hideVod(self):
        if debugs:
            print("*** hideVod ***")

        self["vod_cover"].hide()
        self["vod_logo"].hide()
        self["vod_backdrop"].hide()
        self["main_title"].setText("")
        self["x_title"].setText("")
        self["x_description"].setText("")
        self["tagline"].setText("")
        self["facts"].setText("")
        self["vod_director_label"].setText("")
        self["vod_country_label"].setText("")
        self["vod_cast_label"].setText("")
        self["vod_director"].setText("")
        self["vod_country"].setText("")
        self["vod_cast"].setText("")
        self["rating_text"].setText("")
        self["rating_percent"].setText("")
        self["overview"].setText("")

    def clearVod(self):
        if debugs:
            print("*** clearVod ***")
        # self["vod_cover"].hide()
        # self["vod_logo"].hide()
        # self["vod_backdrop"].hide()
        """
        if self.level == 3 or self.level == 4:
            self["main_title"].setText("")
            """
        self["x_title"].setText("")
        self["x_description"].setText("")
        self["tagline"].setText("")
        self["facts"].setText("")
        self["vod_director"].setText("")
        self["vod_country"].setText("")
        self["vod_cast"].setText("")
        self["rating_text"].setText("0.0")
        self["rating_percent"].setText("")

    def showVod(self):
        if debugs:
            print("*** showVod ***")
        if self["main_list"].getCurrent():
            self["vod_cover"].show()
            self["vod_logo"].show()
            self["vod_backdrop"].show()

    def downloadVideo(self):
        if debugs:
            print("*** downloadVideo ***")

        if self.level != 4:
            return

        if self["main_list"].getCurrent():
            title = self["main_list"].getCurrent()[0]
            stream_url = self["main_list"].getCurrent()[3]
            description = self["main_list"].getCurrent()[6]
            duration = self["main_list"].getCurrent()[12]

            try:
                h, m, s = map(int, duration.split(":"))
                duration = h * 60 + m + s // 60
            except:
                duration = 0

            timestamp = ""
            channel = _("Series")

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
                if stream_url == url:
                    exists = True

            if exists is False:
                downloads_all.append([_("Series"), title, stream_url, "Not Started", 0, 0, description, duration, channel, timestamp])

                with open(downloads_json, "w") as f:
                    json.dump(downloads_all, f, indent=4)

                self.session.openWithCallback(self.opendownloader, MessageBox, _(title) + "\n\n" + _("Added to download manager") + "\n\n" + _("Note recording acts as an open connection.") + "\n" + _("Do not record and play streams at the same time.") + "\n\n" + _("Open download manager?"))

            else:
                self.session.open(MessageBox, _(title) + "\n\n" + _("Already added to download manager"), MessageBox.TYPE_ERROR, timeout=5)

    def opendownloader(self, answer=None):
        if debugs:
            print("*** opendownloader ***")

        if not answer:
            return
        else:
            from . import downloadmanager
            self.session.openWithCallback(self.setIndex, downloadmanager.XStreamity_DownloadManager)

    def check(self, token):
        result = base64.b64decode(token)
        result = zlib.decompress(base64.b64decode(result))
        result = base64.b64decode(result).decode()
        return result

    # code for natural sorting of numbers in string
    def atoi(self, text):
        return int(text) if text.isdigit() else text

    def natural_keys(self, text):
        return [self.atoi(c) for c in re.split(r"(\d+)", text[1])]

    def buildFacts(self, certification, release_date, genre, duration, stream_format):
        if debugs:
            print("*** buildFacts ***")

        facts = []

        if certification:
            facts.append(certification)
        if release_date:
            facts.append(release_date)
        if genre:
            facts.append(genre)
        if duration:
            facts.append(duration)
        if stream_format:
            facts.append(str(stream_format).upper())

        return " • ".join(facts)


def buildCategoryList(index, title, category_id, hidden, png):
    return (title, png, index, category_id, hidden)

# 0 index, 1 name, 2 series_id, 3 cover, 4 plot, 5 cast, 6 director, 7 genre, 8 releaseDate, 9 rating, 10 last_modified, 11 next_url, 12 tmdb, 13 hidden, 14 year, 15 backdrop
# 0 index, 1 name, 2 series_id, 3 cover, 4 overview, 5 cast, 6 director, 7 genre, 8 airdate, 9 rating, 10 last_modified, 11 next_url, 12 tmdb, 13 hidden, 14 season_number, 15 backdrop
# 0 index, 1 title, 2 stream_id, 3 cover, 4 plot, 5 cast, 6 director, 7 genre, 8 releasedate, 9 rating, 10 last_modified, 11 next_url, 12 tmdb_id, 13 hidden, 14 duration, 15 container_extension, 16 shorttitle, 17 episode_num


def buildSeriesTitlesList(index, title, series_id, cover, plot, cast, director, genre, releaseDate, rating, lastmodified, next_url, tmdb, hidden, year, backdrop_path, favourite, px_more, px_fav):
    png = px_fav if favourite else px_more
    return (title, png, index, next_url, series_id, cover, plot, cast, director, genre, releaseDate, rating, lastmodified, year, tmdb, backdrop_path, hidden, favourite)


def buildSeriesSeasonsList(index, title, series_id, cover, plot, cast, director, genre, airDate, rating, lastmodified, next_url, tmdb, hidden, season_number, backdrop_path, parent_index, parent_id, px_more):
    png = px_more
    try:
        title = _("Season ") + str(int(title))
    except:
        pass

    return (title, png, index, next_url, series_id, cover, plot, cast, director, genre, airDate, rating, season_number, lastmodified, hidden, tmdb, backdrop_path, parent_index, parent_id)


def buildSeriesEpisodesList(index, title, series_id, cover, plot, cast, director, genre, releaseDate, rating, lastmodified, next_url, tmdb_id, hidden, duration, container_extension, shorttitle, episode_number, parent_index, parent_id, watched_set, px_play, px_watched):
    png = px_watched if str(series_id) in watched_set else px_play
    return (title, png, index, next_url, series_id, cover, plot, cast, director, genre, releaseDate, rating, duration, container_extension, tmdb_id, shorttitle, lastmodified, hidden, episode_number, parent_index, parent_id)
