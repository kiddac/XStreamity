#!/usr/bin/python
# -*- coding: utf-8 -*-

# Standard library imports
from __future__ import absolute_import, print_function
from __future__ import division

import json
import os
import re
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
from PIL import Image, ImageFile, PngImagePlugin
from twisted.web.client import downloadPage

# Enigma2 components
from Components.ActionMap import ActionMap
from Components.Label import Label
from Components.Pixmap import MultiPixmap, Pixmap
from Components.ServiceEventTracker import ServiceEventTracker, InfoBarBase
from enigma import eTimer, eServiceReference, iPlayableService, ePicLoad
from Tools import Notifications
from Screens.InfoBarGenerics import InfoBarSeek, InfoBarAudioSelection, InfoBarSummarySupport, InfoBarMoviePlayerSummarySupport, InfoBarSubtitleSupport, InfoBarNotifications
from Screens.MessageBox import MessageBox
from Screens.Screen import Screen
from Tools.BoundFunction import boundFunction

try:
    from enigma import eAVSwitch
except Exception:
    from enigma import eAVControl as eAVSwitch

try:
    from .resumepoints import setResumePoint, getResumePoint
except ImportError as e:
    print(e)

# Local application/library-specific imports
from . import _
from . import xstreamity_globals as glob
from .plugin import cfg, dir_tmp, pythonVer, screenwidth, skin_directory
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


class XStreamityCueSheetSupport:
    ENABLE_RESUME_SUPPORT = False

    def __init__(self):
        self.playlists_json = cfg.playlists_json.value
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
        # print("*** service started ***")
        if self.is_closing:
            return

        if self.ENABLE_RESUME_SUPPORT and not self.started:
            # print("*** true ***")

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
                # print("*** true 2 ***")
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
    IPTVInfoBarPVRState,
    XStreamityCueSheetSupport,
    InfoBarAudioSelection,
    InfoBarSeek,
    InfoBarNotifications,
    InfoBarSummarySupport,
    InfoBarSubtitleSupport,
    InfoBarMoviePlayerSummarySupport,
    SubsSupportStatus,
    SubsSupport,
        Screen):

    ENABLE_RESUME_SUPPORT = True
    ALLOW_SUSPEND = True

    def __init__(self, session, streamurl, servicetype, stream_id=None):
        Screen.__init__(self, session)
        self.session = session

        for x in (
            InfoBarBase,
            IPTVInfoBarShowHide,
            InfoBarAudioSelection,
            InfoBarSeek,
            InfoBarNotifications,
            InfoBarSummarySupport,
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
        self.originalservicetype = self.servicetype
        self.stream_id = stream_id

        skin_path = os.path.join(skin_directory, cfg.skin.value)
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
            "channelUp": self.__next__,
            "down": self.__next__,
            "channelDown": self.prev,
            "up": self.prev,
            "tv": self.toggleStreamType,
            "info": self.toggleStreamType,
            "green": self.nextAR,
            "ok": self.refreshInfobar,
        }, -2)

        self.onFirstExecBegin.append(boundFunction(self.playStream, self.servicetype, self.streamurl))

    def refreshInfobar(self):
        IPTVInfoBarShowHide.OkPressed(self)

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

        with open(self.playlists_json, "r") as f:
            try:
                self.playlists_all = json.load(f)
            except:
                os.remove(self.playlists_json)

        if self.playlists_all:
            for index, playlists in enumerate(self.playlists_all):
                playlist_info = playlists["playlist_info"]
                current_playlist_info = glob.active_playlist["playlist_info"]
                if (playlist_info["domain"] == current_playlist_info["domain"] and
                        playlist_info["username"] == current_playlist_info["username"] and
                        playlist_info["password"] == current_playlist_info["password"]):
                    self.playlists_all[index] = glob.active_playlist
                    break

        with open(self.playlists_json, "w") as f:
            json.dump(self.playlists_all, f)

    def addWatchedList(self):
        stream_id = self.stream_id

        if glob.categoryname == "vod":
            if stream_id not in glob.active_playlist["player_info"]["vodwatched"]:
                glob.active_playlist["player_info"]["vodwatched"].append(stream_id)

        elif glob.categoryname == "series":
            if stream_id not in glob.active_playlist["player_info"]["serieswatched"]:
                glob.active_playlist["player_info"]["serieswatched"].append(stream_id)

        with open(self.playlists_json, "r") as f:
            try:
                self.playlists_all = json.load(f)
            except:
                os.remove(self.playlists_json)

        if self.playlists_all:
            for index, playlists in enumerate(self.playlists_all):
                playlist_info = playlists["playlist_info"]
                current_playlist_info = glob.active_playlist["playlist_info"]
                if (playlist_info["domain"] == current_playlist_info["domain"] and
                        playlist_info["username"] == current_playlist_info["username"] and
                        playlist_info["password"] == current_playlist_info["password"]):
                    self.playlists_all[index] = glob.active_playlist
                    break

        with open(self.playlists_json, "w") as f:
            json.dump(self.playlists_all, f)

    def playStream(self, servicetype, streamurl):
        if cfg.infobarcovers.value is True:
            self.downloadImage()

        self["streamcat"].setText("VOD" if glob.categoryname == "vod" else "Series")
        self["streamtype"].setText(str(servicetype))

        try:
            self["extension"].setText(str(os.path.splitext(streamurl)[-1]))
        except:
            pass

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
            os.remove(os.path.join(dir_tmp, "cover.jpg"))
        except:
            pass

        desc_image = ""
        try:
            desc_image = glob.currentchannellist[glob.currentchannellistindex][5]
        except:
            pass

        if desc_image and desc_image != "n/A":
            temp = os.path.join(dir_tmp, "cover.jpg")
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
            preview = os.path.join(dir_tmp, "cover.jpg")

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

        self.playStream(self.servicetype, self.streamurl)

    def __next__(self):
        if glob.categoryname == "series":
            self.servicetype = self.originalservicetype

            if glob.currentchannellist:
                list_length = len(glob.currentchannellist)
                glob.currentchannellistindex += 1
                if glob.currentchannellistindex >= list_length:
                    glob.currentchannellistindex -= 1
                    return
                self.streamurl = glob.currentchannellist[glob.currentchannellistindex][3]
                self.playStream(self.servicetype, self.streamurl)

    def prev(self):
        if glob.categoryname == "series":
            self.servicetype = self.originalservicetype

            if glob.currentchannellist:
                glob.currentchannellistindex -= 1
                if glob.currentchannellistindex < 0:
                    glob.currentchannellistindex = 0
                    return
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
