#!/usr/bin/python
# -*- coding: utf-8 -*-

# for localized messages     
from . import _
from collections import OrderedDict
from Screens.Screen import Screen
from plugin import skin_path, imagefolder, screenwidth, hdr, cfg, skinimagefolder, common_path, json_file
from enigma import eListboxPythonMultiContent, gFont, RT_HALIGN_LEFT, RT_VALIGN_CENTER, eTimer, eServiceReference, iPlayableService
from Components.ActionMap import ActionMap
from Components.Sources.List import List
from Components.MultiContent import MultiContentEntryText, MultiContentEntryPixmapAlphaBlend
from Tools.LoadPixmap import LoadPixmap
from xStaticText import StaticText

#download / parse
import base64
import re
import json
import os
import xstreamity_globals as glob


class XStreamity_HiddenCategories(Screen):

	def __init__(self, session, category_type, channellist):
		Screen.__init__(self, session)
		self.session = session
		
		
		print "********* channellist ****** %s" % channellist

		skin = skin_path + 'hidden.xml'
		self.category_type = category_type
		self.channellist = channellist
	
		with open(skin, 'r') as f:
			self.skin = f.read()
			
		self.setup_title = (_('Hidden Categories'))

		self.startList = []
		self.drawList = []
		self['hidden_list'] = List(self.drawList)
		self['hidden_list'].onSelectionChanged.append(self.getCurrentEntry)
			
		self.currentSelection = 0

		self["key_red"] = StaticText(_('Cancel'))
		self["key_green"] = StaticText(_('Save'))
		self['key_red'] = StaticText(_('Cancel'))
		self['key_yellow'] = StaticText(_('Invert'))
		self['key_blue'] = StaticText(_('Clear All'))

		self.protocol = glob.current_playlist['playlist_info']['protocol']
		self.domain = glob.current_playlist['playlist_info']['domain']
		self.host = glob.current_playlist['playlist_info']['host']

		self['setupActions'] = ActionMap(['ColorActions', 'SetupActions', 'ChannelSelectEPGActions'], {
			 'red': self.keyCancel,
			 'green': self.keyGreen,
			 'yellow': self.toggleAllSelection,
			 'blue': self.clearAllSelection,
			 'save': self.keyGreen,
			 'cancel': self.keyCancel,
			 'ok': self.toggleSelection,
			 }, -2)

		self.onFirstExecBegin.append(self.loadHidden)
		self.onLayoutFinish.append(self.__layoutFinished)

		
		
	def __layoutFinished(self):
		self.setTitle(self.setup_title)
		self.getCurrentEntry()
		
		
	def loadHidden(self):
		self.playlists_all = []
		self.hidelist = []
		domain = glob.current_playlist['playlist_info']['domain']
		username = glob.current_playlist['playlist_info']['username']
		password = glob.current_playlist['playlist_info']['password']
		
		if self.category_type == "live":
			self.hidelist = glob.current_playlist['player_info']['livehidden']
			
		elif self.category_type == "vod":
			self.hidelist = glob.current_playlist['player_info']['vodhidden']
				
		elif self.category_type == "series":
			self.hidelist = glob.current_playlist['player_info']['serieshidden']
			
		for item in self.channellist:
			if item[6] not in self.hidelist:
				self.startList.append([item[0], item[6], False])
			if item[6] in self.hidelist:
				self.startList.append([item[0], item[6], True])	
		self.refresh()


	def buildListEntry(self, name, category_id, enabled):
		if enabled:
			pixmap = LoadPixmap(cached=True, path=common_path + "lock_on.png")
		else:
			pixmap = LoadPixmap(cached=True, path=common_path + "lock_off.png")
		return(pixmap, str(name), str(category_id), enabled)
		
      
	def refresh(self):
		self.drawList = []
		self.drawList = [self.buildListEntry(x[0], x[1], x[2]) for x in self.startList]
		self['hidden_list'].updateList(self.drawList)
		
	def toggleSelection(self):
		if len(self['hidden_list'].list) > 0:
			idx = self['hidden_list'].getIndex()
			print "******** startlist 1******** %s" % self.startList
			self.startList[idx][2] = not self.startList[idx][2]
			print "******** startlist 2******** %s" % self.startList
			self.refresh()  
			
			
	def toggleAllSelection(self):
		for idx, item in enumerate(self['hidden_list'].list):
			self.startList[idx][2] = not self.startList[idx][2]
		self.refresh()  
		
		
	def clearAllSelection(self):
		for idx, item in enumerate(self['hidden_list'].list):
			self.startList[idx][2] = False
		self.refresh() 
	

	def getCurrentEntry(self):
		self.currentSelection = self['hidden_list'].getIndex()
		
		
	def keyCancel(self):
		self.close()
		
		
	def keyGreen(self):
		domain = glob.current_playlist['playlist_info']['domain']
		username = glob.current_playlist['playlist_info']['username']
		password = glob.current_playlist['playlist_info']['password']
		
		if self.category_type == "live":
			glob.current_playlist['player_info']['livehidden'] = []
			print "****************** %s" % glob.current_playlist['player_info']['livehidden']
			
			print "******** startlist ******** %s" % self.startList
			for item in self.startList:
				print item
				if item[2] == True:
					glob.current_playlist['player_info']['livehidden'].append(item[1])
					
			print "****************** %s" % glob.current_playlist['player_info']['livehidden']
			
		elif self.category_type == "vod":
			glob.current_playlist['player_info']['vodhidden'] = []
			for item in self.startList:
				if item[2] == True:
					glob.current_playlist['player_info']['vodhidden'].append(item[1])
				
		elif self.category_type == "series":
			self.hidelist = glob.current_playlist['player_info']['serieshidden']
			for item in self.startList:
				if item[2] == True:
					glob.current_playlist['player_info']['serieshidden'].append(item[1])
						
		self.playlists_all = []
		with open(json_file) as f:
			self.playlists_all = json.load(f, object_pairs_hook=OrderedDict)
		 
		x = 0
		for playlist in self.playlists_all:
			if playlist['playlist_info']['domain'] == str(domain).strip() and playlist['playlist_info']['username'] == str(username).strip() and playlist['playlist_info']['password'] == str(password).strip(): 
				self.playlists_all[x] = glob.current_playlist
				break
			x += 1
	
		with open(json_file, 'w') as f:
			json.dump(self.playlists_all, f)
	
		self.close()
