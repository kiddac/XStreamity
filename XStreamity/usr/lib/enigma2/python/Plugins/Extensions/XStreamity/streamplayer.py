#!/usr/bin/python
# -*- coding: utf-8 -*-

from . import _
from . import xstreamity_globals as glob

from .plugin import skin_path, screenwidth, common_path, cfg, dir_tmp
from .xStaticText import StaticText

from Components.ActionMap import ActionMap
from Components.AVSwitch import AVSwitch
from enigma import eAVSwitch
from Components.config import config, NoSave, ConfigText, ConfigClock
from Components.Label import Label
from Components.ProgressBar import ProgressBar
from Components.Pixmap import Pixmap, MultiPixmap
from Components.ServiceEventTracker import ServiceEventTracker, InfoBarBase
from datetime import datetime, timedelta
from enigma import eTimer, eServiceReference, iPlayableService, ePicLoad
from itertools import cycle, islice
from PIL import Image, ImageChops, ImageFile, PngImagePlugin
from RecordTimer import RecordTimerEntry

from Screens.InfoBarGenerics import InfoBarMenu, InfoBarSeek, InfoBarAudioSelection, InfoBarMoviePlayerSummarySupport, \
    InfoBarSubtitleSupport, InfoBarSummarySupport, InfoBarServiceErrorPopupSupport, InfoBarNotifications

from Screens.MessageBox import MessageBox
from Screens.PVRState import PVRState
from Screens.Screen import Screen
from ServiceReference import ServiceReference
from time import time
from Tools.BoundFunction import boundFunction
from twisted.web.client import downloadPage

import re
import requests

if cfg.subs.getValue() is True:
    try:
        from Plugins.Extensions.SubsSupport import SubsSupport, SubsSupportStatus
    except ImportError:
        class SubsSupport(object):
            def __init__(self, *args, **kwargs):
                pass

        class SubsSupportStatus(object):
            def __init__(self, *args, **kwargs):
                pass
else:
    class SubsSupport(object):
        def __init__(self, *args, **kwargs):
            pass

    class SubsSupportStatus(object):
        def __init__(self, *args, **kwargs):
            pass

import os
import sys

try:
    pythonVer = sys.version_info.major
except:
    pythonVer = 2

# https twisted client hack #
try:
    from twisted.internet import ssl
    from twisted.internet._sslverify import ClientTLSOptions
    sslverify = True
except:
    sslverify = False

if sslverify:
    try:
        from urlparse import urlparse
    except:
        from urllib.parse import urlparse

    class SNIFactory(ssl.ClientContextFactory):
        def __init__(self, hostname=None):
            self.hostname = hostname

        def getContext(self):
            ctx = self._contextFactory(self.method)
            if self.hostname:
                ClientTLSOptions(self.hostname, ctx)
            return ctx


# png hack
def mycall(self, cid, pos, length):
    if cid.decode("ascii") == "tRNS":
        return self.chunk_TRNS(pos, length)
    else:
        return getattr(self, "chunk_" + cid.decode("ascii"))(pos, length)


def mychunk_TRNS(self, pos, length):
    _simple_palette = re.compile(b"^\xff*\x00\xff*$")
    s = ImageFile._safe_read(self.fp, length)
    if self.im_mode == "P":
        if _simple_palette.match(s):
            i = s.find(b"\0")
            if i >= 0:
                self.im_info["transparency"] = i
        else:
            self.im_info["transparency"] = s
    elif self.im_mode in ("1", "L", "I"):
        self.im_info["transparency"] = i16(s)
    elif self.im_mode == "RGB":
        self.im_info["transparency"] = i16(s), i16(s, 2), i16(s, 4)
    return s


if pythonVer != 2:
    PngImagePlugin.ChunkStream.call = mycall
    PngImagePlugin.PngStream.chunk_TRNS = mychunk_TRNS


_initialized = 0


def _mypreinit():
    global _initialized
    if _initialized >= 1:
        return
    try:
        from . import MyPngImagePlugin
        assert MyPngImagePlugin
    except ImportError:
        pass

    _initialized = 1


Image.preinit = _mypreinit


