#!/usr/bin/python
# -*- coding: utf-8 -*-

from __future__ import absolute_import, print_function
from __future__ import division

# Standard library imports
import base64
import json
import os
import time
import tempfile
from datetime import datetime, timedelta
from itertools import cycle, islice

try:
    from urlparse import urlparse
except ImportError:
    from urllib.parse import urlparse

try:
    from http.client import HTTPConnection
    HTTPConnection.debuglevel = 0
except ImportError:
    from httplib import HTTPConnection
    HTTPConnection.debuglevel = 0

# Third-party imports
from PIL import Image
import requests
from requests.adapters import HTTPAdapter, Retry
from twisted.web.client import downloadPage

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

# Enigma2 components
from Components.ActionMap import ActionMap
from Components.Label import Label
from Components.ProgressBar import ProgressBar
from Components.Pixmap import MultiPixmap, Pixmap
from Components.ServiceEventTracker import ServiceEventTracker, InfoBarBase
from Components.config import ConfigClock, ConfigText, NoSave
from enigma import eTimer, eServiceReference, iPlayableService, eEPGCache
from RecordTimer import RecordTimerEntry
from Screens.InfoBarGenerics import InfoBarSeek, InfoBarAudioSelection, InfoBarSummarySupport, InfoBarMoviePlayerSummarySupport, InfoBarSubtitleSupport
from Screens.MessageBox import MessageBox
from Screens.Screen import Screen
from ServiceReference import ServiceReference
from Tools.BoundFunction import boundFunction

try:
    from enigma import eAVSwitch
except Exception:
    from enigma import eAVControl as eAVSwitch

# Local application/library-specific imports
from . import _
from . import xstreamity_globals as glob
from .plugin import cfg, common_path, dir_tmp, pythonVer, screenwidth, skin_directory
from .xStaticText import StaticText

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


class IPTVInfoBarShowHide():
    STATE_HIDDEN = 0
    STATE_HIDING = 1
    STATE_SHOWING = 2
    STATE_SHOWN = 3
    FLAG_CENTER_DVB_SUBS = 2048
    skipToggleShow = False

    def __init__(self):
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


