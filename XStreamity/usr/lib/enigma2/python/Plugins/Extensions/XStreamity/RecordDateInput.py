#!/usr/bin/python
# -*- coding: utf-8 -*-

# for localized messages
from . import _

import owibranding
from Screens.Screen import Screen
from Components.config import config, ConfigClock, ConfigDateTime, getConfigListEntry
from Components.ActionMap import  ActionMap
from Components.ConfigList import ConfigListScreen
from xStaticText import StaticText
import time
import datetime
from plugin import skin_path

class RecordDateInput(Screen, ConfigListScreen):
	def __init__(self, session, config_starttime=None, config_endtime=None, config_date=None,  ):
		Screen.__init__(self, session)
		
		skin = skin_path + 'settings.xml'
		try:
			from boxbranding import getImageDistro, getImageVersion, getOEVersion
		except:
			
			if owibranding.getMachineBrand() == "Dream Multimedia" or owibranding.getOEVersion() == "OE 2.2":
				skin = skin_path + 'DreamOS/settings.xml'
	
		with open(skin, 'r') as f:
			self.skin = f.read()
		
		self['key_red'] = StaticText(_('Close'))
		self['key_green'] = StaticText(_('Save'))

		self.createConfig(config_date, config_starttime, config_endtime)

		self['actions'] = ActionMap(['XStreamityActions'],
		 {
		 'cancel': self.keyCancel,
		 'red': self.keyCancel,
		 'green': self.keyGo,

		 }, -2)

		self.list = []
		ConfigListScreen.__init__(self, self.list)
		self.createSetup(self["config"])

	def createConfig(self, conf_date, conf_starttime, conf_endtime):
		self.save_mask = 0
		if conf_starttime:
			self.save_mask |= 1
		else:
			conf_starttime = ConfigClock(default = time.time()),
		
		if conf_endtime:
			self.save_mask |= 2
		else:
			conf_endtime = ConfigClock(default = time.time()),
			
		if conf_date:
			self.save_mask |= 3
		else:
			conf_date = ConfigDateTime(default=time.time(), formatstring=config.usage.date.full.value, increment=86400)
		
		self.timeinput_date = conf_date
		self.timeinput_starttime = conf_starttime
		self.timeinput_endtime = conf_endtime

	def createSetup(self, configlist):
		self.list = [
			getConfigListEntry(_("Date"), self.timeinput_date),
			getConfigListEntry(_("Start Time"), self.timeinput_starttime),
			getConfigListEntry(_("End Time"), self.timeinput_endtime)
		]
		configlist.list = self.list
		configlist.l.setList(self.list)

	
	def keySelect(self):
		self.keyGo()


	def getTimestamp(self, date, mytime):
		d = time.localtime(date)
		dt = datetime.datetime(d.tm_year, d.tm_mon, d.tm_mday, mytime[0], mytime[1])
		return int(time.mktime(dt.timetuple()))


	def keyGo(self):
		starttime = self.getTimestamp(self.timeinput_date.value, self.timeinput_starttime.value )
		endtime = self.getTimestamp(self.timeinput_date.value, self.timeinput_endtime.value )

		if self.save_mask & 1:
			self.timeinput_starttime.save()
			
		if self.save_mask & 2:
			self.timeinput_endtime.save()
			
		if self.save_mask & 3:
			self.timeinput_date.save()
			
		
		self.close((True, starttime, endtime))

	def keyCancel(self):
		self.close((False,))
