#!/usr/bin/python
# -*- coding: utf-8 -*-

# for localized messages
from . import _

from Components.ActionMap import ActionMap
from Components.Sources.List import List
from Components.Pixmap import Pixmap
from Components.config import config
from datetime import datetime
from enigma import eTimer, eServiceReference
from plugin import skin_path, screenwidth, hdr, cfg, common_path, dir_tmp
from requests.adapters import HTTPAdapter
try:
	from requests.packages.urllib3.util.retry import Retry
except:
	from urllib3.util import Retry
from Screens.Screen import Screen
from Tools.LoadPixmap import LoadPixmap
from twisted.web.client import downloadPage
from xStaticText import StaticText
from Screens.MessageBox import MessageBox

import base64
import json
import os
import re
import requests
import streamplayer
import imagedownload
import time
import xstreamity_globals as glob


class XStreamity_Catchup(Screen):

	def __init__(self, session):
		Screen.__init__(self, session)
		self.session = session

		skin = skin_path + 'catchup.xml'

		with open(skin, 'r') as f:
			self.skin = f.read()

		self.setup_title = (_('Catch Up TV'))
		self.main_title = (_('Catch Up TV'))

		url = str(glob.current_playlist['playlist_info']['player_api']) + "&action=get_live_categories"

		self.level = 1
		self.category = 0

		glob.nextlist = []
		glob.nextlist.append({"playlist_url": url, "index": 0, "level": self.level})

		self["channel"] = StaticText(self.main_title)

		self.list = []
		self.channelList = []
		self["channel_list"] = List(self.channelList, enableWrapAround=True)
		self.selectedlist = self["channel_list"]

		# epg variables
		self["epg_bg"] = Pixmap()
		self["epg_bg"].hide()

		self["epg_title"] = StaticText()
		self["epg_description"] = StaticText()

		self.epgshortlist = []
		self["epg_short_list"] = List(self.epgshortlist, enableWrapAround=True)
		self["epg_short_list"].onSelectionChanged.append(self.displayShortEPG)

		self["epg_picon"] = Pixmap()
		self["epg_picon"].hide()

		self["key_red"] = StaticText(_('Back'))
		self["key_green"] = StaticText(_('OK'))
		self["key_rec"] = StaticText('')

		self.isStream = False
		self.pin = False

		self.protocol = glob.current_playlist['playlist_info']['protocol']
		self.domain = glob.current_playlist['playlist_info']['domain']
		self.host = glob.current_playlist['playlist_info']['host']
		self.livetype = glob.current_playlist['player_info']['livetype']
		self.username = glob.current_playlist['playlist_info']['username']
		self.password = glob.current_playlist['playlist_info']['password']
		self.output = glob.current_playlist['playlist_info']['output']

		self.live_categories = str(glob.current_playlist['playlist_info']['player_api']) + "&action=get_live_categories"
		self.live_streams = str(glob.current_playlist['playlist_info']['player_api']) + "&action=get_live_streams"
		self.simpledatatable = str(glob.current_playlist['playlist_info']['player_api']) + "&action=get_simple_data_table&stream_id="

		self["page"] = StaticText('')
		self["listposition"] = StaticText('')
		self.page = 0
		self.pageall = 0
		self.position = 0
		self.positionall = 0
		self.itemsperpage = 10

		self.showingshortEPG = False

		self.listType = ''

		self["actions"] = ActionMap(["XStreamityActions"], {
			'red': self.back,
			'cancel': self.back,
			'ok':  self.__next__,
			'green': self.__next__,
			"left": self.pageUp,
			"right": self.pageDown,
			"up": self.goUp,
			"down": self.goDown,
			"channelUp": self.pageUp,
			"channelDown": self.pageDown,
			"0": self.reset,
			"rec": self.downloadVideo,
			}, -2)

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
		self["epg_title"].setText('')
		self["epg_description"].setText('')

		self.downloadLiveStreams()

		if self.level == 1:
			url = glob.nextlist[-1]['playlist_url']
			if self.category == 0:
				response = glob.current_playlist['data']['live_categories']

			self.processData(response, url)
		else:
			self.downloadData()


	def downloadData(self):
		url = glob.nextlist[-1]["playlist_url"]
		levelpath = dir_tmp + 'level' + str(self.level) + '.xml'

		if not os.path.exists(levelpath):
			# retries = Retry(total=3, status_forcelist=[408, 429, 500, 503, 504], method_whitelist=["HEAD", "GET", "OPTIONS"], backoff_factor = 1)

			adapter = HTTPAdapter(max_retries=0)
			http = requests.Session()
			http.mount("http://", adapter)

			try:
				r = http.get(url, headers=hdr, stream=True, timeout=10, verify=False)
				r.raise_for_status()
				if r.status_code == requests.codes.ok:

					content = r.json()
					with open(levelpath, 'w') as f:
						f.write(json.dumps(content))

					self.processData(content, url)

			except requests.exceptions.ConnectionError as e:
				print("Error Connecting: %s" % e)


			except requests.exceptions.RequestException as e:
				print(e)
		else:
			with open(levelpath, "r") as f:
				content = f.read()
				self.processData(json.loads(content), url)


	def processData(self, response, url):
		self.channelList = []
		currentCategory = ''
		index = 0

		# ~~~~~~~~~~~~~~~ level 1 ~~~~~~~~~~~~~~~ #
		if "&action=get_live_categories" in url:
			self.isStream = False
			self.listType = "category"
			currentCategory = glob.current_playlist['data']['live_categories']

			nextAction = "&action=get_live_streams&category_id="

		# ~~~~~~~~~~~~~~~ level 2 ~~~~~~~~~~~~~~~ #
		elif "&action=get_live_streams" in url:
			currentCategory = response
			nextAction = ''
			self.isStream = True
			self.listType = "live_streams"

		self.list = []

		if self.listType == "category":
			for item in currentCategory:

				for archive in self.live_list_archive:
					if item['category_id'] == archive['category_id']:

						category_name = item['category_name']
						category_id = item['category_id']
						next_url = "%s%s%s" % (glob.current_playlist['playlist_info']['player_api'], nextAction, category_id)
						self.list.append([index, str(category_name), str(next_url), str(category_id)])
						index += 1
						break
			self.buildLists()

		elif self.listType == "live_streams":
			for item in currentCategory:
				if item['tv_archive'] == 1 and item['tv_archive_duration'] != "0":

					name = item['name']
					stream_id = item['stream_id']
					stream_icon = item['stream_icon']
					epg_channel_id = item['epg_channel_id']
					added = item['added']

					epgnowtitle = epgnowtime = epgnowdescription = epgnexttitle = epgnexttime = epgnextdescription = ''

					next_url = "%s/live/%s/%s/%s.%s" % (self.host, self.username, self.password, stream_id, self.output)

					self.list.append([
						index, str(name), str(stream_id), str(stream_icon), str(epg_channel_id), str(added), str(next_url),
						epgnowtime, epgnowtitle, epgnowdescription, epgnexttime, epgnexttitle, epgnextdescription
					])

					index += 1

			self.buildLists()


		if self["channel_list"].getCurrent():
			if glob.nextlist[-1]['index'] != 0:
				self["channel_list"].setIndex(glob.nextlist[-1]['index'])

			if not self.isStream:
				self.hideEPG()
				pass


	def buildLists(self):
		if self.listType == "category":
			self.channelList = []
			self.channelList = [buildCategoryList(x[0], x[1], x[2], x[3]) for x in self.list]
			self["channel_list"].setList(self.channelList)
			self.selectionChanged()

		elif self.listType == "live_streams":
			self.channelList = []
			self.channelList = [buildLiveStreamList(x[0], x[1], x[2], x[3], x[4], x[5], x[6]) for x in self.list]
			self["channel_list"].setList(self.channelList)
			self.selectionChanged()


	def downloadLiveStreams(self):
		url = self.live_streams

		self.streams = ''
		self.live_list_all = []
		self.live_list_archive = []

		# retries = Retry(total=2, status_forcelist=[408, 429, 500, 503, 504], method_whitelist=["HEAD", "GET", "OPTIONS"], backoff_factor = 1)
		adapter = HTTPAdapter(max_retries=0)
		http = requests.Session()
		http.mount("http://", adapter)

		try:
			r = http.get(url, headers=hdr, stream=True, timeout=10, verify=False)
			r.raise_for_status()
			if r.status_code == requests.codes.ok:
				self.streams = r.json()

		except requests.exceptions.ConnectionError as e:
			print("Error Connecting: %s" % e)

		except requests.exceptions.RequestException as e:
			print(e)

		if self.streams != '':
			for item in self.streams:
				if "tv_archive" and "tv_archive_duration" in item:
					if int(item["tv_archive"]) == 1 and int(item["tv_archive_duration"]) > 0:
						self.live_list_archive.append(item)
		else:
			self.close()


	def back(self):
		self["epg_title"].setText('')
		self["epg_description"].setText('')
		self["epg_picon"].hide()
		self["key_rec"].setText('')

		if self.selectedlist == self["epg_short_list"]:

			instance = self["epg_short_list"].master.master.instance
			instance.setSelectionEnable(0)
			self.catchup_all = []
			self['epg_short_list'].setList(self.catchup_all)

			instance = self["channel_list"].master.master.instance
			instance.setSelectionEnable(1)
			self.selectedlist = self["channel_list"]
		else:

			del glob.nextlist[-1]

			if len(glob.nextlist) == 0:
				self.close()
			else:

				self.stopStream()

				levelpath = str(dir_tmp) + 'level' + str(self.level) + '.xml'
				try:
					os.remove(levelpath)
				except:
					pass
				self.level -= 1
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

		if self["channel_list"].getCurrent():
			self.currentindex = self["channel_list"].getCurrent()[2]
			next_url = self["channel_list"].getCurrent()[3]

			glob.nextlist[-1]['index'] = self.currentindex
			glob.currentchannelist = self.channelList
			glob.currentchannelistindex = self.currentindex


			if self.level == 1:
				glob.nextlist.append({"playlist_url": next_url, "index": 0})
				self["epg_picon"].hide()
				self.level += 1
				self["channel_list"].setIndex(0)
				self.createSetup()
			else:

				self["epg_picon"].show()
				if self.selectedlist == self["channel_list"]:
					self.shortEPG()
				else:
					self.playCatchup()


	def shortEPG(self):
		if self["channel_list"].getCurrent():
			next_url = self["channel_list"].getCurrent()[3]

			if next_url != 'None':
				if "/live/" in next_url:

					stream_id = next_url.rpartition("/")[-1].partition(".")[0]
					response = ''
					shortEPGJson = []

					url = str(self.simpledatatable) + str(stream_id)
					# retries = Retry(total=2, status_forcelist=[408, 429, 500, 503, 504], method_whitelist=["HEAD", "GET", "OPTIONS"], backoff_factor = 1)

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
							if shortEPGJson["epg_listings"]:
								for listing in shortEPGJson["epg_listings"]:
									if 'has_archive' in listing:
										if listing['has_archive'] == 1:

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

											if 'start' in listing:
												epgstart = listing['start']


												if 'end' in listing:
													epgend = listing['end']

													epgstarttimestamp = int(time.mktime(time.strptime(epgstart, "%Y-%m-%d %H:%M:%S")))
													epgendtimestamp = int(time.mktime(time.strptime(epgend, "%Y-%m-%d %H:%M:%S")))

													# add epg timeshift
													epgstarttimestamp += shift * 60 * 60
													epgendtimestamp += shift * 60 * 60

													epg_day = datetime.fromtimestamp(epgstarttimestamp).strftime("%a")
													epg_start_date = datetime.fromtimestamp(epgstarttimestamp).strftime("%d/%m")
													epg_date_all = "%s %s" % (epg_day, epg_start_date)
													epg_time_all = "%s - %s" % (datetime.fromtimestamp(epgstarttimestamp).strftime("%Y-%m-%d %H:%M:%S")[11:16],
																				datetime.fromtimestamp(epgendtimestamp).strftime("%Y-%m-%d %H:%M:%S")[11:16])

													# add catchup buffer
													catchupstart = int(cfg.catchupstart.getValue())
													epgstarttimestamp -= catchupstart * 60
													catchupend = int(cfg.catchupend.getValue())
													epgendtimestamp += catchupend * 60

													epg_duration = int(epgendtimestamp - epgstarttimestamp) / 60

													epgstarttimestamp -= shift * 60 * 60
													epg_date = str((datetime.fromtimestamp(epgstarttimestamp).strftime("%Y-%m-%d %H:%M:%S")).replace(":", "-").replace(" ", ":"))[0:16]

											self.epgshortlist.append(buildShortEPGListEntry(str(epg_date_all), str(epg_time_all), str(epg_title), str(epg_description), str(epg_date), str(epg_duration), index))
											index += 1

								self.epgshortlist.reverse()
								self["epg_short_list"].setList(self.epgshortlist)

								if self["epg_short_list"].getCurrent():
									glob.catchupdata = [str(self["epg_short_list"].getCurrent()[0]), str(self["epg_short_list"].getCurrent()[3])]
								instance = self["epg_short_list"].master.master.instance
								instance.setSelectionEnable(1)

								self.selectedlist = self["epg_short_list"]
								self["key_rec"].setText(_("Download"))
								self.displayShortEPG()
							else:
								self.session.open(MessageBox, _("Catchup currently not available. Missing EPG data"), type=MessageBox.TYPE_INFO, timeout=5)

		return


	def displayShortEPG(self):

		if self["epg_short_list"].getCurrent():
			title = str(self["epg_short_list"].getCurrent()[0])
			description = str(self["epg_short_list"].getCurrent()[3])
			timeall = str(self["epg_short_list"].getCurrent()[2])
			self["epg_title"].setText(timeall + " " + title)
			self["epg_description"].setText(description)


	def playCatchup(self):
		next_url = self["channel_list"].getCurrent()[3]
		stream = next_url.rpartition('/')[-1]
		date = str(self["epg_short_list"].getCurrent()[4])
		duration = str(self["epg_short_list"].getCurrent()[5])

		playurl = "%s/timeshift/%s/%s/%s/%s/%s" % (self.host, self.username, self.password, duration, date,  stream)

		if next_url != 'None' and "/live/" in next_url:
			streamtype = str(glob.current_playlist["player_info"]["catchuptype"])
			self.reference = eServiceReference(int(streamtype), 0, str(playurl))
			glob.catchupdata = [str(self["epg_short_list"].getCurrent()[0]), str(self["epg_short_list"].getCurrent()[3])]
			self.session.openWithCallback(self.createSetup, streamplayer.XStreamity_CatchupPlayer, str(playurl), str(streamtype))
		else:
			from Screens.MessageBox import MessageBox
			self.session.open(MessageBox, _('Catchup error. No data for this slot'), MessageBox.TYPE_WARNING, timeout=5)


	def stopStream(self):
		if glob.currentPlayingServiceRefString != glob.newPlayingServiceRefString:
			if glob.newPlayingServiceRefString != '':
				if self.session.nav.getCurrentlyPlayingServiceReference():
					self.session.nav.stopService()
				self.session.nav.playService(eServiceReference(glob.currentPlayingServiceRefString))


	def selectionChanged(self):
		if self["channel_list"].getCurrent():
			channeltitle = self["channel_list"].getCurrent()[0]
			stream_url = self["channel_list"].getCurrent()[3]

			self["channel"].setText(self.main_title + ": " + str(channeltitle))

			if stream_url != 'None':
				if "/live/" in stream_url:

					self.timerpicon = eTimer()
					try:
						self.timerpicon.callback.append(self.downloadPicon)
					except:
						self.timerpicon_conn = self.timerpicon.timeout.connect(self.downloadPicon)
					self.timerpicon.start(200, True)


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

					imagetype = "picon"
					url = desc_image
					size = [147, 88]
					if screenwidth.width() > 1280:
						size = [220, 130]

					if url != '' and url != "n/A" and url is not None:
						original = dir_tmp + 'original.png'

						try:
							downloadPage(url, original, timeout=5).addCallback(self.checkdownloaded, size, imagetype).addErrback(self.ebPrintError)
						except:

							if url.startswith('https'):
								url = url.replace('https', 'http')
								try:
									downloadPage(url, original, timeout=5).addCallback(self.checkdownloaded, size, imagetype).addErrback(self.ebPrintError)
								except:
									pass
									self.loadDefaultImage()
							else:
								self.loadDefaultImage()
					else:
						self.loadDefaultImage()


	def ebPrintError(self, failure):
		self.loadDefaultImage()
		pass


	def loadDefaultImage(self):
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


	def displayImage(self):
		preview = dir_tmp + 'original.png'
		if self["epg_picon"].instance:
			self["epg_picon"].instance.setPixmapFromFile(preview)


	def showEPGElements(self):
		self["epg_picon"].show()
		self["epg_bg"].show()


	def hideEPG(self):
		self["epg_short_list"].setList([])
		self["epg_picon"].hide()
		self["epg_bg"].hide()
		self["epg_title"].setText('')
		self["epg_description"].setText('')


	# record button download video file
	def downloadVideo(self):
		if self["key_rec"].getText() != '':
			from Screens.MessageBox import MessageBox

			if self["channel_list"].getCurrent():

				next_url = self["channel_list"].getCurrent()[3]
				stream = next_url.rpartition('/')[-1]
				date = str(self["epg_short_list"].getCurrent()[4])
				duration = str(self["epg_short_list"].getCurrent()[5])
				playurl = "%s/timeshift/%s/%s/%s/%s/%s" % (self.host, self.username, self.password, duration, date,  stream)
				extension = str(os.path.splitext(next_url)[-1])

				date_all = str(self["epg_short_list"].getCurrent()[1]).strip()
				time_all = str(self["epg_short_list"].getCurrent()[2]).strip()
				time_start = time_all.partition(" - ")[0].strip()
				current_year = int(datetime.now().year)
				date = str(datetime.strptime(str(current_year) + str(date_all) + str(time_start), "%Y%a %d/%m%H:%M")).replace("-", "").replace(":", "")[:-2]


				otitle = str(self["epg_short_list"].getCurrent()[0])
				channel = str(self["channel_list"].getCurrent()[0])

				title = str(date) + " - " + str(channel) + " - " + str(otitle)

				fileTitle = re.sub(r'[\<\>\:\"\/\\\|\?\*\[\]]', '_', title)
				# fileTitle = re.sub(r' ', '_', fileTitle)
				fileTitle = re.sub(r'_+', '_', fileTitle)

				try:
					downloadPage(str(playurl), str(cfg.downloadlocation.getValue()) + str(fileTitle) + str(extension))
					self.session.open(MessageBox, _('Downloading \n\n' + otitle + "\n\n" + str(cfg.downloadlocation.getValue()) + str(fileTitle) + str(extension)), MessageBox.TYPE_INFO)
				except Exception as e:
					print("download catchup %s" % e)
					pass
				except:
					self.session.open(MessageBox, _('Download Failed\n\n' + otitle + "\n\n" + str(cfg.downloadlocation.getValue()) + str(fileTitle) + str(extension)), MessageBox.TYPE_WARNING)
					pass
		else:
			return


def buildCategoryList(index, title, next_url, category_id):
	png = LoadPixmap(common_path + "more.png")
	return (title, png, index, next_url, category_id)


def buildLiveStreamList(index, title, stream_id, stream_icon, epg_channel_id, added, next_url):
	png = LoadPixmap(common_path + "more.png")
	return (title, png, index, next_url, stream_id, stream_icon, epg_channel_id, added)


def buildShortEPGListEntry(date_all, time_all, title, description, start, duration, index):
	return (title, date_all, time_all, description, start, duration, index)
