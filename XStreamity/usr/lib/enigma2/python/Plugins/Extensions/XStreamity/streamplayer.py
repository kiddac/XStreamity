# for localized messages
from . import _


from Screens.Screen import Screen
from Screens.InfoBar import InfoBar, MoviePlayer
from Screens.InfoBarGenerics import *
from Components.ServiceEventTracker import ServiceEventTracker, InfoBarBase
from Components.config import config, configfile, ConfigBoolean, ConfigClock


#from Screens.PVRState import PVRState, TimeshiftState
from RecordTimer import RecordTimerEntry
from Screens.TimerEntry import TimerEntry as TimerEntry
from Tools import Notifications
from Tools.Directories import pathExists, fileExists
from Screens.MessageBox import MessageBox

try:
	from Plugins.Extensions.SubsSupport import SubsSupport, SubsSupportStatus
except ImportError:
	class SubsSupport(object):
		def __init__(self, *args, **kwargs):
			pass
	class SubsSupportStatus(object):
		def __init__(self, *args, **kwargs):
			pass

from Components.ActionMap import ActionMap
from Components.Sources.Progress import Progress
from Components.ProgressBar import ProgressBar

from Components.Renderer.xRunningText import xRunningText
from Components.Pixmap import Pixmap, MultiPixmap
from Tools.LoadPixmap import LoadPixmap
from Components.Label import Label


#from Components.Sources.List import List
from xStaticText import StaticText

from enigma import eTimer, eServiceReference, iPlayableService, iRecordableService, iServiceInformation
from plugin import skin_path, imagefolder, screenwidth, skinimagefolder, common_path, cfg

import os
import xstreamity_globals as glob
import imagedownload

from datetime import datetime, timedelta
from time import mktime, strptime
from itertools import cycle, islice
from twisted.web.client import downloadPage, getPage, http
from Tools.BoundFunction import boundFunction



class IPTVInfoBarShowHide():
	""" InfoBar show/hide control, accepts toggleShow and hide actions, might start
	fancy animations. """
	STATE_HIDDEN = 0
	STATE_HIDING = 1
	STATE_SHOWING = 2
	STATE_SHOWN = 3
	FLAG_CENTER_DVB_SUBS = 2048
	skipToggleShow = False

	def __init__(self):
		self["ShowHideActions"] = ActionMap(["InfobarShowHideActions"],
		{
		"toggleShow": self.OkPressed,
		"hide": self.hide,
		}, 1)


		self.__event_tracker = ServiceEventTracker(screen=self, eventmap=
		{
			iPlayableService.evStart: self.serviceStarted,
		})

		self.__state = self.STATE_SHOWN
		self.__locked = 0

		self.hideTimer = eTimer()
		try:
			self.hideTimer_conn = self.hideTimer.timeout.connect(self.doTimerHide)
		except:
			self.hideTimer.callback.append(self.doTimerHide)
		self.hideTimer.start(5000, True)

		self.onShow.append(self.__onShow)
		self.onHide.append(self.__onHide)

		#self.onLayoutFinish.append(self.__layoutFinished)


	def __layoutFinished(self):
		try:
			self.pvrStateDialog = None
			self.pvrStateDialog.hide()
		except:
			pass


	def OkPressed(self):
		self.toggleShow()


	def __onShow(self):
		self.__state = self.STATE_SHOWN
		self.startHideTimer()


	def __onHide(self):
		self.__state = self.STATE_HIDDEN


	def serviceStarted(self):
		if self.execing:
			if config.usage.show_infobar_on_zap.value:
				self.doShow()


	def startHideTimer(self):
		if self.__state == self.STATE_SHOWN and not self.__locked:
			self.hideTimer.stop()
			idx = config.usage.infobar_timeout.index
			if idx:
				self.hideTimer.start(idx * 1500, True)

		elif hasattr(self, "pvrStateDialog"):
			self.hideTimer.stop()
			self.skipToggleShow = False


	def doShow(self):
		self.hideTimer.stop()
		self.show()
		self.startHideTimer()


	def doTimerHide(self):
		self.hideTimer.stop()
		if self.__state == self.STATE_SHOWN:
			self.hide()


	def toggleShow(self):
		if self.skipToggleShow:
			self.skipToggleShow = False
			return

		if self.__state == self.STATE_HIDDEN:
			self.show()
			self.hideTimer.stop()
		else:
			self.hide()
			self.startHideTimer()


	def lockShow(self):
		try:
			self.__locked += 1
		except:
			self.__locked = 0
		if self.execing:
			self.show()
			self.hideTimer.stop()
			self.skipToggleShow = False


	def unlockShow(self):
		try:
			self.__locked -= 1
		except:
			self.__locked = 0
		if self.__locked  <0:
			self.__locked = 0
		if self.execing:
			self.startHideTimer()


