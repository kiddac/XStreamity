#!/usr/bin/python
# -*- coding: utf-8 -*-

# for localized messages  	 
from . import _

from Plugins.Plugin import PluginDescriptor
from enigma import getDesktop, addFont
#from Components.ConfigList import *
from Components.config import config, ConfigSubsection, ConfigSelection, ConfigDirectory, ConfigYesNo, ConfigNumber, ConfigSelectionNumber

import os
import shutil

screenwidth = getDesktop(0).size()

dir_src = "/etc/enigma2/X-Streamity/"
dir_dst = "/etc/enigma2/xstreamity/" 
dir_tmp = "/tmp/xstreamity/"
dir_plugins = "/usr/lib/enigma2/python/Plugins/Extensions/XStreamity/"

if screenwidth.width() > 1280:
	skin_directory = "%sskin/fhd/" % (dir_plugins) 
else:
	skin_directory = "%sskin/hd/" % (dir_plugins) 

folders = os.listdir(skin_directory)
if "common" in folders:
	folders.remove("common")

for folder in folders:
	skinlist = folder
	

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

streamtypechoices = [('1', 'DVB(1)'), ('4097', 'IPTV(4097)')]

if os.path.exists("/usr/bin/gstplayer"):
	streamtypechoices.append( ('5001', 'GStreamer(5001)' ) )
	
if os.path.exists("/usr/bin/exteplayer3"):
	streamtypechoices.append( ('5002', 'ExtePlayer(5002)') )
	
if os.path.exists("/usr/bin/apt-get"):
	streamtypechoices.append( ('8193', 'GStreamer(8193)') )

	
cfg.livetype = ConfigSelection(default='4097', choices=streamtypechoices)
cfg.vodtype =ConfigSelection(default='4097', choices=streamtypechoices)	
	

try:
	from Components.UsageConfig import defaultMoviePath
	downloadpath = defaultMoviePath()
except:
	from Components.UsageConfig import defaultStorageDevice
	downloadpath = defaultStorageDevice()
		
		 
cfg.location = ConfigDirectory(default=dir_dst)
cfg.main = ConfigYesNo(default=False)
cfg.livepreview = ConfigYesNo(default=False)
cfg.stopstream = ConfigYesNo(default=False)
cfg.skin = ConfigSelection(default='default', choices=folders)
cfg.parental = ConfigYesNo(default=False)
cfg.timeout = ConfigNumber(default=10)
cfg.downloadlocation = ConfigDirectory(default=downloadpath)
cfg.refreshTMDB = ConfigYesNo(default=False)
cfg.TMDBLanguage = ConfigSelection(default='en', choices=languages)
cfg.catchupstart = ConfigSelectionNumber(0, 30, 1, default = 0)
cfg.catchupend = ConfigSelectionNumber(0, 30, 1, default = 0)
cfg.hideall = ConfigYesNo(default=False) 
cfg.api = ConfigSelection(default='enigma2', choices=[('enigma2', _('Enigma2 (Quick)')), ('player', _('Player (Full)'))])

skin_path = skin_directory + cfg.skin.value + '/'

skin_path = '%s%s/' % (skin_directory, cfg.skin.value)
common_path = '%scommon/' % (skin_directory)
json_file = "%splaylists.json" % (dir_dst) 
playlist_path = "%splaylists.txt" % (dir_dst) 

if cfg.location.value:
	playlist_path = "%s/playlists.txt" % (cfg.location.value) 
	print "******** your momma it exists ********%s" % cfg.location.value
	print "******** your momma it exists ********%s" % cfg.location.getValue()
	

	
fontfolder = "%sfonts/" % (dir_plugins) 
imagefolder = "%sicons/" % (dir_plugins) 
imagefolder = "%s/images/" % (skin_path) 

hdr = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/76.0.3809.100 Safari/537.36',
		 'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
		 'Accept-Encoding': 'deflate' }


# delete old folder
if os.path.exists(dir_src):
	if not os.path.exists(dir_dst):
		os.makedirs(dir_dst)

	for file in os.listdir(dir_src):
		src_file = os.path.join(dir_src, file)
		dst_file = os.path.join(dir_dst, file)
		shutil.move(src_file, dst_file)	
	
	shutil.rmtree('/etc/enigma2/X-Streamity/') 
	#os.rmdir('/etc/enigma2/X-Streamity')

# create folder for working files
if not os.path.exists(dir_dst):
	os.makedirs(dir_dst)
	
# delete temporary folder and contents
if os.path.exists(dir_tmp):	
	shutil.rmtree('/tmp/xstreamity') 

# create temporary folder for downloaded files 
if not os.path.exists(dir_tmp):	
	os.makedirs(dir_tmp)

# check if playlists.txt file exists in specified location
if not os.path.isfile(playlist_path):
	open(playlist_path, 'a').close()

# check if playlists.json file exists in specified location
if not os.path.isfile(json_file):
	open(json_file, 'a').close()

# remove 		
def main(session, **kwargs):
	import main
	
	session.open(main.XStreamity_Main)
	return
	
	
def mainmenu(menuid, **kwargs):
	if menuid == 'mainmenu':
		return [(_('XStreamity'), main, 'XStreamity', 50)]
	else:
		return []
		

def extensionsmenu(session, **kwargs):
	import main
	session.open(main.XStreamity_Main)
	return
	

def Plugins(**kwargs):
	addFont(fontfolder + 'subset-RoundedMplus1c-Regular.ttf', 'xstreamityregular', 100, 0)
	addFont(fontfolder + 'subset-RoundedMplus1c-Medium.ttf', 'xstreamitybold', 100, 0)

	iconFile = 'icons/plugin-icon_sd.png'
	if screenwidth.width() > 1280:
		iconFile = 'icons/plugin-icon.png'
	description = (_('IPTV Xtream Codes playlists player by KiddaC'))
	pluginname = (_('XStreamity'))
	
	main_menu = PluginDescriptor(name = pluginname, description=description, where=PluginDescriptor.WHERE_MENU, fnc=mainmenu, needsRestart=True)
	
	extensions_menu = PluginDescriptor(name = pluginname, description=description, where=PluginDescriptor.WHERE_EXTENSIONSMENU, fnc=extensionsmenu, needsRestart=True)
	
	result = [PluginDescriptor(name = pluginname, description = description,where = PluginDescriptor.WHERE_PLUGINMENU,icon = iconFile,fnc = main)]
	
	result.append(extensions_menu)

	
	if cfg.main.getValue():
		result.append(main_menu)

	return result
