#!/usr/bin/python
# -*- coding: utf-8 -*-

import os
import shutil
import sys
import time
import glob as glob_module
import twisted.python.runtime

from . import _
from . import xstreamity_globals as glob
from Components.config import (
    config, ConfigSubsection, ConfigSelection, ConfigDirectory,
    ConfigYesNo, ConfigSelectionNumber, ConfigClock, ConfigPIN,
    ConfigInteger, configfile, ConfigText
)

from enigma import eTimer, getDesktop, addFont
from Plugins.Plugin import PluginDescriptor
from os.path import isdir

# ------------------------------------------------------------------
# Basic environment / platform checks
# ------------------------------------------------------------------

pythonVer = sys.version_info.major
isDreambox = os.path.exists("/usr/bin/apt-get")
debugs = True

# ------------------------------------------------------------------
# Dependencies checks
# ------------------------------------------------------------------

try:
    from multiprocessing.pool import ThreadPool
    hasMultiprocessing = True
except ImportError:
    hasMultiprocessing = False

try:
    from concurrent.futures import ThreadPoolExecutor
    if twisted.python.runtime.platform.supportsThreads():
        hasConcurrent = True
    else:
        hasConcurrent = False
except ImportError:
    hasConcurrent = False


# ------------------------------------------------------------------
# Paths
# ------------------------------------------------------------------

dir_etc = "/etc/enigma2/xstreamity/"
dir_tmp = "/etc/enigma2/xstreamity/tmp/"
dir_plugins = "/usr/lib/enigma2/python/Plugins/Extensions/XStreamity/"


# ------------------------------------------------------------------
# Version
# ------------------------------------------------------------------

version = ""
try:
    with open(os.path.join(dir_plugins, "version.txt"), "r") as f:
        version = f.readline().strip()
except:
    version = ""


# ------------------------------------------------------------------
# Screen / skin selection
# ------------------------------------------------------------------

screenwidth = getDesktop(0).size()

if screenwidth.width() == 2560:
    skin_directory = os.path.join(dir_plugins, "skin/uhd/")
elif screenwidth.width() > 1280:
    skin_directory = os.path.join(dir_plugins, "skin/fhd/")
else:
    skin_directory = os.path.join(dir_plugins, "skin/hd/")

try:
    folders = [x for x in os.listdir(skin_directory) if x != "common"]
except:
    folders = ["default"]


# ------------------------------------------------------------------
# Language & User-Agent options
# ------------------------------------------------------------------

languages = [
    ("", "English"),
    ("de-DE", "Deutsch"),
    ("es-ES", "Español"),
    ("fr-FR", "Français"),
    ("it-IT", "Italiano"),
    ("nl-NL", "Nederlands"),
    ("tr-TR", "Türkçe"),
    ("cs-CZ", "Český"),
    ("da-DK", "Dansk"),
    ("hr-HR", "Hrvatski"),
    ("hu-HU", "Magyar"),
    ("no-NO", "Norsk"),
    ("pl-PL", "Polski"),
    ("pt-PT", "Português"),
    ("ro-RO", "Română"),
    ("ru-RU", "Pусский"),
    ("sh-SH", "Srpski"),
    ("sk-SK", "Slovenčina"),
    ("fi-FI", "suomi"),
    ("sv-SE", "svenska"),
    ("uk-UA", "Український"),
    ("ar-SA", "العربية"),
    ("bg-BG", "български език"),
    ("el-GR", "ελληνικά"),
    ("sq-AL", "shqip"),
    ("zh-CN", "中文")
]

useragents = [
    ("Enigma2 - XStreamity Plugin", "XStreamity"),
    ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36", "Chrome 124"),
    ("Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0", "Firefox 125"),
    ("Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.6422.165 Mobile Safari/537.36", "Android")
]


# ------------------------------------------------------------------
# Config setup
# ------------------------------------------------------------------

config.plugins.XStreamity = ConfigSubsection()
cfg = config.plugins.XStreamity

live_streamtype_choices = [("1", "DVB(1)"), ("4097", "IPTV(4097)")]
vod_streamtype_choices = [("4097", "IPTV(4097)")]