class IPTVInfoBarPVRState:
	def __init__(self, screen=PVRState, force_show = True):
		self.onChangedEntry = [ ]
		self.onPlayStateChanged.append(self.__playStateChanged)
		self.pvrStateDialog = self.session.instantiateDialog(screen)
		self.onShow.append(self._mayShow)
		self.onHide.append(self.pvrStateDialog.hide)
		self.force_show = force_show


	def _mayShow(self):
		if self.has_key("state") and not self.force_show:
			self["state"].setText("")
			self["statusicon"].setPixmapNum(6)
			self["speed"].setText("")
		if self.shown and self.seekstate != self.SEEK_STATE_EOF and not self.force_show:
			self.pvrStateDialog.show()
			self.startHideTimer()

	def __playStateChanged(self, state):
		playstateString = state[3]
		state_summary = playstateString
		if self.pvrStateDialog.has_key("statusicon"):
			self.pvrStateDialog["state"].setText(playstateString)
			if playstateString == '>':
				self.pvrStateDialog["statusicon"].setPixmapNum(0)
				self.pvrStateDialog["speed"].setText("")
				speed_summary = self.pvrStateDialog["speed"].text
				statusicon_summary = 0
				if self.has_key("state") and self.force_show:
					self["state"].setText(playstateString)
					self["statusicon"].setPixmapNum(0)
					self["speed"].setText("")
			elif playstateString == '||':
				self.pvrStateDialog["statusicon"].setPixmapNum(1)
				self.pvrStateDialog["speed"].setText("")
				speed_summary = self.pvrStateDialog["speed"].text
				statusicon_summary = 1
				if self.has_key("state") and self.force_show:
					self["state"].setText(playstateString)
					self["statusicon"].setPixmapNum(1)
					self["speed"].setText("")
			elif playstateString == 'END':
				self.pvrStateDialog["statusicon"].setPixmapNum(2)
				self.pvrStateDialog["speed"].setText("")
				speed_summary = self.pvrStateDialog["speed"].text
				statusicon_summary = 2
				if self.has_key("state") and self.force_show:
					self["state"].setText(playstateString)
					self["statusicon"].setPixmapNum(2)
					self["speed"].setText("")
			elif playstateString.startswith('>>'):
				speed = state[3].split()
				self.pvrStateDialog["statusicon"].setPixmapNum(3)
				self.pvrStateDialog["speed"].setText(speed[1])
				speed_summary = self.pvrStateDialog["speed"].text
				statusicon_summary = 3
				if self.has_key("state") and self.force_show:
					self["state"].setText(playstateString)
					self["statusicon"].setPixmapNum(3)
					self["speed"].setText(speed[1])
			elif playstateString.startswith('<<'):
				speed = state[3].split()
				self.pvrStateDialog["statusicon"].setPixmapNum(4)
				self.pvrStateDialog["speed"].setText(speed[1])
				speed_summary = self.pvrStateDialog["speed"].text
				statusicon_summary = 4
				if self.has_key("state") and self.force_show:
					self["state"].setText(playstateString)
					self["statusicon"].setPixmapNum(4)
					self["speed"].setText(speed[1])
			elif playstateString.startswith('/'):
				self.pvrStateDialog["statusicon"].setPixmapNum(5)
				self.pvrStateDialog["speed"].setText(playstateString)
				speed_summary = self.pvrStateDialog["speed"].text
				statusicon_summary = 5
				if self.has_key("state") and self.force_show:
					self["state"].setText(playstateString)
					self["statusicon"].setPixmapNum(5)
					self["speed"].setText(playstateString)

			for cb in self.onChangedEntry:
				cb(state_summary, speed_summary, statusicon_summary)




