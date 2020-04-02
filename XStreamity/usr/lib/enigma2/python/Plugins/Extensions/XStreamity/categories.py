#!/usr/bin/python
# -*- coding: utf-8 -*-

# for localized messages     
from . import _

#import owibranding


from Screens.Screen import Screen
from Screens.VirtualKeyBoard import VirtualKeyBoard
from Screens.InfoBar import InfoBar, MoviePlayer
from plugin import skin_path, imagefolder, screenwidth, hdr, cfg, skinimagefolder, common_path
from enigma import eListboxPythonMultiContent, gFont, RT_HALIGN_LEFT, RT_VALIGN_CENTER, eTimer, eServiceReference, iPlayableService
from Components.ActionMap import ActionMap
from Components.Sources.List import List
from Components.MenuList import MenuList
from Components.Sources.Progress import Progress
from Components.Pixmap import Pixmap
from Components.MultiContent import MultiContentEntryText, MultiContentEntryPixmapAlphaBlend
from Components.ProgressBar import ProgressBar
from Components.Renderer.xRunningText import xRunningText 
from Tools.LoadPixmap import LoadPixmap
from Tools.BoundFunction import boundFunction
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
from twisted.web.client import downloadPage, getPage, http
import xstreamity_globals as glob
import streamplayer, imagedownload
import math

from Screens.ParentalControlSetup import ProtectedScreen
from Components.config import *

