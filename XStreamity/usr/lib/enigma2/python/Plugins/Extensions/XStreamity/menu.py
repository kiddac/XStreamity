#!/usr/bin/python
# -*- coding: utf-8 -*-

# for localized messages
from . import _
from collections import OrderedDict
from Components.ActionMap import ActionMap
from Components.Sources.List import List
from xStaticText import StaticText
from Screens.Screen import Screen
from Screens.MessageBox import MessageBox
from plugin import skin_path, hdr, cfg, common_path
from Tools.LoadPixmap import LoadPixmap

#download / parse
import urllib2
import xml.etree.ElementTree as ET
import gzip
import xstreamity_globals as glob
import base64

from Tools.BoundFunction import boundFunction
import os
import json
from StringIO import StringIO


class XStreamity_Menu(Screen):

	def __init__(self, session):
		Screen.__init__(self, session)
		self.session = session

		skin = skin_path + 'menu.xml'
		with open(skin, 'r') as f:
			self.skin = f.read()

		self.startList = []
		self.list = []
		self.drawList = []
		self["list"] = List(self.drawList)

		self.setup_title = (_('Stream Selection'))

		self['key_red'] = StaticText(_('Back'))

		self.tempcategorytypepath = "/tmp/xstreamity/categories.xml"

		self['actions'] = ActionMap(['XStreamityActions'], {
		'red': self.quit,
		'cancel': self.quit,
		'ok' :  self.next,
		}, -2)

		ref = str(glob.current_playlist['playlist_info']['enigma2_api'])
		self.protocol = glob.current_playlist['playlist_info']['protocol']
		self.domain = glob.current_playlist['playlist_info']['domain']
		self.host = glob.current_playlist['playlist_info']['host']
		self.username = glob.current_playlist['playlist_info']['username']
		self.password = glob.current_playlist['playlist_info']['password']
		self.live_categories = "%s/enigma2.php?username=%s&password=%s&type=get_live_categories" % (self.host, self.username, self.password)
		self.live_streams = "%s/player_api.php?username=%s&password=%s&action=get_live_streams" % (self.host, self.username, self.password)

		if ref:
			if not ref.startswith(self.host):
				ref = str(ref.replace(self.protocol + self.domain ,self.host))

		self.onFirstExecBegin.append(boundFunction(self.downloadEnigma2API, ref))
		self.onLayoutFinish.append(self.__layoutFinished)


	def __layoutFinished(self):
		self.setTitle(self.setup_title)


	def quit(self):
		if os.path.exists(self.tempcategorytypepath):
			os.remove(self.tempcategorytypepath)
		self.close()


	def next(self):
		import categories
		import catchup

		if self["list"].getCurrent():

			self.currentList = {"title": self["list"].getCurrent()[1], "playlist_url": self["list"].getCurrent()[3], "index": self["list"].getCurrent()[0]}

			if self["list"].getCurrent()[2] == "3":
				self.session.open(catchup.XStreamity_Catchup, self.startList, self.currentList )
			else:
				self.session.open(categories.XStreamity_Categories, self.startList, self.currentList )


	def downloadEnigma2API(self, url):
		self.list = []
		response = ''
		valid = False

		if not os.path.exists(self.tempcategorytypepath):
			try:
				response = checkGZIP(url)
				if response != '':
					valid = True

					try:
						content = response.read()
					except:
						content = response

					with open(self.tempcategorytypepath, 'w') as f:
						f.write(content)

			except Exception as e:
				print(e)
				pass

			except:
				pass
		else:
			valid = True
			with open(self.tempcategorytypepath, "r") as f:
				content = f.read()


		if valid == True and content != '':
			root = ET.fromstring(content)
			self.list = []
			index = 0

			for channel in root.findall('channel'):
				title64 = channel.findtext('title')
				category_id = str(channel.findtext('category_id'))
				playlist_url = channel.findtext('playlist_url')

				#check if correct port in url
				if playlist_url:
					if not playlist_url.startswith(self.host):
						playlist_url = str(playlist_url.replace(self.protocol + self.domain ,self.host))

				title = base64.b64decode(title64).decode('utf-8')

				if cfg.showlive.value == True and category_id == "0":
					self.startList.append({"title": str(title),"playlist_url": str(playlist_url)})
					self.list.append([index, str(title), str(category_id), str(playlist_url)])

				if cfg.showvod.value == True and category_id == "1":
					self.startList.append({"title": str(title),"playlist_url": str(playlist_url)})
					self.list.append([index, str(title), str(category_id), str(playlist_url)])

				if cfg.showseries.value == True and category_id == "2":
					self.startList.append({"title": str(title),"playlist_url": str(playlist_url)})
					self.list.append([index, str(title), str(category_id), str(playlist_url)])

				index += 1

			if cfg.showcatchup.value == True:
				hascatchup = self.checkCatchup()
				if hascatchup:
					self.list.append([index, "Catch Up TV", "3", self.live_categories])

			self.drawList = []
			self.drawList = [buildListEntry(x[0],x[1],x[2],x[3]) for x in self.list]
			self["list"].setList(self.drawList)

			if len(self.list) == 1:
				self.next()
				self.close()

		else:
			self.session.openWithCallback(self.close ,MessageBox, _('No data, blocked or playlist not compatible with XStreamity plugin.'), MessageBox.TYPE_WARNING, timeout=5)


	def checkCatchup(self):
		url = self.live_streams
		valid = False
		response = ''
		self.catchup_all = []

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
				self.catchup_all =  json.load(response, object_pairs_hook=OrderedDict)
			except:
				try:
					self.catchup_all =  json.loads(response, object_pairs_hook=OrderedDict)
				except:
					pass

			for item in self.catchup_all:
				if "tv_archive" and "tv_archive_duration" in item :
					if int(item["tv_archive"]) == 1 and int(item["tv_archive_duration"]) > 0:
						return True
						break
		return False



def buildListEntry(index, title, category_id, playlisturl):
	png = None

	if category_id == "0": png = LoadPixmap(common_path + "live.png")
	if category_id == "1": png = LoadPixmap(common_path + "vod.png")
	if category_id == "2": png = LoadPixmap(common_path + "series.png")
	if category_id == "3": png = LoadPixmap(common_path + "catchup.png")

	return (index, str(title), str(category_id), str(playlisturl), png)


def checkGZIP(url):
	response = ''
	request = urllib2.Request(url, headers=hdr)

	try:
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
