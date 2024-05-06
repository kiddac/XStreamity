#!/usr/bin/python
# -*- coding: utf-8 -*-

from __future__ import absolute_import, print_function
from __future__ import division

import base64
import json
import os
import re
import time
from datetime import datetime, timedelta
from itertools import cycle, islice

from PIL import Image, ImageFile, PngImagePlugin
from . import _
from . import xstreamity_globals as glob
from .plugin import cfg, common_path, dir_tmp, hdr, playlists_json, pythonVer, screenwidth, skin_directory
from .xStaticText import StaticText

from Components.ActionMap import ActionMap
from Components.Label import Label
from Components.ProgressBar import ProgressBar
from Components.Pixmap import MultiPixmap, Pixmap
from Components.ServiceEventTracker import ServiceEventTracker, InfoBarBase
from Components.config import ConfigClock, ConfigText, NoSave
from enigma import eTimer, eServiceReference, iPlayableService, ePicLoad
from RecordTimer import RecordTimerEntry


from Screens.InfoBarGenerics import InfoBarSeek, InfoBarAudioSelection, InfoBarSummarySupport, InfoBarMoviePlayerSummarySupport, InfoBarSubtitleSupport


from Screens.MessageBox import MessageBox
from Screens.Screen import Screen
from ServiceReference import ServiceReference
from Tools.BoundFunction import boundFunction
from Tools import Notifications

from twisted.web.client import downloadPage

try:
    from urlparse import urlparse
except ImportError:
    from urllib.parse import urlparse

try:
    from enigma import eAVSwitch
except Exception:
    from enigma import eAVControl as eAVSwitch

try:
    from http.client import HTTPConnection
    HTTPConnection.debuglevel = 0
except ImportError:
    from httplib import HTTPConnection
    HTTPConnection.debuglevel = 0

try:
    from .resumepoints import setResumePoint, getResumePoint
except ImportError as e:
    print(e)

import requests
from requests.adapters import HTTPAdapter, Retry

if cfg.subs.value is True:
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
        with open("/proc/sys/vm/drop_caches", "w") as drop_caches:
            drop_caches.write("1\n2\n3\n")
    except IOError:
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
        self.hideTimer.start(3000, True)

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
            self.doShow()

    def startHideTimer(self):
        if self.__state == self.STATE_SHOWN and not self.__locked:
            self.hideTimer.stop()
            self.hideTimer.start(3000, True)

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


class PVRState2(Screen):
    def __init__(self, session):
        Screen.__init__(self, session)
        self["eventname"] = Label()
        self["state"] = Label()
        self["speed"] = Label()
        self["statusicon"] = MultiPixmap()


PVRState = PVRState2


class InfoBarMoviePlayerSummary(Screen):
    skin = """
    <screen position="0,0" size="132,64">
        <widget source="global.CurrentTime" render="Label" position="62,46" size="64,18" font="Regular;16" halign="right" >
            <convert type="ClockToText">WithSeconds</convert>
        </widget>
        <widget source="session.RecordState" render="FixedLabel" text=" " position="62,46" size="64,18" zPosition="1" >
            <convert type="ConfigEntryTest">config.usage.blinking_display_clock_during_recording,True,CheckSourceBoolean</convert>
            <convert type="ConditionalShowHide">Blink</convert>
        </widget>
        <widget source="session.CurrentService" render="Label" position="6,4" size="120,42" font="Regular;18" >
            <convert type="ServiceName">Name</convert>
        </widget>
        <widget source="session.CurrentService" render="Progress" position="6,46" size="56,18" borderWidth="1" >
            <convert type="ServicePosition">Position</convert>
        </widget>
    </screen>"""

    def __init__(self, session, parent):
        Screen.__init__(self, session, parent=parent)
        self["state_summary"] = StaticText("")
        self["speed_summary"] = StaticText("")
        self["statusicon_summary"] = MultiPixmap()
        self.onShow.append(self.addWatcher)
        self.onHide.append(self.removeWatcher)

    def addWatcher(self):
        self.parent.onChangedEntry.append(self.selectionChanged)

    def removeWatcher(self):
        self.parent.onChangedEntry.remove(self.selectionChanged)

    def selectionChanged(self, state_summary, speed_summary, statusicon_summary):
        self["state_summary"].setText(state_summary)
        self["speed_summary"].setText(speed_summary)
        self["statusicon_summary"].setPixmapNum(int(statusicon_summary))