if os.path.exists("/usr/bin/gstplayer"):
    live_streamtype_choices.append(("5001", "GStreamer(5001)"))
    vod_streamtype_choices.append(("5001", "GStreamer(5001)"))

if os.path.exists("/usr/bin/exteplayer3"):
    live_streamtype_choices.append(("5002", "ExtePlayer(5002)"))
    vod_streamtype_choices.append(("5002", "ExtePlayer(5002)"))

if isDreambox:
    live_streamtype_choices.append(("8193", "DreamOS GStreamer(8193)"))
    vod_streamtype_choices.append(("8193", "DreamOS GStreamer(8193)"))

cfg.livetype = ConfigSelection(default="4097", choices=live_streamtype_choices)
cfg.vodtype = ConfigSelection(default="4097", choices=vod_streamtype_choices)


# ------------------------------------------------------------------
# Download location (safe, minimal writes)
# ------------------------------------------------------------------

result = cfg.downloadlocation.value if hasattr(cfg, "downloadlocation") else ""

if not result:
    try:
        if isdir("/media/hdd/movie/"):
            result = "/media/hdd/movie/"
        elif isdir("/media/usb/movie/"):
            result = "/media/usb/movie/"
        elif config.usage.instantrec_path.value:
            result = config.usage.instantrec_path.value
        elif config.movielist.last_videodir.value:
            result = config.movielist.last_videodir.value
        else:
            result = "/media/"
    except Exception as e:
        print(e)
        result = "/media/"

cfg.downloadlocation = ConfigDirectory(default=result)
# ------------------------------------------------------------------
# EPG location (prefer system epgcachepath if available)
# ------------------------------------------------------------------

epg_base = "/etc/enigma2/"

try:
    if hasattr(config, "misc") and hasattr(config.misc, "epgcachepath"):
        epgcachepath = config.misc.epgcachepath.value
        if epgcachepath:
            epg_base = epgcachepath
except:
    pass

cfg.epglocation = ConfigDirectory(default=os.path.join(epg_base, "xstreamity", "epg") + "/")
cfg.location = ConfigDirectory(default=dir_etc)
cfg.location = ConfigDirectory(default=dir_etc)
cfg.main = ConfigYesNo(default=True)
cfg.livepreview = ConfigYesNo(default=False)
cfg.stopstream = ConfigYesNo(default=False)
cfg.skin = ConfigSelection(default="default", choices=folders)
cfg.timeout = ConfigSelectionNumber(1, 20, 1, default=20, wraparound=True)
cfg.TMDB = ConfigYesNo(default=True)
cfg.TMDBLanguage2 = ConfigSelection(default="", choices=languages)
cfg.catchupstart = ConfigSelectionNumber(0, 30, 1, default=0, wraparound=True)
cfg.catchupend = ConfigSelectionNumber(0, 30, 1, default=0, wraparound=True)
cfg.subs = ConfigYesNo(default=False)
cfg.skipplaylistsscreen = ConfigYesNo(default=False)
cfg.wakeup = ConfigClock(default=((9 * 60) + 9) * 60)
cfg.adult = ConfigYesNo(default=False)
cfg.adultpin = ConfigPIN(default=0000)
cfg.retries = ConfigSubsection()
cfg.retries.adultpin = ConfigSubsection()
cfg.retries.adultpin.tries = ConfigInteger(default=3)
cfg.retries.adultpin.time = ConfigInteger(default=3)
cfg.location_valid = ConfigYesNo(default=True)
cfg.channelpicons = ConfigYesNo(default=True)
cfg.infobarpicons = ConfigYesNo(default=True)
cfg.channelcovers = ConfigYesNo(default=True)
cfg.infobarcovers = ConfigYesNo(default=True)
cfg.boot = ConfigYesNo(default=False)
cfg.useragent = ConfigSelection(default="Enigma2 - XStreamity Plugin", choices=useragents)
cfg.vodcategoryorder = ConfigSelection(default=(_("Sort: Original")), choices=[(_("Sort: A-Z"), "A-Z"), (_("Sort: Z-A"), "Z-A"), (_("Sort: Original"), _("Original"))])
cfg.vodstreamorder = ConfigSelection(default=(_("Sort: Original")), choices=[(_("Sort: A-Z"), "A-Z"), (_("Sort: Z-A"), "Z-A"), (_("Sort: Added"), _("Added")), (_("Sort: Year"), _("Year")), (_("Sort: Original"), _("Original"))])
cfg.seriescategoryorder = ConfigSelection(default=(_("Sort: Original")), choices=[(_("Sort: A-Z"), "A-Z"), (_("Sort: Z-A"), "Z-A"), (_("Sort: Original"), _("Original"))])
cfg.seriesorder = ConfigSelection(default=(_("Sort: Original")), choices=[(_("Sort: A-Z"), "A-Z"), (_("Sort: Z-A"), "Z-A"), (_("Sort: Added"), _("Added")), (_("Sort: Year"), _("Year")), (_("Sort: Original"), _("Original"))])