class XStreamity_StreamPlayer(Screen, InfoBarBase, InfoBarMoviePlayerSummarySupport, InfoBarServiceNotifications, IPTVInfoBarShowHide, InfoBarSeek, InfoBarAudioSelection, InfoBarSubtitleSupport, IPTVInfoBarPVRState, InfoBarInstantRecord ):


	def __init__(self, session, streamurl, servicetype):
		Screen.__init__(self, session)

		self.session = session

		InfoBarBase.__init__(self)
		InfoBarMoviePlayerSummarySupport.__init__(self)		
		InfoBarServiceNotifications.__init__(self)	
		IPTVInfoBarShowHide.__init__(self)
		InfoBarSeek.__init__(self)
		InfoBarAudioSelection.__init__(self)
		InfoBarSubtitleSupport.__init__(self)
		IPTVInfoBarPVRState.__init__(self, PVRState, True)
		InfoBarInstantRecord.__init__(self)


		protocol = glob.current_playlist['playlist_info']['protocol']
		domain = glob.current_playlist['playlist_info']['domain']
		host = glob.current_playlist['playlist_info']['host']

		self.streamurl = streamurl
		self.servicetype = servicetype

		skin = skin_path + 'streamplayer.xml'

		self["epg_description"] = StaticText()
		self["nowchannel"] = StaticText()
		self["nowtitle"] = StaticText()
		self["nexttitle"] = StaticText()
		self["nowtime"] = StaticText()
		self["nexttime"] = StaticText()
		self["streamcat"] = StaticText()
		self["streamtype"] = StaticText()
		self["extension"] = StaticText()
		self["progress"] = ProgressBar()
		self["progress"].hide()
		self["epg_picon"] = Pixmap()

		self["eventname"] = Label()
		self["state"] = Label()
		self["speed"] = Label()
		self["statusicon"] = MultiPixmap()

		self["PTSSeekBack"] = Pixmap()
		self["PTSSeekPointer"] = Pixmap()

		with open(skin, 'r') as f:
			self.skin = f.read()

		self.setup_title = _('TV')

		self['actions'] = ActionMap(["XStreamityActions"], {
			'cancel': self.back,
			'tv': self.toggleStreamType,
			"channelUp": self.next,
			"channelDown": self.prev,
			"up": self.prev,
			"down": self.next,
			"stop": self.back,
			"rec": self.IPTVstartInstantRecording,

			}, -2)

		self.onLayoutFinish.append(self.__layoutFinished)


	def __layoutFinished(self):
		self.playStream(self.servicetype, self.streamurl)


	def IPTVstartInstantRecording(self, limitEvent = True):

		import RecordDateInput
		begin = int(time())
		end = begin + 3600

		self.starttime=ConfigClock(default = begin)
		self.endtime=ConfigClock(default = end)

		dlg = self.session.openWithCallback(self.RecordDateInputClosed, RecordDateInput.RecordDateInput, self.starttime, self.endtime)
		dlg.setTitle(_("Please enter recording time"))



	def RecordDateInputClosed(self, ret = None):
		if ret[0]:
			begin = ret[1]
			end = ret[2]
			info = { }

			name = glob.currentepglist[glob.currentchannelistindex][7]
			description = glob.currentepglist[glob.currentchannelistindex][8]
			eventid = glob.currentepglist[glob.currentchannelistindex][0]

			self.getProgramInfoAndEvent(info, name)
			serviceref = info["serviceref"]

			if isinstance(serviceref, eServiceReference):
				serviceref = ServiceReference(serviceref)

			recording = RecordTimerEntry(serviceref, begin, end, name, description, eventid, dirname = str(cfg.downloadlocation.getValue()))
			recording.dontSave = True

			simulTimerList = self.session.nav.RecordTimer.record(recording)

			if simulTimerList is None:	# no conflict
				recording.autoincrease = False
				self.recording.append(recording)

				self.session.open(MessageBox, _('Recording Started.'), MessageBox.TYPE_INFO, timeout=5)
			else:
				self.session.open(MessageBox, _('Recording Failed.'), MessageBox.TYPE_WARNING)
				return
		else:
			self.session.open(MessageBox, _('Recording Failed.'), MessageBox.TYPE_WARNING)
			return


	def playStream(self, servicetype, streamurl):
		self["epg_description"].setText(glob.currentepglist[glob.currentchannelistindex][8])
		self["nowchannel"].setText(glob.currentchannelist[glob.currentchannelistindex][0])
		self["nowtitle"].setText(glob.currentepglist[glob.currentchannelistindex][7])
		self["nexttitle"].setText(glob.currentepglist[glob.currentchannelistindex][10])
		self["nowtime"].setText(glob.currentepglist[glob.currentchannelistindex][6])
		self["nexttime"].setText(glob.currentepglist[glob.currentchannelistindex][9])
		self["streamcat"].setText("Live")
		self["streamtype"].setText(str(servicetype))

		try:
			self["extension"].setText(str(os.path.splitext(streamurl)[-1]))
		except:
			pass

		start = ''
		end = ''
		percent = 0

		if glob.currentepglist[glob.currentchannelistindex][6] != '':
			start = glob.currentepglist[glob.currentchannelistindex][6]

		if glob.currentepglist[glob.currentchannelistindex][9] != '':
			end = glob.currentepglist[glob.currentchannelistindex][9]

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


		self.downloadPicon()

		self.reference = eServiceReference(int(self.servicetype),0,self.streamurl)
		self.reference.setName(str(glob.currentchannelist[glob.currentchannelistindex][0]))

		self.session.nav.stopService()
		self.session.nav.playService(self.reference)

		self.__event_tracker = ServiceEventTracker(screen=self, eventmap={
		  iPlayableService.evStart: self.__evStart,
		  iPlayableService.evSeekableStatusChanged : self.__evSeekableStatusChanged,
		  iPlayableService.evEOF: self.__evEOF,
		  })


	def downloadPicon(self):

		size = []
		stream_url = ''
		desc_image = ''

		if glob.currentchannelist:
			stream_url = glob.currentchannelist[glob.currentchannelistindex][8]
			desc_image = glob.currentchannelist[glob.currentchannelistindex][5]

		if stream_url != 'None':
			imagetype = "picon"
			size = [147,88]
			if screenwidth.width() > 1280:
				size = [220,130]

		if size != []:
			if desc_image != '':
				temp = '/tmp/xstreamity/temp.png'
				preview = '/tmp/xstreamity/preview.png'
				try:
					downloadPage(desc_image, temp).addCallback(self.checkdownloaded, size, imagetype, temp)
				except:
					pass
			else:
				self.loadDefaultImage()


	def checkdownloaded(self, data, piconSize, imageType, temp):
		preview = ''
		if os.path.exists(temp):
			print "file exists"
			try:
				preview = imagedownload.updatePreview(piconSize, imageType, temp)
			except:
				pass

			if preview != '':
				if self["epg_picon"].instance:
					self["epg_picon"].instance.setPixmapFromFile(preview)
			else:
				self.loadDefaultImage()
		else:
			print "file does not exist"
		return preview


	def __evStart(self):
		print "********************* evStart *****************"


	def __evSeekableStatusChanged(self):
		print "********************* evSeekableStatusChanged *****************"


	def __evEOF(self):
		print "********************* evEOF *****************"


	def back(self):
		if self.session.nav.getCurrentlyPlayingServiceReference():
			glob.newPlayingServiceRef = self.session.nav.getCurrentlyPlayingServiceReference()
			glob.newPlayingServiceRefString = self.session.nav.getCurrentlyPlayingServiceReference().toString()
			glob.nextlist[-1]['index'] = glob.currentchannelistindex
		self.close()


	def toggleStreamType(self):
		currentindex = 0

		streamtypelist = ["1","4097"]
		
		if os.path.exists("/usr/bin/gstplayer"):
			streamtypelist.append("5001")
			
		if os.path.exists("/usr/bin/exteplayer3"):
			streamtypelist.append("5002")
			
		if os.path.exists("/usr/bin/apt-get"):
			streamtypelist.append("8193")
			

		for index, item in enumerate(streamtypelist, start=0):
			if str(item) == str(self.servicetype):
				currentindex = index
				break

		nextStreamType = islice(cycle(streamtypelist),currentindex+1,None)
		self.servicetype = int(next(nextStreamType))

		self.playStream(self.servicetype, self.streamurl)


	def next(self):
		if glob.currentchannelist:
			listlength = len(glob.currentchannelist)
			glob.currentchannelistindex += 1
			if glob.currentchannelistindex + 1 > listlength:
				glob.currentchannelistindex = 0
			self.streamurl = glob.currentchannelist[glob.currentchannelistindex][8]
			self.playStream(self.servicetype, self.streamurl)


	def prev(self):
		if glob.currentchannelist:
			listlength = len(glob.currentchannelist)
			glob.currentchannelistindex -= 1
			if glob.currentchannelistindex + 1 == 0:
				glob.currentchannelistindex = listlength - 1

			self.streamurl = glob.currentchannelist[glob.currentchannelistindex][8]
			self.playStream(self.servicetype, self.streamurl)


	def loadDefaultImage(self):
		if screenwidth.width() > 1280:
			if self["epg_picon"].instance:
				self["epg_picon"].instance.setPixmapFromFile(common_path + "picon.png")
		else:

			if self["epg_picon"].instance:
					self["epg_picon"].instance.setPixmapFromFile(common_path + "picon_sd.png")