class IPTVInfoBarPVRState:
    def __init__(self, screen=PVRState, force_show=True):
        self.onChangedEntry = []
        self.onPlayStateChanged.append(self.__playStateChanged)
        self.pvrStateDialog = self.session.instantiateDialog(screen)
        self.onShow.append(self._mayShow)
        self.onHide.append(self.pvrStateDialog.hide)
        self.force_show = force_show

    def createSummary(self):
        return InfoBarMoviePlayerSummary

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


skin_path = os.path.join(skin_directory, cfg.skin.value)


class XStreamity_StreamPlayer(
    InfoBarBase,
    IPTVInfoBarShowHide,
    IPTVInfoBarPVRState,
    InfoBarAudioSelection,
    InfoBarSeek,
    InfoBarSummarySupport,
    InfoBarSubtitleSupport,
    InfoBarMoviePlayerSummarySupport,
        Screen):

    ALLOW_SUSPEND = True

    def __init__(self, session, streamurl, servicetype, direct_source=None, stream_id=None):
        Screen.__init__(self, session)
        self.session = session

        if str(os.path.splitext(streamurl)[-1]) == ".m3u8" and servicetype == "1":
            servicetype = "4097"

        for x in (
            InfoBarBase,
            IPTVInfoBarShowHide,
            InfoBarAudioSelection,
            InfoBarSeek,
            InfoBarSummarySupport,
            InfoBarSubtitleSupport,
            InfoBarMoviePlayerSummarySupport
        ):
            x.__init__(self)

        IPTVInfoBarPVRState.__init__(self, PVRState, True)

        self.streamurl = streamurl
        self.servicetype = servicetype
        self.originalservicetype = self.servicetype
        self.direct_source = direct_source

        skin = os.path.join(skin_path, "streamplayer.xml")
        with open(skin, "r") as f:
            self.skin = f.read()

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
        self["PTSSeekBack"] = Pixmap()
        self["PTSSeekPointer"] = Pixmap()

        self["eventname"] = Label()
        self["state"] = Label()
        self["speed"] = Label()
        self["statusicon"] = MultiPixmap()

        self.ar_id_player = 0

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
            "0": self.restartStream,
            "ok": self.refreshInfobar,
        }, -2)

        self.__event_tracker = ServiceEventTracker(
            screen=self,
            eventmap={
                iPlayableService.evUpdatedInfo: self.__evUpdatedInfo,
            },
        )

        self.streamcheck = 0

        self.onFirstExecBegin.append(boundFunction(self.playStream, self.servicetype, self.streamurl, self.direct_source))

    def restartStream(self):
        if self.session:
            self.session.nav.stopService()
            self.playStream(self.servicetype, self.streamurl, self.direct_source)

    def refreshInfobar(self):
        start = glob.currentepglist[glob.currentchannellistindex][2]
        end = glob.currentepglist[glob.currentchannellistindex][5]
        percent = 0

        if start and end:
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
            try:
                player_api = str(glob.active_playlist["playlist_info"]["player_api"])
                stream_id = str(glob.currentchannellist[glob.currentchannellistindex][4])

                shortEPGJson = []
                url = player_api + "&action=get_short_epg&stream_id=" + str(stream_id) + "&limit=2"

                retries = Retry(total=3, backoff_factor=1)
                adapter = HTTPAdapter(max_retries=retries)
                http = requests.Session()
                http.mount("http://", adapter)
                http.mount("https://", adapter)

                r = http.get(url, headers=hdr, timeout=(10, 20), verify=False)
                r.raise_for_status()
                if r.status_code == requests.codes.ok:
                    response = r.json()
                    shortEPGJson = response.get("epg_listings", [])

                if shortEPGJson and len(shortEPGJson) > 1:
                    self.epgshortlist = []
                    for listing in shortEPGJson:
                        title = base64.b64decode(listing.get("title", "")).decode("utf-8")
                        description = base64.b64decode(listing.get("description", "")).decode("utf-8")
                        shift = int(glob.active_playlist["player_info"].get("serveroffset", 0))
                        start = listing.get("start", "")
                        end = listing.get("end", "")
                        if start and end:
                            time_formats = ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H-%M-%S", "%Y-%m-%d-%H:%M:%S", "%Y- %m-%d %H:%M:%S"]
                            for time_format in time_formats:
                                try:
                                    start_datetime = datetime.strptime(start, time_format) + timedelta(hours=shift)
                                    start_time = start_datetime.strftime("%H:%M")
                                    self.epgshortlist.append([str(title), str(description), str(start_time)])
                                    break
                                except ValueError:
                                    pass

                    templist = list(glob.currentepglist[glob.currentchannellistindex])
                    if self.epgshortlist:
                        templist[4] = str(self.epgshortlist[0][1])  # description
                        templist[3] = str(self.epgshortlist[0][0])  # title
                        templist[2] = str(self.epgshortlist[0][2])  # now start
                        templist[6] = str(self.epgshortlist[1][0])  # next title
                        templist[5] = str(self.epgshortlist[1][2])  # next start

                    glob.currentepglist[glob.currentchannellistindex] = tuple(templist)
                    self["progress"].setValue(0)
            except Exception as e:
                print("Error during short EPG update:", e)

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
        dt_now = datetime.now()

        current_channel = glob.currentepglist[glob.currentchannellistindex]
        if current_channel[3]:
            name = current_channel[3]
        else:
            name = glob.currentchannellist[glob.currentchannellistindex][0]

        if current_channel[5]:
            endstring = current_channel[5]
            end_dt = datetime.strptime(str(endstring), "%H:%M")
            end_dt = end_dt.replace(year=dt_now.year, month=dt_now.month, day=dt_now.day)
            end = int(time.mktime(end_dt.timetuple()))

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

            recording = RecordTimerEntry(
                serviceref, begin, end, name, description, eventid, dirname=str(cfg.downloadlocation.value)
            )
            recording.dontSave = True

            simulTimerList = self.session.nav.RecordTimer.record(recording)

            if simulTimerList is None:  # no conflict
                recording.autoincrease = False

                self.session.open(MessageBox, _("Recording Timer Set."), MessageBox.TYPE_INFO, timeout=5)
            else:
                self.session.open(MessageBox, _("Recording Failed."), MessageBox.TYPE_WARNING)
        else:
            return

    def addRecentLiveList(self):
        if glob.adultChannel:
            return

        name = glob.originalChannelList2[glob.currentchannellistindex][1]
        stream_id = glob.originalChannelList2[glob.currentchannellistindex][2]
        stream_icon = glob.originalChannelList2[glob.currentchannellistindex][3]
        epg_channel_id = glob.originalChannelList2[glob.currentchannellistindex][4]
        added = glob.originalChannelList2[glob.currentchannellistindex][5]
        category_id = glob.originalChannelList2[glob.currentchannellistindex][6]
        custom_sid = glob.originalChannelList2[glob.currentchannellistindex][7]

        # Remove existing entry if stream_id matches
        recent_entries = glob.active_playlist["player_info"]["liverecents"]
        recent_entries[:] = [recent for recent in recent_entries if recent["stream_id"] != stream_id]

        new_recent = {
            "name": name,
            "stream_id": stream_id,
            "stream_icon": stream_icon,
            "epg_channel_id": epg_channel_id,
            "added": added,
            "category_id": category_id,
            "custom_sid": custom_sid
        }

        recent_entries.insert(0, new_recent)

        if len(recent_entries) >= 20:
            recent_entries.pop()

        if os.path.exists(playlists_json):
            with open(playlists_json, "r") as f:
                try:
                    self.playlists_all = json.load(f)
                except:
                    os.remove(playlists_json)

            if self.playlists_all:
                for index, playlist in enumerate(self.playlists_all):
                    if playlist["playlist_info"] == glob.active_playlist["playlist_info"]:
                        self.playlists_all[index] = glob.active_playlist
                        break

        with open(playlists_json, "w") as f:
            json.dump(self.playlists_all, f)

    def playStream(self, servicetype, streamurl, direct_source):
        self["streamcat"].setText("Live")
        self["streamtype"].setText(str(servicetype))

        try:
            self["extension"].setText(str(os.path.splitext(streamurl)[-1]))
        except:
            pass

        streamurl = direct_source if glob.active_playlist["player_info"]["directsource"] == "Direct Source" and direct_source else streamurl

        self.reference = eServiceReference(int(servicetype), 0, streamurl)
        self.reference.setName(glob.currentchannellist[glob.currentchannellistindex][0])

        currently_playing_ref = self.session.nav.getCurrentlyPlayingServiceReference()
        if currently_playing_ref and currently_playing_ref.toString() != self.reference.toString():
            self.session.nav.stopService()

        self.session.nav.playService(self.reference)

        currently_playing_ref = self.session.nav.getCurrentlyPlayingServiceReference()
        if currently_playing_ref:
            glob.newPlayingServiceRef = currently_playing_ref
            glob.newPlayingServiceRefString = currently_playing_ref.toString()
        if cfg.infobarpicons.value is True:
            self.downloadImage()

        self.refreshInfobar()

        self.timerrefresh = eTimer()
        try:
            self.timerrefresh.callback.append(self.refreshInfobar)
        except:
            self.timerrefresh_conn = self.timerrefresh.timeout.connect(self.refreshInfobar)

        self.timerrefresh.start(5 * 60 * 1000, False)

    def __evUpdatedInfo(self):
        self.originalservicetype = self.servicetype

        self.timerCache = eTimer()
        try:
            self.timerCache.stop()
        except:
            pass

        try:
            self.timerCache.callback.append(clear_caches)
        except:
            self.timerCache_conn = self.timerCache.timeout.connect(clear_caches)
        self.timerCache.start(5 * 60 * 1000, False)

        self.timerRecent = eTimer()

        try:
            self.timerRecent.callback.append(self.addRecentLiveList)
        except:
            self.timerRecent_conn = self.timerRecent.timeout.connect(self.addRecentLiveList)
        self.timerRecent.start(30 * 1000, True)

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
        current_index = 0
        self.streamcheck = 0
        for index, item in enumerate(streamtypelist):
            if str(item) == str(self.servicetype):
                current_index = index
                break
        next_stream_type = islice(cycle(streamtypelist), current_index + 1, None)
        try:
            self.servicetype = int(next(next_stream_type))
        except:
            pass
        self.playStream(self.servicetype, self.streamurl, self.direct_source)

    def downloadImage(self):
        self.loadDefaultImage()
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

    def loadDefaultImage(self, data=None):
        if self["picon"].instance:
            self["picon"].instance.setPixmapFromFile(os.path.join(common_path, "picon.png"))

    def resizeImage(self, data=None):
        # print("*** resizeImage ***")
        original = os.path.join(dir_tmp, "temp.png")

        # Determine the target size based on screen width
        if screenwidth.width() == 2560:
            size = [294, 176]
        elif screenwidth.width() > 1280:
            size = [220, 130]
        else:
            size = [147, 88]

        if os.path.exists(original):
            try:
                im = Image.open(original)

                # Convert to RGBA if not already
                if im.mode != "RGBA":
                    im = im.convert("RGBA")
                try:
                    im.thumbnail(size, Image.Resampling.LANCZOS)
                except:
                    im.thumbnail(size, Image.ANTIALIAS)

                # Create blank RGBA image
                bg = Image.new("RGBA", size, (255, 255, 255, 0))

                # Calculate position for centering
                left = (size[0] - im.size[0]) // 2
                top = (size[1] - im.size[1]) // 2

                # Paste resized image onto blank image
                bg.paste(im, (left, top), mask=im)

                # Save as PNG
                bg.save(original, "PNG")

                # Set pixmap for picon instance
                if self["picon"].instance:
                    self["picon"].instance.setPixmapFromFile(original)

            except Exception as e:
                print("Error resizing image:", e)
                self.loadDefaultImage()
        else:
            self.loadDefaultImage()

    def __next__(self):
        self.servicetype = self.originalservicetype
        self.streamcheck = 0

        if glob.currentchannellist:
            list_length = len(glob.currentchannellist)
            glob.currentchannellistindex += 1
            if glob.currentchannellistindex + 1 > list_length:
                glob.currentchannellistindex = 0
            self.streamurl = glob.currentchannellist[glob.currentchannellistindex][3]
            self.direct_source = glob.currentchannellist[glob.currentchannellistindex][7]
            self.playStream(self.servicetype, self.streamurl, self.direct_source)

    def prev(self):
        self.servicetype = self.originalservicetype
        self.streamcheck = 0

        if glob.currentchannellist:
            list_length = len(glob.currentchannellist)
            glob.currentchannellistindex -= 1
            if glob.currentchannellistindex + 1 == 0:
                glob.currentchannellistindex = list_length - 1

            self.streamurl = glob.currentchannellist[glob.currentchannellistindex][3]
            self.direct_source = glob.currentchannellist[glob.currentchannellistindex][7]
            self.playStream(self.servicetype, self.streamurl, self.direct_source)

    def nextARfunction(self):
        self.ar_id_player += 1
        if self.ar_id_player > 6:
            self.ar_id_player = 0
        try:
            eAVSwitch.getInstance().setAspectRatio(self.ar_id_player)
            return VIDEO_ASPECT_RATIO_MAP[self.ar_id_player]
        except Exception as e:
            print(e)
            return _("Resolution Change Failed")

    def nextAR(self):
        message = self.nextARfunction()
        self.session.open(MessageBox, message, type=MessageBox.TYPE_INFO, timeout=1)


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