# ------------------------------------------------------------------
# File paths
# ------------------------------------------------------------------

playlist_file = os.path.join(dir_etc, "playlists.txt")
playlists_json = os.path.join(dir_etc, "x-playlists.json")
downloads_json = os.path.join(dir_etc, "downloads2.json")
skin_path = os.path.join(skin_directory, cfg.skin.value)
common_path = os.path.join(skin_directory, "common/")

location = cfg.location.value

if location:
    if os.path.exists(location):
        playlist_file = os.path.join(cfg.location.value, "playlists.txt")
        cfg.location_valid.setValue(True)
    else:
        os.makedirs(location)  # Create directory if it doesn't exist
        playlist_file = os.path.join(location, "playlists.txt")

        cfg.location_valid.setValue(True)
else:
    cfg.location.setValue(dir_etc)
    cfg.location_valid.setValue(False)

cfg.playlist_file = ConfigText(playlist_file)
cfg.playlists_json = ConfigText(playlists_json)
cfg.downloads_json = ConfigText(downloads_json)

cfg.playlist_file.value = playlist_file  # Force overwrite
cfg.playlist_file.save()

cfg.playlists_json.value = playlists_json  # Force overwrite
cfg.playlists_json.save()

cfg.save()
configfile.save()

glob.original_playlist_file = cfg.playlist_file.value
glob.original_playlists_json = cfg.playlists_json.value

# ------------------------------------------------------------------
# Check folders
# ------------------------------------------------------------------

# create folder for working files
if not os.path.exists(dir_etc):
    os.makedirs(dir_etc)

# create temporary folder for downloaded files
if not os.path.exists(dir_tmp):
    os.makedirs(dir_tmp)

# check if playlists.txt file exists in specified location
if not os.path.isfile(cfg.playlist_file.value):
    with open(cfg.playlist_file.value, "a") as f:
        f.close()

# check if x-playlists.json file exists in specified location
if not os.path.isfile(cfg.playlists_json.value):
    with open(cfg.playlists_json.value, "a") as f:
        f.close()

# check if x-downloads.json file exists in specified location
if not os.path.isfile(cfg.downloads_json.value):
    with open(cfg.downloads_json.value, "a") as f:
        f.close()


# ------------------------------------------------------------------
# Fonts (safe)
# ------------------------------------------------------------------

font_folder = os.path.join(dir_plugins, "fonts/")
for font, name in [
    ("m-plus-rounded-1c-regular.ttf", "xstreamityregular"),
    ("m-plus-rounded-1c-medium.ttf", "xstreamitybold"),
    ("slyk-medium.ttf", "slykregular"),
    ("slyk-bold.ttf", "slykbold"),
    ("classfont2.ttf", "klass"),
]:
    try:
        addFont(os.path.join(font_folder, font), name, 100, 0)
    except:
        pass


# ------------------------------------------------------------------
# Headers
# ------------------------------------------------------------------

hdr = {
    'User-Agent': str(cfg.useragent.value),
    'Accept-Encoding': 'gzip, deflate'
}


# ------------------------------------------------------------------
# Main entry
# ------------------------------------------------------------------