class XStreamity_VodPlayer(Screen, InfoBarBase, InfoBarMoviePlayerSummarySupport, InfoBarServiceNotifications, InfoBarShowHide, InfoBarSeek, InfoBarAudioSelection, InfoBarSubtitleSupport, IPTVInfoBarPVRState, SubsSupportStatus, SubsSupport ):


	def __init__(self, session, streamurl, servicetype):
		Screen.__init__(self, session)

		self.session = session

		InfoBarBase.__init__(self)
		InfoBarMoviePlayerSummarySupport.__init__(self)		
		InfoBarServiceNotifications.__init__(self)
		InfoBarShowHide.__init__(self)
		InfoBarSeek.__init__(self)
		InfoBarAudioSelection.__init__(self)
		InfoBarSubtitleSupport.__init__(self)
		IPTVInfoBarPVRState.__init__(self, PVRState, True)
		SubsSupport.__init__(self, searchSupport=True, embeddedSupport=True)
		SubsSupportStatus.__init__(self)

		protocol = glob.current_playlist['playlist_info']['protocol']
		domain = glob.current_playlist['playlist_info']['domain']
		host = glob.current_playlist['playlist_info']['host']

		self.streamurl = streamurl
		self.servicetype = servicetype

		skin = skin_path + 'vodplayer.xml'

		self["streamcat"] = StaticText()
		self["streamtype"] = StaticText()
		self["extension"] = StaticText()
		self["cover"] = Pixmap()

		self["eventname"] = Label()
		self["state"] = Label()
		self["speed"] = Label()
		self["statusicon"] = MultiPixmap()

		with open(skin, 'r') as f:
			self.skin = f.read()

		self.setup_title = _('VOD')

		self['actions'] = ActionMap(["XStreamityActions"], {
			'cancel': self.back,
			'tv': self.toggleStreamType,
			"channelUp": self.next,
			"channelDown": self.prev,
			"up": self.prev,
			"down": self.next,
			"stop": self.back,

			}, -2)

		self.onLayoutFinish.append(self.__layoutFinished)


	def __layoutFinished(self):
		self.playStream(self.servicetype, self.streamurl)


	def playStream(self, servicetype, streamurl):

		self.reference = eServiceReference(int(self.servicetype),0,self.streamurl)
		self.reference.setName(glob.currentchannelist[glob.currentchannelistindex][0])

		if streamurl != 'None' and "/movie/" in streamurl:
			self["streamcat"].setText("VOD")
		else:
			self["streamcat"].setText("Series")
		self["streamtype"].setText(str(servicetype))

		try:
			self["extension"].setText(str(os.path.splitext(streamurl)[-1]))
		except:
			pass

		self.downloadPicon()

		self.session.nav.stopService()
		self.session.nav.playService(self.reference)



	def downloadPicon(self):
		size = []
		stream_url = ''
		desc_image = ''

		if glob.currentchannelist:
			stream_url = glob.currentchannelist[glob.currentchannelistindex][8]
			desc_image = glob.currentchannelist[glob.currentchannelistindex][5]

		if stream_url != 'None':
			imagetype = "cover"
			size = [147,220]
			if screenwidth.width() > 1280:
				size = [220,330]

		if size != []:

			if desc_image != '':
				temp = '/tmp/xstreamity/temp.png'
				preview = '/tmp/xstreamity/preview.png'

				try:
					downloadPage(desc_image, temp).addCallback(self.checkdownloaded, size, imagetype, temp)
				except:
					pass
			else:
				self.loadDefaultImage()


	def checkdownloaded(self, data, piconSize, imageType, temp):
		preview = ''
		if os.path.exists(temp):
			print "file exists"
			try:
				preview = imagedownload.updatePreview(piconSize, imageType, temp)
			except:
				pass

			if preview != '':
				if self["cover"].instance:
					self["cover"].instance.setPixmapFromFile(preview)
			else:
				self.loadDefaultImage()
		else:
			print "file does not exist"
		return preview


	def back(self):
		if self.session.nav.getCurrentlyPlayingServiceReference():
			glob.newPlayingServiceRef = self.session.nav.getCurrentlyPlayingServiceReference()
			glob.newPlayingServiceRefString = self.session.nav.getCurrentlyPlayingServiceReference().toString()
			glob.nextlist[-1]['index'] = glob.currentchannelistindex
		self.close()


	def toggleStreamType(self):
		currentindex = 0
		streamtypelist = ["1","4097"]
		
		if os.path.exists("/usr/bin/gstplayer"):
			streamtypelist.append("5001")
			
		if os.path.exists("/usr/bin/exteplayer3"):
			streamtypelist.append("5002")
			
		if os.path.exists("/usr/bin/apt-get"):
			streamtypelist.append("8193")

		for index, item in enumerate(streamtypelist, start=0):
			if str(item) == str(self.servicetype):
				currentindex = index
				break
		nextStreamType = islice(cycle(streamtypelist),currentindex+1,None)
		self.servicetype = int(next(nextStreamType))
		self.playStream(self.servicetype, self.streamurl)


	def next(self):

		if glob.currentchannelist:
			stream_url = glob.currentchannelist[glob.currentchannelistindex][8]
			listlength = len(glob.currentchannelist)
			glob.currentchannelistindex += 1
			if glob.currentchannelistindex + 1 > listlength:
				glob.currentchannelistindex = 0
			self.streamurl = stream_url
			self.playStream(self.servicetype, self.streamurl)


	def prev(self):
		if glob.currentchannelist:
			stream_url = glob.currentchannelist[glob.currentchannelistindex][8]
			listlength = len(glob.currentchannelist)
			glob.currentchannelistindex -= 1
			if glob.currentchannelistindex + 1 == 0:
				glob.currentchannelistindex = listlength - 1

			self.streamurl = stream_url
			self.playStream(self.servicetype, self.streamurl)


	def loadDefaultImage(self):
		if self["cover"].instance:
			self["cover"].instance.setPixmapFromFile(common_path + "cover.png")