class XStreamity_VodPlayer(
    InfoBarBase,
    IPTVInfoBarShowHide,
    InfoBarSeek,
    InfoBarAudioSelection,
    IPTVInfoBarPVRState,
    XStreamityCueSheetSupport,
    InfoBarMoviePlayerSummarySupport,
    InfoBarSubtitleSupport,
    SubsSupportStatus,
    SubsSupport,
        Screen):

    ENABLE_RESUME_SUPPORT = True
    ALLOW_SUSPEND = True

    def __init__(self, session, streamurl, servicetype, direct_source=None, stream_id=None):
        Screen.__init__(self, session)
        self.session = session

        for x in (
            IPTVInfoBarShowHide,
            InfoBarBase,
            InfoBarSeek,
            InfoBarAudioSelection,
            InfoBarMoviePlayerSummarySupport,
            InfoBarSubtitleSupport
        ):
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
        with open(skin, "r") as f:
            self.skin = f.read()

        self["streamcat"] = StaticText()
        self["streamtype"] = StaticText()
        self["extension"] = StaticText()
        self["cover"] = Pixmap()
        self["eventname"] = Label()
        self["state"] = Label()
        self["speed"] = Label()
        self["statusicon"] = MultiPixmap()
        self["PTSSeekBack"] = Pixmap()
        self["PTSSeekPointer"] = Pixmap()

        self.PicLoad = ePicLoad()
        try:
            self.PicLoad.PictureData.get().append(self.DecodePicture)
        except:
            self.PicLoad_conn = self.PicLoad.PictureData.connect(self.DecodePicture)

        self.ar_id_player = 0

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

        for recent in glob.active_playlist["player_info"]["vodrecents"]:
            if stream_id == recent["stream_id"]:
                glob.active_playlist["player_info"]["vodrecents"].remove(recent)
                break

        new_recent = {
            "name": name,
            "stream_id": stream_id,
            "stream_icon": stream_icon,
            "added": added,
            "rating": rating,
            "container_extension": container_extension
        }

        glob.active_playlist["player_info"]["vodrecents"].insert(0, new_recent)

        if len(glob.active_playlist["player_info"]["vodrecents"]) >= 20:
            glob.active_playlist["player_info"]["vodrecents"].pop(0)

        with open(playlists_json, "r") as f:
            try:
                self.playlists_all = json.load(f)
            except:
                os.remove(playlists_json)

        if self.playlists_all:
            for index, playlists in enumerate(self.playlists_all):
                playlist_info = playlists["playlist_info"]
                current_playlist_info = glob.active_playlist["playlist_info"]
                if (playlist_info["domain"] == current_playlist_info["domain"] and
                        playlist_info["username"] == current_playlist_info["username"] and
                        playlist_info["password"] == current_playlist_info["password"]):
                    self.playlists_all[index] = glob.active_playlist
                    break

        with open(playlists_json, "w") as f:
            json.dump(self.playlists_all, f)

    def addWatchedList(self):
        stream_id = self.stream_id

        if glob.categoryname == "vod":

            if stream_id not in glob.active_playlist["player_info"]["vodwatched"]:
                glob.active_playlist["player_info"]["vodwatched"].append(stream_id)

        elif glob.categoryname == "series":

            if stream_id not in glob.active_playlist["player_info"]["serieswatched"]:
                glob.active_playlist["player_info"]["serieswatched"].append(stream_id)

        with open(playlists_json, "r") as f:
            try:
                self.playlists_all = json.load(f)
            except:
                os.remove(playlists_json)

        if self.playlists_all:
            for index, playlists in enumerate(self.playlists_all):
                playlist_info = playlists["playlist_info"]
                current_playlist_info = glob.active_playlist["playlist_info"]
                if (playlist_info["domain"] == current_playlist_info["domain"] and
                        playlist_info["username"] == current_playlist_info["username"] and
                        playlist_info["password"] == current_playlist_info["password"]):
                    self.playlists_all[index] = glob.active_playlist
                    break

        with open(playlists_json, "w") as f:
            json.dump(self.playlists_all, f)

    def playStream(self, servicetype, streamurl, direct_source):
        if cfg.infobarcovers.value is True:
            self.downloadImage()

        self["streamcat"].setText("VOD" if glob.categoryname == "vod" else "Series")
        self["streamtype"].setText(str(servicetype))

        try:
            self["extension"].setText(str(os.path.splitext(streamurl)[-1]))
        except:
            pass

        if glob.active_playlist["player_info"]["directsource"] == "Direct Source" and direct_source:
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
            self.timerCache.start(5 * 60 * 1000, False)

            if glob.categoryname == "vod":
                self.timerRecent = eTimer()
                try:
                    self.timerRecent.callback.append(self.addRecentVodList)
                except:
                    self.timerRecent_conn = self.timerRecent.timeout.connect(self.addRecentVodList)
                self.timerRecent.start(5 * 60 * 1000, True)

            self.timerWatched = eTimer()
            try:
                self.timerWatched.callback.append(self.addWatchedList)
            except:
                self.timerWatched_conn = self.timerWatched.timeout.connect(self.addWatchedList)
            self.timerWatched.start(15 * 60 * 1000, True)

    def downloadImage(self):
        self.loadDefaultImage()
        try:
            os.remove(os.path.join(dir_tmp, "original.jpg"))
            os.remove(os.path.join(dir_tmp, "temp.jpg"))
        except:
            pass

        desc_image = ""
        try:
            desc_image = glob.currentchannellist[glob.currentchannellistindex][5]
        except:
            pass

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

    def loadDefaultImage(self, data=None):
        if self["cover"].instance:
            self["cover"].instance.setPixmapFromFile(os.path.join(skin_directory, "common/cover.png"))

    def resizeImage(self, data=None):
        if self["cover"].instance:
            preview = os.path.join(dir_tmp, "temp.jpg")

            if screenwidth.width() == 2560:
                width = 293
                height = 440
            elif screenwidth.width() > 1280:
                width = 220
                height = 330
            else:
                width = 147
                height = 220

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

        try:
            self.session.nav.stopService()
        except:
            pass

        try:
            self.session.nav.playService(eServiceReference(glob.currentPlayingServiceRefString))
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
        self.ar_id_player += 1
        if self.ar_id_player > 6:
            self.ar_id_player = 0
        try:
            eAVSwitch.getInstance().setAspectRatio(self.ar_id_player)
            return VIDEO_ASPECT_RATIO_MAP[self.ar_id_player]
        except Exception as e:
            print(e)
            return _("Resolution Change Failed")

    def nextAR(self):
        message = self.nextARfunction()
        self.session.open(MessageBox, message, type=MessageBox.TYPE_INFO, timeout=1)


