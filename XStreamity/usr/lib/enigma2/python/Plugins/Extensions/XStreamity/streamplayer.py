#!/usr/bin/python
# -*- coding: utf-8 -*-

from __future__ import absolute_import, print_function

from . import _
from . import xstreamity_globals as glob

from .plugin import skin_directory, screenwidth, common_path, hdr, cfg, dir_tmp, pythonVer, playlists_json
from .xStaticText import StaticText

from Components.ActionMap import ActionMap

try:
    from Components.AVSwitch import iAVSwitch
except:
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
from Tools import Notifications

from Screens.InfoBarGenerics import InfoBarMenu, InfoBarSeek, InfoBarAudioSelection, InfoBarMoviePlayerSummarySupport, \
    InfoBarSubtitleSupport, InfoBarSummarySupport, InfoBarServiceErrorPopupSupport, InfoBarNotifications

try:
    from .resumepoints import setResumePoint, getResumePoint
except Exception as e:
    print(e)

from Screens.MessageBox import MessageBox
from Screens.PVRState import PVRState
from Screens.Screen import Screen
from ServiceReference import ServiceReference
from Tools.BoundFunction import boundFunction
from twisted.web.client import downloadPage

try:
    from urlparse import urlparse
except:
    from urllib.parse import urlparse

import json
import os
import re
import requests
from requests.adapters import HTTPAdapter, Retry
import base64
import time

try:
    from http.client import HTTPConnection
    HTTPConnection.debuglevel = 0
except:
    from httplib import HTTPConnection
    HTTPConnection.debuglevel = 0
requests.packages.urllib3.disable_warnings()


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


# https twisted client hack #
try:
    from twisted.internet import ssl
    from twisted.internet._sslverify import ClientTLSOptions
    sslverify = True
except:
    sslverify = False

if sslverify:
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
    i16 = PngImagePlugin.i16
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
    0: "4:3 Letterbox",
    1: "4:3 PanScan",
    2: "16:9",
    3: "16:9 Always",
    4: "16:10 Letterbox",
    5: "16:10 PanScan",
    6: "16:9 Letterbox"
}

streamtypelist = ["1", "4097"]
vodstreamtypelist = ["4097"]

if os.path.exists("/usr/bin/gstplayer"):
    streamtypelist.append("5001")
    vodstreamtypelist.append("5001")


if os.path.exists("/usr/bin/exteplayer3"):
    streamtypelist.append("5002")
    vodstreamtypelist.append("5002")

if os.path.exists("/usr/bin/apt-get"):
    streamtypelist.append("8193")
    vodstreamtypelist.append("8193")


def clear_caches():
    try:
        os.system("echo 1 > /proc/sys/vm/drop_caches")
        os.system("echo 2 > /proc/sys/vm/drop_caches")
        os.system("echo 3 > /proc/sys/vm/drop_caches")
    except:
        pass