def main(session, **kwargs):

    if os.path.exists(dir_tmp):
        shutil.rmtree(dir_tmp)

    os.makedirs(dir_tmp)

    epgfolder = os.path.join(cfg.epglocation.value, '*', '*.xml')

    for file_path in glob_module.glob(epgfolder):
        try:
            os.remove(file_path)
        except:
            pass

    from . import mainmenu
    session.open(mainmenu.XStreamity_MainMenu)


# ------------------------------------------------------------------
# Menus / autostart / boot
# ------------------------------------------------------------------

def mainmenu(menu_id, **kwargs):
    if menu_id == "mainmenu":
        return [(_("XStreamity"), main, "XStreamity", 50)]
    return []


class XSAutoStartTimer:
    def __init__(self, session):
        self.session = session
        self.timer = eTimer()
        try:
            self.timer_conn = self.timer.timeout.connect(self.onTimer)
        except:
            self.timer.callback.append(self.onTimer)
        self.update()

    def getWakeTime(self):
        clock = cfg.wakeup.value
        nowt = time.time()
        now = time.localtime(nowt)
        return int(time.mktime((now.tm_year, now.tm_mon, now.tm_mday, clock[0], clock[1], 0, now.tm_wday, now.tm_yday, now.tm_isdst)))

    def update(self, atLeast=0):
        self.timer.stop()
        wake = self.getWakeTime()
        now = int(time.time())
        if wake < now + atLeast:
            wake += 86400
        self.timer.startLongTimer(max(60, min(3600, wake - now)))

    def onTimer(self):
        self.timer.stop()
        now = int(time.time())
        wake = self.getWakeTime()
        atLeast = 0
        if abs(wake - now) < 60:
            self.runUpdate()
            atLeast = 60
        self.update(atLeast)

    def runUpdate(self):
        print("\n *********** Updating XStreamity EPG ************ \n")
        from . import update
        update.XStreamity_Update(self.session)


xsAutoStartTimer = None


def autostart(reason, session=None, **kwargs):
    global xsAutoStartTimer
    if reason == 0 and session and xsAutoStartTimer is None:
        xsAutoStartTimer = XSAutoStartTimer(session)


glb_session = None
glb_startDelay = None


class StartDelay:
    def __init__(self):
        self.timerboot = eTimer()

    def start(self):
        delay = 2000

        try:
            self.timer_conn = self.timerboot.timeout.connect(self.query)
        except:
            self.timerboot.callback.append(self.query)

        self.timerboot.start(delay, True)

    def query(self):
        from . import playlists
        glb_session.open(playlists.XStreamity_Playlists)
        return


def bootstart(reason, **kwargs):
    # print("*** bootstart ***")
    global glb_session
    global glb_startDelay
    if reason == 0 and "session" in kwargs:
        glb_session = kwargs["session"]
        glb_startDelay = StartDelay()
        glb_startDelay.start()


def Plugins(**kwargs):
    iconFile = "icons/plugin-icon_sd.png"
    if screenwidth.width() > 1280:
        iconFile = "icons/plugin-icon.png"
    description = _("IPTV Xtream Codes playlists player by KiddaC")
    pluginname = _("XStreamity")

    main_menu = PluginDescriptor(name=pluginname, description=description, where=PluginDescriptor.WHERE_MENU, fnc=mainmenu, needsRestart=True)

    extensions_menu = PluginDescriptor(name=pluginname, description=description, where=PluginDescriptor.WHERE_EXTENSIONSMENU, fnc=main, needsRestart=True)

    boot_start = PluginDescriptor(name=pluginname, description=description, where=[PluginDescriptor.WHERE_AUTOSTART, PluginDescriptor.WHERE_SESSIONSTART], fnc=bootstart, needsRestart=True)

    result = [PluginDescriptor(name=pluginname, description=description, where=[PluginDescriptor.WHERE_AUTOSTART, PluginDescriptor.WHERE_SESSIONSTART], fnc=autostart),
              PluginDescriptor(name=pluginname, description=description, where=PluginDescriptor.WHERE_PLUGINMENU, icon=iconFile, fnc=main)]

    result.append(extensions_menu)

    if cfg.main.value:
        result.append(main_menu)

    if cfg.boot.value:
        result.append(boot_start)

    return result
