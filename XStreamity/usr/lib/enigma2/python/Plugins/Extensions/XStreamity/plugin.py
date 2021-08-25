#!/usr/bin/python
# -*- coding: utf-8 -*-

from . import _

from Plugins.Plugin import PluginDescriptor
from enigma import getDesktop, addFont
from Components.config import config, ConfigSubsection, ConfigSelection, ConfigDirectory, ConfigYesNo, ConfigSelectionNumber

import os
import shutil

with open("/usr/lib/enigma2/python/Plugins/Extensions/XStreamity/version.txt", 'r') as f:
    version = f.readline()

screenwidth = getDesktop(0).size()

dir_etc = "/etc/enigma2/xstreamity/"
dir_tmp = "/tmp/xstreamity/"
dir_plugins = "/usr/lib/enigma2/python/Plugins/Extensions/XStreamity/"

if screenwidth.width() > 1280:
    skin_directory = "%sskin/fhd/" % (dir_plugins)
else:
    skin_directory = "%sskin/hd/" % (dir_plugins)


folders = os.listdir(skin_directory)
if "common" in folders:
    folders.remove("common")

languages = [
    ('en', 'English'),
    ('de', 'Deutsch'),
    ('es', 'Español'),
    ('fr', 'Français'),
    ('it', 'Italiano'),
    ('nl', 'Nederlands'),
    ('tr', 'Türkçe'),
    ('cs', 'Český'),
    ('da', 'Dansk'),
    ('hr', 'Hrvatski'),
    ('hu', 'Magyar'),
    ('no', 'Norsk'),
    ('pl', 'Polski'),
    ('pt', 'Português'),
    ('ro', 'Română'),
    ('ru', 'Pусский'),
    ('sh', 'Srpski'),
    ('sk', 'Slovenčina'),
    ('fi', 'suomi'),
    ('sv', 'svenska'),
    ('uk', 'Український'),
    ('ar', 'العربية'),
    ('bg', 'български език'),
    ('el', 'ελληνικά'),
    ('sq', 'shqip')
]
config.plugins.XStreamity = ConfigSubsection()

cfg = config.plugins.XStreamity

streamtype_choices = [('1', 'DVB(1)'), ('4097', 'IPTV(4097)')]

if os.path.exists("/usr/bin/gstplayer"):
    streamtype_choices.append(('5001', 'GStreamer(5001)'))

if os.path.exists("/usr/bin/exteplayer3"):
    streamtype_choices.append(('5002', 'ExtePlayer(5002)'))

if os.path.exists("/usr/bin/apt-get"):
    streamtype_choices.append(('8193', 'GStreamer(8193)'))


cfg.livetype = ConfigSelection(default='1', choices=streamtype_choices)
cfg.vodtype = ConfigSelection(default='4097', choices=streamtype_choices)
downloadpath = None

try:
    from Components.UsageConfig import defaultMoviePath
    downloadpath = defaultMoviePath()
    cfg.downloadlocation = ConfigDirectory(default=downloadpath)
except:
    if os.path.exists("/usr/bin/apt-get"):
        cfg.downloadlocation = ConfigDirectory(default='/media/hdd/movie/')


cfg.location = ConfigDirectory(default=dir_etc)
cfg.main = ConfigYesNo(default=True)
cfg.livepreview = ConfigYesNo(default=False)
cfg.stopstream = ConfigYesNo(default=False)
cfg.skin = ConfigSelection(default='default', choices=folders)
cfg.parental = ConfigYesNo(default=False)
cfg.timeout = ConfigSelectionNumber(1, 20, 1, default=6)
cfg.TMDB = ConfigYesNo(default=True)
cfg.TMDBLanguage = ConfigSelection(default='en', choices=languages)
cfg.catchupstart = ConfigSelectionNumber(0, 30, 1, default=0)
cfg.catchupend = ConfigSelectionNumber(0, 30, 1, default=0)
cfg.subs = ConfigYesNo(default=False)
cfg.skipplaylistsscreen = ConfigYesNo(default=False)

skin_path = '%s%s/' % (skin_directory, cfg.skin.value)
common_path = '%scommon/' % (skin_directory)
playlists_json = "%sx-playlists.json" % (dir_etc)
downloads_json = "%sx-downloads.json" % (dir_etc)
playlist_file = "%splaylists.txt" % (dir_etc)

if cfg.location.value:
    playlist_file = "%s/playlists.txt" % (cfg.location.value)

font_folder = "%sfonts/" % (dir_plugins)
icon_folder = "%sicons/" % (dir_plugins)
image_folder = "%s/images/" % (skin_path)


"""
hdr = {
'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:87.0) Gecko/20100101 Firefox/87.0',
'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
'Accept-Language': 'en-GB,en;q=0.5',
'Accept-Encoding': 'gzip, deflate',
}
"""


hdr = {'User-Agent': 'Enigma2 - XStreamity Plugin'}


# create folder for working files
if not os.path.exists(dir_etc):
    os.makedirs(dir_etc)

# delete temporary folder and contents
if os.path.exists(dir_tmp):
    shutil.rmtree('/tmp/xstreamity')

# create temporary folder for downloaded files
if not os.path.exists(dir_tmp):
    os.makedirs(dir_tmp)

# check if playlists.txt file exists in specified location
if not os.path.isfile(playlist_file):
    open(playlist_file, 'a').close()

# check if x-playlists.json file exists in specified location
if not os.path.isfile(playlists_json):
    open(playlists_json, 'a').close()

# check if x-downloads.json file exists in specified location
if not os.path.isfile(downloads_json):
    open(downloads_json, 'a').close()


def main(session, **kwargs):
    from . import mainmenu
    session.open(mainmenu.XStreamity_MainMenu)
    return


def mainmenu(menu_id, **kwargs):
    if menu_id == 'mainmenu':
        return [(_('XStreamity'), main, 'XStreamity', 50)]
    else:
        return []


def extensionsmenu(session, **kwargs):
    from . import mainmenu
    session.open(mainmenu.XStreamity_MainMenu)
    return


def Plugins(**kwargs):
    addFont(font_folder + 'm-plus-rounded-1c-regular.ttf', 'xstreamityregular', 100, 0)
    addFont(font_folder + 'm-plus-rounded-1c-medium.ttf', 'xstreamitybold', 100, 0)

    iconFile = 'icons/plugin-icon_sd.png'
    if screenwidth.width() > 1280:
        iconFile = 'icons/plugin-icon.png'
    description = (_('IPTV Xtream Codes playlists player by KiddaC'))
    pluginname = (_('XStreamity'))

    main_menu = PluginDescriptor(name=pluginname, description=description, where=PluginDescriptor.WHERE_MENU, fnc=mainmenu, needsRestart=True)

    extensions_menu = PluginDescriptor(name=pluginname, description=description, where=PluginDescriptor.WHERE_EXTENSIONSMENU, fnc=extensionsmenu, needsRestart=True)

    result = [PluginDescriptor(name=pluginname, description=description, where=PluginDescriptor.WHERE_PLUGINMENU, icon=iconFile, fnc=main)]

    result.append(extensions_menu)

    if cfg.main.getValue():
        result.append(main_menu)

    return result
