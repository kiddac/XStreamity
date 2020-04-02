#!/usr/bin/python
# -*- coding: utf-8 -*-

# for localized messages  	 
from . import _

from Plugins.Plugin import PluginDescriptor
from enigma import getDesktop, addFont
from Screens.Screen import Screen
from Components.ConfigList import *
from Components.config import *

import os
import xstreamity_globals as glob
import shutil

screenwidth = getDesktop(0).size()

if screenwidth.width() > 1280:
	skin_directory = '/usr/lib/enigma2/python/Plugins/Extensions/XStreamity/skin/fhd/' 
	
else:
	skin_directory = '/usr/lib/enigma2/python/Plugins/Extensions/XStreamity/skin/hd/' 


folders = os.listdir(skin_directory)
if "common" in folders:
	folders.remove("common")

for folder in folders:
	skinlist = folder
	

config.plugins.XStreamity = ConfigSubsection()

cfg = config.plugins.XStreamity

if os.path.isdir('/usr/lib/enigma2/python/Plugins/SystemPlugins/ServiceApp'):
	cfg.livetype = ConfigSelection(default='4097', choices=[
	 ('1', _('DVB(1)')),
	 ('4097', _('IPTV(4097)')), 
	 ('5001', _('GStreamer(5001)')), 
	 ('5002', 'ExtPlayer(5002)')])
	cfg.vodtype = ConfigSelection(default='4097', choices=[
	 ('1', _('DVB(1)')), 
	 ('4097', _('IPTV(4097)')), 
	 ('5001', _('GStreamer(5001)')), 
	 ('5002', 'ExtPlayer(5002)')])
else:
	cfg.livetype = ConfigSelection(default='4097', choices=[('1', _('DVB(1)')), ('4097', _('IPTV(4097)'))])
	cfg.vodtype =ConfigSelection(default='4097', choices=[('1', _('DVB(1)')), ('4097', _('IPTV(4097)'))])		 
			 
cfg.location = ConfigDirectory(default='/etc/enigma2/X-Streamity/')
cfg.main = ConfigYesNo(default=False)
cfg.showpicons = ConfigYesNo(default=True)
cfg.showcovers = ConfigYesNo(default=True)
cfg.hirescovers = ConfigYesNo(default=False)
cfg.livepreview = ConfigYesNo(default=False)
cfg.stopstream = ConfigYesNo(default=False)
cfg.showlive = ConfigYesNo(default=True)
cfg.showvod = ConfigYesNo(default=True)
cfg.showseries = ConfigYesNo(default=True)
cfg.skin = ConfigSelection(default='default', choices=folders)
cfg.parental = ConfigYesNo(default=False)
cfg.timeout = ConfigNumber(default=10)
cfg.showcatchup = ConfigYesNo(default=True)
cfg.downloadlocation = ConfigDirectory(default='/media/')

skin_path = skin_directory + cfg.skin.value + '/'
common_path = skin_directory + 'common' + '/'

playlist_path = '/etc/enigma2/X-Streamity/playlists.txt'		
if cfg.location.value:
	playlist_path = cfg.location.value + '/playlists.txt'	
	
		 
json_file = '/etc/enigma2/X-Streamity/playlists.json'

fontfolder = '/usr/lib/enigma2/python/Plugins/Extensions/XStreamity/fonts/'
imagefolder = '/usr/lib/enigma2/python/Plugins/Extensions/XStreamity/icons/'
skinimagefolder = skin_path + '/images/'


hdr = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/76.0.3809.100 Safari/537.36',
		 'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
		 'Accept-Encoding': 'deflate' }


# create folder for working files
if not os.path.exists('/etc/enigma2/X-Streamity/'):
	os.makedirs('/etc/enigma2/X-Streamity/')
	
# delete temporary folder and contents
if os.path.exists('/tmp/xstreamity/'):	
	shutil.rmtree('/tmp/xstreamity') 

# create temporary folder for downloaded files 
if not os.path.exists('/tmp/xstreamity/'):	
	os.makedirs('/tmp/xstreamity/')


	
	
		
def main(session, **kwargs):
	import main
	
	session.open(main.XStreamity_Main)
	return
	
	
def mainmenu(menuid, **kwargs):
	if menuid == 'mainmenu':
		return [(_('XStreamity'), main, 'XStreamity', 50)]
	else:
		return []
		


def Plugins(**kwargs):
	addFont(fontfolder + 'subset-RoundedMplus1c-Regular.ttf', 'xstreamityregular', 100, 0)
	addFont(fontfolder + 'subset-RoundedMplus1c-Medium.ttf', 'xstreamitybold', 100, 0)

	iconFile = 'icons/plugin-icon_sd.png'
	if screenwidth.width() > 1280:
		iconFile = 'icons/plugin-icon.png'
	description = (_('IPTV Xtream Codes playlists player by KiddaC'))
	pluginname = (_('XStreamity'))
	
	main_menu = PluginDescriptor(name = pluginname, description=description, where=PluginDescriptor.WHERE_MENU, fnc=mainmenu, needsRestart=True)
	
	result = [PluginDescriptor(name = pluginname, description = description,where = PluginDescriptor.WHERE_PLUGINMENU,icon = iconFile,fnc = main)]
	
	if cfg.main.getValue():
		result.append(main_menu)

	return result
