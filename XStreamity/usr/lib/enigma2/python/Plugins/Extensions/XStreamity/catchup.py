#!/usr/bin/python
# -*- coding: utf-8 -*-

# for localized messages     
from . import _

from collections import OrderedDict

#import owibranding

from Screens.Screen import Screen
from Screens.VirtualKeyBoard import VirtualKeyBoard
from Screens.InfoBar import InfoBar, MoviePlayer
from plugin import skin_path, imagefolder, screenwidth, hdr, cfg, skinimagefolder, common_path
from enigma import eListboxPythonMultiContent, gFont, RT_HALIGN_LEFT, RT_VALIGN_CENTER, eTimer, eServiceReference, iPlayableService
from Components.ActionMap import ActionMap
from Components.Sources.List import List
from Components.MenuList import MenuList
from Components.Pixmap import Pixmap
from Components.MultiContent import MultiContentEntryText, MultiContentEntryPixmapAlphaBlend
from Components.Renderer.xRunningText import xRunningText 
from Tools.LoadPixmap import LoadPixmap
from Tools.BoundFunction import boundFunction

from xStaticText import StaticText
from datetime import datetime, timedelta
import calendar

#download / parse
import base64
import re
import json
import os
import gzip

import urllib2
import xml.etree.ElementTree as ET
from twisted.web.client import downloadPage, getPage, http
import xstreamity_globals as glob
import streamplayer, imagedownload

from Screens.ParentalControlSetup import ProtectedScreen
from Components.config import *