class XStreamity_CatchupPlayer(

    InfoBarBase,
    IPTVInfoBarShowHide,
    InfoBarSeek,
    InfoBarAudioSelection,
    IPTVInfoBarPVRState,
    XStreamityCueSheetSupport,
    InfoBarMoviePlayerSummarySupport,
    InfoBarSubtitleSupport,
    SubsSupportStatus,
    SubsSupport,
        Screen):

    def __init__(self, session, streamurl, servicetype):
        Screen.__init__(self, session)
        self.session = session

        if str(os.path.splitext(streamurl)[-1]) == ".m3u8" and servicetype == "1":
            servicetype = "4097"

        for x in (
            InfoBarBase,
            IPTVInfoBarShowHide,
            InfoBarAudioSelection,
            InfoBarSeek,
            InfoBarSubtitleSupport,
            InfoBarMoviePlayerSummarySupport
        ):
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

        skin = os.path.join(skin_path, "catchupplayer.xml")
        with open(skin, "r") as f:
            self.skin = f.read()

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
        self["x_description"].setText(glob.catchupdata[1])
        self["streamcat"].setText("Catch")
        self["streamtype"].setText(str(servicetype))

        try:
            self["extension"].setText(str(os.path.splitext(streamurl)[-1]))
        except:
            pass

        self.reference = eServiceReference(int(servicetype), 0, streamurl)
        self.reference.setName(glob.catchupdata[0])

        currently_playing_ref = self.session.nav.getCurrentlyPlayingServiceReference()
        if currently_playing_ref and currently_playing_ref.toString() != self.reference.toString():
            self.session.nav.stopService()

        self.session.nav.playService(self.reference)

        currently_playing_ref = self.session.nav.getCurrentlyPlayingServiceReference()
        if currently_playing_ref:
            glob.newPlayingServiceRef = currently_playing_ref
            glob.newPlayingServiceRefString = currently_playing_ref.toString()

        if cfg.infobarpicons.value is True:
            self.downloadImage()

        self.timerCache = eTimer()
        try:
            self.timerCache.callback.append(clear_caches)
        except:
            self.timerCache_conn = self.timerCache.timeout.connect(clear_caches)
        self.timerCache.start(5 * 60 * 1000, False)

    def downloadImage(self):
        self.loadDefaultImage()
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

    def loadDefaultImage(self, data=None):
        if self["picon"].instance:
            self["picon"].instance.setPixmapFromFile(os.path.join(common_path, "picon.png"))

    def resizeImage(self, data=None):
        # print("*** resizeImage ***")
        original = os.path.join(dir_tmp, "temp.png")

        # Determine the target size based on screen width
        if screenwidth.width() == 2560:
            size = [294, 176]
        elif screenwidth.width() > 1280:
            size = [220, 130]
        else:
            size = [147, 88]

        if os.path.exists(original):
            try:
                im = Image.open(original)

                # Convert to RGBA if not already
                if im.mode != "RGBA":
                    im = im.convert("RGBA")
                try:
                    im.thumbnail(size, Image.Resampling.LANCZOS)
                except:
                    im.thumbnail(size, Image.ANTIALIAS)

                # Create blank RGBA image
                bg = Image.new("RGBA", size, (255, 255, 255, 0))

                # Calculate position for centering
                left = (size[0] - im.size[0]) // 2
                top = (size[1] - im.size[1]) // 2

                # Paste resized image onto blank image
                bg.paste(im, (left, top), mask=im)

                # Save as PNG
                bg.save(original, "PNG")

                # Set pixmap for picon instance
                if self["picon"].instance:
                    self["picon"].instance.setPixmapFromFile(original)

            except Exception as e:
                print("Error resizing image:", e)
                self.loadDefaultImage()
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
        self.ar_id_player += 1
        if self.ar_id_player > 6:
            self.ar_id_player = 0
        try:
            eAVSwitch.getInstance().setAspectRatio(self.ar_id_player)
            return VIDEO_ASPECT_RATIO_MAP[self.ar_id_player]
        except Exception as e:
            print(e)
            return _("Resolution Change Failed")

    def nextAR(self):
        message = self.nextARfunction()
        self.session.open(MessageBox, message, type=MessageBox.TYPE_INFO, timeout=1)
