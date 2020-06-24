# for localized messages
from . import _


from Components.ActionMap import ActionMap
from Components.AVSwitch import AVSwitch
from Components.config import config, ConfigClock
from Components.Label import Label
from Components.ProgressBar import ProgressBar
from Components.Pixmap import Pixmap, MultiPixmap
from Components.ServiceEventTracker import ServiceEventTracker, InfoBarBase
from datetime import datetime, timedelta
from enigma import eTimer, eServiceReference, iPlayableService, ePicLoad
from itertools import cycle, islice
from plugin import skin_path, screenwidth, common_path, cfg, dir_tmp
from RecordTimer import RecordTimerEntry
from Screens.InfoBarGenerics import InfoBarMoviePlayerSummarySupport, InfoBarServiceNotifications, InfoBarSeek, InfoBarAudioSelection, InfoBarSubtitleSupport, InfoBarInstantRecord, InfoBarShowHide
from Screens.MessageBox import MessageBox
from Screens.PVRState import PVRState
from Screens.Screen import Screen
from ServiceReference import ServiceReference
from time import time
from Tools.BoundFunction import boundFunction
from twisted.web.client import downloadPage
from xStaticText import StaticText

try:
	from Plugins.Extensions.SubsSupport import SubsSupport, SubsSupportStatus
except ImportError:
	class SubsSupport(object):
		def __init__(self, *args, **kwargs):
			pass
	class SubsSupportStatus(object):
		def __init__(self, *args, **kwargs):
			pass

