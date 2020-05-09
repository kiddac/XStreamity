#!/usr/bin/python
# -*- coding: utf-8 -*-

# for localized messages
from . import _

from collections import OrderedDict
from Screens.Screen import Screen
from Screens.VirtualKeyBoard import VirtualKeyBoard
from plugin import skin_path, screenwidth, hdr, cfg, common_path
from enigma import eTimer, eServiceReference
from Components.ActionMap import ActionMap
from Components.Sources.List import List
from Components.Pixmap import Pixmap
from Components.ProgressBar import ProgressBar
from Components.config import config
from Tools.LoadPixmap import LoadPixmap
from xStaticText import StaticText
from datetime import datetime, timedelta

#download / parse
import base64
import re
import json
import os
import gzip
import urllib2
import xml.etree.ElementTree as ET
from twisted.web.client import downloadPage

import xstreamity_globals as glob
import streamplayer, imagedownload
import math

from StringIO import StringIO



class XStreamity_Categories(Screen):

	def __init__(self, session, category):
		Screen.__init__(self, session)
		self.session = session
	
		self.searchString = ''

		skin = skin_path + 'categories.xml'

		with open(skin, 'r') as f:
			self.skin = f.read()

		self.setup_title = (_('Categories'))
		
		if category == 0:
			self.main_title = "Live Streams"
			url = str(glob.current_playlist['playlist_info']['enigma2_api']) + "&type=get_live_categories"
		if category == 1:
			self.main_title = "Vod"
			url = str(glob.current_playlist['playlist_info']['enigma2_api']) + "&type=get_vod_categories"
		if category == 2:
			self.main_title = "TV Series"
			url = str(glob.current_playlist['playlist_info']['enigma2_api']) + "&type=get_series_categories"


		self.level = 1
		
		glob.nextlist = []
		glob.nextlist.append({"playlist_url": url, "index": 0, "level": self.level})

		self["channel"] = StaticText(self.main_title)

		self.list1 = []
		self.channelList = []
		self["channel_list"] = List(self.channelList, enableWrapAround=True)
		self["channel_list"].onSelectionChanged.append(self.selectionChanged)
		
		self.selectedlist = self["channel_list"]

		self.listAll = []
		self.channelListAll = []

		#epg variables
		self["epg_bg"] = Pixmap()
		self["epg_bg"].hide()

		self["epg_title"] = StaticText()
		self["epg_description"] = StaticText()

		self.epglist = []
		self["epg_list"] = List(self.epglist)
		
		self.epgshortlist = []
		self["epg_short_list"] =  List(self.epgshortlist, enableWrapAround=True)
		self["epg_short_list"].onSelectionChanged.append(self.displayShortEPG)

		self["epg_picon"] = Pixmap()
		self["epg_picon"].hide()

		#vod variables
		self["vod_background"] = Pixmap()
		self["vod_background"].hide()
		self["vod_cover"] = Pixmap()
		self["vod_cover"].hide()
		self["vod_video_type_label"] = StaticText()
		self["vod_duration_label"]= StaticText()
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

		self.isStream = False
		self.filtered = False
		self.filter_list = []

		self.pin = False

		self.protocol = glob.current_playlist['playlist_info']['protocol']
		self.domain = glob.current_playlist['playlist_info']['domain']
		self.host = glob.current_playlist['playlist_info']['host']

		self["page"] = StaticText('')
		self["listposition"] = StaticText('')
		self.page = 0
		self.pageall = 0
		self.position = 0
		self.positionall = 0
		self.itemsperpage = 12

		self.downloading = False
		self.downloadingpicon = False
		self.downloadingcover = False
		
		self.showingshortEPG = False
		
		self.token = "ZUp6enk4cko4ZzBKTlBMTFNxN3djd25MOHEzeU5Zak1Bdkd6S3lPTmdqSjhxeUxMSTBNOFRhUGNBMjBCVmxBTzlBPT0K"

		self["actions"] = ActionMap(["XStreamityActions"], {
			'red': self.back,
			'cancel': self.back,
			'ok' :  self.next,
			'green' : self.next,
			'yellow' : self.sort,
			'blue' : self.search,
			'epg' : self.nownext,
			"epg_long" : self.shortEPG,
			'text' : self.nownext,
			"left": self.pageUp,
			"right": self.pageDown,
			"up": self.goUp,
			"down": self.goDown,
			"channelUp": self.pageUp,
			"channelDown": self.pageDown,
			"rec": self.downloadVod,
			"0": self.reset,
			"menu": self.showHiddenList,
		

			}, -1)
			
		self["actions"].csel = self


		self.onFirstExecBegin.append(self.createSetup)
		
		self.onLayoutFinish.append(self.__layoutFinished)


	def __layoutFinished(self):
		self.setTitle(self.setup_title)



	def createSetup(self):
		if self.filtered:
			self.resetSearch()

		self["epg_title"].setText('')
		self["epg_description"].setText('')
		self.downloadtimer = eTimer()

		ref = str(glob.nextlist[-1]["playlist_url"])

		"""
		try:
			import boxbranding
			print "BOXBRANDING"
			print "getMachineBuild = %s" % boxbranding.getMachineBuild()
			print "getMachineBrand = %s" % boxbranding.getMachineBrand()
			print "getMachineName = %s" % boxbranding.getMachineName()
			print "getMachineProcModel = %s" % boxbranding.getMachineProcModel()
			print "getBoxType = %s" % boxbranding.getBoxType()
			print "getBrandOEM = %s" % boxbranding.getBrandOEM()
			print "getOEVersion = %s" % boxbranding.getOEVersion()
			print "getDriverDate = %s" % boxbranding.getDriverDate()
			print "getImageVersion = %s" % boxbranding.getImageVersion()
			print "getImageBuild = %s" % boxbranding.getImageBuild()
			print "getImageDistro = %s" % boxbranding.getImageDistro()
		except:
			print "**** image does not have boxbranding"
			pass

		try:
			import owibranding
			print "OWIBRANDING"
			print "getMachineBuild = %s" % owibranding.getMachineBuild()
			print "getMachineBrand = %s" % owibranding.getMachineBrand()
			print "getMachineName = %s" % owibranding.getMachineName()
			print "getMachineProcModel = %s" % owibranding.getMachineProcModel()
			print "getBoxType = %s" % owibranding.getBoxType()
			print "getOEVersion = %s" % owibranding.getOEVersion()
			print "getDriverDate = %s" % owibranding.getDriverDate()
			print "getImageVersion = %s" % owibranding.getImageVersion()
			print "getImageBuild = %s" % owibranding.getImageBuild()
			print "getImageDistro = %s" % owibranding.getImageDistro()
		except:
			print "**** owibranding failed to load"
			pass
			"""

		if self.level == 1:
			self["key_menu"].setText(_("Hide/Show"))
			self["key_epg"].setText('')
		else:
			self["key_menu"].setText('')

		self.downloadEnigma2Categories(ref)
		#self.selectionChanged()


	def downloadEnigma2Categories(self, url):
		self.list1 = []
		self.channelList = []
		self.listAll = []
		self.channelListAll = []
		self.voditemlist = []

		response = ''
		index = 0
		indexAll = 0
		levelpath = '/tmp/xstreamity/level' + str(self.level) + '.xml'
		valid = False

		if not os.path.exists(levelpath):
			try:
				response = checkGZIP(url)
				if response != '':
					valid = True

					try:
						content = response.read()
					except:
						content = response

					with open(levelpath, 'w') as f:
						f.write(content)

			except Exception as e:
				print(e)
				pass

			except:
				pass
		else:
			valid = True
			with open(levelpath, "r") as f:
				content = f.read()

		self.isStream = False
		if valid == True and content != '':
			root = ET.fromstring(content)
			for channel in root.findall('channel'):
				hidden = False
				title64 = ''
				title = ''
				description64 = ''
				description = ''
				category_id = ''
				playlist_url = ''
				desc_image = ''
				stream_url = ''
				time = ''
				epgnowtitle = ''
				epgnowtime = ''
				epgnowdescription = ''
				epgnexttitle = ''
				epgnexttime = ''
				epgnextdescription = ''
				vodItems = {}

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


				if stream_url and "/live/" in stream_url:
					# check if channel has EPG data
					if description != '':
						lines = re.split("\n", description)
						newdescription = []

						#use string manipulation rather than regex for speed.
						for line in lines:
							if line.startswith("[") or line.startswith("("):
								newdescription.append(line)
							  
							if line.startswith("COVER_BIG:"):
								coverurl = title.partition(":")[-1]
								if coverurl.startswith("https://image.tmdb.org/t/p/"):
									dimensions = coverurl.partition("/p/")[2].partition("/")[0]
									if screenwidth.width() <= 1280:
										desc_image = coverurl.replace(dimensions, "w267")
									else:
										desc_image = coverurl.replace(dimensions, "w300")
								 
					
						try:
							epgnowtime = newdescription[0].partition(" ")[0].lstrip("[").rstrip("]")
						except:
							pass

						try:
							epgnowtitle = newdescription[0].partition(" ")[-1].strip()
						except:
							pass

						try:
							epgnowdescription = newdescription[1].lstrip("(").rstrip(")").strip()
						except:
							pass

						try:
							epgnexttime = newdescription[2].partition(" ")[0].lstrip("[").rstrip("]")
						except:
							pass

						try:
							epgnexttitle = newdescription[2].partition(" ")[-1].strip()
						except:
							pass

						try:
							epgnextdescription = newdescription[3].lstrip("(").rstrip(")").strip()
						except:
							pass

						if "epgshift" in glob.current_playlist["player_info"]:
							if glob.current_playlist["player_info"]["epgshift"] != 0:

								#apply epg timeshift
								if epgnowtime != "":
									epgnowtime =  "%s:2020" % epgnowtime
									time = datetime.strptime(epgnowtime, "%H:%M:%Y")
									shift = int(glob.current_playlist["player_info"]["epgshift"])
									epgnowshifttime = time + timedelta(hours=shift)
									epgnowtime = format(epgnowshifttime, '%H:%M')

								if epgnexttime != "":
									epgnexttime =  "%s:2020" % epgnexttime
									time = datetime.strptime(epgnexttime, "%H:%M:%Y")
									shift = int(glob.current_playlist["player_info"]["epgshift"])
									epgnextshifttime = time + timedelta(hours=shift)
									epgnexttime = format(epgnextshifttime, '%H:%M')

				if stream_url and "/movie/" in stream_url:
					vodLines = description.splitlines()

					for line in vodLines:
						vodItems[str(line.partition(": ")[0])] = str(line.partition(": ")[-1].encode('utf-8'))

				if playlist_url and category_id:
					if "get_live_streams" in playlist_url and category_id in glob.current_playlist['player_info']['livehidden']:
						hidden = True

					elif "get_vod_streams" in playlist_url and category_id in glob.current_playlist['player_info']['vodhidden']:
						hidden = True

					elif "get_series" in playlist_url and category_id in glob.current_playlist['player_info']['serieshidden']:
						hidden = True

				if hidden == False:
					self.list1.append([index, str(title), str(description),str(desc_image), str(category_id), str(playlist_url), str(stream_url), \
					str(epgnowtime), str(epgnowtitle), str(epgnowdescription), \
					str(epgnexttime), str(epgnexttitle), str(epgnextdescription)]
					)
					self.voditemlist.append([str(title), vodItems])
					index += 1
					
				self.listAll.append([indexAll, str(title), str(description),str(desc_image), str(category_id), str(playlist_url), str(stream_url), \
				str(epgnowtime), str(epgnowtitle), str(epgnowdescription), \
				str(epgnexttime), str(epgnexttitle), str(epgnextdescription)]
				)  

				indexAll += 1

			self.channelList = []
			self.channelList = [buildChannelListEntry(x[0], x[1], x[2], x[3], x[4], x[5], x[6]) for x in self.list1]
			
			self.channelListAll = []
			self.channelListAll = [buildChannelListEntry(x[0], x[1], x[2], x[3], x[4], x[5], x[6]) for x in self.listAll]

			self["channel_list"].setList(self.channelList)

			self.epglist = []
			self.epglist = [buildEPGListEntry(x[0], x[1], x[7], x[8], x[9], x[10], x[11], x[12]) for x in self.list1]

			
			self["epg_list"].setList([])

			glob.sort_list1 = self.channelList[:]
			glob.sort_list2 = self.epglist[:]
			glob.sort_list3 = self.voditemlist[:]

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
		
		if self.selectedlist == self["epg_short_list"]:
			 self.shortEPG()
			 return
			
		self.resetSearch()
		self.hideEPG()
		self.hideVod()
		del glob.nextlist[-1]

		self["key_yellow"].setText(_('Sort: A-Z'))
		self["key_rec"].setText('')

		if cfg.stopstream.value == True:
			self.stopStream()

		levelpath = '/tmp/xstreamity/level' + str(self.level) + '.xml'
		if os.path.exists(levelpath):
			os.remove(levelpath)
		self.level -= 1

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

		self["key_yellow"].setText(_('Sort: A-Z'))
		if self["channel_list"].getCurrent():

			currentindex =  self["channel_list"].getCurrent()[1]

			glob.nextlist[-1]['index'] = currentindex

			self.channelList = glob.sort_list1
			self.epglist = glob.sort_list2
			self.voditemlist = glob.sort_list3

			glob.currentchannelist = self.channelList
			glob.currentchannelistindex = currentindex
			glob.currentepglist = self.epglist

			playlist_url = self.channelList[currentindex][5]
			stream_url = self.channelList[currentindex][6]
			
			if not self.isStream:
				glob.nextlist.append({"playlist_url": playlist_url, "index": 0})
				self.level += 1
				self.createSetup()
			else:
				streamtype = "4097"

				if stream_url != 'None' and "/live/" in stream_url:
					
					
					streamtype = glob.current_playlist["player_info"]["livetype"]
					self.reference = eServiceReference(int(streamtype), 0, stream_url)
					if self.session.nav.getCurrentlyPlayingServiceReference():
						if self.session.nav.getCurrentlyPlayingServiceReference().toString() != self.reference.toString() and cfg.livepreview.value == True:
							self.session.nav.stopService()
							self.session.nav.playService(self.reference)
							if self.session.nav.getCurrentlyPlayingServiceReference():
								glob.newPlayingServiceRef = self.session.nav.getCurrentlyPlayingServiceReference()
								glob.newPlayingServiceRefString = glob.newPlayingServiceRef.toString()

						else:
							self.session.nav.stopService()
							self.session.openWithCallback(self.createSetup, streamplayer.XStreamity_StreamPlayer, str(stream_url), str(streamtype))
					else:
						self.session.nav.stopService()
						self.session.openWithCallback(self.createSetup, streamplayer.XStreamity_StreamPlayer, str(stream_url), str(streamtype))

				if stream_url != 'None' and ("/movie/" in stream_url or "/series/" in stream_url):
					streamtype = glob.current_playlist["player_info"]["vodtype"]
					self.reference = eServiceReference(int(streamtype), 0, stream_url)
					self.session.openWithCallback(self.createSetup,streamplayer.XStreamity_VodPlayer, str(stream_url), str(streamtype))



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


	def displayProgress(self):
		start = ''
		end = ''
		percent = 0


		if self["epg_list"].getCurrent():

			startnowtime = self["epg_list"].getCurrent()[2]
			startnexttime = self["epg_list"].getCurrent()[5]

			if startnowtime != '':
				start = startnowtime

			if startnexttime != '':
				end = startnexttime

		if start != '' and end != '':
			self["progress"].show()
			start_time = datetime.strptime(start, "%H:%M")
			end_time = datetime.strptime(end, "%H:%M")
			if end_time < start_time:
				end_time = datetime.strptime(end, "%H:%M")  + timedelta(hours=24)

			total_time = end_time - start_time
			duration = 0
			if total_time.total_seconds() > 0:
			  duration = total_time.total_seconds()/60

			now = datetime.now().strftime("%H:%M")
			current_time = datetime.strptime(now, "%H:%M")
			elapsed = current_time - start_time

			elapsedmins = 0
			if elapsed.total_seconds() > 0:
			  elapsedmins = elapsed.total_seconds()/60

			if duration > 0:
			  percent = int(elapsedmins / duration * 100)
			else:
			  percent = 100

			if percent < 0:
				percent = 0
				
			if percent > 100:
				percent = 100

			self["progress"].setValue(percent)
		else:
			self["progress"].hide()


	def selectionChanged(self):
		self.timerpicon = eTimer()
		self.timerpicon.stop()
		
		self.timercover = eTimer()
		self.timercover.stop()
		
		#self["epg_short_list"].setList([])
		self.showingshortEPG = False
		
		if self["channel_list"].getCurrent():

			channeltitle = self["channel_list"].getCurrent()[0]
			stream_url = self["channel_list"].getCurrent()[6]
			currentindex = self["channel_list"].getIndex()
			
			self.position = currentindex + 1
			self.positionall = len(self.channelList)

			self.page = int(math.ceil(float(self.position) / float(self.itemsperpage)))
			self.pageall = int(math.ceil(float(self.positionall) / float(self.itemsperpage)))

			self["page"].setText('Page: ' + str(self.page) + " of " + str(self.pageall))
			self["listposition"].setText(str(self.position) + "/" + str(self.positionall))

			self["channel"].setText(self.main_title + ": " + str(channeltitle))

			
			if stream_url != 'None':
				if "/live/" in stream_url:
					self.downloadingpicon = False
					try:
						self.timerpicon.callback.append(self.downloadPicon)
					except:
						self.timerpicon_conn = self.timerpicon.timeout.connect(self.downloadPicon)
					self.timerpicon.start(200, True)

					self.displayEPG()
					self.displayProgress()
					self["key_rec"].setText('')

				else:
					self.hideEPG()
					self["key_rec"].setText(_("Download"))

					if "/movie/" in stream_url:
						self.downloadingcover = False
						try:
							self.timercover.callback.append(self.downloadCover)
						except:
							self.timercover_conn = self.timercover.timeout.connect(self.downloadCover)
						self.timercover.start(500, True)
						if cfg.refreshTMDB.value == True:
							self.getTMDB()
							self.displayVod()
						else:
							self.displayVod()
							
					else:
						self.hideVod()
						


	def displayEPG(self):
		if self["epg_list"].getCurrent() is None:
			self["epg_picon"].show()
			self["epg_bg"].show()
			self["epg_list"].setList(self.epglist)

		if self["epg_list"].getCurrent():
			currentindex = self["channel_list"].getIndex()
	
			instance = self["epg_list"].master.master.instance
			instance.setSelectionEnable(1)
			self["epg_list"].setIndex(currentindex)

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
				stream_url = self["channel_list"].getCurrent()[6]
				if stream_url != 'None':
					if "/live/" in stream_url:
						
						stream_id = stream_url.rpartition("/")[-1].partition(".")[0]
								
						response = ''
						player_api = str(glob.current_playlist["playlist_info"]["player_api"])
						shortEPGJson = []
						try:
							response = checkGZIP(str(player_api) + "&action=get_short_epg&stream_id=" + str(stream_id) + "&limit=50")

						except Exception as e:
							print(e)
							
						except:
							pass
							
						if response != '':
							try:
								shortEPGJson = json.load(response, object_pairs_hook=OrderedDict)
							except:
								try:
									shortEPGJson = json.loads(response, object_pairs_hook=OrderedDict)
								except:
									pass
									
							epg_title = ""
							epg_description = ""
							epg_date_all = ""
							epg_time_all = ""

							index = 0 
							
							self.epgshortlist = []

							if "epg_listings" in shortEPGJson:
								for listing in shortEPGJson["epg_listings"]:
									
									if 'title' in listing:
										epg_title = base64.b64decode(listing['title'])

									if 'description' in listing:
										epg_description = base64.b64decode(listing['description'])
										
									if 'start_timestamp' in listing and 'stop_timestamp' in listing:
										start_timestamp = int(listing['start_timestamp'])
										stop_timestamp = int(listing['stop_timestamp'])
										
										if "epgshift" in glob.current_playlist["player_info"]:
											if glob.current_playlist["player_info"]["epgshift"] != 0:
												shift = int(glob.current_playlist["player_info"]["epgshift"])
												start_timestamp += shift * 3600
												stop_timestamp += shift * 3600
										
										epg_day = datetime.fromtimestamp(start_timestamp).strftime("%a")
										epg_start_date = datetime.fromtimestamp(start_timestamp).strftime("%d/%m")
										epg_date_all = "%s %s" % (epg_day, epg_start_date)
										epg_time_all = "%s - %s" % (datetime.fromtimestamp(start_timestamp).strftime("%H:%M"), datetime.fromtimestamp(stop_timestamp).strftime("%H:%M"))

									self.epgshortlist.append(buildShortEPGListEntry(str(epg_date_all), str(epg_time_all), str(epg_title), str(epg_description), index ))
									
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
			self.selectionChanged()
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

		
					
	def nownext(self):
		
		if self["channel_list"].getCurrent():
			currentindex = self["channel_list"].getCurrent()[1]

			stream_url = self.channelList[currentindex][6]

			if stream_url != 'None':
				if "/live/" in stream_url:
					if self["key_epg"] != '' and self["epg_list"].getCurrent():
						startnowtime = self["epg_list"].getCurrent()[2]
						titlenow = self["epg_list"].getCurrent()[3]
						descriptionnow = self["epg_list"].getCurrent()[4]

						startnexttime = self["epg_list"].getCurrent()[5]
						titlenext =  self["epg_list"].getCurrent()[6]
						descriptionnext = self["epg_list"].getCurrent()[7]

						if self["key_epg"].getText() != '' or None:
							current_epg = self["key_epg"].getText()
							if current_epg == (_("Next Info")):

								nexttitle = "Next %s:  %s" % (startnexttime, titlenext )
								self["epg_title"].setText(nexttitle)
								self["epg_description"].setText(descriptionnext)
								self["key_epg"].setText(_("Now Info"))

							else:
								nowtitle = "%s - %s  %s" % (startnowtime, startnexttime, titlenow)
								self["epg_title"].setText(nowtitle)
								self["epg_description"].setText(descriptionnow)
								self["key_epg"].setText(_("Next Info"))

				elif "/movie/" in stream_url:
					if self["key_rec"] != '':
						self.openIMDb()
		


	def displayVod(self):
		self["vod_cover"].show()
		self["vod_background"].show()
		self["vod_video_type_label"].setText(_('Video Type:'))
		self["vod_duration_label"].setText(_('Duration:'))
		self["vod_genre_label"].setText(_('Genre:'))
		self["vod_rating_label"].setText(_('Rating:'))
		self["vod_country_label"].setText(_('Country:'))
		self["vod_release_date_label"].setText(_('Release Date:'))
		self["vod_director_label"].setText(_('Director:'))
		self["vod_cast_label"].setText(_('Cast:'))

		if self["channel_list"].getCurrent():

			currentindex = self["channel_list"].getIndex()
			
			currentvod = self.voditemlist[currentindex][1]

			stream_url = self["channel_list"].getCurrent()[6]
			if len(self.voditemlist) > 0:
				self["vod_title"].setText(self.voditemlist[currentindex][0])
				
				if 'NAME' in currentvod and currentvod["NAME"] != '':
					self["vod_title"].setText(currentvod["NAME"])
				elif 'O_NAME' in currentvod and currentvod["O_NAME"] != '':
					self["vod_title"].setText(currentvod["O_NAME"])
					
				if 'DESCRIPTION' in currentvod and currentvod["DESCRIPTION"] != '':
					self["vod_description"].setText(currentvod["DESCRIPTION"])
				elif 'PLOT' in currentvod and currentvod["PLOT"] != '':
					self["vod_description"].setText(currentvod["PLOT"])
				else:
					self["vod_description"].setText('')

				try:
					if self["channel_list"].getCurrent():
						self["vod_video_type"].setText(stream_url.split('.')[-1])
				except:
					pass

				if 'DURATION' in currentvod and currentvod["DURATION"] != '':
					self["vod_duration"].setText(currentvod["DURATION"]) 
				else:
					self["vod_duration"].setText('')
					
				if 'GENRE' in currentvod and (currentvod["GENRE"] != '' or currentvod["GENRE"] != []):
					self["vod_genre"].setText(currentvod["GENRE"])
				else:
					self["vod_genre"].setText('')
				
				if 'RATING' in currentvod and currentvod["RATING"] != '':
					self["vod_rating"].setText(currentvod["RATING"])
				else:
					self["vod_rating"].setText('')
					
				if 'COUNTRY' in currentvod and currentvod["COUNTRY"] != '':
					self["vod_country"].setText(currentvod["COUNTRY"])
				else:
					self["vod_country"].setText('')
					
				if 'RELEASEDATE' in currentvod and currentvod["RELEASEDATE"] != '':
					try:
						self["vod_release_date"].setText(datetime.strptime(currentvod["RELEASEDATE"], "%Y-%m-%d").strftime("%Y"))
					except:
						pass
				else:
					self["vod_release_date"].setText('')

				if 'DIRECTOR' in currentvod and (currentvod["DIRECTOR"] != '' or currentvod["DIRECTOR"] != []):
					self["vod_director"].setText(currentvod["DIRECTOR"])
				else:
					self["vod_director"].setText('')

				if 'CAST' in currentvod and (currentvod["CAST"] != '' or currentvod["CAST"] != []):
					self["vod_cast"].setText(currentvod["CAST"])
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


	def sort(self):
		if self["channel_list"].getCurrent():
			stream_url = self["channel_list"].getCurrent()[6]

			if not self.filtered:
				current_sort = self["key_yellow"].getText()

				if current_sort == (_('Sort: A-Z')):
					self["key_yellow"].setText(_('Sort: Z-A'))
					self.channelList.sort(key=lambda x: x[0], reverse=False)

					if stream_url != 'None' and "/live/" in stream_url:
						self.epglist.sort(key=lambda x: x[0], reverse=False)
			
					if stream_url != 'None' and "/movie/" in stream_url:
						self.voditemlist.sort(key=lambda x: x[0], reverse=False)


				if current_sort == (_('Sort: Z-A')):
					self["key_yellow"].setText(_('Sort: Original'))
					self.channelList.sort(key=lambda x: x[0], reverse=True)	
	
					if stream_url != 'None' and "/live/" in stream_url:
						self.epglist.sort(key=lambda x: x[0], reverse=True)
				
					if stream_url != 'None' and "/movie/" in stream_url:
						self.voditemlist.sort(key=lambda x: x[0], reverse=True)

				if current_sort == (_('Sort: Original')):
					self["key_yellow"].setText(_('Sort: A-Z'))
					self.channelList = glob.sort_list1
					
					if self["channel_list"].getCurrent():
						
						if stream_url != 'None' and "/live/" in stream_url:
							self.epglist = glob.sort_list2

						if stream_url != 'None' and "/movie/" in stream_url:
								self.voditemlist = glob.sort_list3
				
				self["channel_list"].setList(self.channelList)
				self["channel_list"].setIndex(0)
					
				if stream_url != 'None' and "/live/" in stream_url:
					self["epg_list"].setList(self.epglist)
					self["epg_list"].setIndex(0)
					
				if stream_url != 'None' and "/movie/" in stream_url:
					self.displayVod()


	def search(self):
		current_filter = self["key_blue"].getText()
		if current_filter != (_('Reset Search')):
			self.session.openWithCallback(self.filterChannels, VirtualKeyBoard, title = _("Filter this category..."), text = self.searchString)
		else:
			self.resetSearch()


	def filterChannels(self, result):
		if result:
			self.searchString = result
			self["key_blue"].setText(_('Reset Search'))
			self["key_yellow"].setText('')

			glob.filter_list1 = self.channelList[:]
			glob.filter_list2 = self.epglist[:]
			glob.filter_list3 = self.voditemlist[:]

			self.channelList = [channel for channel in self.channelList if str(result).lower() in str(channel[0]).lower()]
			self.epglist = [channel for channel in self.epglist if str(result).lower() in str(channel[0]).lower()]
			self.voditemlist = [channel for channel in self.voditemlist if str(result).lower() in str(channel[0]).lower()]

			self["epg_list"].setList(self.epglist)
			self["channel_list"].setList(self.channelList)

			self.filtered = True


	def resetSearch(self):
		self["key_blue"].setText(_('Search'))
		self["key_yellow"].setText(_('Sort: A-Z'))
		self.channelList = glob.filter_list1
		self.epglist = glob.filter_list2
		self.voditemlist = glob.filter_list3

		self["epg_list"].setList(self.epglist)
		self.displayEPG()
		self.displayProgress()

		self["channel_list"].setList(self.channelList)

		glob.filter_list1 = []
		glob.filter_list2 = []
		glob.filter_list3 = []
		self.filtered = False


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

			imagetype = "picon"
			url = desc_image
			size = [147,88]
			if screenwidth.width() > 1280:
				size = [220,130]

			if url != '' and url != "n/A" and url != None:
				original = '/tmp/xstreamity/original.png'
			
				d = downloadPage(url, original, timeout=3)
				d.addCallback(self.checkdownloaded, size, imagetype)
				d.addErrback(self.ebPrintError)
				return d
			else:
				self.loadDefaultImage()
	

	def downloadCover(self):
		self.timercover.stop()
		if self.downloadingcover:
			return
		self.downloadingcover = True

		if os.path.exists("/tmp/xstreamity/preview.png"):
			os.remove("/tmp/xstreamity/preview.png")
			
		if os.path.exists("/tmp/xstreamity/original.png"):
			os.remove("/tmp/xstreamity/original.png")
			
		url = ''
		size = []
		if self["channel_list"].getCurrent():

			currentindex = self["channel_list"].getIndex()
				
			desc_image = self["channel_list"].getCurrent()[3]


			self.loadDefaultImage()
			imagetype = "cover"

			url = desc_image
			
			if 'COVER_BIG' in self.voditemlist[currentindex][1]:
				if self.voditemlist[currentindex][1]["COVER_BIG"] != '' and self.voditemlist[currentindex][1]["COVER_BIG"] != None and self.voditemlist[currentindex][1]["COVER_BIG"] != "n/A":
					url = self.voditemlist[currentindex][1]["COVER_BIG"]
				else:
					url = ''

			size = [267, 400]
			if screenwidth.width() > 1280:
				size = [400,600]


			if url != '' and url != "n/A" and url != None:
				original = '/tmp/xstreamity/original.png'
			
				d = downloadPage(url, original, timeout=3)
				d.addCallback(self.checkdownloaded, size, imagetype)
				d.addErrback(self.ebPrintError)
				return d
			else:
				self.loadDefaultImage()

				
	def ebPrintError(self, failure):
		pass


	def check(self, token):
		result =  base64.b64decode((base64.b64decode(base64.b64decode(token)).decode('zlib').decode('utf-8')))
		return result
		

	def checkdownloaded(self, data, piconSize, imageType):
		self.downloading = False
		self.downloadingpicon = False
		self.downloadingcover = False
			
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
			if self["vod_cover"].instance:
				self["vod_cover"].instance.setPixmapFromFile(preview)

			if self["epg_picon"].instance:
				self["epg_picon"].instance.setPixmapFromFile(preview)
		else:
			self.loadDefaultImage()
				
		if stream_url != 'None' and "/movie/" in stream_url:
			self.displayVod()
		#return preview
		

	def loadDefaultImage(self):
		if self["vod_cover"].instance:
			self["vod_cover"].instance.setPixmapFromFile(skin_path + "images/vod_cover.png")

		if self["epg_picon"].instance:
			self["epg_picon"].instance.setPixmapFromFile(common_path + "picon.png")


	#play original channel
	def stopStream(self):
		if glob.currentPlayingServiceRefString != glob.newPlayingServiceRefString:
			if glob.newPlayingServiceRefString != '':
				self.session.nav.playService(eServiceReference(glob.currentPlayingServiceRefString))


	def downloadVod(self):
		if self['key_rec'] != '':
			seriesstring = ''
			from Screens.MessageBox import MessageBox

			if self["channel_list"].getCurrent():
				currentindex =  self["channel_list"].getCurrent()[1]
				stream_url = self.channelList[currentindex][6]
				extension = str(os.path.splitext(stream_url)[-1])

				title = self.channelList[currentindex][0]

				if "/series/" in stream_url:
					if os.path.exists("/tmp/xstreamity/level4.xml"):
						with open('/tmp/xstreamity/level4.xml') as f:
							content =  f.read()
							try:
								seriesstring = (content.split("<category_title>"))[1].split("</category_title>")[0]
								title = seriesstring + " " + title
							except:
								seriesstring = ''

				fileTitle = re.sub(r'[\<\>\:\"\/\\\|\?\*\[\]]', '_', title)
				fileTitle = re.sub(r' ', '_', fileTitle)
				fileTitle = re.sub(r'_+', '_', fileTitle)

				try:
					downloadPage(stream_url, str(cfg.downloadlocation.getValue()) + str(fileTitle) + str(extension))
					self.session.open(MessageBox, _('Downloading \n\n' + str(stream_url) + "\n\n" +  str(cfg.downloadlocation.getValue()) + str(fileTitle) + str(extension) ), MessageBox.TYPE_INFO)
				except Exception as err:
					print "download vod %s" % err
					pass
				except:
					self.session.open(MessageBox, _('Download Failed\n\n' + str(stream_url) + "\n\n" +  str(cfg.downloadlocation.getValue()) + str(fileTitle) + str(extension) ), MessageBox.TYPE_WARNING)
					pass
		else:
			return


	def showHiddenList(self):
		if self["key_menu"] != '':
			import hidden
			if self["channel_list"].getCurrent():
				playlist_url = self["channel_list"].getCurrent()[5]
				if "get_live_streams" in playlist_url:
					self.session.openWithCallback(self.createSetup, hidden.XStreamity_HiddenCategories, "live", self.channelListAll)
				if "get_vod_streams" in playlist_url:
					self.session.openWithCallback(self.createSetup, hidden.XStreamity_HiddenCategories, "vod", self.channelListAll)
				if "get_series" in playlist_url:
					self.session.openWithCallback(self.createSetup, hidden.XStreamity_HiddenCategories, "series", self.channelListAll)

		
	def getTMDB(self):
		if os.path.exists("/tmp/xstreamity/search.txt"):
			os.remove("/tmp/xstreamity/search.txt")
			
		if self["channel_list"].getCurrent():
			
			title = self["channel_list"].getCurrent()[0]
			stream_url = self["channel_list"].getCurrent()[6]

			currentindex = self["channel_list"].getIndex()
			
			currentvod = self.voditemlist[currentindex][1]

			
			if stream_url != 'None' and "/movie/" in stream_url:
				
				isIMDB = False
				
				if 'TMDB_ID' in currentvod: 
					if currentvod["TMDB_ID"][:1].isdigit():
			
						#print "******* TMDB_ID ********* %s " % currentvod["TMDB_ID"]
						self.getTMDBDetails(currentvod["TMDB_ID"])
						return
						
					else:
						#print "****** isIMDB ******"
						isIMDB = True

				searchtitle = title.lower()
				searchtitle = searchtitle.replace('  ', ' ') 
				searchtitle = searchtitle.replace('_', '%20') 
				
				searchtitle = searchtitle.strip()
				#if title ends in 'the', move 'the' to the beginning
				if searchtitle.endswith("the"):
					searchtitle.rsplit(' ',1)[0]
					searchtitle =  searchtitle.rsplit(' ',1)[0]
					searchtitle = "the " + str(searchtitle)
					
				searchtitle = searchtitle.replace(' ', '%20') 
				
				bad_chars = ["sd", "hd", "fhd", "uhd", "4k", "vod", "1080p", "720p", "blueray", "x264", "aac", "ozlem", "hindi", "hdrip",
				"uk:", "de:", "nl:", "cg:", "al:", "ae:", "at:", "ee:", "lt:", "be:", "bg:", "cz:", "sk:", "dk:", "hr:", "rs:",  "ba:", "fi:", "fr:", "de:", "gr:", "hu:", "ir:", "it:", "br:", "mx:", "mk:", "nl:", "no:", 
				"pl:", "pt:", "ro:", "ru:", "es:", "se:", "ch:", "tr:", "us:",
				"(", ")", "[", "]", "u-", "3d", "-", "'"]
				for j in range (1900, 2025):
					bad_chars.append(str(j))
				
				for i in bad_chars : 
					searchtitle = searchtitle.replace(i, '') 

				if isIMDB == False:
					searchurl = 'http://api.themoviedb.org/3/search/movie?api_key=' + str(self.check(self.token)) + '&query=%22' + str(searchtitle) + '%22'
				else:
					searchurl = 'http://api.themoviedb.org/3/find/' + str(currentvod["TMDB_ID"]) + '?api_key=' + str(self.check(self.token)) + '&external_source=imdb_id'

				try:
					downloadPage(searchurl, "/tmp/xstreamity/search.txt", timeout=3).addCallback(self.processTMDB, isIMDB)
				except Exception as err:
					print "download TMDB %s" % err
					pass
				except:
					pass

			
	def processTMDB(self, result, IMDB):
		#print "******* IMDB ******** %s" % IMDB	
		with open('/tmp/xstreamity/search.txt', "r") as f:
			response = f.read()

		if response != '':
			
				try:
					self.searchresult = json.loads(response)
					
					if IMDB == False:
					
						if 'results' in self.searchresult:
							if 'id' in self.searchresult['results'][0]:
								resultid = self.searchresult['results'][0]['id']
								self.getTMDBDetails(resultid)
							else:
								return
					else:
						#print "**** movie_results ******"
						if 'movie_results' in self.searchresult:
							if 'id' in self.searchresult['movie_results'][0]:
								resultid = self.searchresult['movie_results'][0]['id']
								self.getTMDBDetails(resultid)
							else:
								return
				except:
					pass
			
				
			
	def getTMDBDetails(self, resultid):
		if os.path.exists("/tmp/xstreamity/movie.txt"):
			os.remove("/tmp/xstreamity/movie.txt")
		language = "en"
		
	
		if cfg.refreshTMDB.value == True:
			language = cfg.TMDBLanguage.value
				

		detailsurl = "http://api.themoviedb.org/3/movie/" + str(resultid) + "?api_key=" + str(self.check(self.token)) + "&append_to_response=credits&language=" + str(language)
		
		try:
			downloadPage(detailsurl, "/tmp/xstreamity/movie.txt", timeout=3).addCallback(self.processTMDBDetails)
		except Exception as err:
			print "download TMDB details %s" % err
			pass
		except:
			pass


		
	def processTMDBDetails(self, result):
		valid = False
		response = ''
		
		posterpath = ''
		self.detailsresult = []
		name = ''
		oname = ''
		description = ''
		duration = ''
		rating = ''
		genre = []
		country = []
		releasedate = ''
		director = []
		cast = []
		
		with open('/tmp/xstreamity/movie.txt', "r") as f:
			response = f.read()

		if response != '':
			valid = False
			try:
				self.detailsresult = json.loads(response, object_pairs_hook=OrderedDict)
				valid = True
				
			except:
				pass
				

			if valid:
				if "poster_path" in self.detailsresult:
					if self.detailsresult["poster_path"] != None:
						posterpath = "http://image.tmdb.org/t/p/w300" + str(self.detailsresult["poster_path"])
					
				if "title" in self.detailsresult:
					name = str(self.detailsresult["title"])

				if "original_title" in self.detailsresult:
					oname = str(self.detailsresult["original_title"])
				
				if "overview" in self.detailsresult:
					description = str(self.detailsresult["overview"])
				
				if "runtime" in self.detailsresult:
					if self.detailsresult["runtime"] != 0 or self.detailsresult["runtime"] != None: 
						duration = str(timedelta(minutes=self.detailsresult["runtime"]))
						
				if "vote_average" in self.detailsresult:
					if self.detailsresult["vote_average"] != 0: 
						rating = str(self.detailsresult["vote_average"])
				
				if "genres" in self.detailsresult:
					for genreitem in self.detailsresult["genres"]:

						genre.append(str(genreitem["name"])) 
			
				if "production_countries" in self.detailsresult:
					for pcountry in self.detailsresult["production_countries"]:
						country.append(str(pcountry["name"]))
					
				if "release_date" in self.detailsresult:
					releasedate =  str(self.detailsresult["release_date"])
				
				if "credits" in  self.detailsresult:
					if "cast" in  self.detailsresult["credits"]:
						for actor in self.detailsresult["credits"]["cast"]:
							if "character" in actor:
								cast.append(str(actor["name"])) 

				if "credits" in  self.detailsresult:
					if "crew" in  self.detailsresult["credits"]:
						for actor in self.detailsresult["credits"]["crew"]:
							if "job" in actor:
								director.append(str(actor["name"])) 

				genre = " / ".join(map(str, genre))
				cast = ", ".join(map(str,cast))
				director = ", ".join(map(str,director))
				country = ", ".join(map(str,country))
				
				if self["channel_list"].getCurrent():
					currentindex = self["channel_list"].getIndex()
					
					currentvod = self.voditemlist[currentindex][1]
					
					if len(self.voditemlist) > 0:
						
						if name != '':	
							currentvod["NAME"] = name
						if oname != '':
							currentvod["O_NAME"] = oname
							
						if description != '':
							currentvod["DESCRIPTION"] = description
							currentvod["PLOT"] = description
						
						if duration != '' and duration != 0:	
							currentvod["DURATION"] = duration
						
						
						if genre != [] or genre != '':
							currentvod["GENRE"] = genre

						if rating != '' and rating != 0:
							currentvod["RATING"] = rating

						if country !=  [] or country != '':
							currentvod["COUNTRY"] = country
					
						if releasedate != '':
							currentvod["RELEASEDATE"] = releasedate
					
						
						if director != [] or director != '':
							currentvod["DIRECTOR"] = director

						if cast != [] or director != '':
							currentvod["CAST"] = cast
						
						if posterpath != '':
							currentvod["COVER_BIG"] = posterpath

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

		
								
				
def buildChannelListEntry(index, title, description, desc_image, category_id, playlisturl, stream_url):
	png = None
	if stream_url == 'None':
		png = LoadPixmap(common_path + "more.png")
	else:
		png = LoadPixmap(common_path + "play.png")
	return (title, index, description, desc_image, category_id, playlisturl, stream_url, png)

		
def buildEPGListEntry(index, title, epgnowtime, epgnowtitle, epgnowdescription, epgnexttime, epgnexttitle, epgnextdescription):
	return (title, index, epgnowtime, epgnowtitle, epgnowdescription, epgnexttime, epgnexttitle, epgnextdescription )
	
	
def buildShortEPGListEntry(date_all, time_all, title, description, index):
	return (title, date_all, time_all, description, index)
								

def checkGZIP(url):
	response = ''
	request = urllib2.Request(url, headers=hdr)
	try:
		timeout = cfg.timeout.getValue()
		response= urllib2.urlopen(request, timeout=timeout)

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