class XStreamity_Catchup(Screen):
	
	def __init__(self, session, startList, currentList):
		Screen.__init__(self, session)
		self.session = session
		
		self.currentList =[] 
		self.currentList.append(currentList)
		
		skin = skin_path + 'catchup.xml'
	
		with open(skin, 'r') as f:
			self.skin = f.read()
			
		self.setup_title = (_('Catch Up TV'))
		self.main_title = self.currentList[-1]["title"]
		
		self["channel"] = StaticText(self.main_title)
		
		self.list1 = []
		self.channelList = []
		self["channel_list"] = MenuList1(self.channelList)
		self["channel_list"].onSelectionChanged.append(self.selectionChanged)
		self.selectedlist = self["channel_list"]
		
		#epg variables
		self["epg_bg"] = Pixmap()
		self["epg_bg"].hide()
		self["epg_title"] = StaticText()
		self["epg_description"] = StaticText()
		self["epg_picon"] = Pixmap()
		
		self["key_red"] = StaticText(_('Back'))
		self["key_green"] = StaticText(_('OK'))
		self["key_yellow"] = StaticText('')
		self["key_blue"] = StaticText('')
	
		self.isStream = False
		self.pin = False
		
		self.protocol = glob.current_playlist['playlist_info']['protocol']
		self.domain = glob.current_playlist['playlist_info']['domain']
		self.host = glob.current_playlist['playlist_info']['host']
		self.username = glob.current_playlist['playlist_info']['username']
		self.password = glob.current_playlist['playlist_info']['password']
		self.live_categories = "%s/player_api.php?username=%s&password=%s&action=get_live_streams" % (self.host, self.username, self.password)
		self.simpledatatable = "%s/player_api.php?username=%s&password=%s&action=get_simple_data_table&stream_id=" % (self.host, self.username, self.password)
		
		self.catchup_all = []
		self["catchup_list"] = MenuList3(self.catchup_all)
		self["catchup_list"].onSelectionChanged.append(self.selectionChanged)

		self["actions"] = ActionMap(["XStreamityActions"], {
			'red': self.back,
			'cancel': self.back,
			'ok' :  self.next,
			'green' : self.next,
	
			
			"left": self.goLeft,
			"right": self.goRight,
			"up": self.goUp,
			"down": self.goDown,
			"channelUp": self.pageUp,
			"channelDown": self.pageDown,
			"0": self.reset,
			}, -2)
			
		glob.nextlist = []
		glob.nextlist.append({"playlist_url": self.currentList[-1]["playlist_url"], "index": 0})

		self.onFirstExecBegin.append(self.createSetup)
		self.onLayoutFinish.append(self.__layoutFinished)
		
		
	def __layoutFinished(self):
		self.setTitle(self.setup_title)
		self.selectionChanged()
			
		
	def createSetup(self):
		self["epg_title"].setText('')
		self["epg_description"].setText('')
		self.downloadtimer = eTimer()
		ref = str(glob.nextlist[-1]["playlist_url"])
		self.downloadLiveCategories(self.live_categories)
		self.downloadEnigma2Categories(ref)	
		
		
	def downloadLiveCategories(self, url):
		valid = False
		response = ''
		self.live_list_all = []
		self.live_list_archive = []
		
		try:
			response = checkGZIP(url)
			if response != '':
				valid = True
		except Exception as e:
			print(e)
			pass

		except:
			pass
			
		if valid == True and response != '':
			try:
				self.live_list_all =  json.load(response, object_pairs_hook=OrderedDict)
			except:
				try:
					self.live_list_all =  json.loads(response, object_pairs_hook=OrderedDict)
				except:
					pass
			
			for item in self.live_list_all:
				if "tv_archive" and "tv_archive_duration" in item :
					
					if int(item["tv_archive"]) == 1 and int(item["tv_archive_duration"]) > 0:
						self.live_list_archive.append(item)
		else:
			self.close()
			

	def downloadEnigma2Categories(self, url):
		self.list1 = []
		response = ''
		index = 0
		valid = False
		try:
			response = checkGZIP(url)
			if response != '':
				valid = True
		except Exception as e:
			print(e)
			pass

		except:
			pass
			
		self.isStream = False
		if valid == True and response != '':
			root = ET.fromstring(response.read())
			
			for channel in root.findall('channel'):
				title64 = ''
				title = ''
				description64 = ''
				description = ''
				category_id = ''
				playlist_url = ''
				desc_image = ''
				stream_url = ''
			
				time = ''
				starttime = ''
				endtime = ''
				programme = ''
				epgnowtitle = ''
				epgnowtime = ''
				epgnowdescription = ''
				epgnexttitle = ''
				epgnexttime = ''
				epgnextdescription = ''

				title64 = channel.findtext('title')
				title = base64.b64decode(title64).decode('utf-8')
				
				description64 = channel.findtext('description')
				description = base64.b64decode(description64).decode('utf-8')

				#fix invalid utf-8 characters
				try:
					title = ''.join(chr(ord(c)) for c in title).decode('utf8')
				except:
					pass
					
				try:
					description = ''.join(chr(ord(c)) for c in description).decode('utf8')
				except:
					pass
					
				category_id = channel.findtext('category_id')
				playlist_url = channel.findtext('playlist_url')
				desc_image = channel.findtext('desc_image')
				stream_url = channel.findtext('stream_url') 
					
				#remove times from title
				if stream_url and "/live/" in stream_url:
					if len(title.split("[")) > 1:
						if len(title.split("[")) < 3:
							title = title.split("[")[0].strip()
						else:
							if title.find('[') == 0:
								title = "[" + title.split("[")[1]
							else:
								title = title.partition("[")[0]
				
				
				#fix missing port from playlist_url
				if playlist_url:
					if not playlist_url.startswith(self.host):
						playlist_url = str(playlist_url.replace(self.protocol + self.domain ,self.host))
			
				if stream_url:
					self.isStream = True
					#replace stream_url with user output type
					stream_url = stream_url.replace('.ts', "." + glob.current_playlist['playlist_info']['output'])
					if not stream_url.startswith(self.host):
						stream_url = str(stream_url.replace(self.protocol + self.domain ,self.host))
				
					
				hasCatchup = False
				for item in self.live_list_archive:
					if str(category_id) == str(item['category_id']):
						if not stream_url:
							hasCatchup = True
							
							break
						if stream_url:
							stream = stream_url.rpartition('/')[-1]
							stream = stream.replace("." + glob.current_playlist['playlist_info']['output'], "")
							if str(stream) == str(item['stream_id']):
								hasCatchup = True
								break
						
				if hasCatchup:
					self.list1.append([index, str(title), str(description),str(desc_image), str(category_id), str(playlist_url), str(stream_url), \
					str(epgnowtime), str(epgnowtitle), str(epgnowdescription), \
					str(epgnexttime), str(epgnexttitle), str(epgnextdescription)
					])  
				
					index += 1
	
			self.channelList = []
			self.channelList = [buildChannelListEntry(x[0], x[1], x[2], x[3], x[4], x[5], x[6]) for x in self.list1]
			self["channel_list"].setList(self.channelList)
			

			if self["channel_list"].getCurrent():
				#self["channel_list"].selectionEnabled(1)
				try:
					self["channel_list"].moveToIndex(glob.nextlist[-1]['index'])
				except:
					self["channel_list"].moveToIndex(0)
	
		else:
			from Screens.MessageBox import MessageBox
			if not self["channel_list"].getCurrent():
				self.session.openWithCallback(self.close, MessageBox, _('No data or playlist not compatible with X-Streamity plugin.'), MessageBox.TYPE_WARNING, timeout=5)
			else:
				self.session.open(MessageBox, _('Server taking too long to respond.\nAdjust server timeout in main settings.'), MessageBox.TYPE_WARNING, timeout=5)
				self.back()
			

	def back(self):
		if cfg.stopstream.value == True:
			self.stopStream()
			
		if self.selectedlist == self["catchup_list"]:
			self["catchup_list"].selectionEnabled(0)
			self.catchup_all = []
			self['catchup_list'].setList(self.catchup_all)
		
			self["channel_list"].selectionEnabled(1)
			self.selectedlist = self["channel_list"]
		else:
			del glob.nextlist[-1]
			if len(glob.nextlist) == 0:
				self.close()
			else:
				self.createSetup()


	def pinEntered(self, result):
		from Screens.MessageBox import MessageBox
		if not result: 
			self.pin = False
			self.session.open(MessageBox, _("Incorrect pin code."), type=MessageBox.TYPE_ERROR, timeout=5)
		self.next2()
		

	def next(self):
		if not self.isStream:
			self.pin = True
			if cfg.parental.getValue() == True:
				adult = "all,", "+18", "adult", "18+", "18 rated", "xxx" ,"sex", "porn", "pink", "blue"
				if any(s in str(self["channel_list"].getCurrent()[0]).lower() for s in adult):  
					
					from Screens.InputBox import PinInput
					self.session.openWithCallback(self.pinEntered, PinInput, pinList = [config.ParentalControl.setuppin.value], triesEntry = config.ParentalControl.retries.servicepin, title = _("Please enter the parental control pin code"), windowTitle = _("Enter pin code"))
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
		if self.pin == False:
			return
			
		if self["channel_list"].getCurrent():   
			self.currentindex =  self["channel_list"].getCurrent()[3]
			
			glob.nextlist[-1]['index'] = self.currentindex  
			glob.currentchannelist = self.channelList
			glob.currentchannelistindex = self.currentindex
			
			playlist_url = self.channelList[self.currentindex][7]
			stream_url = self.channelList[self.currentindex][8]
			
			if not self.isStream:
				glob.nextlist.append({"playlist_url": playlist_url, "index": 0}) 
				self.createSetup()	
			else:
				if self.selectedlist == self["channel_list"]:
					self.getCatchupList()
				else:
					self.playCatchup()
					
	
	def getCatchupList(self):
		response = ''
		stream = ''
		stream_url = self.channelList[self.currentindex][8]
	
		if stream_url:
			stream = stream_url.rpartition('/')[-1]
			stream = stream.replace("." + glob.current_playlist['playlist_info']['output'], "")
			
		simpleurl = str(self.simpledatatable) + str(stream)
		

		req = urllib2.Request(simpleurl, headers=hdr)
		try:
			response = urllib2.urlopen(req)
		
		except urllib2.URLError as e:
			print(e)
			pass
			
		except socket.timeout as e:
			print(e)
			pass
			
		except:
			print("\n ***** downloadSimpleData unknown error")
			pass
	
		if response != "":
			simple_data_table = json.load(response)
			
			with open('/etc/enigma2/X-Streamity/catchup_json.json', 'w') as f:
				json.dump(simple_data_table, f)
				
			self.archive = []
			hasarchive = False
			if 'epg_listings' in simple_data_table:
				for listing in simple_data_table['epg_listings']:
					if 'has_archive' in listing:
						if listing['has_archive'] == 1:
							hasarchive = True
							self.archive.append(listing)
				
			if hasarchive:			
				with open('/etc/enigma2/X-Streamity/catchup_json2.json', 'w') as f:
					json.dump(self.archive, f)
					
				#remove oldest catchup item in list. Usual void.
				self.archive.pop(0)
				
				self.getlistings()
				
				
	def getlistings(self):
		cu_date_all = ""
		cu_time_all = ""
		cu_title = ""
		cu_description = ""
		cu_play_start = ""
		cu_duration = ""
		cu_start = ""
		cu_start_time = ""
		cu_end = ""
		cu_end_time = ""
		
		
		index = 0
		self.catchup_all = []
		for listing in self.archive:
			if 'start' in listing:
			 
				cu_start = datetime.strptime(listing['start'], '%Y-%m-%d %H:%M:%S')
				cu_start_time = cu_start.strftime("%H:%M")
				cu_day = calendar.day_abbr[cu_start.weekday()]
				cu_start_date = cu_start.strftime("%d/%m")
				cu_play_start = cu_start.strftime('%Y-%m-%d:%H-%M')
				cu_date_all = "%s %s" % (cu_day, cu_start_date)

			if 'end' in listing:
				cu_end = datetime.strptime(listing['end'], '%Y-%m-%d %H:%M:%S')
				cu_end_time = cu_end.strftime("%H:%M")
			

			if "epgshift" in glob.current_playlist["player_info"]:
				if glob.current_playlist["player_info"]["epgshift"] != 0:
					shift = int(glob.current_playlist["player_info"]["epgshift"])
					
					if cu_start_time != "":

						cu_startshift = cu_start + timedelta(hours=shift)
						cu_start_time = format(cu_startshift, '%H:%M') 
						
					if cu_start_time != "":
						cu_endshift = cu_end + timedelta(hours=shift)
						cu_end_time = format(cu_endshift, '%H:%M') 
						
									
			cu_time_all = "%s - %s" % (cu_start_time, cu_end_time)
				
			if 'start_timestamp' in listing and 'stop_timestamp' in listing:
				cu_duration = (int(listing['stop_timestamp']) - int(listing['start_timestamp'])) / 60 

			if 'title' in listing:
				cu_title = base64.b64decode(listing['title'])
				
			if 'description' in listing:
				cu_description = base64.b64decode(listing['description'])
				
			self.catchup_all.append(MenuCatchup(str(cu_date_all), str(cu_time_all), str(cu_title), str(cu_description), str(cu_play_start), str(cu_duration) , index ))
			
			index += 1

		self['catchup_list'].setList(self.catchup_all)
		self["catchup_list"].selectionEnabled(1)
		self.selectedlist = self["catchup_list"]
		self.selectionChanged()

		
	def playCatchup(self):
		streamurl = ''
		streamtype = "4097"
		stream = ''
		stream_url = self["channel_list"].getCurrent()[8]
		
		if stream_url:
			stream = stream_url.rpartition('/')[-1]

		#playurl = "%s/streaming/timeshift.php?username=%s&password=%s&stream=%s&start=%s&duration=%s" % (self.host, self.username, self.password, stream, str(self["catchup_list"].getCurrent()[5]), str(self["catchup_list"].getCurrent()[6]))
		playurl = "%s/timeshift/%s/%s/%s/%s/%s" % (self.host, self.username, self.password, str(self["catchup_list"].getCurrent()[6]), str(self["catchup_list"].getCurrent()[5]),  stream)
		
		req = urllib2.Request(playurl, headers=hdr)
		valid = False
		try:
			response = urllib2.urlopen(req)
			valid = True
			
		
		except urllib2.URLError as e:
			print(e)
			
			pass
			
		except socket.timeout as e:
			print(e)
			
			pass
			
		except:
			print("\n ***** downloadSimpleData unknown error")
			pass
			
		
		if valid == True:
			if stream_url != 'None' and "/live/" in stream_url:
				streamtype = "1"
				self.reference = eServiceReference(int(streamtype), 0, str(playurl))
				glob.catchupdata = [str(self["catchup_list"].getCurrent()[0]), str(self["catchup_list"].getCurrent()[4])]
				self.session.openWithCallback(self.createSetup,streamplayer.XStreamity_CatchupPlayer, str(playurl), str(streamtype))
		else:
			from Screens.MessageBox import MessageBox
			self.session.open(MessageBox, _('Catchup error. No data for this slot'), MessageBox.TYPE_WARNING, timeout=5)
			

		
	def goLeft(self):
		self.selectedlist.pageUp()
		
			
	def goRight(self):
		self.selectedlist.pageDown()
			

	def goUp(self): 
		self.selectedlist.up()


	def goDown(self):
		self.selectedlist.down()
			

	def pageUp(self):
		self.selectedlist.pageUp()
			

	def pageDown(self):
		self.selectedlist.pageDown()
			
						
	def reset(self):
		self.selectedlist.moveToIndex(0)
			

	def selectionChanged(self):
		if self["channel_list"].getCurrent():
			
			channeltitle = self["channel_list"].getCurrent()[0]
			stream_url = self["channel_list"].getCurrent()[8]
			
			self["channel"].setText(self.main_title + ": " + str(channeltitle))
			
			self.timer3 = eTimer()
			self.timer3.stop()
				
			if stream_url != 'None' and "/live/" in stream_url:
				# delay download to stop lag on channel scrolling
				self.timer3.start(500, True)
				try:
					self.timer3_conn = self.timer3.timeout.connect(self.delayedDownload)
				except:
					self.timer3.callback.append(self.delayedDownload)  
		if self.selectedlist == self["catchup_list"]:		
			if self["catchup_list"].getCurrent():
				self["epg_title"].setText(self["catchup_list"].getCurrent()[0])
				self["epg_description"].setText(self["catchup_list"].getCurrent()[4])
			
			
			
	def delayedDownload(self):
		url = ''
		size = []
		if self["channel_list"].getCurrent():
			
			desc_image = self["channel_list"].getCurrent()[5]
			stream_url = self["channel_list"].getCurrent()[8]
			
			if stream_url != 'None' and "/live/" in stream_url and cfg.showpicons.value == True:
				imagetype = "picon"
				url = desc_image
				size = [147,88]
				if screenwidth.width() > 1280:
					size = [220,130]
					
		if size != []:
			if url != '': 
				temp = '/tmp/xstreamity/temp.png'
				preview = '/tmp/xstreamity/preview.png'

				try:
					downloadPage(url, temp).addCallback(self.checkdownloaded, size, imagetype, temp)
				except:
					pass
			else:
				self.loadDefaultImage() 
				
	
	def checkdownloaded(self, data, piconSize, imageType, temp):
		preview = ''
		if os.path.exists(temp):

			try:
				preview = imagedownload.updatePreview(piconSize, imageType, temp)
			except:
				pass

			if preview != '':
				if self["epg_picon"].instance:
					self["epg_picon"].instance.setPixmapFromFile(preview)   
			else:   
				self.loadDefaultImage() 
		return preview
	
		
	def loadDefaultImage(self):
		if self["epg_picon"].instance:
			self["epg_picon"].instance.setPixmapFromFile(common_path + "picon.png")
		
			
	#play original channel
	def stopStream(self):
		if glob.currentPlayingServiceRefString != glob.newPlayingServiceRefString:
			if glob.newPlayingServiceRefString != '':
				self.session.nav.playService(eServiceReference(glob.currentPlayingServiceRefString))	
	
		