class XStreamity_Categories(Screen):

	def __init__(self, session, startList, currentList):
		Screen.__init__(self, session)
		self.session = session
		
		self.currentList =[] 
		self.currentList.append(currentList)
		
		self.searchString = ''
		
		skin = skin_path + 'categories.xml'
	
		with open(skin, 'r') as f:
			self.skin = f.read()
			
		self.setup_title = (_('Categories'))
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

		self.epglist = []
		self["epg_list"] = MenuList2(self.epglist)
		self["epg_list"].selectionEnabled(0)

		self["epg_picon"] = Pixmap()
		
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
		
		self.level = 1

		self["actions"] = ActionMap(["XStreamityActions"], {
			'red': self.back,
			'cancel': self.back,
			'ok' :  self.next,
			'green' : self.next,
			'yellow' : self.sort,
			'blue' : self.search,
			'epg' : self.nownext,
			'text' : self.nownext,
			"left": self.goLeft,
			"right": self.goRight,
			"up": self.goUp,
			"down": self.goDown,
			"channelUp": self.pageUp,
			"channelDown": self.pageDown,
			"rec": self.downloadVod,
			"0": self.reset,
			}, -2)
			
		glob.nextlist = []
		glob.nextlist.append({"playlist_url": self.currentList[-1]["playlist_url"], "index": 0, "level": self.level})
		self.onFirstExecBegin.append(self.createSetup)
		self.onLayoutFinish.append(self.__layoutFinished)
		
		
	def __layoutFinished(self):
		self.setTitle(self.setup_title)
		self.selectionChanged()
			
		
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

		self.downloadEnigma2Categories(ref)
	

	def downloadEnigma2Categories(self, url):
		self.list1 = []
		self.voditemlist = []
	
		response = ''
		index = 0
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
					

				if stream_url and "/live/" in stream_url:
					# check if channel has EPG data
					if description != '':
						lines = re.split("\n", description)
						newdescription = []
						
						#use string manipulation rather than regex for speed.
						for line in lines:
						  if line.startswith("[") or line.startswith("("):
							newdescription.append(line)
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

				self.list1.append([index, str(title), str(description),str(desc_image), str(category_id), str(playlist_url), str(stream_url), \
				str(epgnowtime), str(epgnowtitle), str(epgnowdescription), \
				str(epgnexttime), str(epgnexttitle), str(epgnextdescription)]
				)  
				
				self.voditemlist.append([str(title), vodItems])
				
				index += 1
	
			self.channelList = []
			self.channelList = [buildChannelListEntry(x[0], x[1], x[2], x[3], x[4], x[5], x[6]) for x in self.list1]
			self["channel_list"].setList(self.channelList)
			
			self.epglist = []
			self.epglist = [buildEPGListEntry(x[0], x[1], x[7], x[8], x[9], x[10], x[11], x[12]) for x in self.list1]
			self["epg_list"].setList(self.epglist)

			
			glob.sort_list1 = self.channelList[:]
			glob.sort_list2 = self.epglist[:]
			glob.sort_list4 = self.voditemlist[:]

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
		self.resetSearch()
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
				
			currentindex =  self["channel_list"].getCurrent()[3]

			glob.nextlist[-1]['index'] = currentindex  
			
			self.channelList = glob.sort_list1
			self.epglist = glob.sort_list2
			self.voditemlist = glob.sort_list4
	
			glob.currentchannelist = self.channelList
			glob.currentchannelistindex = currentindex
			glob.currentepglist = self.epglist
		
			playlist_url = self.channelList[currentindex][7]
			stream_url = self.channelList[currentindex][8]
			

			if not self.isStream:
				glob.nextlist.append({"playlist_url": playlist_url, "index": 0}) 
				self.level += 1
				self.createSetup()
			else:
				streamurl = ''
				streamtype = "4097"
			
				if stream_url != 'None' and "/live/" in stream_url:
					streamtype = glob.current_playlist["player_info"]["livetype"]
					self.reference = eServiceReference(int(streamtype), 0, stream_url)
					
					if self.session.nav.getCurrentlyPlayingServiceReference():
						if self.session.nav.getCurrentlyPlayingServiceReference().toString() != self.reference.toString() and cfg.livepreview.value == True:
							self.session.nav.playService(self.reference)
							if self.session.nav.getCurrentlyPlayingServiceReference():
								glob.newPlayingServiceRef = self.session.nav.getCurrentlyPlayingServiceReference()
								glob.newPlayingServiceRefString = glob.newPlayingServiceRef.toString()
			
						else:
							self.session.openWithCallback(self.createSetup,streamplayer.XStreamity_StreamPlayer, str(stream_url), str(streamtype))
					else:
						self.session.nav.playService(self.reference)
						if self.session.nav.getCurrentlyPlayingServiceReference():
							glob.newPlayingServiceRef = self.session.nav.getCurrentlyPlayingServiceReference()
							glob.newPlayingServiceRefString = glob.newPlayingServiceRef.toString()

				if stream_url != 'None' and ("/movie/" in stream_url or "/series/" in stream_url):
					streamtype = glob.current_playlist["player_info"]["vodtype"]
					self.reference = eServiceReference(int(streamtype), 0, stream_url)
					self.session.openWithCallback(self.createSetup,streamplayer.XStreamity_VodPlayer, str(stream_url), str(streamtype))


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
		

	def displayProgress(self):
		start = ''
		end = ''
		percent = 0
		
	
		if self["epg_list"].getCurrent():
			
			startnowtime = self["epg_list"].getCurrent()[6]
			startnexttime = self["epg_list"].getCurrent()[9]
		
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
		if self["channel_list"].getCurrent():
			
			channeltitle = self["channel_list"].getCurrent()[0]
			stream_url = self["channel_list"].getCurrent()[8]
			currentindex = self["channel_list"].getSelectionIndex()

			self.position = currentindex + 1
			self.positionall = len(self.channelList)
			
			self.page = int(math.ceil(float(self.position) / float(self.itemsperpage)))
			self.pageall = int(math.ceil(float(self.positionall) / float(self.itemsperpage)))
			
			self["page"].setText('Page: ' + str(self.page) + " of " + str(self.pageall))
			self["listposition"].setText(str(self.position) + "/" + str(self.positionall))

			self["channel"].setText(self.main_title + ": " + str(channeltitle))
			self["progress"].hide()
			
			self.timer3 = eTimer()
			self.timer3.stop()
			
			if stream_url != 'None' or '': 
				if "/live/" in stream_url:
					self["key_rec"].setText('')
					self.displayEPG()   
					self.displayProgress()
					
					# delay download to stop lag on channel scrolling
					self.timer3.start(500, True)
					try:
						self.timer3_conn = self.timer3.timeout.connect(self.delayedDownload)
					except:
						self.timer3.callback.append(self.delayedDownload)   
				elif "/movie/" or "/series/" in stream_url:
					self["key_rec"].setText(_("Download"))
					self.hideEPG()
			else:
				self.hideEPG()
			
					
					
				

			if stream_url != 'None' and "/movie/" in stream_url:
				self.displayVod()

				# delay download to stop lag on channel scrolling
				self.timer3.start(500, True)
				try:
					self.timer3_conn = self.timer3.timeout.connect(self.delayedDownload)
				except:
					self.timer3.callback.append(self.delayedDownload)
			else:
				self.hideVod()
				
	
	def nownext(self):
		if self["epg_list"].getCurrent():
			currentindex = self["channel_list"].getCurrent()[3]
			
			stream_url = self.channelList[currentindex][8]
			
			if stream_url != 'None':
				if "/live/" in stream_url:
					
					if self["key_epg"] != '':
				
						startnowtime = self["epg_list"].getCurrent()[6]
						titlenow = self["epg_list"].getCurrent()[7]
						descriptionnow = self["epg_list"].getCurrent()[8]
						
						startnexttime = self["epg_list"].getCurrent()[9]
						titlenext =  self["epg_list"].getCurrent()[10]
						descriptionnext = self["epg_list"].getCurrent()[11]
						 
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
			
				elif "/movie/" or "/series/" in stream_url:
					if self["key_rec"] != '':
						self.openIMDb()
		
				
	def openIMDb(self):
		from Screens.MessageBox import MessageBox
		try:
			from Plugins.Extensions.IMDb.plugin import IMDB, IMDBEPGSelection
			try:
				name = self["channel_list"].getCurrent()[0]
			except:
				name = ''

			self.session.open(IMDB, name, False)
		except ImportError:
			self.session.open(MessageBox, _('The IMDb plugin is not installed!\nPlease install it.'), type=MessageBox.TYPE_INFO, timeout=10)
					
				

	def displayEPG(self):
		if self["epg_list"].getCurrent():
			
			try:
				currentindex = self["channel_list"].getSelectionIndex()
			except:
				currentindex = self["channel_list"].getSelectedIndex()
				
			self["epg_list"].moveToIndex(currentindex)
			
			startnowtime = self["epg_list"].getCurrent()[6]
			titlenow = self["epg_list"].getCurrent()[7]
			descriptionnow = self["epg_list"].getCurrent()[8]
			startnexttime = self["epg_list"].getCurrent()[9]
			
			self["epg_picon"].show()
			self["epg_bg"].show()  
			    

			if titlenow:
				nowtitle = "%s - %s  %s" % (startnowtime, startnexttime, titlenow)
				
				self["key_epg"].setText(_("Next Info"))
				self["epg_list"].selectionEnabled(1)
			else: 
				nowtitle = ""
				self["key_epg"].setText('')
				self["epg_list"].selectionEnabled(0)
				
			self["epg_title"].setText(nowtitle)         
			self["epg_description"].setText(descriptionnow)

		
			
	def hideEPG(self):
		self["epg_picon"].hide()
		self["epg_bg"].hide()
		self["epg_title"].setText('')
		self["epg_description"].setText('')
		self["epg_list"].selectionEnabled(0)
	
		
		
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
		
			try:
				currentindex = self["channel_list"].getSelectionIndex()
			except:
				currentindex = self["channel_list"].getSelectedIndex()
	
			currentvod = self.voditemlist[currentindex][1]
			
			stream_url = self["channel_list"].getCurrent()[8]
			if len(self.voditemlist) > 0:
				if 'NAME' in currentvod:
					self["vod_title"].setText(currentvod["NAME"])
				elif 'O_NAME' in currentvod:
					self["vod_title"].setText(currentvod["O_NAME"])
				
				if 'DESCRIPTION' in currentvod:
					self["vod_description"].setText(currentvod["DESCRIPTION"])
				elif 'PLOT' in currentvod:
					self["vod_description"].setText(currentvod["PLOT"])
				
				try:
					if self["channel_list"].getCurrent():
						self["vod_video_type"].setText(stream_url.split('.')[-1])
				except:
					pass
				
				if 'DURATION' in currentvod:    
					self["vod_duration"].setText(currentvod["DURATION"])
					
				if 'GENRE' in currentvod:
					self["vod_genre"].setText(currentvod["GENRE"])
					
				if 'RATING' in currentvod:
					self["vod_rating"].setText(currentvod["RATING"])
					
				if 'COUNTRY' in currentvod:
					self["vod_country"].setText(currentvod["COUNTRY"])
					
				if 'RELEASEDATE' in currentvod:
					try:
						self["vod_release_date"].setText(datetime.strptime(currentvod["RELEASEDATE"], "%Y-%m-%d").strftime("%Y"))
					except:
						pass

				if 'DIRECTOR' in currentvod:
					self["vod_director"].setText(currentvod["DIRECTOR"])
					
				if 'CAST' in currentvod:
					self["vod_cast"].setText(currentvod["CAST"])
	
		
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
			stream_url = self["channel_list"].getCurrent()[8]
			
			if not self.filtered:
				current_sort = self["key_yellow"].getText()

				if current_sort == (_('Sort: A-Z')):
					
					self["key_yellow"].setText(_('Sort: Z-A'))
					sort_type = 0
					reverse_flag = False
		
					self.channelList.sort(key=lambda x: x[0], reverse=reverse_flag)
					self.epglist.sort(key=lambda x: x[0], reverse=reverse_flag)
					self.voditemlist.sort(key=lambda x: x[0], reverse=reverse_flag)
					
					if stream_url != 'None' and "/movie/" in stream_url:
						self.displayVod()
						
					self["epg_list"].setList(self.epglist)
					self["epg_list"].moveToIndex(0)
					self["channel_list"].setList(self.channelList)
					self["channel_list"].moveToIndex(0)

				if current_sort == (_('Sort: Z-A')):
					self["key_yellow"].setText(_('Sort: Original'))
					sort_type = 0
					reverse_flag = True
					
					self.channelList.sort(key=lambda x: x[0], reverse=reverse_flag)
					self.epglist.sort(key=lambda x: x[0], reverse=reverse_flag)
					self.voditemlist.sort(key=lambda x: x[0], reverse=reverse_flag)
					
					if self["channel_list"].getCurrent():
						if stream_url != 'None' and "/movie/" in stream_url:
							self.displayVod()
							
					self["epg_list"].setList(self.epglist)
					self["epg_list"].moveToIndex(0)
					self["channel_list"].setList(self.channelList)
					self["channel_list"].moveToIndex(0)
						
				if current_sort == (_('Sort: Original')):
					self.voditemlist = glob.sort_list4
					
					if self["channel_list"].getCurrent():
						if stream_url != 'None' and "/movie/" in stream_url:
							self.displayVod()
					
					self.epglist = glob.sort_list2
					self["epg_list"].setList(self.epglist)
					self["epg_list"].moveToIndex(0)
					
					self.channelList = glob.sort_list1 
					self["channel_list"].setList(self.channelList)
					self["channel_list"].moveToIndex(0)
					
					self["key_yellow"].setText(_('Sort: A-Z'))
	
			
	def search(self):
		text = ''
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
			glob.filter_list4 = self.voditemlist[:]
			
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
		self.voditemlist = glob.filter_list4

		self["epg_list"].setList(self.epglist)
		self.displayEPG()   
		self.displayProgress()
		
		self["channel_list"].setList(self.channelList)
		
		glob.filter_list1 = []
		glob.filter_list2 = []
		glob.filter_list3 = []
		
		self.filtered = False

		
	def delayedDownload(self):
		url = ''
		size = []
		if self["channel_list"].getCurrent():
			try:
				currentindex = self["channel_list"].getSelectionIndex()
			except:
				currentindex = self["channel_list"].getSelectedIndex()
			
			desc_image = self["channel_list"].getCurrent()[5]
			stream_url = self["channel_list"].getCurrent()[8]
			
			if stream_url != 'None' and "/live/" in stream_url and cfg.showpicons.value == True:
				
				imagetype = "picon"
				url = desc_image
				size = [147,88]
				if screenwidth.width() > 1280:
					size = [220,130]
					
			if stream_url != 'None' and "/movie/" in stream_url and cfg.showcovers.value == True:
				imagetype = "cover"
				
					
				if cfg.hirescovers.value: 
					if 'COVER_BIG' in self.voditemlist[currentindex][1]:
						url = self.voditemlist[currentindex][1]["COVER_BIG"]
					else:
						url = desc_image

				url = desc_image

				size = [267, 400]
				if screenwidth.width() > 1280:
					size = [400,600]
				
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
				if self["vod_cover"].instance:
					self["vod_cover"].instance.setPixmapFromFile(preview)
					
				if self["epg_picon"].instance:
					self["epg_picon"].instance.setPixmapFromFile(preview)   
			else:   
				self.loadDefaultImage() 
		
		return preview
	
		
	def loadDefaultImage(self):
		if self["vod_cover"].instance:
			self["vod_cover"].instance.setPixmapFromFile(common_path + "vod_cover.png")
	
		if self["epg_picon"].instance:
			self["epg_picon"].instance.setPixmapFromFile(common_path + "picon.png")
		
		
	#play original channel
	def stopStream(self):
		if glob.currentPlayingServiceRefString != glob.newPlayingServiceRefString:
			if glob.newPlayingServiceRefString != '':
				self.session.nav.playService(eServiceReference(glob.currentPlayingServiceRefString))	
	

	def downloadVod(self):
		if self['key_rec'] != '':
			from Screens.MessageBox import MessageBox
			
			if cfg.downloadlocation.getValue() == '/media/':
				self.session.open(MessageBox, _('VOD download folder not defined in main settings.'), MessageBox.TYPE_WARNING)
				return

				
			if self["channel_list"].getCurrent():
				currentindex =  self["channel_list"].getCurrent()[3]
				stream_url = self.channelList[currentindex][8]
				extension = str(os.path.splitext(stream_url)[-1])
				title = self.channelList[currentindex][0]
				
				fileTitle = re.sub(r'[\<\>\:\"\/\\\|\?\*]', '_', title)
				fileTitle = re.sub(r' ', '_', fileTitle)
				fileTitle = re.sub(r'_+', '_', fileTitle)

				try:
					downloadPage(stream_url, str(cfg.downloadlocation.getValue()) + str(fileTitle) + str(extension))
					self.session.open(MessageBox, _('Downloading \n\n' + str(stream_url) + "\n\n" +  str(cfg.downloadlocation.getValue()) + "\n\n" + str(fileTitle) + str(extension) ), MessageBox.TYPE_INFO)

				except:
					self.session.open(MessageBox, _('Download Failed\n\n' + str(stream_url) + "\n\n" +  str(cfg.downloadlocation.getValue()) + "\n\n" + str(fileTitle) + str(extension) ), MessageBox.TYPE_WARNING)
					pass
		else:
			return
			

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
			
			
					
		
class MenuList2(MenuList):
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
				
				
def buildEPGListEntry(title, index, epgnowtime, epgnowtitle, epgnowdescription, epgnexttime, epgnexttitle, epgnextdescription):
	
	if screenwidth.width() > 1280:
		return [title,
			MultiContentEntryText(pos = (15, 0), size = (90, 60), font=0, flags = RT_HALIGN_LEFT|RT_VALIGN_CENTER, text = epgnowtime),
			MultiContentEntryText(pos = (105, 0), size = (525, 60), font=0, flags = RT_HALIGN_LEFT|RT_VALIGN_CENTER, text = epgnowtitle),
			MultiContentEntryText(pos = (705, 0), size = (90, 60), font=0, flags = RT_HALIGN_LEFT|RT_VALIGN_CENTER, text = epgnexttime),
			MultiContentEntryText(pos = (795, 0), size = (525, 60), font=0, flags = RT_HALIGN_LEFT|RT_VALIGN_CENTER, text = epgnexttitle),
			index, epgnowtime, epgnowtitle, epgnowdescription, epgnexttime, epgnexttitle, epgnextdescription
			]
	else:
		return [title,  
			MultiContentEntryText(pos = (8, 0), size = (60, 40), font=0, flags = RT_HALIGN_LEFT|RT_VALIGN_CENTER, text = epgnowtime),
			MultiContentEntryText(pos = (70, 0), size = (350, 40), font=0, flags = RT_HALIGN_LEFT|RT_VALIGN_CENTER, text = epgnowtitle),
			MultiContentEntryText(pos = (470, 0), size = (60, 40), font=0, flags = RT_HALIGN_LEFT|RT_VALIGN_CENTER, text = epgnexttime),
			MultiContentEntryText(pos = (532, 0), size = (350, 40), font=0, flags = RT_HALIGN_LEFT|RT_VALIGN_CENTER, text = epgnexttitle),
			index, epgnowtime, epgnowtitle, epgnowdescription, epgnexttime, epgnexttitle, epgnextdescription
			]
			
	
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

	

		