class XStreamity_CatchupPlayer(Screen, InfoBarBase, InfoBarMoviePlayerSummarySupport, InfoBarServiceNotifications, InfoBarShowHide, InfoBarSeek, InfoBarAudioSelection, InfoBarSubtitleSupport, IPTVInfoBarPVRState, SubsSupportStatus, SubsSupport ):

	def __init__(self, session, streamurl, servicetype):
		Screen.__init__(self, session)

		self.session = session

		InfoBarBase.__init__(self)
		InfoBarMoviePlayerSummarySupport.__init__(self)		
		InfoBarServiceNotifications.__init__(self)
		InfoBarShowHide.__init__(self)
		InfoBarSeek.__init__(self)
		InfoBarAudioSelection.__init__(self)
		InfoBarSubtitleSupport.__init__(self)
		IPTVInfoBarPVRState.__init__(self, PVRState, True)
		SubsSupport.__init__(self, searchSupport=True, embeddedSupport=True)
		SubsSupportStatus.__init__(self)

		protocol = glob.current_playlist['playlist_info']['protocol']
		domain = glob.current_playlist['playlist_info']['domain']
		host = glob.current_playlist['playlist_info']['host']

		self.streamurl = streamurl
		self.servicetype = servicetype

		skin = skin_path + 'catchupplayer.xml'
		self["epg_description"] = StaticText()
		self["streamcat"] = StaticText()
		self["streamtype"] = StaticText()
		self["extension"] = StaticText()
		self["epg_picon"] = Pixmap()

		self["eventname"] = Label()
		self["state"] = Label()
		self["speed"] = Label()
		self["statusicon"] = MultiPixmap()

		with open(skin, 'r') as f:
			self.skin = f.read()

		self.setup_title = _('Catch Up')

		self['actions'] = ActionMap(["XStreamityActions"], {
			'cancel': self.back,
			'tv': self.toggleStreamType,
			"stop": self.back,

			}, -2)

		self.onLayoutFinish.append(self.__layoutFinished)


	def __layoutFinished(self):
		self.playStream(self.servicetype, self.streamurl)


	def playStream(self, servicetype, streamurl):
		self["epg_description"].setText(glob.catchupdata[1])
		self["streamcat"].setText("Catch")
		self["streamtype"].setText(str(servicetype))

		try:
			self["extension"].setText(str(os.path.splitext(streamurl)[-1]))
		except:
			pass

		self.downloadPicon()

		self.reference = eServiceReference(int(servicetype),0,streamurl)
		self.reference.setName(glob.catchupdata[0])

		self.session.nav.stopService()
		self.session.nav.playService(self.reference)


	def downloadPicon(self):

		size = []
		stream_url = ''
		desc_image = ''

		if glob.currentchannelist:
			stream_url = glob.currentchannelist[glob.currentchannelistindex][8]
			desc_image = glob.currentchannelist[glob.currentchannelistindex][5]

		if stream_url != 'None':
			imagetype = "picon"
			size = [147,88]
			if screenwidth.width() > 1280:
				size = [220,130]

		if size != []:
			if desc_image != '':
				temp = '/tmp/xstreamity/temp.png'
				preview = '/tmp/xstreamity/preview.png'
				try:
					downloadPage(desc_image, temp).addCallback(self.checkdownloaded, size, imagetype, temp)
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
				if self["epg_picon"].instance:
					self["epg_picon"].instance.setPixmapFromFile(preview)
			else:
				self.loadDefaultImage()
		else:
			print "file does not exist"
		return preview


	def back(self):
		print "**** back 0 *****"
		if self.session.nav.getCurrentlyPlayingServiceReference():
			print "**** back 1 *****"
			glob.newPlayingServiceRef = self.session.nav.getCurrentlyPlayingServiceReference()
			glob.newPlayingServiceRefString = self.session.nav.getCurrentlyPlayingServiceReference().toString()
			glob.nextlist[-1]['index'] = glob.currentchannelistindex
			print "****** back 2 ****"
		self.close()
		print "****** back 3 ******"


	def toggleStreamType(self):
		currentindex = 0
		streamtypelist = ["1","4097"]
		
		if os.path.exists("/usr/bin/gstplayer"):
			streamtypelist.append("5001")
			
		if os.path.exists("/usr/bin/exteplayer3"):
			streamtypelist.append("5002")
			
		if os.path.exists("/usr/bin/apt-get"):
			streamtypelist.append("8193")

		for index, item in enumerate(streamtypelist, start=0):
			if str(item) == str(self.servicetype):
				currentindex = index
				break
		nextStreamType = islice(cycle(streamtypelist),currentindex+1,None)
		self.servicetype = int(next(nextStreamType))
		self.playStream(self.servicetype, self.streamurl)


	def loadDefaultImage(self):
		if screenwidth.width() > 1280:
			if self["epg_picon"].instance:
				self["epg_picon"].instance.setPixmapFromFile(common_path + "picon.png")
		else:

			if self["epg_picon"].instance:
					self["epg_picon"].instance.setPixmapFromFile(common_path + "picon_sd.png")


