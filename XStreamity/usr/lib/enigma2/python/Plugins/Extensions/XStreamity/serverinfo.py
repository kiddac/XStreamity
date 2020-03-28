#!/usr/bin/python
# -*- coding: utf-8 -*-

# for localized messages  	 
from . import _

from Screens.Screen import Screen
from Components.Label import Label
from Components.ActionMap import ActionMap
from xStaticText import StaticText
from datetime import datetime
from plugin import skin_path
import xstreamity_globals as glob
import json

class XStreamity_UserInfo(Screen):

	def __init__(self, session):
		Screen.__init__(self, session)
		self.session = session
		
		skin = skin_path + 'userinfo.xml'
		with open(skin, 'r') as f:
			self.skin = f.read()    
			
		self.setup_title = (_('User Information'))
		
		self['authorised'] = Label('')
		self['status'] = Label('')
		self['expiry'] = Label('')
		self['created'] = Label('')
		self['trial'] = Label('')
		self['activeconn'] = Label('')
		self['maxconn'] = Label('')
		self['formats'] = Label('')
		self['realurl'] = Label('')
		self['timezone'] = Label('')
		self['fullurl'] = Label('')

		self['actions'] = ActionMap(['XStreamityActions'], {
		 'ok': self.quit,
		 'cancel': self.quit,
		 'red' : self.quit,
		 'menu': self.quit}, -2)
	
		self['key_red'] = StaticText(_('Close'))

		self.createUserSetup()
		self.onLayoutFinish.append(self.__layoutFinished)
		
		
	def __layoutFinished(self):
		self.setTitle(self.setup_title)
		
		
	def createUserSetup(self):
		
		if 'auth' in glob.current_playlist['user_info']:
			self['authorised'].setText(str(glob.current_playlist['user_info']['auth']))
			
		if 'status' in glob.current_playlist['user_info']:
			self['status'].setText(str(glob.current_playlist['user_info']['status']))
			
		if 'exp_date' in glob.current_playlist['user_info']:
			try:
				self['expiry'].setText(str(datetime.fromtimestamp(int(glob.current_playlist['user_info']['exp_date'])).strftime('%d-%m-%Y  %H:%M')))
			except: 
				self['expiry'].setText('Null')
				
		if 'created_at' in glob.current_playlist['user_info']:
			try:
				self['created'].setText(str(datetime.fromtimestamp(int(glob.current_playlist['user_info']['created_at'])).strftime('%d-%m-%Y  %H:%M')))
			except: 
				self['created'].setText('Null')
			
		if 'is_trial' in glob.current_playlist['user_info']:
			self['trial'].setText(str(glob.current_playlist['user_info']['is_trial']))
			
		if 'active_cons' in glob.current_playlist['user_info']:
			self['activeconn'].setText(str(glob.current_playlist['user_info']['active_cons']))
			
		if 'max_connections' in glob.current_playlist['user_info']:
			self['maxconn'].setText(str(glob.current_playlist['user_info']['max_connections']))
			
		if 'allowed_output_formats' in glob.current_playlist['user_info']:
			self['formats'].setText(str(json.dumps(glob.current_playlist['user_info']['allowed_output_formats'])).lstrip("[").rstrip("]"))
		
		if 'url' in glob.current_playlist['server_info']:
			self['realurl'].setText(str(glob.current_playlist['server_info']['url']))
			
		if 'timezone' in glob.current_playlist['server_info']:
			self['timezone'].setText(str(glob.current_playlist['server_info']['timezone']))
			
		if 'full_url' in glob.current_playlist['playlist_info']:
			self['fullurl'].setText(str(glob.current_playlist['playlist_info']['full_url']))
				

	def quit(self):
		self.close()