class MenuList1(MenuList):
	def __init__(self, list, enableWrapAround=True):
		MenuList.__init__(self, list, enableWrapAround, eListboxPythonMultiContent)
		if screenwidth.width() > 1280:
			self.l.setFont(0, gFont("xstreamityregular", 27))
			self.l.setFont(1, gFont("xstreamitybold", 27))
			self.l.setItemHeight(60)    
		else:
			self.l.setFont(0, gFont("xstreamityregular", 18))
			self.l.setFont(1, gFont("xstreamitybold", 18))
			self.l.setItemHeight(40)    


		
def buildChannelListEntry(index, title, description, desc_image, category_id, playlisturl, stream_url):
	png = None
	if stream_url == 'None':
		png = LoadPixmap(common_path + "more.png")
	else:
		png = LoadPixmap(common_path + "play.png")	
		
	if screenwidth.width() > 1280:

		return [title, 
		MultiContentEntryText(pos = (15, 0), size = (360, 60), font=0, flags = RT_HALIGN_LEFT|RT_VALIGN_CENTER, text = title),
		MultiContentEntryPixmapAlphaBlend(pos=(387, 20), size=(27, 21), png = png),
		index, description, desc_image, category_id, playlisturl, stream_url]
			
	else:
		
		return [title,
		MultiContentEntryText(pos = (8, 0), size = (240, 40), font=0, flags = RT_HALIGN_LEFT|RT_VALIGN_CENTER, text = title),
		MultiContentEntryPixmapAlphaBlend(pos=(258, 13), size=(18, 14), png = png),
		 index, description, desc_image, category_id, playlisturl, stream_url]