hdr = {
    'User-Agent': str(cfg.useragent.value),
    'Accept-Encoding': 'gzip, deflate'
}


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

    def __init__(self, session, streamurl, servicetype, stream_id=None):
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

        self.playlists_json = cfg.playlists_json.value
        self.streamurl = streamurl
        self.servicetype = servicetype
        self.originalservicetype = self.servicetype

        skin_path = os.path.join(skin_directory, cfg.skin.value)
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

        self._http = requests.Session()
        retries = Retry(total=1, backoff_factor=1)
        adapter = HTTPAdapter(max_retries=retries)
        self._http.mount("http://", adapter)
        self._http.mount("https://", adapter)

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
            "ok": self.OKButton,
        }, -2)

        epg_cache = eEPGCache.getInstance()
        if epg_cache:
            epg_cache.save()

        self.timerImage = eTimer()
        try:
            self.timerImage.callback.append(self.downloadImage)
        except:
            self.timerImage_conn = self.timerImage.timeout.connect(self.downloadImage)

        self.timerRecent = eTimer()
        try:
            self.timerRecent.callback.append(self.addRecentLiveList)
        except:
            self.timerRecent_conn = self.timerRecent.timeout.connect(self.addRecentLiveList)

        self.onFirstExecBegin.append(boundFunction(self.playStream, self.servicetype, self.streamurl))
        self.onClose.append(self.__onClose)

    def __onClose(self):
        try:
            self._http.close()
        except:
            pass
        self._http = None

    def _stopTimer(self, name):
        t = getattr(self, name, None)
        if t:
            try:
                t.stop()
            except:
                pass

    def _cleanupTimer(self, name):
        t = getattr(self, name, None)
        if t:
            try:
                t.stop()
            except:
                pass
            try:
                t.callback[:] = []
            except:
                pass
        try:
            setattr(self, name, None)
        except:
            pass

    def restartStream(self):
        if self.session:
            self.session.nav.stopService()
            self.playStream(self.servicetype, self.streamurl)

    def OKButton(self):
        self.refreshInfobar()
        IPTVInfoBarShowHide.OkPressed(self)

    def refreshInfobar(self):
        if glob.currentepglist:

            startnowunixtime = glob.currentepglist[glob.currentchannellistindex][9]
            startnextunixtime = glob.currentepglist[glob.currentchannellistindex][10]

            percent = 0

            if startnowunixtime and startnextunixtime:
                self["progress"].show()

                now = int(time.time())
                total_time = startnextunixtime - startnowunixtime
                elapsed = now - startnowunixtime

                percent = int(elapsed / total_time * 100) if total_time > 0 else 0

                self["progress"].setValue(percent)
            else:
                self["progress"].hide()

            # Check every 5 mins to see if EPG needs to be updated
            nowtime = datetime.now()
            minutes = nowtime.minute
            if minutes % 5 == 1:

                now = int(time.time())

                if startnextunixtime and now >= startnextunixtime:
                    try:
                        player_api = str(glob.active_playlist["playlist_info"]["player_api"])
                        stream_id = str(glob.currentchannellist[glob.currentchannellistindex][4])

                        shortEPGJson = []
                        url = player_api + "&action=get_short_epg&stream_id=" + str(stream_id) + "&limit=2"

                        http = self._http
                        try:
                            with http.get(url, headers=hdr, timeout=(10, 20), verify=False) as r:
                                r.raise_for_status()

                                if r.status_code == requests.codes.ok:
                                    response = r.json()
                                    shortEPGJson = response.get("epg_listings", [])
                        except Exception as e:
                            print("Error fetching or processing response:", e)
                            response = None
                            shortEPGJson = []

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
                        else:
                            templist = list(glob.currentepglist[glob.currentchannellistindex])
                            templist[4] = glob.currentepglist[glob.currentchannellistindex][7]  # description
                            templist[3] = glob.currentepglist[glob.currentchannellistindex][6]  # title
                            templist[2] = glob.currentepglist[glob.currentchannellistindex][5]  # now start
                            templist[6] = ""  # next title
                            templist[5] = ""  # next start
                            glob.currentepglist[glob.currentchannellistindex] = tuple(templist)
                    except Exception as e:
                        print("Error during short EPG update:", e)

            self["x_description"].setText(glob.currentepglist[glob.currentchannellistindex][4])
            self["nowchannel"].setText(glob.currentchannellist[glob.currentchannellistindex][0])
            self["nowtitle"].setText(glob.currentepglist[glob.currentchannellistindex][3])
            self["nexttitle"].setText(glob.currentepglist[glob.currentchannellistindex][6])
            self["nowtime"].setText(glob.currentepglist[glob.currentchannellistindex][2])
            self["nexttime"].setText(glob.currentepglist[glob.currentchannellistindex][5])
        else:
            self["x_description"].setText("")
            self["nowchannel"].setText(glob.currentchannellist[glob.currentchannellistindex][0])
            self["nowtitle"].setText("")
            self["nexttitle"].setText("")
            self["nowtime"].setText("")
            self["nexttime"].setText("")

    def IPTVstartInstantRecording(self, limitEvent=True):
        from . import record
        name = glob.currentchannellist[glob.currentchannellistindex][0]
        begin = int(time.time())
        end = begin + 3600
        self.date = time.time()

        try:
            if glob.currentepglist[glob.currentchannellistindex][3]:
                name = glob.currentepglist[glob.currentchannellistindex][3]

            if glob.currentepglist[glob.currentchannellistindex][10]:
                end = glob.currentepglist[glob.currentchannellistindex][10]
        except:
            pass

        self.name = NoSave(ConfigText(default=name, fixed_size=False))
        self.starttime = NoSave(ConfigClock(default=begin))
        self.endtime = NoSave(ConfigClock(default=end))
        self.session.openWithCallback(self.RecordDateInputClosed, record.RecordDateInput, self.name, self.date, self.starttime, self.endtime, True)

    def RecordDateInputClosed(self, ret=None):
        if ret:
            begin = ret[1]
            end = ret[2]
            name = ret[3]
            description = ""

            if glob.currentepglist[glob.currentchannellistindex][4]:
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

        self.playlists_all = []
        if os.path.exists(self.playlists_json):
            try:
                with open(self.playlists_json, "r") as f:
                    self.playlists_all = json.load(f) or []
            except:
                try:
                    os.remove(self.playlists_json)
                except:
                    pass
                self.playlists_all = []

            if self.playlists_all:
                for index, playlist in enumerate(self.playlists_all):
                    if playlist["playlist_info"] == glob.active_playlist["playlist_info"]:
                        self.playlists_all[index] = glob.active_playlist
                        break

            with open(self.playlists_json, "w") as f:
                json.dump(self.playlists_all, f, indent=4)

    def playStream(self, servicetype, streamurl):
        self._stopTimer("timerImage")
        self._stopTimer("timerRecent")

        if not streamurl:
            return

        self["streamcat"].setText("Live")
        self["streamtype"].setText(str(servicetype))

        try:
            self["extension"].setText(str(os.path.splitext(streamurl)[-1]))
        except:
            pass

        startnowunixtime = glob.currentepglist[glob.currentchannellistindex][9]
        startnextunixtime = glob.currentepglist[glob.currentchannellistindex][10]

        service_ref = ""

        if startnowunixtime and startnextunixtime:
            title = glob.currentepglist[glob.currentchannellistindex][3]
            description = glob.currentepglist[glob.currentchannellistindex][4]
            eventid = int("99" + self.streamurl.rpartition("/")[-1].partition(".")[0])

            start_time = startnowunixtime
            end_time = startnextunixtime

            self.unique_ref = 0
            stream_id = str(glob.currentchannellist[glob.currentchannellistindex][4])

            for j in str(self.streamurl):
                value = ord(j)
                self.unique_ref += value

            bouquet_id1 = int(stream_id) // 65535
            bouquet_id2 = int(stream_id) - int(bouquet_id1 * 65535)
            service_ref = eServiceReference(str(servicetype) + ":0:1:" + str(format(bouquet_id1, "x")) + ":" + str(format(bouquet_id2, "x")) + ":" + str(format(self.unique_ref, "x")) + ":0:0:0:0:" + str(streamurl).replace(":", "%3a"))
            service_ref.setName(glob.currentchannellist[glob.currentchannellistindex][0])
            self.reference = service_ref

            try:
                epg_cache = eEPGCache.getInstance()
                if epg_cache:
                    duration = end_time - start_time

                    epg_cache.importEvent(service_ref.toString(), [(start_time, duration, title, description, "", 0, eventid)])

            except Exception as e:
                print("Error adding event to EPG cache: %s" % e)

        if not service_ref:
            self.reference = eServiceReference(int(servicetype), 0, streamurl)
            self.reference.setName(glob.currentchannellist[glob.currentchannellistindex][0])

        playing = self.session.nav.getCurrentlyPlayingServiceReference()

        if playing:

            if self.session.nav.getCurrentlyPlayingServiceReference().toString() != self.reference.toString():
                try:
                    self.session.nav.playService(self.reference)
                except Exception as e:
                    print(e)
        else:
            try:
                self.session.nav.playService(self.reference)
            except Exception as e:
                print(e)

        nowref = self.session.nav.getCurrentlyPlayingServiceReference()
        if nowref:
            glob.newPlayingServiceRef = nowref
            glob.newPlayingServiceRefString = nowref.toString()

        if cfg.infobarpicons.value is True:
            self.timerImage.start(250, True)

        # add to recently watched
        self.timerRecent.start(5 * 60 * 1000, True)

        self.originalservicetype = self.servicetype

        self.refreshInfobar()

    def back(self):
        self._cleanupTimer("timerImage")
        self._cleanupTimer("timerRecent")

        glob.nextlist[-1]["index"] = glob.currentchannellistindex

        startnowunixtime = glob.currentepglist[glob.currentchannellistindex][9]
        startnextunixtime = glob.currentepglist[glob.currentchannellistindex][10]

        if startnowunixtime and startnextunixtime:
            try:
                epg_cache = eEPGCache.getInstance()
                if epg_cache:
                    epg_cache.flushEPG()
                    epg_cache.load()
            except Exception as e:
                print(e)

        self.close()

    def toggleStreamType(self):
        current_index = 0
        for index, item in enumerate(streamtypelist):
            if str(item) == str(self.servicetype):
                current_index = index
                break
        next_stream_type = islice(cycle(streamtypelist), current_index + 1, None)
        try:
            self.servicetype = int(next(next_stream_type))
        except:
            pass
        self.playStream(self.servicetype, self.streamurl)

    def downloadImage(self):
        # Clear picon immediately on zap so previous one doesn't remain if new fails
        self.loadDefaultImage()

        try:
            self._picon_req_id += 1
        except:
            self._picon_req_id = 1

        req_id = self._picon_req_id

        desc_image = ""
        try:
            desc_image = glob.currentchannellist[glob.currentchannellistindex][5]
        except:
            desc_image = ""

        if not desc_image or desc_image == "n/A":
            return

        fd = None
        temp = None

        try:
            fd, temp = tempfile.mkstemp(prefix="xst_picon_", suffix=".png", dir=dir_tmp)
            try:
                os.close(fd)
            except:
                pass

            parsed = urlparse(desc_image)
            domain = parsed.hostname
            scheme = parsed.scheme

            url = desc_image
            if pythonVer == 3:
                try:
                    url = desc_image.encode()
                except:
                    url = desc_image

            def _cleanup_temp():
                try:
                    if temp and os.path.exists(temp):
                        os.remove(temp)
                except:
                    pass

            def _ok(_data=None):
                # Ignore stale callbacks (e.g. user zapped again)
                if getattr(self, "_picon_req_id", 0) != req_id:
                    _cleanup_temp()
                    return

                self.resizeImage(temp)

            def _err(_failure=None):
                # Ignore stale callbacks
                if getattr(self, "_picon_req_id", 0) != req_id:
                    _cleanup_temp()
                    return

                _cleanup_temp()
                self.loadDefaultImage()

            if scheme == "https" and sslverify:
                sniFactory = SNIFactory(domain)
                d = downloadPage(url, temp, sniFactory, timeout=2)
            else:
                d = downloadPage(url, temp, timeout=2)

            d.addCallback(_ok)
            d.addErrback(_err)

        except:
            try:
                if fd:
                    os.close(fd)
            except:
                pass

            try:
                if temp and os.path.exists(temp):
                    os.remove(temp)
            except:
                pass

            self.loadDefaultImage()

    def loadDefaultImage(self, data=None):
        if self["picon"].instance:
            self["picon"].instance.setPixmapFromFile(os.path.join(common_path, "picon.png"))

    def resizeImage(self, original, data=None):
        if screenwidth.width() == 2560:
            size = [294, 176]
        elif screenwidth.width() > 1280:
            size = [220, 130]
        else:
            size = [147, 88]

        if os.path.exists(original):
            try:
                with Image.open(original) as im:
                    if im.mode != "RGBA":
                        im = im.convert("RGBA")

                    try:
                        im.thumbnail(size, Image.Resampling.LANCZOS)
                    except:
                        im.thumbnail(size, Image.ANTIALIAS)

                    bg = Image.new("RGBA", size, (255, 255, 255, 0))

                    left = (size[0] - im.size[0]) // 2
                    top = (size[1] - im.size[1]) // 2

                    bg.paste(im, (left, top), mask=im)
                    bg.save(original, "PNG")

                if self["picon"].instance:
                    self["picon"].instance.setPixmapFromFile(original)

            except Exception as e:
                print("Error resizing image:", e)
                self.loadDefaultImage()

            try:
                os.remove(original)
            except:
                pass
        else:
            self.loadDefaultImage()

    def __next__(self):
        self.servicetype = self.originalservicetype

        if glob.currentchannellist:
            list_length = len(glob.currentchannellist)
            glob.currentchannellistindex += 1
            if glob.currentchannellistindex >= list_length:
                glob.currentchannellistindex = 0
            self.streamurl = glob.currentchannellist[glob.currentchannellistindex][3]
            self.playStream(self.servicetype, self.streamurl)

    def prev(self):
        self.servicetype = self.originalservicetype

        if glob.currentchannellist:
            list_length = len(glob.currentchannellist)
            glob.currentchannellistindex -= 1
            if glob.currentchannellistindex < 0:
                glob.currentchannellistindex = list_length - 1

            self.streamurl = glob.currentchannellist[glob.currentchannellistindex][3]
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