import os
import xstreamity_globals as glob
import imagedownload


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
		if self.__locked < 0:
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
			speedtext = ""
			self.pvrStateDialog["speed"].setText("")
			speed_summary = self.pvrStateDialog["speed"].text
			
			if playstateString == '>':
				statusicon_summary = 0
				self.pvrStateDialog["statusicon"].setPixmapNum(statusicon_summary)
		
			elif playstateString == '||':
				statusicon_summary = 1
				self.pvrStateDialog["statusicon"].setPixmapNum(statusicon_summary)
					
			elif playstateString == 'END':
				statusicon_summary = 2
				self.pvrStateDialog["statusicon"].setPixmapNum(statusicon_summary)

			elif playstateString.startswith('>>'):
				speed = state[3].split()
				statusicon_summary = 3
				self.pvrStateDialog["statusicon"].setPixmapNum(statusicon_summary)
				self.pvrStateDialog["speed"].setText(speed[1])
				speedtext = speed[1]
		
			elif playstateString.startswith('<<'):
				speed = state[3].split()
				statusicon_summary = 4
				self.pvrStateDialog["statusicon"].setPixmapNum(statusicon_summary)
				self.pvrStateDialog["speed"].setText(speed[1])
				speedtext = speed[1]
				
			elif playstateString.startswith('/'):
				statusicon_summary = 5
				self.pvrStateDialog["statusicon"].setPixmapNum(statusicon_summary)
				self.pvrStateDialog["speed"].setText(playstateString)

				speedtext = playstateString
						
			if self.has_key("state") and self.force_show:		
				self["state"].setText(playstateString)
				self["statusicon"].setPixmapNum(statusicon_summary)
				self["speed"].setText(speedtext)

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
		  
		self.streamurl = streamurl
		self.servicetype = servicetype
		self.retries = 0

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
			'info': self.toggleStreamType,
			"channelUp": self.next,
			"channelDown": self.prev,
			"up": self.prev,
			"down": self.next,
			"stop": self.back,
			"rec": self.IPTVstartInstantRecording,
			"red": self.back

			}, -2)

		self.onFirstExecBegin.append(boundFunction(self.playStream, self.servicetype, self.streamurl))


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

			name = glob.currentepglist[glob.currentchannelistindex][3]
			description = glob.currentepglist[glob.currentchannelistindex][4]
			eventid = glob.currentepglist[glob.currentchannelistindex][1]

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
		self["epg_description"].setText(glob.currentepglist[glob.currentchannelistindex][4])
		self["nowchannel"].setText(glob.currentchannelist[glob.currentchannelistindex][0])
		self["nowtitle"].setText(glob.currentepglist[glob.currentchannelistindex][3])
		self["nexttitle"].setText(glob.currentepglist[glob.currentchannelistindex][6])
		self["nowtime"].setText(glob.currentepglist[glob.currentchannelistindex][2])
		self["nexttime"].setText(glob.currentepglist[glob.currentchannelistindex][5])
		self["streamcat"].setText("Live")
		self["streamtype"].setText(str(servicetype))
		
		try:
			self["extension"].setText(str(os.path.splitext(streamurl)[-1]))
		except:
			pass

		start = ''
		end = ''
		percent = 0

		if glob.currentepglist[glob.currentchannelistindex][2] != '':
			start = glob.currentepglist[glob.currentchannelistindex][2]

		if glob.currentepglist[glob.currentchannelistindex][5] != '':
			end = glob.currentepglist[glob.currentchannelistindex][5]

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
			
			if elapsed.days < 0:
				elapsed = timedelta(days=0,seconds=elapsed.seconds)
							
			elapsedmins = 0
			
			if elapsed.total_seconds() > 0:
			  elapsedmins = elapsed.total_seconds()/60

			if duration > 0:
			  percent = int(elapsedmins / duration * 100)
			else:
			  percent = 100

			self["progress"].setValue(percent)
		else:
			self["progress"].hide()

		self.reference = eServiceReference(int(self.servicetype),0,self.streamurl)
		#self.reference.setName(str(glob.currentepglist[glob.currentchannelistindex][3]))
		
		"""
		if self.session.nav.getCurrentlyPlayingServiceReference():
			if self.session.nav.getCurrentlyPlayingServiceReference().toString() != self.reference.toString():
				self.session.nav.playService(self.reference)
				
		else:
			self.session.nav.playService(self.reference, forceRestart=True)
			
		if self.session.nav.getCurrentlyPlayingServiceReference():
			glob.newPlayingServiceRef = self.session.nav.getCurrentlyPlayingServiceReference()
			glob.newPlayingServiceRefString = self.session.nav.getCurrentlyPlayingServiceReference().toString()
			"""

		self.session.nav.playService(self.reference)
			
		if self.session.nav.getCurrentlyPlayingServiceReference():
			glob.newPlayingServiceRef = self.session.nav.getCurrentlyPlayingServiceReference()
			glob.newPlayingServiceRefString = self.session.nav.getCurrentlyPlayingServiceReference().toString()

		
		self.__event_tracker = ServiceEventTracker(screen=self, eventmap={
		  iPlayableService.evEnd: self.__evEnd,
		  iPlayableService.evTunedIn: self.__evTunedIn,
		  iPlayableService.evTuneFailed: self.__evTuneFailed,
		  iPlayableService.evUpdatedInfo: self.__evUpdatedInfo,
		  iPlayableService.evSeekableStatusChanged : self.__evSeekableStatusChanged, 
		  iPlayableService.evEOF: self.__evEOF,	  
		  })
		  			
		self.downloadPicon()


	def downloadPicon(self):
		size = []
		stream_url = ''
		desc_image = ''

		if glob.currentchannelist:
			stream_url = glob.currentchannelist[glob.currentchannelistindex][3]
			desc_image = glob.currentchannelist[glob.currentchannelistindex][5]

		if stream_url != 'None':
			imagetype = "picon"
			size = [147,88]
			if screenwidth.width() > 1280:
				size = [220,130]

		if desc_image and desc_image != "n/A" and desc_image != "":
			temp = dir_tmp + 'temp.png'
			try:
				downloadPage(desc_image, temp, timeout=3).addCallback(self.checkdownloaded, size, imagetype, temp)
			except:
				if desc_image.startswith('https'):
					desc_image = desc_image.replace('https','http')
					try:
						downloadPage(desc_image, temp, timeout=3).addCallback(self.checkdownloaded, size, imagetype, temp)
					except:
						pass
						self.loadDefaultImage()
				else:
					self.loadDefaultImage()	
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
			print("file does not exist")
		return preview
		
	
	def loadDefaultImage(self):
		if self["epg_picon"].instance:
			self["epg_picon"].instance.setPixmapFromFile(common_path + "picon.png")


	def __evEnd(self):
		print("** evEnd **")


	def __evTunedIn(self):
		print("** evTunedIn **")
		if self.servicetype == "1":
			self.hasStreamData = False
			self.timerstream = eTimer()
			try:
				self.timerstream.callback.append(self.checkStream)
			except:
				self.timerstream_conn = self.timerstream.timeout.connect(self.checkStream)
			self.timerstream.start(2000, True)
			
		
	def __evTuneFailed(self):
		print("** evTuneFailed **")
		self.back()
		

	def __evUpdatedInfo(self):
		#print("** evUpdatedInfo **")
		if self.servicetype == "1":
			self.hasStreamData = True
			
			
	def __evSeekableStatusChanged(self):
		print("** evSeekableStatusChanged **")


	def __evEOF(self):
		print("** evEOF **")
		if self.servicetype == "1":
			self.session.nav.stopService()
			self.session.nav.playService(self.reference, forceRestart=True)
			

	def checkStream(self):	
		if self.hasStreamData == False:
			if self.retries < 2:
				self.retries += 1
				self.session.nav.stopService()
				self.session.nav.playService(self.reference, forceRestart=True)
			

	def back(self):
		glob.nextlist[-1]['index'] = glob.currentchannelistindex
		
		#if cfg.stopstream.value == True:
			#self.stopStream()
		self.close()


	def toggleStreamType(self):
		currentindex = 0
		self.retries = 0

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
		self.retries = 0
		if glob.currentchannelist:
			listlength = len(glob.currentchannelist)
			glob.currentchannelistindex += 1
			if glob.currentchannelistindex + 1 > listlength:
				glob.currentchannelistindex = 0
			self.streamurl = glob.currentchannelist[glob.currentchannelistindex][3]
			self.playStream(self.servicetype, self.streamurl)


	def prev(self):
		self.retries = 0
		if glob.currentchannelist:
			listlength = len(glob.currentchannelist)
			glob.currentchannelistindex -= 1
			if glob.currentchannelistindex + 1 == 0:
				glob.currentchannelistindex = listlength - 1

			self.streamurl = glob.currentchannelist[glob.currentchannelistindex][3]
			self.playStream(self.servicetype, self.streamurl)


	#play original channel
	def stopStream(self):
		if glob.currentPlayingServiceRefString != glob.newPlayingServiceRefString:
			if glob.newPlayingServiceRefString != '':
				self.session.nav.playService(eServiceReference(glob.currentPlayingServiceRefString))
				


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

		self.streamurl = streamurl
		self.servicetype = servicetype

		skin = skin_path + 'vodplayer.xml'

		self["streamcat"] = StaticText()
		self["streamtype"] = StaticText()
		self["extension"] = StaticText()
		
		self.PicLoad = ePicLoad()
		self.Scale = AVSwitch().getFramebufferScale()
		try:
			self.PicLoad.PictureData.get().append(self.DecodePicture)
		except:
			self.PicLoad_conn = self.PicLoad.PictureData.connect(self.DecodePicture)
		
		self["cover"] = Pixmap()

		self["eventname"] = Label()
		self["state"] = Label()
		self["speed"] = Label()
		self["statusicon"] = MultiPixmap()
		
		self["PTSSeekBack"] = Pixmap()
		self["PTSSeekPointer"] = Pixmap()

		with open(skin, 'r') as f:
			self.skin = f.read()

		self.setup_title = _('VOD')

		self['actions'] = ActionMap(["XStreamityActions"], {
			'cancel': self.back,
			'tv': self.toggleStreamType,
			'info': self.toggleStreamType,
			"channelUp": self.next,
			"channelDown": self.prev,
			"up": self.prev,
			"down": self.next,
			"stop": self.back,
			"red": self.back,

			}, -2)

		self.onFirstExecBegin.append(boundFunction(self.playStream, self.servicetype, self.streamurl))


	def playStream(self, servicetype, streamurl):
		if streamurl != 'None' and "/movie/" in streamurl:
			self["streamcat"].setText("VOD")
		else:
			self["streamcat"].setText("Series")
		self["streamtype"].setText(str(servicetype))

		try:
			self["extension"].setText(str(os.path.splitext(streamurl)[-1]))
		except:
			pass
				
		self.reference = eServiceReference(int(self.servicetype),0, self.streamurl)
		self.reference.setName(glob.currentchannelist[glob.currentchannelistindex][0])
		
		self.session.nav.playService(self.reference)
			
		if self.session.nav.getCurrentlyPlayingServiceReference():
			glob.newPlayingServiceRef = self.session.nav.getCurrentlyPlayingServiceReference()
			glob.newPlayingServiceRefString = self.session.nav.getCurrentlyPlayingServiceReference().toString()
					
		self.downloadCover()
		

	def downloadCover(self):
		try:
			os.remove(dir_tmp + 'original.jpg')
		except:
			pass
		
		size = []
		stream_url = ''
		desc_image = ''

		if glob.currentchannelist:
			stream_url = glob.currentchannelist[glob.currentchannelistindex][3]
			desc_image = glob.currentchannelist[glob.currentchannelistindex][5]

		if stream_url != 'None':
			imagetype = "cover"
			size = [147,220]
			if screenwidth.width() > 1280:
				size = [220,330]


		if desc_image and desc_image != "n/A" and desc_image != "":
			
			temp = dir_tmp + 'temp.jpg'

			try:
				downloadPage(desc_image, temp, timeout=3).addCallback(self.checkdownloaded, size, imagetype, temp)
			except:
				if desc_image.startswith('https'):
					desc_image = desc_image.replace('https','http')
					try:
						downloadPage(desc_image, temp, timeout=3).addCallback(self.checkdownloaded, size, imagetype, temp)
					except:	
						pass
						self.loadDefaultImage()
				else:
					self.loadDefaultImage()
		else:
			self.loadDefaultImage()


	def checkdownloaded(self, data, piconSize, imageType, temp):
		if imageType == "cover":
			if self["cover"].instance:	
				self.displayVodImage()	
				

	def loadDefaultImage(self):
		if self["cover"].instance:
			self["cover"].instance.setPixmapFromFile(common_path + "cover.png")


	def displayVodImage(self):
		preview = dir_tmp + 'temp.jpg'
		width = 147
		height = 220
		
		if screenwidth.width() > 1280:
			width = 220
			height = 330
			
		self.PicLoad.setPara([width,height,self.Scale[0],self.Scale[1],0,1,"FF000000"])
		
		if self.PicLoad.startDecode(preview):
				# if this has failed, then another decode is probably already in progress
				# throw away the old picload and try again immediately
				self.PicLoad = ePicLoad()
				try:
					self.PicLoad.PictureData.get().append(self.DecodePicture)
				except:
					self.PicLoad_conn = self.PicLoad.PictureData.connect(self.DecodePicture)
				self.PicLoad.setPara([width,height,self.Scale[0],self.Scale[1],0,1,"FF000000"])
				self.PicLoad.startDecode(preview)


	def DecodePicture(self, PicInfo = None):
		ptr = self.PicLoad.getData()
		if ptr is not None:
			self["cover"].instance.setPixmap(ptr)
			self["cover"].instance.show()
			
				
	def back(self):
		glob.nextlist[-1]['index'] = glob.currentchannelistindex
		
		#if cfg.stopstream.value == True:
			#self.stopStream()	
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
			self.playStream(self.servicetype, self.streamurl)


	def prev(self):
		if glob.currentchannelist:
			
			listlength = len(glob.currentchannelist)
			glob.currentchannelistindex -= 1
			if glob.currentchannelistindex + 1 == 0:
				glob.currentchannelistindex = listlength - 1
			self.playStream(self.servicetype, self.streamurl)


	#play original channel
	def stopStream(self):
		if glob.currentPlayingServiceRefString != glob.newPlayingServiceRefString:
			if glob.newPlayingServiceRefString != '':
				if self.session.nav.getCurrentlyPlayingServiceReference():
					self.session.nav.stopService()
				self.session.nav.playService(eServiceReference(glob.currentPlayingServiceRefString))


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
		
		self["PTSSeekBack"] = Pixmap()
		self["PTSSeekPointer"] = Pixmap()

		with open(skin, 'r') as f:
			self.skin = f.read()

		self.setup_title = _('Catch Up')

		self['actions'] = ActionMap(["XStreamityActions"], {
			'cancel': self.back,
			'red': self.back,
			'tv': self.toggleStreamType,
			'info': self.toggleStreamType,
			"stop": self.back,

			}, -2)

		self.onFirstExecBegin.append(boundFunction(self.playStream, self.servicetype, self.streamurl))


	def playStream(self, servicetype, streamurl):
		self["epg_description"].setText(glob.catchupdata[1])
		self["streamcat"].setText("Catch")
		self["streamtype"].setText(str(servicetype))

		try:
			self["extension"].setText(str(os.path.splitext(streamurl)[-1]))
		except:
			pass

		self.reference = eServiceReference(int(servicetype),0,streamurl)
		self.reference.setName(glob.catchupdata[0])

		self.session.nav.playService(self.reference)
			
		if self.session.nav.getCurrentlyPlayingServiceReference():
			glob.newPlayingServiceRef = self.session.nav.getCurrentlyPlayingServiceReference()
			glob.newPlayingServiceRefString = self.session.nav.getCurrentlyPlayingServiceReference().toString()
					
		self.downloadPicon()
		
		
	def downloadPicon(self):
		size = []
		stream_url = ''
		desc_image = ''

		if glob.currentchannelist:
			stream_url = glob.currentchannelist[glob.currentchannelistindex][3]
			desc_image = glob.currentchannelist[glob.currentchannelistindex][5]

		if stream_url != 'None':
			imagetype = "picon"
			size = [147,88]
			if screenwidth.width() > 1280:
				size = [220,130]

		if desc_image and desc_image != "n/A" and desc_image != "":
			
			temp = dir_tmp + 'temp.png'
			try:
				downloadPage(desc_image, temp, timeout=3).addCallback(self.checkdownloaded, size, imagetype, temp)
			except:
				if desc_image.startswith('https'):
					desc_image = desc_image.replace('https','http')
					try:
						downloadPage(desc_image, temp, timeout=3).addCallback(self.checkdownloaded, size, imagetype, temp)
					except:
						pass
						self.loadDefaultImage()
				else:
					self.loadDefaultImage()	
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
			print("file does not exist")
		return preview
		
		
	def loadDefaultImage(self):
		if self["epg_picon"].instance:
			self["epg_picon"].instance.setPixmapFromFile(common_path + "picon.png")


	def back(self):
		glob.nextlist[-1]['index'] = glob.currentchannelistindex
		#if cfg.stopstream.value == True:
			#self.stopStream()
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


	#play original channel
	def stopStream(self):
		if glob.currentPlayingServiceRefString != glob.newPlayingServiceRefString:
			if glob.newPlayingServiceRefString != '':
				if self.session.nav.getCurrentlyPlayingServiceReference():
					self.session.nav.stopService()
				self.session.nav.playService(eServiceReference(glob.currentPlayingServiceRefString))