def MenuCatchup(date_all, time_all, title, description, start, duration, index):			
	if screenwidth.width() > 1280:
		return [title,
				MultiContentEntryText(pos = (15, 0), size = (213, 60), font=0, flags = RT_HALIGN_LEFT|RT_VALIGN_CENTER, text = date_all ),
				MultiContentEntryText(pos = (240, 0), size = (240, 60), font=0, flags = RT_HALIGN_LEFT|RT_VALIGN_CENTER, text = time_all),
				MultiContentEntryText(pos = (480, 0), size = (828, 60), font=0, flags = RT_HALIGN_LEFT|RT_VALIGN_CENTER, text = title),
			 description, start, duration, index
			]
	else:
			return [title,
				MultiContentEntryText(pos = (10, 0), size = (182, 60), font=0, flags = RT_HALIGN_LEFT|RT_VALIGN_CENTER, text = date_all ),
				MultiContentEntryText(pos = (160, 0), size = (160, 60), font=0, flags = RT_HALIGN_LEFT|RT_VALIGN_CENTER, text = time_all),
				MultiContentEntryText(pos = (320, 0), size = (552, 60), font=0, flags = RT_HALIGN_LEFT|RT_VALIGN_CENTER, text = title),
			 description, start, duration, index
			]
			

class MenuList3(MenuList):
	def __init__(self, list, enableWrapAround=True):
		MenuList.__init__(self, list, enableWrapAround, eListboxPythonMultiContent)
		if screenwidth.width() > 1280:
			self.l.setFont(0, gFont("xstreamityregular", 27))
			self.l.setFont(1, gFont("xstreamitybold", 27))
			self.l.setItemHeight(60)    
		else:
			self.l.setFont(0, gFont("xstreamityregular", 18))
			self.l.setFont(1, gFont("xstreamitybold", 18))
			self.l.setItemHeight(40) 
	  

def checkGZIP(url):
	response = ''
	request = urllib2.Request(url, headers=hdr)

	try:
		timeout = cfg.timeout.getValue()
		response= urllib2.urlopen(request)
		
		if response.info().get('Content-Encoding') == 'gzip':
			print "*** content is gzipped %s " % url
			buffer = StringIO( response.read())
			deflatedContent = gzip.GzipFile(fileobj=buffer)
			return deflatedContent
		else:
			return response
	except:
		pass
		return response
