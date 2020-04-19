#!/usr/bin/python
# -*- coding: utf-8 -*-

# for localized messages
from . import _
from collections import OrderedDict
from Screens.Screen import Screen
#from Screens.InfoBar import InfoBar, MoviePlayer
from plugin import skin_path, screenwidth, hdr, cfg, common_path
from enigma import eTimer, eServiceReference
from Components.ActionMap import ActionMap
from Components.Sources.List import List
from Components.Pixmap import Pixmap
from Tools.LoadPixmap import LoadPixmap
from xStaticText import StaticText
from datetime import datetime, timedelta
import calendar

#download / parse
import base64
import json
import os
import gzip
import socket

import urllib2
import xml.etree.ElementTree as ET
from twisted.web.client import downloadPage
import xstreamity_globals as glob
import streamplayer, imagedownload
from Components.config import config
#from Components.ParentalControl import parentalControl
#from Screens.ParentalControlSetup import ProtectedScreen

from StringIO import StringIO



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
		self["channel_list"] = List(self.channelList, enableWrapAround=True)
		self["channel_list"].onSelectionChanged.append(self.selectionChanged)
		self.selectedlist = self["channel_list"]

		#epg variables
		self["epg_bg"] = Pixmap()
		self["epg_bg"].hide()
		self["epg_title"] = StaticText()
		self["epg_description"] = StaticText()
		self["epg_picon"] = Pixmap()
		self["epg_picon"].hide()
		
		self.catchup_all = []
		self["catchup_list"] = List(self.catchup_all, enableWrapAround=True)
		self["catchup_list"].onSelectionChanged.append(self.selectionChanged)
		


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
		
		self.downloadingpicon = False

		self["actions"] = ActionMap(["XStreamityActions"], {
			'red': self.back,
			'cancel': self.back,
			'ok' :  self.next,
			'green' : self.next,
			"left": self.pageUp,
			"right": self.pageDown,
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
		self.channelList = []
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

					if stream_url and "/live/" in stream_url:
						if title.find('[') == 0:
							title = "[" + str(title.split("[")[1])
						else:
							if not len(title.split("[")) <= 1:
								title = str(title.partition("[")[0])				


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
				try:
					self["channel_list"].setIndex(glob.nextlist[-1]['index'])
				except:
					self["channel_list"].setIndex(0)

		else:
			from Screens.MessageBox import MessageBox
			if not self["channel_list"].getCurrent():
				self.session.openWithCallback(self.close, MessageBox, _('No data or playlist not compatible with X-Streamity plugin.'), MessageBox.TYPE_WARNING, timeout=5)
			else:
				self.session.open(MessageBox, _('Server taking too long to respond.\nAdjust server timeout in main settings.'), MessageBox.TYPE_WARNING, timeout=5)
				self.back()


	def back(self):

		self["epg_title"].setText('')
		self["epg_description"].setText('')
		self["epg_picon"].hide()
		if cfg.stopstream.value == True:
			self.stopStream()

		if self.selectedlist == self["catchup_list"]:
			instance = self["catchup_list"].master.master.instance
			instance.setSelectionEnable(0)
			self.catchup_all = []
			self['catchup_list'].setList(self.catchup_all)

			instance = self["channel_list"].master.master.instance
			instance.setSelectionEnable(1)
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
			self.currentindex =  self["channel_list"].getCurrent()[1]

			glob.nextlist[-1]['index'] = self.currentindex
			glob.currentchannelist = self.channelList
			glob.currentchannelistindex = self.currentindex

			playlist_url = self.channelList[self.currentindex][5]

			if not self.isStream:
				glob.nextlist.append({"playlist_url": playlist_url, "index": 0})
				self["epg_picon"].hide()
				self.createSetup()
			else:
				self["epg_picon"].show()
				if self.selectedlist == self["channel_list"]:
					self.getCatchupList()
				else:
					self.playCatchup()


	def getCatchupList(self):
		response = ''
		stream = ''
		stream_url = self.channelList[self.currentindex][6]

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

			"""
			with open('/etc/enigma2/X-Streamity/catchup_json.json', 'w') as f:
				json.dump(simple_data_table, f)
				"""

			self.archive = []
			hasarchive = False
			if 'epg_listings' in simple_data_table:
				for listing in simple_data_table['epg_listings']:
					if 'has_archive' in listing:
						if listing['has_archive'] == 1:
							hasarchive = True
							self.archive.append(listing)

			if hasarchive:
				"""
				with open('/etc/enigma2/X-Streamity/catchup_json2.json', 'w') as f:
					json.dump(self.archive, f)
					"""

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
		shift = 0
		catchupstart = 0
		catchupend = 0

		index = 0
		self.catchup_all = []
		for listing in self.archive:
			
			if 'title' in listing:
				cu_title = base64.b64decode(listing['title'])

			if 'description' in listing:
				cu_description = base64.b64decode(listing['description'])
				
			if 'start_timestamp' in listing and 'stop_timestamp' in listing:
				start_timestamp = int(listing['start_timestamp'])
				stop_timestamp = int(listing['stop_timestamp'])
				
				if "epgshift" in glob.current_playlist["player_info"]:
					if glob.current_playlist["player_info"]["epgshift"] != 0:
						shift = int(glob.current_playlist["player_info"]["epgshift"])
						
						start_timestamp += shift * 3600
						stop_timestamp += shift * 3600

				cu_day = datetime.fromtimestamp(start_timestamp).strftime("%a")
				cu_start_date = datetime.fromtimestamp(start_timestamp).strftime("%d/%m")
				cu_date_all = "%s %s" % (cu_day, cu_start_date)
				cu_time_all = "%s - %s" % (datetime.fromtimestamp(start_timestamp).strftime("%H:%M"), datetime.fromtimestamp(stop_timestamp).strftime("%H:%M"))
			
	
				if cfg.catchupstart.getValue() != 0:
					catchupstart = int(cfg.catchupstart.getValue())
					
				if cfg.catchupend.getValue() != 0:
					catchupend = int(cfg.catchupend.getValue())
					
				cu_play_start = datetime.fromtimestamp(start_timestamp - (catchupstart * 60) ).strftime('%Y-%m-%d:%H-%M')
				
				cu_duration = ((stop_timestamp + (catchupend * 60)) - (start_timestamp - (catchupstart * 60))) / 60
			
			self.catchup_all.append(MenuCatchup(str(cu_date_all), str(cu_time_all), str(cu_title), str(cu_description), str(cu_play_start), str(cu_duration) , index ))
			

			index += 1

		self.catchup_all.reverse()
		self['catchup_list'].setList(self.catchup_all)
		instance = self["catchup_list"].master.master.instance
		instance.setSelectionEnable(1)
		
			
		self.selectedlist = self["catchup_list"]
		self.selectionChanged()


	def playCatchup(self):
		streamtype = "4097"
		stream = ''
		stream_url = self["channel_list"].getCurrent()[6]

		if stream_url:
			stream = stream_url.rpartition('/')[-1]

		#playurl = "%s/streaming/timeshift.php?username=%s&password=%s&stream=%s&start=%s&duration=%s" % (self.host, self.username, self.password, stream, str(self["catchup_list"].getCurrent()[4]), str(self["catchup_list"].getCurrent()[5]))
		
		playurl = "%s/timeshift/%s/%s/%s/%s/%s" % (self.host, self.username, self.password, str(self["catchup_list"].getCurrent()[5]), str(self["catchup_list"].getCurrent()[4]),  stream)
		
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
				streamtype = "4097"
				self.reference = eServiceReference(int(streamtype), 0, str(playurl))
				glob.catchupdata = [str(self["catchup_list"].getCurrent()[0]), str(self["catchup_list"].getCurrent()[3])]
				self.session.openWithCallback(self.createSetup,streamplayer.XStreamity_CatchupPlayer, str(playurl), str(streamtype))
		else:
			from Screens.MessageBox import MessageBox
			self.session.open(MessageBox, _('Catchup error. No data for this slot'), MessageBox.TYPE_WARNING, timeout=5)


	def goUp(self):
		instance = self.selectedlist.master.master.instance
		instance.moveSelection(instance.moveUp)


	def goDown(self):
		instance = self.selectedlist.master.master.instance
		instance.moveSelection(instance.moveDown)


	def pageUp(self):
		instance = self.selectedlist.master.master.instance
		instance.moveSelection(instance.pageUp)


	def pageDown(self):
		instance = self.selectedlist.master.master.instance
		instance.moveSelection(instance.pageDown)
		

	def reset(self):
		self.selectedlist.setIndex(0)


	def selectionChanged(self):
		self.timerpicon = eTimer()
		self.timerpicon.stop()
		
		if self["channel_list"].getCurrent():

			channeltitle = self["channel_list"].getCurrent()[0]
			stream_url = self["channel_list"].getCurrent()[6]

			self["channel"].setText(self.main_title + ": " + str(channeltitle))

			self.timer3 = eTimer()
			self.timer3.stop()
			
			if stream_url != 'None':
				if "/live/" in stream_url:
					self.downloadingpicon = False
					try:
						self.timerpicon.callback.append(self.downloadPicon)
					except:
						self.timerpicon_conn = self.timerpicon.timeout.connect(self.downloadPicon)
					self.timerpicon.start(200, True)
					
		if self.selectedlist == self["catchup_list"]:
			if self["catchup_list"].getCurrent():
				self["epg_title"].setText(self["catchup_list"].getCurrent()[0])
				self["epg_description"].setText(self["catchup_list"].getCurrent()[3])


	def downloadPicon(self):
		self.timerpicon.stop()
		if self.downloadingpicon:
			return
		self.downloadingpicon = True

		if os.path.exists("/tmp/xstreamity/preview.png"):
			os.remove("/tmp/xstreamity/preview.png")
			
		if os.path.exists("/tmp/xstreamity/original.png"):
			os.remove("/tmp/xstreamity/original.png")
			
		url = ''
		size = []
		if self["channel_list"].getCurrent():	
			desc_image = self["channel_list"].getCurrent()[3]

			if cfg.showpicons.value == True:

				imagetype = "picon"
				url = desc_image
				size = [147,88]
				if screenwidth.width() > 1280:
					size = [220,130]


			if url != '' and url != "n/A" and url != None:
				original = '/tmp/xstreamity/original.png'
			
				d = downloadPage(url, original)
				d.addCallback(self.checkdownloaded, size, imagetype)
				d.addErrback(self.ebPrintError)
				return d
			
			else:
				self.loadDefaultImage()

	def ebPrintError(self, failure):
		pass


	def checkdownloaded(self, data, piconSize, imageType):
			
		self.downloadingpicon = False
		original = '/tmp/xstreamity/original.png'
		if self["channel_list"].getCurrent():
			preview = ''
			if os.path.exists(original):
				try:
					preview = imagedownload.updatePreview(piconSize, imageType, original)
					self.displayImage(preview)
				except Exception as err:
					print "* error ** %s" % err
				except:
					pass


	def displayImage(self, preview):
		stream_url = self["channel_list"].getCurrent()[6]
		preview = '/tmp/xstreamity/preview.png'
		if os.path.exists(preview):
			if self["epg_picon"].instance:
				self["epg_picon"].instance.setPixmapFromFile(preview)
		else:
			self.loadDefaultImage()
				
		if stream_url != 'None' and "/movie/" in stream_url:
			self.displayVod()
		#return preview
		
		
	def loadDefaultImage(self):
		if self["epg_picon"].instance:
			self["epg_picon"].instance.setPixmapFromFile(common_path + "picon.png")


	#play original channel
	def stopStream(self):
		if glob.currentPlayingServiceRefString != glob.newPlayingServiceRefString:
			if glob.newPlayingServiceRefString != '':
				self.session.nav.playService(eServiceReference(glob.currentPlayingServiceRefString))


		 
def buildChannelListEntry(index, title, description, desc_image, category_id, playlisturl, stream_url):
	png = LoadPixmap(common_path + "more.png")
	return (title, index, description, desc_image, category_id, playlisturl, stream_url, png)


def MenuCatchup(date_all, time_all, title, description, start, duration, index):
	return (title, date_all, time_all, description, start, duration, index)


def checkGZIP(url):
	response = ''
	request = urllib2.Request(url, headers=hdr)

	try:
		#timeout = cfg.timeout.getValue()
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