class IPTVInfoBarShowHide():
    STATE_HIDDEN = 0
    STATE_HIDING = 1
    STATE_SHOWING = 2
    STATE_SHOWN = 3
    FLAG_CENTER_DVB_SUBS = 2048
    skipToggleShow = False

    def __init__(self):
        self["ShowHideActions"] = ActionMap(["InfobarShowHideActions", "OKCancelActions"], {
            "ok": self.OkPressed,
            "toggleShow": self.OkPressed,
            "cancel": self.hide,
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
        if "state" in self and not self.force_show:
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
                if playstateString == ">":
                    statusicon_summary = 0
                    self.pvrStateDialog["statusicon"].setPixmapNum(statusicon_summary)

                elif playstateString == "||":
                    statusicon_summary = 1
                    self.pvrStateDialog["statusicon"].setPixmapNum(statusicon_summary)

                elif playstateString == "END":
                    statusicon_summary = 2
                    self.pvrStateDialog["statusicon"].setPixmapNum(statusicon_summary)

                elif playstateString.startswith(">>"):
                    speed = state[3].split()
                    statusicon_summary = 3
                    self.pvrStateDialog["statusicon"].setPixmapNum(statusicon_summary)
                    self.pvrStateDialog["speed"].setText(speed[1])
                    speedtext = speed[1]

                elif playstateString.startswith("<<"):
                    speed = state[3].split()
                    statusicon_summary = 4
                    self.pvrStateDialog["statusicon"].setPixmapNum(statusicon_summary)
                    self.pvrStateDialog["speed"].setText(speed[1])
                    speedtext = speed[1]

                elif playstateString.startswith("/"):
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


skin_path = os.path.join(skin_directory, cfg.skin.getValue())


class XStreamity_StreamPlayer(InfoBarBase, InfoBarMenu, InfoBarSeek, InfoBarAudioSelection, InfoBarMoviePlayerSummarySupport, InfoBarSubtitleSupport, InfoBarSummarySupport, InfoBarServiceErrorPopupSupport, InfoBarNotifications, IPTVInfoBarShowHide, IPTVInfoBarPVRState, Screen):
    ALLOW_SUSPEND = True

    def __init__(self, session, streamurl, servicetype, direct_source=None, stream_id=None):
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
        self.originalservicetype = self.servicetype
        self.direct_source = direct_source
        self.hasStreamData = False

        skin = os.path.join(skin_path, "streamplayer.xml")

        self["x_description"] = StaticText()
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
        self["picon"] = Pixmap()

        self["eventname"] = Label()
        self["state"] = Label()
        self["speed"] = Label()
        self["statusicon"] = MultiPixmap()

        self["PTSSeekBack"] = Pixmap()
        self["PTSSeekPointer"] = Pixmap()

        self.ar_id_player = 0

        with open(skin, "r") as f:
            self.skin = f.read()

        self.setup_title = _("TV")

        self["actions"] = ActionMap(["XStreamityActions"], {
            "cancel": self.back,
            "stop": self.back,
            "red": self.back,
            "channelUp": self.__next__,
            "down": self.__next__,
            "channelDown": self.prev,
            "up": self.prev,
            "tv": self.toggleStreamType,
            "info": self.toggleStreamType,
            "green": self.nextAR,
            "rec": self.IPTVstartInstantRecording,
            "0": self.restartStream
        }, -2)

        self.__event_tracker = ServiceEventTracker(
            screen=self,
            eventmap={
                iPlayableService.evStart: self.__evStart,
                iPlayableService.evTuneFailed: self.__evTuneFailed,
                iPlayableService.evUpdatedInfo: self.__evUpdatedInfo,
                iPlayableService.evEOF: self.__evEOF,
            },
        )

        self.streamcheck = 0

        self.onFirstExecBegin.append(boundFunction(self.playStream, self.servicetype, self.streamurl, self.direct_source))

    def restartStream(self):
        # print("*** restartStream ***")
        if self.session:
            self.session.nav.stopService()
            self.playStream(self.servicetype, self.streamurl, self.direct_source)
        else:
            return

    def refreshInfobar(self):
        # print("*** refreshInfobar ***")
        start = ""
        end = ""
        percent = 0

        if glob.currentepglist[glob.currentchannellistindex][2] != "":
            start = glob.currentepglist[glob.currentchannellistindex][2]

        if glob.currentepglist[glob.currentchannellistindex][5] != "":
            end = glob.currentepglist[glob.currentchannellistindex][5]

        if start != "" and end != "":
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

        current_hour = int(datetime.now().hour)
        current_minute = int(datetime.now().minute)
        next_time = str(glob.currentepglist[glob.currentchannellistindex][5])

        if next_time and ((current_hour >= int(next_time.split(":")[0]) and current_minute > int(next_time.split(":")[1])) or (current_hour > int(next_time.split(":")[0]) and current_minute >= int(next_time.split(":")[1]))):
            # print("*** updating short epg ***")
            response = ""

            player_api = str(glob.current_playlist["playlist_info"]["player_api"])
            stream_id = str(glob.currentchannellist[glob.currentchannellistindex][4])

            shortEPGJson = []

            url = player_api + "&action=get_short_epg&stream_id=" + str(stream_id) + "&limit=2"

            retries = Retry(total=3, backoff_factor=1)
            adapter = HTTPAdapter(max_retries=retries)
            http = requests.Session()
            http.mount("http://", adapter)
            http.mount("https://", adapter)
            response = ""
            try:
                r = http.get(url, headers=hdr, timeout=(10, 20), verify=False)
                r.raise_for_status()
                if r.status_code == requests.codes.ok:
                    try:
                        response = r.json()
                    except Exception as e:
                        print(e)

            except Exception as e:
                print(e)

            if response:
                shortEPGJson = response

                self.epgshortlist = []

                if "epg_listings" in shortEPGJson and shortEPGJson["epg_listings"]:
                    for listing in shortEPGJson["epg_listings"]:

                        title = ""
                        description = ""
                        start = ""

                        if "title" in listing:
                            title = base64.b64decode(listing["title"]).decode("utf-8")

                        if "description" in listing:
                            description = base64.b64decode(listing["description"]).decode("utf-8")

                        shift = 0

                        if "serveroffset" in glob.current_playlist["player_info"]:
                            shift = int(glob.current_playlist["player_info"]["serveroffset"])

                        if listing["start"] and listing["end"]:

                            start = listing["start"]
                            start_datetime = datetime.strptime(start, "%Y-%m-%d %H:%M:%S") + timedelta(hours=shift)

                        start_time = start_datetime.strftime("%H:%M")
                        self.epgshortlist.append([str(title), str(description), str(start_time)])

                    templist = list(glob.currentepglist[glob.currentchannellistindex])

                    templist[4] = str(self.epgshortlist[0][1])  # description
                    templist[3] = str(self.epgshortlist[0][0])  # title
                    templist[2] = str(self.epgshortlist[0][2])  # now start
                    templist[6] = str(self.epgshortlist[1][0])  # next title
                    templist[5] = str(self.epgshortlist[1][2])  # next start

                    glob.currentepglist[glob.currentchannellistindex] = tuple(templist)

                    self["progress"].setValue(0)

        self["x_description"].setText(glob.currentepglist[glob.currentchannellistindex][4])
        self["nowchannel"].setText(glob.currentchannellist[glob.currentchannellistindex][0])
        self["nowtitle"].setText(glob.currentepglist[glob.currentchannellistindex][3])
        self["nexttitle"].setText(glob.currentepglist[glob.currentchannellistindex][6])
        self["nowtime"].setText(glob.currentepglist[glob.currentchannellistindex][2])
        self["nexttime"].setText(glob.currentepglist[glob.currentchannellistindex][5])

    def IPTVstartInstantRecording(self, limitEvent=True):
        from . import record
        begin = int(time.time())
        end = begin + 3600

        if glob.currentepglist[glob.currentchannellistindex][3]:
            name = glob.currentepglist[glob.currentchannellistindex][3]
        else:
            name = glob.currentchannellist[glob.currentchannellistindex][0]

        self.name = NoSave(ConfigText(default=name, fixed_size=False))
        self.date = time.time()
        self.starttime = NoSave(ConfigClock(default=begin))
        self.endtime = NoSave(ConfigClock(default=end))
        self.session.openWithCallback(self.RecordDateInputClosed, record.RecordDateInput, self.name, self.date, self.starttime, self.endtime, True)

    def RecordDateInputClosed(self, ret=None):
        if ret:
            begin = ret[1]
            end = ret[2]
            name = ret[3]

            description = glob.currentepglist[glob.currentchannellistindex][4]
            eventid = int(self.streamurl.rpartition("/")[-1].partition(".")[0])
            serviceref = eServiceReference(1, 0, self.streamurl)

            if isinstance(serviceref, eServiceReference):
                serviceref = ServiceReference(serviceref)

            recording = RecordTimerEntry(serviceref, begin, end, name, description, eventid, dirname=str(cfg.downloadlocation.getValue()))
            recording.dontSave = True

            simulTimerList = self.session.nav.RecordTimer.record(recording)

            if simulTimerList is None:  # no conflict
                recording.autoincrease = False

                self.session.open(MessageBox, _("Recording Timer Set."), MessageBox.TYPE_INFO, timeout=5)
            else:
                self.session.open(MessageBox, _("Recording Failed."), MessageBox.TYPE_WARNING)
                return
        else:
            return

    def addRecentLiveList(self):
        # print("**** addrecentlivelist ***")
        if glob.adultChannel:
            return

        name = glob.originalChannelList2[glob.currentchannellistindex][1]
        stream_id = glob.originalChannelList2[glob.currentchannellistindex][2]
        stream_icon = glob.originalChannelList2[glob.currentchannellistindex][3]
        epg_channel_id = glob.originalChannelList2[glob.currentchannellistindex][4]
        added = glob.originalChannelList2[glob.currentchannellistindex][5]
        category_id = glob.originalChannelList2[glob.currentchannellistindex][6]
        custom_sid = glob.originalChannelList2[glob.currentchannellistindex][7]

        for recent in glob.current_playlist["player_info"]["liverecents"]:
            if stream_id == recent["stream_id"]:
                glob.current_playlist["player_info"]["liverecents"].remove(recent)
                break

        newrecent = {
            "name": name,
            "stream_id": stream_id,
            "stream_icon": stream_icon,
            "epg_channel_id": epg_channel_id,
            "added": added,
            "category_id": category_id,
            "custom_sid": custom_sid
        }

        glob.current_playlist["player_info"]["liverecents"].insert(0, newrecent)

        if len(glob.current_playlist["player_info"]["liverecents"]) >= 20:
            glob.current_playlist["player_info"]["liverecents"].pop(0)

        with open(playlists_json, "r") as f:
            try:
                self.playlists_all = json.load(f)
            except:
                os.remove(playlists_json)

        if self.playlists_all:
            x = 0
            for playlists in self.playlists_all:
                if playlists["playlist_info"]["domain"] == glob.current_playlist["playlist_info"]["domain"] and playlists["playlist_info"]["username"] == glob.current_playlist["playlist_info"]["username"] and playlists["playlist_info"]["password"] == glob.current_playlist["playlist_info"]["password"]:
                    self.playlists_all[x] = glob.current_playlist
                    break
                x += 1
        with open(playlists_json, "w") as f:
            json.dump(self.playlists_all, f)

    def playStream(self, servicetype, streamurl, direct_source):
        # print("*** playStream ***")

        self["streamcat"].setText("Live")
        self["streamtype"].setText(str(servicetype))

        try:
            self["extension"].setText(str(os.path.splitext(streamurl)[-1]))
        except:
            pass

        if glob.current_playlist["player_info"]["directsource"] == "Direct Source":
            if direct_source:
                streamurl = str(direct_source)

        self.reference = eServiceReference(int(self.servicetype), 0, streamurl)
        self.reference.setName(glob.currentchannellist[glob.currentchannellistindex][0])

        if self.session.nav.getCurrentlyPlayingServiceReference():
            if self.session.nav.getCurrentlyPlayingServiceReference().toString() != self.reference.toString():
                self.session.nav.stopService()

        self.session.nav.playService(self.reference)

        if self.session.nav.getCurrentlyPlayingServiceReference():
            glob.newPlayingServiceRef = self.session.nav.getCurrentlyPlayingServiceReference()
            glob.newPlayingServiceRefString = self.session.nav.getCurrentlyPlayingServiceReference().toString()

        if cfg.infobarpicons.value is True:
            self.downloadImage()

        self.refreshInfobar()

        self.timerrefresh = eTimer()
        try:
            self.timerrefresh.callback.append(self.refreshInfobar)
        except:
            self.timerrefresh_conn = self.timerrefresh.timeout.connect(self.refreshInfobar)
        self.timerrefresh.start(30000)

    def __evStart(self):
        if self.hasStreamData is False:
            self.timerstream = eTimer()
            try:
                self.timerstream.callback.append(self.checkStream)
            except:
                self.timerstream_conn = self.timerstream.timeout.connect(self.checkStream)
            self.timerstream.start(7000, True)
        else:
            try:
                self.timerstream.stop()
            except:
                pass

    def __evUpdatedInfo(self):
        # print("__evUpdatedInfo")
        self.originalservicetype = self.servicetype
        self.hasStreamData = True

        self.timerCache = eTimer()
        try:
            self.timerCache.stop()
        except:
            pass

        try:
            self.timerCache.callback.append(clear_caches)
        except:
            self.timerCache_conn = self.timerCache.timeout.connect(clear_caches)
        self.timerCache.start(600000, False)

        self.timerRecent = eTimer()

        try:
            self.timerRecent.callback.append(self.addRecentLiveList)
        except:
            self.timerRecent_conn = self.timerRecent.timeout.connect(self.addRecentLiveList)
        self.timerRecent.start(20000, True)

    def __evTuneFailed(self):
        self.hasStreamData = False
        try:
            self.session.nav.stopService()
        except:
            pass

    def __evEOF(self):
        self.hasStreamData = False
        try:
            self.session.nav.stopService()
        except:
            pass

    def checkStream(self):
        # print("checkStream")
        if self.hasStreamData is False:
            if self.streamcheck == 0:
                self.streamFailed()

            elif self.streamcheck == 1:
                self.streamTypeFailed()
            else:
                self.__evTuneFailed()

    def streamFailed(self, data=None):
        self.streamcheck = 1
        self.playStream(self.servicetype, self.streamurl, self.direct_source)

    def streamTypeFailed(self, data=None):
        if str(self.servicetype) == "1":
            self.servicetype = "4097"
        elif str(self.servicetype) == "4097":
            self.servicetype = "1"

        self.streamcheck = 2
        self.playStream(self.servicetype, self.streamurl, self.direct_source)

    def back(self):
        glob.nextlist[-1]["index"] = glob.currentchannellistindex

        try:
            self.timerCache.stop()
        except:
            pass

        self.close()

    def toggleStreamType(self):
        currentindex = 0
        self.streamcheck = 0
        self.hasStreamData = False
        for index, item in enumerate(streamtypelist, start=0):
            if str(item) == str(self.servicetype):
                currentindex = index
                break
        nextStreamType = islice(cycle(streamtypelist), currentindex + 1, None)
        self.servicetype = int(next(nextStreamType))
        self.playStream(self.servicetype, self.streamurl, self.direct_source)

    def downloadImage(self):
        self.loadBlankImage()
        try:
            os.remove(os.path.join(dir_tmp, "original.png"))
            os.remove(os.path.join(dir_tmp, "temp.png"))
        except:
            pass

        desc_image = ""
        try:
            desc_image = glob.currentchannellist[glob.currentchannellistindex][5]
        except:
            pass

        if desc_image and desc_image != "n/A":
            temp = os.path.join(dir_tmp, "temp.png")
            try:
                parsed = urlparse(desc_image)
                domain = parsed.hostname
                scheme = parsed.scheme

                if pythonVer == 3:
                    desc_image = desc_image.encode()

                if scheme == "https" and sslverify:
                    sniFactory = SNIFactory(domain)
                    downloadPage(desc_image, temp, sniFactory, timeout=5).addCallback(self.resizeImage).addErrback(self.loadDefaultImage)
                else:
                    downloadPage(desc_image, temp, timeout=5).addCallback(self.resizeImage).addErrback(self.loadDefaultImage)
            except:
                self.loadDefaultImage()
        else:
            self.loadDefaultImage()

    def loadBlankImage(self, data=None):
        if self["picon"].instance:
            self["picon"].instance.setPixmapFromFile(os.path.join(common_path, "picon_blank.png"))

    def loadDefaultImage(self, data=None):
        if self["picon"].instance:
            self["picon"].instance.setPixmapFromFile(os.path.join(common_path, "picon.png"))

    def resizeImage(self, data=None):
        original = os.path.join(dir_tmp, "temp.png")

        size = [147, 88]
        if screenwidth.width() > 1280:
            size = [220, 130]

        if os.path.exists(original):
            try:
                im = Image.open(original).convert("RGBA")
                try:
                    im.thumbnail(size, Image.Resampling.LANCZOS)
                except:
                    im.thumbnail(size, Image.ANTIALIAS)

                # crop and center image
                bg = Image.new("RGBA", size, (255, 255, 255, 0))

                imagew, imageh = im.size
                im_alpha = im.convert("RGBA").split()[-1]
                bgwidth, bgheight = bg.size
                bg_alpha = bg.convert("RGBA").split()[-1]
                temp = Image.new("L", (bgwidth, bgheight), 0)
                temp.paste(im_alpha, (int((bgwidth - imagew) / 2), int((bgheight - imageh) / 2)), im_alpha)
                bg_alpha = ImageChops.screen(bg_alpha, temp)
                bg.paste(im, (int((bgwidth - imagew) / 2), int((bgheight - imageh) / 2)))
                im = bg

                im.save(original, "PNG")

                if self["picon"].instance:
                    self["picon"].instance.setPixmapFromFile(original)

            except Exception as e:
                print("******* picon resize failed *******")
                print(e)
        else:
            self.loadDefaultImage()

    def __next__(self):
        self.servicetype = self.originalservicetype
        self.streamcheck = 0
        self.hasStreamData = False

        if glob.currentchannellist:
            listlength = len(glob.currentchannellist)
            glob.currentchannellistindex += 1
            if glob.currentchannellistindex + 1 > listlength:
                glob.currentchannellistindex = 0
            self.streamurl = glob.currentchannellist[glob.currentchannellistindex][3]
            self.direct_source = glob.currentchannellist[glob.currentchannellistindex][7]
            self.playStream(self.servicetype, self.streamurl, self.direct_source)

    def prev(self):
        self.servicetype = self.originalservicetype
        self.streamcheck = 0
        self.hasStreamData = False

        if glob.currentchannellist:
            listlength = len(glob.currentchannellist)
            glob.currentchannellistindex -= 1
            if glob.currentchannellistindex + 1 == 0:
                glob.currentchannellistindex = listlength - 1

            self.streamurl = glob.currentchannellist[glob.currentchannellistindex][3]
            self.direct_source = glob.currentchannellist[glob.currentchannellistindex][7]
            self.playStream(self.servicetype, self.streamurl, self.direct_source)

    def nextARfunction(self):
        try:
            self.ar_id_player += 1
            if self.ar_id_player > 6:
                self.ar_id_player = 0
            try:
                iAVSwitch.setAspectRatio(self.ar_id_player)
            except:
                eAVSwitch.getInstance().setAspectRatio(self.ar_id_player)

            return VIDEO_ASPECT_RATIO_MAP[self.ar_id_player]
        except Exception as e:
            print(e)
            return "nextAR ERROR %s" % e

    def nextAR(self):
        message = self.nextARfunction()
        self.session.open(MessageBox, message, type=MessageBox.TYPE_INFO, timeout=3)


class XStreamityCueSheetSupport:
    ENABLE_RESUME_SUPPORT = False

    def __init__(self):
        self.cut_list = []
        self.is_closing = False
        self.started = False
        self.resume_point = ""
        if not os.path.exists("/etc/enigma2/xstreamity/resumepoints.pkl"):
            with open("/etc/enigma2/xstreamity/resumepoints.pkl", "w"):
                pass

        self.__event_tracker = ServiceEventTracker(screen=self, eventmap={
            iPlayableService.evUpdatedInfo: self.__serviceStarted,
        })

    def __serviceStarted(self):
        if self.is_closing:
            return

        if self.ENABLE_RESUME_SUPPORT and not self.started:

            self.started = True
            last = None

            service = self.session.nav.getCurrentService()

            if service is None:
                return

            seekable = service.seek()
            if seekable is None:
                return  # Should not happen?

            length = seekable.getLength() or (None, 0)
            length[1] = abs(length[1])

            try:
                last = getResumePoint(self.session)
            except Exception as e:
                print(e)
                return

            if last is None:
                return
            if (last > 900000) and (not length[1] or (last < length[1] - 900000)):
                self.resume_point = last
                newlast = last // 90000
                Notifications.AddNotificationWithCallback(self.playLastCB, MessageBox, _("Do you want to resume this playback?") + "\n" + (_("Resume position at %s") % ("%d:%02d:%02d" % (newlast // 3600, newlast % 3600 // 60, newlast % 60))), MessageBox.TYPE_YESNO, 10)

    def playLastCB(self, answer):
        if answer is True and self.resume_point:
            service = self.session.nav.getCurrentService()
            seekable = service.seek()
            if seekable is not None:
                seekable.seekTo(self.resume_point)
        self.hideAfterResume()

    def hideAfterResume(self):
        if isinstance(self, IPTVInfoBarShowHide):
            try:
                self.hide()
            except Exception as e:
                print(e)


class XStreamity_VodPlayer(InfoBarBase, InfoBarMenu, InfoBarSeek, InfoBarAudioSelection, InfoBarMoviePlayerSummarySupport, InfoBarSubtitleSupport, InfoBarSummarySupport, InfoBarServiceErrorPopupSupport, InfoBarNotifications, IPTVInfoBarShowHide, IPTVInfoBarPVRState, XStreamityCueSheetSupport, SubsSupportStatus, SubsSupport, Screen):

    ENABLE_RESUME_SUPPORT = True
    ALLOW_SUSPEND = True

    def __init__(self, session, streamurl, servicetype, direct_source=None, stream_id=None):
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

        try:
            XStreamityCueSheetSupport.__init__(self)
        except Exception as e:
            print(e)

        IPTVInfoBarPVRState.__init__(self, PVRState, True)

        if cfg.subs.value is True:
            SubsSupport.__init__(self, searchSupport=True, embeddedSupport=True)
            SubsSupportStatus.__init__(self)

        self.streamurl = streamurl
        self.servicetype = servicetype
        self.direct_source = direct_source
        self.stream_id = stream_id

        skin = os.path.join(skin_path, "vodplayer.xml")

        self["streamcat"] = StaticText()
        self["streamtype"] = StaticText()
        self["extension"] = StaticText()

        self.PicLoad = ePicLoad()
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

        with open(skin, "r") as f:
            self.skin = f.read()

        self.setup_title = _("VOD")

        self["actions"] = ActionMap(["XStreamityActions"], {
            "cancel": self.back,
            "stop": self.back,
            "red": self.back,
            "tv": self.toggleStreamType,
            "info": self.toggleStreamType,
            "green": self.nextAR,
        }, -2)

        self.onFirstExecBegin.append(boundFunction(self.playStream, self.servicetype, self.streamurl, self.direct_source))

    def addRecentVodList(self):
        # print("**** addrecentvodlist ***")
        name = glob.originalChannelList2[glob.currentchannellistindex][1]
        stream_id = glob.originalChannelList2[glob.currentchannellistindex][2]
        stream_icon = glob.originalChannelList2[glob.currentchannellistindex][3]
        added = glob.originalChannelList2[glob.currentchannellistindex][4]
        rating = glob.originalChannelList2[glob.currentchannellistindex][5]
        container_extension = glob.originalChannelList2[glob.currentchannellistindex][8]

        for recent in glob.current_playlist["player_info"]["vodrecents"]:
            if stream_id == recent["stream_id"]:
                glob.current_playlist["player_info"]["vodrecents"].remove(recent)
                break

        newrecent = {
            "name": name,
            "stream_id": stream_id,
            "stream_icon": stream_icon,
            "added": added,
            "rating": rating,
            "container_extension": container_extension
        }

        glob.current_playlist["player_info"]["vodrecents"].insert(0, newrecent)

        if len(glob.current_playlist["player_info"]["vodrecents"]) >= 20:
            glob.current_playlist["player_info"]["vodrecents"].pop(0)

        with open(playlists_json, "r") as f:
            try:
                self.playlists_all = json.load(f)
            except:
                os.remove(playlists_json)

        if self.playlists_all:
            x = 0
            for playlists in self.playlists_all:
                if playlists["playlist_info"]["domain"] == glob.current_playlist["playlist_info"]["domain"] and playlists["playlist_info"]["username"] == glob.current_playlist["playlist_info"]["username"] and playlists["playlist_info"]["password"] == glob.current_playlist["playlist_info"]["password"]:
                    self.playlists_all[x] = glob.current_playlist
                    break
                x += 1
        with open(playlists_json, "w") as f:
            json.dump(self.playlists_all, f)

    def addWatchedList(self):
        stream_id = self.stream_id

        if glob.categoryname == "vod":

            if stream_id not in glob.current_playlist["player_info"]["vodwatched"]:
                glob.current_playlist["player_info"]["vodwatched"].append(stream_id)

        elif glob.categoryname == "series":

            if stream_id not in glob.current_playlist["player_info"]["serieswatched"]:
                glob.current_playlist["player_info"]["serieswatched"].append(stream_id)

        with open(playlists_json, "r") as f:
            try:
                self.playlists_all = json.load(f)
            except:
                os.remove(playlists_json)

        if self.playlists_all:
            x = 0
            for playlists in self.playlists_all:
                if playlists["playlist_info"]["domain"] == glob.current_playlist["playlist_info"]["domain"] and playlists["playlist_info"]["username"] == glob.current_playlist["playlist_info"]["username"] and playlists["playlist_info"]["password"] == glob.current_playlist["playlist_info"]["password"]:
                    self.playlists_all[x] = glob.current_playlist
                    break
                x += 1
        with open(playlists_json, "w") as f:
            json.dump(self.playlists_all, f)

    def playStream(self, servicetype, streamurl, direct_source):

        if cfg.infobarcovers.value is True:
            self.downloadImage()

        if glob.categoryname == "vod":
            self["streamcat"].setText("VOD")
        else:
            self["streamcat"].setText("Series")
        self["streamtype"].setText(str(servicetype))

        try:
            self["extension"].setText(str(os.path.splitext(streamurl)[-1]))
        except:
            pass

        if glob.current_playlist["player_info"]["directsource"] == "Direct Source":
            if direct_source:
                streamurl = direct_source

        self.reference = eServiceReference(int(self.servicetype), 0, streamurl)
        self.reference.setName(glob.currentchannellist[glob.currentchannellistindex][0])

        if self.session.nav.getCurrentlyPlayingServiceReference():
            if self.session.nav.getCurrentlyPlayingServiceReference().toString() != self.reference.toString():

                try:
                    self.session.nav.stopService()
                except:
                    pass

                self.session.nav.playService(self.reference)

        else:
            self.session.nav.playService(self.reference)

        if self.session.nav.getCurrentlyPlayingServiceReference():
            glob.newPlayingServiceRef = self.session.nav.getCurrentlyPlayingServiceReference()
            glob.newPlayingServiceRefString = self.session.nav.getCurrentlyPlayingServiceReference().toString()

            self.timerCache = eTimer()
            try:
                self.timerCache.callback.append(clear_caches)
            except:
                self.timerCache_conn = self.timerCache.timeout.connect(clear_caches)
            self.timerCache.start(60000, False)

            if glob.categoryname == "vod":
                self.timerRecent = eTimer()
                try:
                    self.timerRecent.callback.append(self.addRecentVodList)
                except:
                    self.timerRecent_conn = self.timerRecent.timeout.connect(self.addRecentVodList)
                self.timerRecent.start(20000, True)

            self.timerWatched = eTimer()
            try:
                self.timerWatched.callback.append(self.addWatchedList)
            except:
                self.timerWatched_conn = self.timerWatched.timeout.connect(self.addWatchedList)
            self.timerWatched.start(15000, True)

    def downloadImage(self):
        self.loadBlankImage()
        try:
            os.remove(os.path.join(dir_tmp, "original.jpg"))
            os.remove(os.path.join(dir_tmp, "temp.jpg"))
        except:
            pass

        desc_image = ""

        desc_image = glob.currentchannellist[glob.currentchannellistindex][5]

        if desc_image and desc_image != "n/A":
            temp = os.path.join(dir_tmp, "temp.jpg")
            try:
                parsed = urlparse(desc_image)
                domain = parsed.hostname
                scheme = parsed.scheme

                if pythonVer == 3:
                    desc_image = desc_image.encode()

                if scheme == "https" and sslverify:
                    sniFactory = SNIFactory(domain)
                    downloadPage(desc_image, temp, sniFactory, timeout=5).addCallback(self.resizeImage).addErrback(self.loadDefaultImage)
                else:
                    downloadPage(desc_image, temp, timeout=5).addCallback(self.resizeImage).addErrback(self.loadDefaultImage)
            except:
                self.loadDefaultImage()
        else:
            self.loadDefaultImage()

    def loadBlankImage(self, data=None):
        if self["cover"].instance:
            self["cover"].instance.setPixmapFromFile(os.path.join(skin_path, "images/vod_blank.png"))

    def loadDefaultImage(self, data=None):
        if self["cover"].instance:
            self["cover"].instance.setPixmapFromFile(os.path.join(skin_path, "images/vod_cover_small.png"))

    def resizeImage(self, data=None):
        if self["cover"].instance:
            preview = os.path.join(dir_tmp, "temp.jpg")

            width = 147
            height = 220
            if screenwidth.width() > 1280:
                width = 220
                height = 330

            self.PicLoad.setPara([width, height, 1, 1, 0, 1, "FF000000"])

            if self.PicLoad.startDecode(preview):
                # if this has failed, then another decode is probably already in progress
                # throw away the old picload and try again immediately
                self.PicLoad = ePicLoad()
                try:
                    self.PicLoad.PictureData.get().append(self.DecodePicture)
                except:
                    self.PicLoad_conn = self.PicLoad.PictureData.connect(self.DecodePicture)
                self.PicLoad.setPara([width, height, 1, 1, 0, 1, "FF000000"])
                self.PicLoad.startDecode(preview)

    def DecodePicture(self, PicInfo=None):
        ptr = self.PicLoad.getData()
        if ptr is not None:
            self["cover"].instance.setPixmap(ptr)
            self["cover"].instance.show()

    def back(self):
        glob.nextlist[-1]["index"] = glob.currentchannellistindex
        try:
            setResumePoint(self.session)
        except Exception as e:
            print(e)

        try:
            self.timerCache.stop()
        except:
            pass

        self.close()

    def toggleStreamType(self):
        currentindex = 0

        for index, item in enumerate(vodstreamtypelist, start=0):
            if str(item) == str(self.servicetype):
                currentindex = index
                break
        nextStreamType = islice(cycle(vodstreamtypelist), currentindex + 1, None)
        try:
            self.servicetype = int(next(nextStreamType))
        except:
            pass

        self.playStream(self.servicetype, self.streamurl, self.direct_source)

    def nextARfunction(self):
        try:
            self.ar_id_player += 1
            if self.ar_id_player > 6:
                self.ar_id_player = 0
            try:
                iAVSwitch.setAspectRatio(self.ar_id_player)
            except:
                eAVSwitch.getInstance().setAspectRatio(self.ar_id_player)

            return VIDEO_ASPECT_RATIO_MAP[self.ar_id_player]
        except Exception as e:
            print(e)
            return "nextAR ERROR %s" % e

    def nextAR(self):
        message = self.nextARfunction()
        self.session.open(MessageBox, message, type=MessageBox.TYPE_INFO, timeout=3)


class XStreamity_CatchupPlayer(InfoBarBase, InfoBarMenu, InfoBarSeek, InfoBarAudioSelection, InfoBarMoviePlayerSummarySupport, InfoBarSubtitleSupport, InfoBarSummarySupport, InfoBarServiceErrorPopupSupport, InfoBarNotifications, IPTVInfoBarShowHide, IPTVInfoBarPVRState, XStreamityCueSheetSupport, SubsSupportStatus, SubsSupport, Screen):

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

        try:
            XStreamityCueSheetSupport.__init__(self)
        except:
            pass

        IPTVInfoBarPVRState.__init__(self, PVRState, True)

        if cfg.subs.value is True:
            SubsSupport.__init__(self, searchSupport=True, embeddedSupport=True)
            SubsSupportStatus.__init__(self)

        self.streamurl = streamurl
        self.servicetype = servicetype

        skin = os.path.join(skin_path, "catchupplayer.xml")

        self["x_description"] = StaticText()
        self["streamcat"] = StaticText()
        self["streamtype"] = StaticText()
        self["extension"] = StaticText()
        self["picon"] = Pixmap()

        self["eventname"] = Label()
        self["state"] = Label()
        self["speed"] = Label()
        self["statusicon"] = MultiPixmap()

        self["PTSSeekBack"] = Pixmap()
        self["PTSSeekPointer"] = Pixmap()

        self.ar_id_player = 0

        with open(skin, "r") as f:
            self.skin = f.read()

        self.setup_title = _("Catch Up")

        self["actions"] = ActionMap(["XStreamityActions"], {
            "cancel": self.back,
            "red": self.back,
            "stop": self.back,
            "tv": self.toggleStreamType,
            "info": self.toggleStreamType,
            "green": self.nextAR,
        }, -2)

        self.onFirstExecBegin.append(boundFunction(self.playStream, self.servicetype, self.streamurl))

    def playStream(self, servicetype, streamurl):
        if cfg.infobarpicons.value is True:
            self.downloadImage()

        self["x_description"].setText(glob.catchupdata[1])
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

            self.timerCache = eTimer()
            try:
                self.timerCache.callback.append(clear_caches)
            except:
                self.timerCache_conn = self.timerCache.timeout.connect(clear_caches)
            self.timerCache.start(60000, False)

    def downloadImage(self):
        self.loadBlankImage()
        try:
            os.remove(os.path.join(dir_tmp, "original.png"))
            os.remove(os.path.join(dir_tmp, "temp.png"))
        except:
            pass

        try:
            desc_image = glob.currentchannellist[glob.currentchannellistindex][5]
        except:
            pass
            desc_image = ""

        if desc_image and desc_image != "n/A":
            temp = os.path.join(dir_tmp, "temp.png")
            try:
                parsed = urlparse(desc_image)
                domain = parsed.hostname
                scheme = parsed.scheme

                if pythonVer == 3:
                    desc_image = desc_image.encode()

                if scheme == "https" and sslverify:
                    sniFactory = SNIFactory(domain)
                    downloadPage(desc_image, temp, sniFactory, timeout=5).addCallback(self.resizeImage).addErrback(self.loadDefaultImage)
                else:
                    downloadPage(desc_image, temp, timeout=5).addCallback(self.resizeImage).addErrback(self.loadDefaultImage)
            except:
                self.loadDefaultImage()
        else:
            self.loadDefaultImage()

    def loadBlankImage(self, data=None):
        if self["picon"].instance:
            self["picon"].instance.setPixmapFromFile(os.path.join(common_path, "picon_blank.png"))

    def loadDefaultImage(self, data=None):
        if self["picon"].instance:
            self["picon"].instance.setPixmapFromFile(os.path.join(common_path, "picon.png"))

    def resizeImage(self, data=None):
        # print("*** resizeImage ***")
        original = os.path.join(dir_tmp, "temp.png")

        size = [147, 88]
        if screenwidth.width() > 1280:
            size = [220, 130]

        if os.path.exists(original):
            try:
                im = Image.open(original).convert("RGBA")
                try:
                    im.thumbnail(size, Image.Resampling.LANCZOS)
                except:
                    im.thumbnail(size, Image.ANTIALIAS)

                # crop and center image
                bg = Image.new("RGBA", size, (255, 255, 255, 0))

                imagew, imageh = im.size
                im_alpha = im.convert("RGBA").split()[-1]
                bgwidth, bgheight = bg.size
                bg_alpha = bg.convert("RGBA").split()[-1]
                temp = Image.new("L", (bgwidth, bgheight), 0)
                temp.paste(im_alpha, (int((bgwidth - imagew) / 2), int((bgheight - imageh) / 2)), im_alpha)
                bg_alpha = ImageChops.screen(bg_alpha, temp)
                bg.paste(im, (int((bgwidth - imagew) / 2), int((bgheight - imageh) / 2)))
                im = bg

                im.save(original, "PNG")

                if self["picon"].instance:
                    self["picon"].instance.setPixmapFromFile(original)

            except Exception as e:
                print("******* picon resize failed *******")
                print(e)
        else:
            self.loadDefaultImage()

    def back(self):
        glob.nextlist[-1]["index"] = glob.currentchannellistindex
        try:
            setResumePoint(self.session)
        except Exception as e:
            print(e)

        try:
            self.timerCache.stop()
        except:
            pass

        try:
            self.session.nav.stopService()
        except:
            pass

        self.close()

    def toggleStreamType(self):
        currentindex = 0

        for index, item in enumerate(vodstreamtypelist, start=0):
            if str(item) == str(self.servicetype):
                currentindex = index
                break
        nextStreamType = islice(cycle(vodstreamtypelist), currentindex + 1, None)
        self.servicetype = int(next(nextStreamType))
        self.playStream(self.servicetype, self.streamurl)

    def nextARfunction(self):
        try:
            self.ar_id_player += 1
            if self.ar_id_player > 6:
                self.ar_id_player = 0
            try:
                eAVSwitch.getInstance().setAspectRatio(self.ar_id_player)
            except:
                iAVSwitch.setAspectRatio(self.ar_id_player)
            return VIDEO_ASPECT_RATIO_MAP[self.ar_id_player]
        except Exception as e:
            print(e)
            return "nextAR ERROR %s" % e

    def nextAR(self):
        message = self.nextARfunction()
        self.session.open(MessageBox, message, type=MessageBox.TYPE_INFO, timeout=3)
