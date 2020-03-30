#!/usr/bin/python
# -*- coding: utf-8 -*-

# for localized messages     
from . import _

from collections import OrderedDict

from Components.ActionMap import ActionMap
from Components.Sources.List import List
#from Components.MultiContent import MultiContentEntryText, MultiContentEntryPixmapAlphaBlend
from xStaticText import StaticText

from enigma import eTimer, eServiceReference
from Screens.Screen import Screen
from plugin import skin_path, imagefolder, json_file, screenwidth, hdr, playlist_path, cfg, skinimagefolder, common_path

from Components.Pixmap import Pixmap
from Tools.LoadPixmap import LoadPixmap
from Screens.MessageBox import MessageBox

import os
import urllib2
import json

import xstreamity_globals as glob
import server, serverinfo, menu, settings
from datetime import datetime

from ServiceReference import ServiceReference

from twisted.web.client import downloadPage, getPage, http
import gzip
from StringIO import StringIO


#from Components.ServiceList import ServiceList


class XStreamity_Main(Screen):

	def __init__(self, session):
		Screen.__init__(self, session)
		self.session = session
		
		skin = skin_path + 'playlists.xml'
		with open(skin, 'r') as f:
			self.skin = f.read()
			
		self.list = []
		self['menu'] = List(self.list)
			
		self.setup_title = (_('Select Server'))
		
		self['key_red'] = StaticText(_('Back'))
		
		self['key_green'] = StaticText(_('Add'))
		
		self['key_yellow'] = StaticText()
		self['key_blue'] = StaticText()
		self['key_info'] = StaticText()
		self['key_menu'] = StaticText(_('Settings'))
		
		self.list = []
		self.drawList = []
		self["playlists"] = List(self.drawList)
		
		self["splash"] = Pixmap()
		self["scroll_up"] = Pixmap()
		self["scroll_down"] = Pixmap()

		
		self["splash"].show()
		self["scroll_up"].hide()
		self["scroll_down"].hide()
		
		self.tempplaylistpath = "/tmp/playlists.json"

		self['actions'] = ActionMap(['XStreamityActions'], {
		'red': self.quit,
		'green': self.addServer,
		'yellow': self.editServer,
		'blue': self.deleteServer,
		'cancel': self.quit,
		'info': self.openUserInfo,
		'ok' :  self.getStreamTypes,
		'menu' : self.settings
		
		}, -2)
		
		# check if playlists.txt file exists in specified location
		
	
		if not os.path.isfile(playlist_path):
			open(playlist_path, 'a').close()
			
		if os.path.isfile(playlist_path) and os.stat(playlist_path).st_size > 0:
			self.stripPlaylistUserFile()
			self.checkPlaylistUserFile()
	
			
		# check if playlists.json file exists in specified location
		self.playlists_all = []
		if not os.path.isfile(json_file):
			open(json_file, 'a').close()
		
		with open(json_file) as f:
			try:
				self.playlists_all = json.load(f, object_pairs_hook=OrderedDict)
			except:
				os.remove(json_file) 

		if os.path.isfile(playlist_path) and os.stat(playlist_path).st_size > 0:
			self.getPlaylistUserFile()
			self.removeOldPlaylists()
		
		if self.session.nav.getCurrentlyPlayingServiceReference():
			glob.currentPlayingServiceRef = self.session.nav.getCurrentlyPlayingServiceReference()
			glob.currentPlayingServiceRefString = self.session.nav.getCurrentlyPlayingServiceReference().toString()
			glob.currentServiceName = ServiceReference(glob.currentPlayingServiceRef).getServiceName()
			glob.newPlayingServiceRef = self.session.nav.getCurrentlyPlayingServiceReference()
			glob.newPlayingServiceRefString = glob.newPlayingServiceRef.toString()
		
		self.timer = eTimer()
		try: ## DreamOS fix
			self.timer_conn = self.timer.timeout.connect(self.downloadUserInfo)
		except:
			try:
				self.timer.callback.append(self.downloadUserInfo)
			except:
				self.downloadUserInfo()
		self.timer.start(200, True)

		self.onLayoutFinish.append(self.__layoutFinished)
		
		
	def __layoutFinished(self):
		self.setTitle(self.setup_title)
		
			
	def stripPlaylistUserFile(self):
		with open(playlist_path, 'r+') as f:
			lines = f.readlines()
			f.seek(0)
			f.writelines((line.strip(' ') for line in lines if line.strip()))
			f.truncate()
			
			
	def checkPlaylistUserFile(self):
		with open(playlist_path, 'r+') as f:
			lines = f.readlines()
			f.seek(0)
			for line in lines:
				if not line.startswith('http://') and not line.startswith('https://') and not line.startswith('#'):
					line = '# ' + line
				if "mpegts" in line:
					line = line.replace("mpegts", "ts")
				f.write(line)
			f.truncate()

	
	def getPlaylistUserFile(self):
		with open(playlist_path) as f:
			lines = f.readlines()
			f.seek(0)
			self.index = 0

			for line in lines:
				line = line.strip()
				self.protocol = 'http://'
				self.domain = ''
				self.port = 80
				self.username = ''
				self.password = ''
				self.type = 'm3u_plus'
				self.output = 'ts'
				self.host = ''
				self.player_api = ''
				self.enigma2_api = ''
				self.livetype = cfg.livetype.value
				self.vodtype = cfg.vodtype.value
				self.epgshift = 0
		
				urlsplit1 = line.split("/")
				urlsplit2 = line.split("?")
				
				self.protocol = urlsplit1[0] + "//"
			
				if not (self.protocol == "http://" or self.protocol == "https://"):
					continue
				
				if len(urlsplit1) > 2:
					self.domain = urlsplit1[2].split(':')[0]
					if len(urlsplit1[2].split(':')) > 1:
						self.port = urlsplit1[2].split(':')[1]
				
				self.host =  "%s%s:%s" % (self.protocol, self.domain, self.port)
				
				if len(urlsplit2) > 1:
					for param in urlsplit2[1].split("&"):
						if param.startswith("username"):
							self.username = param.split('=')[1]
						if param.startswith("password"):
							self.password = param.split('=')[1]
						if param.startswith("type"):
							self.type = param.split('=')[1]
						if param.startswith("output"):
							self.output = param.split('=')[1].strip()
							if self.output != "ts" or self.output != "m3u8":
								self.output = "ts"
					
				self.player_api = "%s/player_api.php?username=%s&password=%s" % (self.host, self.username, self.password)
				self.panel_api = "%s/panel_api.php?username=%s&password=%s" % (self.host, self.username, self.password)
				self.enigma2_api = "%s/enigma2.php?username=%s&password=%s" % (self.host, self.username, self.password)
				self.full_url = "%s/get.php?username=%s&password=%s&type=%s&output=%s" % (self.host, self.username, self.password, self.type, self.output)
			
				self.addPlaylistToJsonFile()
				self.index += 1
		

	def addPlaylistToJsonFile(self):
		playlist_exists = False
		if self.playlists_all != []:
			for playlists in self.playlists_all:
				
				#extra check in case playlists.txt details have been amended 
				if "domain" in playlists["playlist_info"] and "username" in playlists["playlist_info"] and "password" in playlists["playlist_info"]:
					if playlists["playlist_info"]["domain"] == self.domain and playlists["playlist_info"]["username"] == self.username and playlists["playlist_info"]["password"] == self.password:
						playlist_exists = True
						playlists["playlist_info"]["type"] = self.type
						playlists["playlist_info"]["output"] = self.output
						playlists["playlist_info"]["full_url"] = self.full_url	
							
		if playlist_exists == False:
			self.playlists_all.append({"playlist_info": OrderedDict([
				("index", self.index),
				("name", self.domain),
				("protocol",self.protocol),
				("domain", self.domain),
				("port", self.port),
				("username", self.username),
				("password", self.password),
				("type", self.type),
				("output", self.output),
				("host", self.host),
				("player_api", self.player_api),
				("panel_api", self.panel_api),
				("enigma2_api", self.enigma2_api),
				("full_url", self.full_url),
				]),
				"player_info": OrderedDict([
				("livetype", self.livetype),
				("vodtype", self.vodtype),
				("epgshift", self.epgshift),
				])
			})	
			

	def removeOldPlaylists(self):
		if self.playlists_all != []:
			
				deleteList = []
			
				with open(playlist_path) as f:
					lines = f.readlines()
			
				for playlist in self.playlists_all:
					exists = False
					for line in lines:
						if not line.startswith('#'):
							if str(playlist["playlist_info"]["domain"]) in line and 'username=' + str(playlist["playlist_info"]["username"]) in line and 'password=' + str(playlist["playlist_info"]["password"]) in line:
								exists = True
		
					if exists == False:
						deleteList.append(playlist)
						
				for playlist in deleteList:
					self.playlists_all.remove(playlist)
						
									
	def downloadUserInfo(self):
		index = 0 
		
		if not os.path.exists(self.tempplaylistpath):
			for playlists in self.playlists_all:
				response = ''
				
				valid = False
				panel = "new"
				player_api = str(playlists["playlist_info"]["player_api"])
				panel_api = str(playlists["playlist_info"]["panel_api"])
				full_url = str(playlists["playlist_info"]["full_url"])
				domain = str(playlists["playlist_info"]["domain"])
				username = str(playlists["playlist_info"]["username"])
				password = str(playlists["playlist_info"]["password"])
				
				player_req = urllib2.Request(player_api, headers=hdr)

				if 'get.php' in full_url and domain != '' and username != '' and password != '':
			
					try:
						response = checkGZIP(player_api)
						if response != '':
							valid = True
							panel = "new"
					except Exception as e:
						print(e)
						try:
							response = checkGZIP(panel_api)
							valid = True
							panel = "old"
						except Exception as e:
							print(e)

						except:
							pass

					except:
						pass
								
				if valid and response != '':
					try:
						self.playlists_all[index].update(json.load(response, object_pairs_hook=OrderedDict))
					except:
						try:
							self.playlists_all[index].update(json.loads(response, object_pairs_hook=OrderedDict))
						except:
							pass
						
				index += 1			
		else:
			with open(self.tempplaylistpath, "r") as f:
				response = f.read()
				self.playlists_all = json.loads(response)

		self["splash"].hide()
		self.buildPlaylistList()	
			
		
	def writeJsonFile(self):
		with open(json_file, 'w') as f:
			json.dump(self.playlists_all, f)
			
		with open(self.tempplaylistpath, 'w') as f:
			json.dump(self.playlists_all, f)
		self.createSetup()
		
	
	def buildPlaylistList(self):
		for playlists in self.playlists_all:
			if 'user_info' in playlists:
				if 'message' in playlists['user_info']:
					del playlists['user_info']['message']  
				
				if 'server_info' in playlists:		
					if 'https_port' in playlists['server_info']:
						del playlists['server_info']['https_port']  
						
					if 'rtmp_port' in playlists['server_info']:
						del playlists['server_info']['rtmp_port']  
						
			if 'available_channels' in playlists:
				del playlists['available_channels']
						
		self.writeJsonFile()
				

	def buildListEntry(self, index, name, url, expires, status, active, activenum, maxc, maxnum):
		if status == (_('Active')):
			pixmap = LoadPixmap(cached=True, path=common_path + 'led_green.png')
						
			if int(activenum) > int(maxnum) and int(maxnum) != 0:
				pixmap = LoadPixmap(cached=True, path=common_path + 'led_yellow.png')
		if status == (_('Banned')):
			pixmap = LoadPixmap(cached=True, path=common_path + 'led_red.png')
		if status == (_('Expired')):
			pixmap = LoadPixmap(cached=True, path=common_path + 'led_grey.png')
		if status == (_('Disabled')):
			pixmap = LoadPixmap(cached=True, path=common_path + 'led_grey.png')
		if status == (_('Server Not Responding')):
			pixmap = LoadPixmap(cached=True, path=common_path + 'led_red.png')
		if status == (_('Not Authorised')):
			pixmap = LoadPixmap(cached=True, path=common_path + 'led_red.png')

		return(index, str(name), str(url), str(expires), str(status), pixmap, str(active), str(activenum), str(maxc), str(maxnum))
			
						
	def createSetup(self):
		#self['playlists'].setIndex(0)
		self.list = []
		index = 0
		
		for playlist in self.playlists_all:
			playlisttext = ''
			validstate = 'Invalid'
			name = ''
			url = ''
			active = ''
			activenum = ''
			maxc = ''
			maxnum = ''
			status = (_('Server Not Responding'))  
			expires = ''
			
			if playlist != {}:
				if 'playlist_info' in playlist and 'name' in playlist['playlist_info']:
					name = playlist['playlist_info']['name']
				else:
					name = playlist['playlist_info']['domain']
					
				url = playlist['playlist_info']['host']
				
				if 'user_info' in playlist and 'auth' in playlist['user_info']:
		
						status = (_('Not Authorised')) 
						
						if playlist['user_info']['auth'] == 1:
							if 'status' in playlist['user_info']:
								if playlist['user_info']['status'] == 'Active':
									status = (_('Active')) 
								elif playlist['user_info']['status'] == 'Banned':
									status = (_('Banned'))
								elif playlist['user_info']['status'] == 'Disabled':
									status = (_('Disabled'))  
								elif playlist['user_info']['status'] == 'Expired':
									status = (_('Expired'))
							
								if status == (_('Active')):
									if 'exp_date' in playlist['user_info']:
										try:
											expires = str("Expires: ") + str(datetime.fromtimestamp(int(playlist['user_info']['exp_date'])).strftime('%d-%m-%Y'))
										except: 
											expires = str("Expires: Null")
									
									if 'active_cons' in playlist['user_info']:
										active = str("Active Conn:")
										activenum = playlist['user_info']['active_cons']
										
									if 'max_connections' in playlist['user_info']:
										maxc = str("Max Conn:")
										maxnum = playlist['user_info']['max_connections']


				self.list.append([index, name, url, expires, status, active, activenum, maxc, maxnum])
				index += 1
		
		if self.list != []:
			self.getCurrentEntry()
			self['playlists'].onSelectionChanged.append(self.getCurrentEntry)
			self['key_yellow'].setText(_('Edit'))
			self['key_blue'].setText(_('Delete'))
			self['key_info'].setText(_('Info'))

		self.drawList = []
		self.drawList = [self.buildListEntry(x[0],x[1],x[2],x[3],x[4],x[5],x[6],x[7],x[8]) for x in self.list]
		self["playlists"].setList(self.drawList)
		
		
		
	def playOriginalChannel(self):
		if glob.currentPlayingServiceRefString != glob.newPlayingServiceRefString:
			if glob.newPlayingServiceRefString != '':
				self.session.nav.playService(eServiceReference(glob.currentPlayingServiceRefString))	
			
		
		
	def quit(self):
		self.playOriginalChannel()
		if os.path.exists(self.tempplaylistpath):
			os.remove(self.tempplaylistpath)
		self.close()
		
		
	def addServer(self):
		glob.configchanged = False
		self.session.openWithCallback(self.refresh, server.XStreamity_AddServer, False)
		return
		
		
	def editServer(self):
		if self.list != []:
			glob.configchanged = False
			self.session.openWithCallback(self.refresh, server.XStreamity_AddServer, True)
		return
		
		
	def deleteServer(self, answer = None):
		if self.list != []:
			currentplaylist = glob.current_playlist.copy()

			if answer is None:
				self.session.openWithCallback(self.deleteServer, MessageBox, _('Delete selected playlist?'))
			elif answer:
				with open(playlist_path, 'r+') as f:
					lines = f.readlines()
					f.seek(0)
					for line in lines:
						if str(currentplaylist['playlist_info']['domain']) in line and "username=" + str(currentplaylist['playlist_info']['username']) in line:
							line = '#' + str(line)
						f.write(line)    
					f.truncate()
					f.close()
				self['playlists'].setIndex(0)
			self.refresh()
				
		
	def refresh(self):
		self["splash"].show()
		self.playlists_all = []
		if not os.path.isfile(json_file) or not os.stat(json_file).st_size > 0:
			open(json_file, 'a').close()
		
		with open(json_file) as f:
			try:
				self.playlists_all = json.load(f, object_pairs_hook=OrderedDict)
			except:
				os.remove(json_file) 

		self.getPlaylistUserFile()
		self.removeOldPlaylists()
		
		if glob.configchanged:
			self.timer = eTimer()
			self.timer.start(200, True)
			try: ## DreamOS fix
				self.timer_conn = self.timer.timeout.connect(self.downloadUserInfo)
			except:
				self.timer.callback.append(self.downloadUserInfo)
		else:
			self["splash"].hide()
			self.buildPlaylistList()	
			
		self.createSetup()
		
		
	def getCurrentEntry(self):
		if self.list != []:
			glob.current_selection = self['playlists'].getIndex()
			glob.current_playlist = self.playlists_all[glob.current_selection]
			
			if self['playlists'].count() > 5:
				self["scroll_up"].show()
				self["scroll_down"].show()
			
			if self['playlists'].getIndex() < 5:
				self["scroll_up"].hide()

				
			if self['playlists'].getIndex()+1 > ((self['playlists'].count() // 5) * 5):
				self["scroll_down"].hide()				
		else:
			glob.current_selection = 0
			glob.current_playlist = []
			

	def openUserInfo(self):
		if self.list != []:
			if 'user_info' in glob.current_playlist:
				if 'auth' in glob.current_playlist['user_info']: 
					if glob.current_playlist['user_info']['auth'] == 1:
						self.session.open(serverinfo.XStreamity_UserInfo)

			
	def getStreamTypes(self):
		if 'user_info' in glob.current_playlist:
			if 'auth' in glob.current_playlist['user_info']:
				if glob.current_playlist['user_info']['auth'] == 1 and glob.current_playlist['user_info']['status'] == "Active":
					self.session.open(menu.XStreamity_Menu)
						
	def getStreamsTypeTemp(self):
			self.session.open(menu.XStreamity_Menu) 
	

	def settings(self):
		changed = False
		self.session.openWithCallback(self.settingsChanged, settings.XStreamity_Settings)
	
	
	def settingsChanged(self, data = None):
		if glob.changed == True:
			self.close()
	
			
def checkGZIP(url):
	response = ''
	request = urllib2.Request(url, headers=hdr)

	try:
		response= urllib2.urlopen(request, timeout=10)
		
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