VIDEO_ASPECT_RATIO_MAP = {
    0: '4:3 Letterbox',
    1: '4:3 PanScan',
    2: '16:9',
    3: '16:9 Always',
    4: '16:10 Letterbox',
    5: '16:10 PanScan',
    6: '16:9 Letterbox'
}


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
        self["ShowHideActions"] = ActionMap(["InfobarShowHideActions"], {
            "toggleShow": self.OkPressed,
            "hide": self.hide,
        }, 1)

        self.__event_tracker = ServiceEventTracker(screen=self, eventmap={
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
    def __init__(self, screen=PVRState, force_show=True):
        self.onChangedEntry = []
        self.onPlayStateChanged.append(self.__playStateChanged)
        self.pvrStateDialog = self.session.instantiateDialog(screen)
        self.onShow.append(self._mayShow)
        self.onHide.append(self.pvrStateDialog.hide)
        self.force_show = force_show

    def _mayShow(self):
        if 'state' in self and not self.force_show:
            self["state"].setText("")
            self["statusicon"].setPixmapNum(6)
            self["speed"].setText("")
        if self.shown and self.seekstate != self.SEEK_STATE_EOF and not self.force_show:
            self.pvrStateDialog.show()
            self.startHideTimer()

    def __playStateChanged(self, state):
        playstateString = state[3]
        state_summary = playstateString

        if "statusicon" in self.pvrStateDialog:
            self.pvrStateDialog["state"].setText(playstateString)
            speedtext = ""
            self.pvrStateDialog["speed"].setText("")
            speed_summary = self.pvrStateDialog["speed"].text
            if playstateString:
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

            if "state" in self and self.force_show:
                self["state"].setText(playstateString)
                self["statusicon"].setPixmapNum(statusicon_summary)
                self["speed"].setText(speedtext)

            for cb in self.onChangedEntry:
                cb(state_summary, speed_summary, statusicon_summary)


class XStreamity_StreamPlayer(
    InfoBarBase,
    InfoBarMenu,
    InfoBarSeek,
    InfoBarAudioSelection,
    InfoBarMoviePlayerSummarySupport,
    InfoBarSubtitleSupport,
    InfoBarSummarySupport,
    InfoBarServiceErrorPopupSupport,
    InfoBarNotifications,
    IPTVInfoBarShowHide,
    IPTVInfoBarPVRState,
    Screen
):

    def __init__(self, session, streamurl, servicetype):
        Screen.__init__(self, session)

        self.session = session

        if str(os.path.splitext(streamurl)[-1]) == ".m3u8":
            if servicetype == "1":
                servicetype = "4097"

        for x in InfoBarBase, \
                InfoBarMenu, \
                InfoBarSeek, \
                InfoBarAudioSelection, \
                InfoBarMoviePlayerSummarySupport, \
                InfoBarSubtitleSupport, \
                InfoBarSummarySupport, \
                InfoBarServiceErrorPopupSupport, \
                InfoBarNotifications, \
                IPTVInfoBarShowHide:
            x.__init__(self)

        IPTVInfoBarPVRState.__init__(self, PVRState, True)

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

        self.ar_id_player = 0

        with open(skin, 'r') as f:
            self.skin = f.read()

        self.setup_title = _('TV')

        self['actions'] = ActionMap(["XStreamityActions"], {
            'cancel': self.back,
            "stop": self.back,
            "red": self.back,

            "channelUp": self.__next__,
            "down": self.__next__,
            "channelDown": self.prev,
            "up": self.prev,
            'tv': self.toggleStreamType,
            'info': self.toggleStreamType,
            "green": self.nextAR,
            "rec": self.IPTVstartInstantRecording,
        }, -2)

        self.onFirstExecBegin.append(boundFunction(self.playStream, self.servicetype, self.streamurl))

    def IPTVstartInstantRecording(self, limitEvent=True):
        from . import record
        begin = int(time())
        end = begin + 3600

        if glob.currentepglist[glob.currentchannellistindex][3]:
            name = glob.currentepglist[glob.currentchannellistindex][3]
        else:
            name = glob.currentchannellist[glob.currentchannellistindex][0]

        self.name = NoSave(ConfigText(default=name, fixed_size=False))
        self.date = time()
        self.starttime = NoSave(ConfigClock(default=begin))
        self.endtime = NoSave(ConfigClock(default=end))
        self.session.openWithCallback(self.RecordDateInputClosed, record.RecordDateInput, self.name, self.date, self.starttime, self.endtime, True)

    def RecordDateInputClosed(self, ret=None):
        if ret:
            begin = ret[1]
            end = ret[2]
            name = ret[3]

            description = glob.currentepglist[glob.currentchannellistindex][4]
            eventid = int(self.streamurl.rpartition('/')[-1].partition('.')[0])
            serviceref = eServiceReference(1, 0, self.streamurl)

            if isinstance(serviceref, eServiceReference):
                serviceref = ServiceReference(serviceref)

            recording = RecordTimerEntry(serviceref, begin, end, name, description, eventid, dirname=str(cfg.downloadlocation.getValue()))
            recording.dontSave = True

            simulTimerList = self.session.nav.RecordTimer.record(recording)

            if simulTimerList is None:  # no conflict
                recording.autoincrease = False

                self.session.open(MessageBox, _('Recording Timer Set.'), MessageBox.TYPE_INFO, timeout=5)
            else:
                self.session.open(MessageBox, _('Recording Failed.'), MessageBox.TYPE_WARNING)
                return
        else:
            return

    def playStream(self, servicetype, streamurl):
        self["epg_description"].setText(glob.currentepglist[glob.currentchannellistindex][4])
        self["nowchannel"].setText(glob.currentchannellist[glob.currentchannellistindex][0])
        self["nowtitle"].setText(glob.currentepglist[glob.currentchannellistindex][3])
        self["nexttitle"].setText(glob.currentepglist[glob.currentchannellistindex][6])
        self["nowtime"].setText(glob.currentepglist[glob.currentchannellistindex][2])
        self["nexttime"].setText(glob.currentepglist[glob.currentchannellistindex][5])
        self["streamcat"].setText("Live")
        self["streamtype"].setText(str(servicetype))

        try:
            self["extension"].setText(str(os.path.splitext(streamurl)[-1]))
        except:
            pass

        start = ''
        end = ''
        percent = 0

        if glob.currentepglist[glob.currentchannellistindex][2] != '':
            start = glob.currentepglist[glob.currentchannellistindex][2]

        if glob.currentepglist[glob.currentchannellistindex][5] != '':
            end = glob.currentepglist[glob.currentchannellistindex][5]

        if start != '' and end != '':
            self["progress"].show()
            start_time = datetime.strptime(start, "%H:%M")
            end_time = datetime.strptime(end, "%H:%M")

            if end_time < start_time:
                end_time = datetime.strptime(end, "%H:%M") + timedelta(hours=24)

            total_time = end_time - start_time

            duration = 0

            if total_time.total_seconds() > 0:
                duration = total_time.total_seconds() / 60

            now = datetime.now().strftime("%H:%M")
            current_time = datetime.strptime(now, "%H:%M")
            elapsed = current_time - start_time

            if elapsed.days < 0:
                elapsed = timedelta(days=0, seconds=elapsed.seconds)

            elapsedmins = 0

            if elapsed.total_seconds() > 0:
                elapsedmins = elapsed.total_seconds() / 60

            if duration > 0:
                percent = int(elapsedmins / duration * 100)
            else:
                percent = 100

            self["progress"].setValue(percent)
        else:
            self["progress"].hide()

        self.reference = eServiceReference(int(self.servicetype), 0, self.streamurl)
        self.reference.setName(glob.currentchannellist[glob.currentchannellistindex][0])

        if self.session.nav.getCurrentlyPlayingServiceReference():
            if self.session.nav.getCurrentlyPlayingServiceReference().toString() != self.reference.toString():
                self.session.nav.stopService()
                self.session.nav.playService(self.reference)
        else:
            self.session.nav.playService(self.reference)

        if self.session.nav.getCurrentlyPlayingServiceReference():
            glob.newPlayingServiceRef = self.session.nav.getCurrentlyPlayingServiceReference()
            glob.newPlayingServiceRefString = self.session.nav.getCurrentlyPlayingServiceReference().toString()
        self.downloadImage()

    def downloadImage(self):
        try:
            os.remove(str(dir_tmp) + 'original.png')
            os.remove(str(dir_tmp) + 'temp.png')
        except:
            pass

        original = str(dir_tmp) + 'original.png'
        desc_image = ''
        try:
            desc_image = glob.currentchannellist[glob.currentchannellistindex][5]
        except:
            pass

        if desc_image and desc_image != "n/A":
            temp = dir_tmp + 'temp.png'
            try:
                if desc_image.startswith("https") and sslverify:
                    parsed_uri = urlparse(desc_image)
                    domain = parsed_uri.hostname
                    sniFactory = SNIFactory(domain)
                    if pythonVer == 3:
                        desc_image = desc_image.encode()
                    downloadPage(desc_image, temp, sniFactory, timeout=5).addCallback(self.resizeImage)
                else:
                    if pythonVer == 3:
                        desc_image = desc_image.encode()
                    downloadPage(desc_image, temp, timeout=5).addCallback(self.resizeImage)
            except:
                self.loadDefaultImage()
        else:
            self.loadDefaultImage()

    def loadDefaultImage(self):
        if self["epg_picon"].instance:
            self["epg_picon"].instance.setPixmapFromFile(common_path + "picon.png")

    def resizeImage(self, data=None):
        # print("*** resizeImage ***")
        original = str(dir_tmp) + 'temp.png'

        size = [147, 88]
        if screenwidth.width() > 1280:
            size = [220, 130]

        if os.path.exists(original):
            try:
                im = Image.open(original).convert('RGBA')
                im.thumbnail(size, Image.ANTIALIAS)

                # crop and center image
                bg = Image.new('RGBA', size, (255, 255, 255, 0))

                imagew, imageh = im.size
                im_alpha = im.convert('RGBA').split()[-1]
                bgwidth, bgheight = bg.size
                bg_alpha = bg.convert('RGBA').split()[-1]
                temp = Image.new('L', (bgwidth, bgheight), 0)
                temp.paste(im_alpha, (int((bgwidth - imagew) / 2), int((bgheight - imageh) / 2)), im_alpha)
                bg_alpha = ImageChops.screen(bg_alpha, temp)
                bg.paste(im, (int((bgwidth - imagew) / 2), int((bgheight - imageh) / 2)))
                im = bg

                im.save(original, 'PNG')

                if self["epg_picon"].instance:
                    self["epg_picon"].instance.setPixmapFromFile(original)

            except Exception as e:
                print("******* picon resize failed *******")
                print(e)
        else:
            self.loadDefaultImage()

    def back(self):
        glob.nextlist[-1]['index'] = glob.currentchannellistindex
        self.close()

    def toggleStreamType(self):
        currentindex = 0
        self.retries = 0

        streamtypelist = ["1", "4097"]

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

        nextStreamType = islice(cycle(streamtypelist), currentindex + 1, None)
        self.servicetype = int(next(nextStreamType))

        self.playStream(self.servicetype, self.streamurl)

    def __next__(self):
        self.retries = 0
        if glob.currentchannellist:
            listlength = len(glob.currentchannellist)
            glob.currentchannellistindex += 1
            if glob.currentchannellistindex + 1 > listlength:
                glob.currentchannellistindex = 0
            self.streamurl = glob.currentchannellist[glob.currentchannellistindex][3]

            self.playStream(self.servicetype, self.streamurl)

    def prev(self):
        self.retries = 0
        if glob.currentchannellist:
            listlength = len(glob.currentchannellist)
            glob.currentchannellistindex -= 1
            if glob.currentchannellistindex + 1 == 0:
                glob.currentchannellistindex = listlength - 1

            self.streamurl = glob.currentchannellist[glob.currentchannellistindex][3]
            self.playStream(self.servicetype, self.streamurl)

    def nextARfunction(self):
        try:
            self.ar_id_player += 1
            if self.ar_id_player > 6:
                self.ar_id_player = 0
            eAVSwitch.getInstance().setAspectRatio(self.ar_id_player)
            print('self.ar_id_player NEXT %s' % VIDEO_ASPECT_RATIO_MAP[self.ar_id_player])
            return VIDEO_ASPECT_RATIO_MAP[self.ar_id_player]
        except Exception as ex:
            print(ex)
            return 'nextAR ERROR %s' % ex

    def nextAR(self):
        message = self.nextARfunction()
        self.session.open(MessageBox, message, type=MessageBox.TYPE_INFO, timeout=3)


class XStreamity_VodPlayer(
    InfoBarBase,
    InfoBarMenu,
    InfoBarSeek,
    InfoBarAudioSelection,
    InfoBarMoviePlayerSummarySupport,
    InfoBarSubtitleSupport,
    InfoBarSummarySupport,
    InfoBarServiceErrorPopupSupport,
    InfoBarNotifications,
    IPTVInfoBarShowHide,
    IPTVInfoBarPVRState,
    SubsSupportStatus,
    SubsSupport,
    Screen
):

    def __init__(self, session, streamurl, servicetype):
        Screen.__init__(self, session)
        self.session = session

        for x in InfoBarBase, \
                InfoBarMenu, \
                InfoBarSeek, \
                InfoBarAudioSelection, \
                InfoBarMoviePlayerSummarySupport, \
                InfoBarSubtitleSupport, \
                InfoBarSummarySupport, \
                InfoBarServiceErrorPopupSupport, \
                InfoBarNotifications, \
                IPTVInfoBarShowHide:
            x.__init__(self)

        IPTVInfoBarPVRState.__init__(self, PVRState, True)

        if cfg.subs.value is True:
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

        self.ar_id_player = 0

        with open(skin, 'r') as f:
            self.skin = f.read()

        self.setup_title = _('VOD')

        self['actions'] = ActionMap(["XStreamityActions"], {
            'cancel': self.back,
            "stop": self.back,
            "red": self.back,
            'tv': self.toggleStreamType,
            'info': self.toggleStreamType,
            "green": self.nextAR,
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

        self.reference = eServiceReference(int(self.servicetype), 0, self.streamurl)
        self.reference.setName(glob.currentchannellist[glob.currentchannellistindex][0])

        if self.session.nav.getCurrentlyPlayingServiceReference():
            if self.session.nav.getCurrentlyPlayingServiceReference().toString() != self.reference.toString():
                self.session.nav.stopService()
                self.session.nav.playService(self.reference)
        else:
            self.session.nav.playService(self.reference)

        if self.session.nav.getCurrentlyPlayingServiceReference():
            glob.newPlayingServiceRef = self.session.nav.getCurrentlyPlayingServiceReference()
            glob.newPlayingServiceRefString = self.session.nav.getCurrentlyPlayingServiceReference().toString()

        self.downloadImage()

    def downloadImage(self):
        try:
            os.remove(str(dir_tmp) + 'original.jpg')
            os.remove(str(dir_tmp) + 'temp.jpg')
        except:
            pass

        original = str(dir_tmp) + 'original.jpg'
        desc_image = ''

        desc_image = glob.currentchannellist[glob.currentchannellistindex][5]

        if desc_image and desc_image != "n/A":
            temp = dir_tmp + 'temp.jpg'
            try:
                if desc_image.startswith("https") and sslverify:
                    parsed_uri = urlparse(desc_image)
                    domain = parsed_uri.hostname
                    sniFactory = SNIFactory(domain)
                    if pythonVer == 3:
                        desc_image = desc_image.encode()
                    downloadPage(desc_image, temp, sniFactory, timeout=5).addCallback(self.resizeImage)
                else:
                    if pythonVer == 3:
                        desc_image = desc_image.encode()
                    downloadPage(desc_image, temp, timeout=5).addCallback(self.resizeImage)
            except:
                self.loadDefaultImage()
        else:
            self.loadDefaultImage()

    def loadDefaultImage(self):
        if self["cover"].instance:
            self["cover"].instance.setPixmapFromFile(skin_path + "images/vod_cover.png")

    def resizeImage(self, data=None):
        if self["cover"].instance:
            preview = str(dir_tmp) + 'temp.jpg'

            width = 147
            height = 220
            if screenwidth.width() > 1280:
                width = 220
                height = 330

            self.PicLoad.setPara([width, height, self.Scale[0], self.Scale[1], 0, 1, "FF000000"])

            if self.PicLoad.startDecode(preview):
                # if this has failed, then another decode is probably already in progress
                # throw away the old picload and try again immediately
                self.PicLoad = ePicLoad()
                try:
                    self.PicLoad.PictureData.get().append(self.DecodePicture)
                except:
                    self.PicLoad_conn = self.PicLoad.PictureData.connect(self.DecodePicture)
                self.PicLoad.setPara([width, height, self.Scale[0], self.Scale[1], 0, 1, "FF000000"])
                self.PicLoad.startDecode(preview)

    def DecodePicture(self, PicInfo=None):
        ptr = self.PicLoad.getData()
        if ptr is not None:
            self["cover"].instance.setPixmap(ptr)
            self["cover"].instance.show()

    def back(self):
        glob.nextlist[-1]['index'] = glob.currentchannellistindex
        self.close()

    def toggleStreamType(self):
        currentindex = 0
        streamtypelist = ["1", "4097"]

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
        nextStreamType = islice(cycle(streamtypelist), currentindex + 1, None)
        self.servicetype = int(next(nextStreamType))
        self.playStream(self.servicetype, self.streamurl)

    def nextARfunction(self):
        try:
            self.ar_id_player += 1
            if self.ar_id_player > 6:
                self.ar_id_player = 0
            eAVSwitch.getInstance().setAspectRatio(self.ar_id_player)
            print('self.ar_id_player NEXT %s' % VIDEO_ASPECT_RATIO_MAP[self.ar_id_player])
            return VIDEO_ASPECT_RATIO_MAP[self.ar_id_player]
        except Exception as ex:
            print(ex)
            return 'nextAR ERROR %s' % ex

    def nextAR(self):
        message = self.nextARfunction()
        self.session.open(MessageBox, message, type=MessageBox.TYPE_INFO, timeout=3)


class XStreamity_CatchupPlayer(
    InfoBarBase,
    InfoBarMenu,
    InfoBarSeek,
    InfoBarAudioSelection,
    InfoBarMoviePlayerSummarySupport,
    InfoBarSubtitleSupport,
    InfoBarSummarySupport,
    InfoBarServiceErrorPopupSupport,
    InfoBarNotifications,
    IPTVInfoBarShowHide,
    IPTVInfoBarPVRState,
    SubsSupportStatus,
    SubsSupport,
    Screen
):

    def __init__(self, session, streamurl, servicetype):
        Screen.__init__(self, session)

        self.session = session

        if str(os.path.splitext(streamurl)[-1]) == ".m3u8":
            if servicetype == "1":
                servicetype = "4097"

        for x in InfoBarBase, \
                InfoBarMenu, \
                InfoBarSeek, \
                InfoBarAudioSelection, \
                InfoBarMoviePlayerSummarySupport, \
                InfoBarSubtitleSupport, \
                InfoBarSummarySupport, \
                InfoBarServiceErrorPopupSupport, \
                InfoBarNotifications, \
                IPTVInfoBarShowHide:
            x.__init__(self)

        IPTVInfoBarPVRState.__init__(self, PVRState, True)

        if cfg.subs.value is True:
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

        self.ar_id_player = 0

        with open(skin, 'r') as f:
            self.skin = f.read()

        self.setup_title = _('Catch Up')

        self['actions'] = ActionMap(["XStreamityActions"], {
            'cancel': self.back,
            'red': self.back,
            "stop": self.back,
            'tv': self.toggleStreamType,
            'info': self.toggleStreamType,
            "green": self.nextAR,
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

        self.reference = eServiceReference(int(servicetype), 0, streamurl)
        self.reference.setName(glob.catchupdata[0])
        if self.session.nav.getCurrentlyPlayingServiceReference():
            if self.session.nav.getCurrentlyPlayingServiceReference().toString() != self.reference.toString():
                self.session.nav.stopService()
                self.session.nav.playService(self.reference)
        else:
            self.session.nav.playService(self.reference)

        if self.session.nav.getCurrentlyPlayingServiceReference():
            glob.newPlayingServiceRef = self.session.nav.getCurrentlyPlayingServiceReference()
            glob.newPlayingServiceRefString = self.session.nav.getCurrentlyPlayingServiceReference().toString()

        if self.session.nav.getCurrentlyPlayingServiceReference():
            glob.newPlayingServiceRef = self.session.nav.getCurrentlyPlayingServiceReference()
            glob.newPlayingServiceRefString = self.session.nav.getCurrentlyPlayingServiceReference().toString()

        self.downloadImage()

    def downloadImage(self):
        try:
            os.remove(str(dir_tmp) + 'original.png')
            os.remove(str(dir_tmp) + 'temp.png')
        except:
            pass

        original = str(dir_tmp) + 'original.png'
        desc_image = ''
        try:
            desc_image = glob.currentchannellist[glob.currentchannellistindex][5]
        except:
            pass

        if desc_image and desc_image != "n/A":
            temp = dir_tmp + 'temp.png'
            try:
                if desc_image.startswith("https") and sslverify:
                    parsed_uri = urlparse(desc_image)
                    domain = parsed_uri.hostname
                    sniFactory = SNIFactory(domain)
                    if pythonVer == 3:
                        desc_image = desc_image.encode()
                    downloadPage(desc_image, temp, sniFactory, timeout=3).addCallback(self.resizeImage).addErrback(self.loadDefaultImage)
                else:
                    if pythonVer == 3:
                        desc_image = desc_image.encode()
                    downloadPage(desc_image, temp, timeout=5).addCallback(self.resizeImage).addErrback(self.loadDefaultImage)
            except:
                self.loadDefaultImage()
        else:
            self.loadDefaultImage()

    def loadDefaultImage(self, data=None):
        if data:
            print(data)
        if self["epg_picon"].instance:
            self["epg_picon"].instance.setPixmapFromFile(common_path + "picon.png")

    def resizeImage(self, data=None):
        # print("*** resizeImage ***")
        original = str(dir_tmp) + 'temp.png'

        size = [147, 88]
        if screenwidth.width() > 1280:
            size = [220, 130]

        if os.path.exists(original):
            try:
                im = Image.open(original).convert('RGBA')
                im.thumbnail(size, Image.ANTIALIAS)

                # crop and center image
                bg = Image.new('RGBA', size, (255, 255, 255, 0))

                imagew, imageh = im.size
                im_alpha = im.convert('RGBA').split()[-1]
                bgwidth, bgheight = bg.size
                bg_alpha = bg.convert('RGBA').split()[-1]
                temp = Image.new('L', (bgwidth, bgheight), 0)
                temp.paste(im_alpha, (int((bgwidth - imagew) / 2), int((bgheight - imageh) / 2)), im_alpha)
                bg_alpha = ImageChops.screen(bg_alpha, temp)
                bg.paste(im, (int((bgwidth - imagew) / 2), int((bgheight - imageh) / 2)))
                im = bg

                im.save(original, 'PNG')

                if self["epg_picon"].instance:
                    self["epg_picon"].instance.setPixmapFromFile(original)

            except Exception as e:
                print("******* picon resize failed *******")
                print(e)
        else:
            self.loadDefaultImage()

    def back(self):
        glob.nextlist[-1]['index'] = glob.currentchannellistindex
        self.close()

    def toggleStreamType(self):
        currentindex = 0
        streamtypelist = ["1", "4097"]

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
        nextStreamType = islice(cycle(streamtypelist), currentindex + 1, None)
        self.servicetype = int(next(nextStreamType))
        self.playStream(self.servicetype, self.streamurl)

    def nextARfunction(self):
        try:
            self.ar_id_player += 1
            if self.ar_id_player > 6:
                self.ar_id_player = 0
            eAVSwitch.getInstance().setAspectRatio(self.ar_id_player)
            print('self.ar_id_player NEXT %s' % VIDEO_ASPECT_RATIO_MAP[self.ar_id_player])
            return VIDEO_ASPECT_RATIO_MAP[self.ar_id_player]
        except Exception as ex:
            print(ex)
            return 'nextAR ERROR %s' % ex

    def nextAR(self):
        message = self.nextARfunction()
        self.session.open(MessageBox, message, type=MessageBox.TYPE_INFO, timeout=3)
