#!/usr/bin/python
# -*- coding: utf-8 -*-

# for localized messages
from . import _

from .plugin import skin_path
from .xStaticText import StaticText

from Components.ActionMap import ActionMap
from Components.ConfigList import ConfigListScreen
from Components.config import getConfigListEntry, ConfigText, ConfigPassword, ConfigNumber
from Components.Pixmap import Pixmap
from Screens.MessageBox import MessageBox
from Screens.Screen import Screen

import datetime
import time
import os


class RecordDateInput(ConfigListScreen, Screen):

	def __init__(self, session, config_name=None, config_date=None, config_starttime=None, config_endtime=None, config_instant=False):
		Screen.__init__(self, session)
		self.session = session

		skin = skin_path + 'settings.xml'

		if os.path.exists('/var/lib/dpkg/status'):
			skin = skin_path + 'DreamOS/settings.xml'

		with open(skin, 'r') as f:
			self.skin = f.read()

		self.list = []
		ConfigListScreen.__init__(self, self.list, session=self.session)

		self['key_red'] = StaticText(_('Close'))
		self['key_green'] = StaticText(_('Save'))

		self['HelpWindow'] = Pixmap()
		self['VKeyIcon'] = Pixmap()
		self['HelpWindow'].hide()
		self['VKeyIcon'].hide()

		self.conf_name = config_name
		self.conf_date = config_date
		self.conf_starttime = config_starttime
		self.conf_endtime = config_endtime
		self.conf_instant = config_instant

		self.setup_title = (_('Please enter recording time'))

		if self.conf_instant:
			self.setup_title = (_('Please enter recording end time'))

		self['actions'] = ActionMap(['XStreamityActions'], {
				'cancel': self.cancel,
				'red': self.cancel,
				'green': self.keyGo,
			}, -2)

		self.onFirstExecBegin.append(self.initConfig)
		self.onLayoutFinish.append(self.__layoutFinished)


	def __layoutFinished(self):
		self.setTitle(self.setup_title)


	def cancel(self, answer=None):
		if answer is None:
			if self['config'].isChanged():
				self.session.openWithCallback(self.cancel, MessageBox, _('Really close without saving settings?'))
			else:
				self.close()
		elif answer:
			for x in self['config'].list:
				x[1].cancel()

			self.close()
		return


	def initConfig(self):
		self.timeinput_name = self.conf_name
		self.timeinput_date = self.conf_date
		self.timeinput_starttime = self.conf_starttime
		self.timeinput_endtime = self.conf_endtime
		self.createSetup()


	def createSetup(self):
		self.list = []

		self.list.append(getConfigListEntry(_('Name'), self.timeinput_name))
		if self.conf_instant is False:
			self.list.append(getConfigListEntry(_('Start Time'), self.timeinput_starttime))

		self.list.append(getConfigListEntry(_('End Time'), self.timeinput_endtime))

		self['config'].list = self.list
		self['config'].l.setList(self.list)
		self.handleInputHelpers()


	def handleInputHelpers(self):
		if self['config'].getCurrent() is not None:

			if 'VKeyIcon' in self:
				self['VirtualKB'].setEnabled(False)
				self['VKeyIcon'].hide()

			if isinstance(self['config'].getCurrent()[1], ConfigText) or isinstance(self['config'].getCurrent()[1], ConfigPassword):
				if 'VKeyIcon' in self:
					if isinstance(self['config'].getCurrent()[1], ConfigNumber):
						self['VirtualKB'].setEnabled(False)
						self['VKeyIcon'].hide()
					else:
						self['VirtualKB'].setEnabled(True)
						self['VKeyIcon'].show()

					if not isinstance(self['config'].getCurrent()[1], ConfigNumber):
						if isinstance(self['config'].getCurrent()[1].help_window, ConfigText) or isinstance(self['config'].getCurrent()[1].help_window, ConfigPassword):
							if self['config'].getCurrent()[1].help_window.instance is not None:
								helpwindowpos = self['HelpWindow'].getPosition()

								if helpwindowpos:
									helpwindowposx, helpwindowposy = helpwindowpos
									if helpwindowposx and helpwindowposy:
										from enigma import ePoint
										self['config'].getCurrent()[1].help_window.instance.move(ePoint(helpwindowposx, helpwindowposy))


	def getTimestamp(self, date, mytime):
		d = time.localtime(date)
		dt = datetime.datetime(d.tm_year, d.tm_mon, d.tm_mday, mytime[0], mytime[1])
		return int(time.mktime(dt.timetuple()))


	def keyGo(self):
		starttime = self.getTimestamp(self.timeinput_date, self.timeinput_starttime.value)
		if self.timeinput_endtime.value < self.timeinput_starttime.value:
			self.timeinput_date += 86400
		endtime = self.getTimestamp(self.timeinput_date, self.timeinput_endtime.value)
		self.close((True, starttime, endtime, self.timeinput_name.value))
