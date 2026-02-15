#!/usr/bin/python
# -*- coding: utf-8 -*-

# Standard library imports
from __future__ import absolute_import, print_function
from __future__ import division
import os
import re
import tempfile
from itertools import cycle, islice
from datetime import datetime, timedelta

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
from Components.Pixmap import MultiPixmap, Pixmap
from Components.ServiceEventTracker import ServiceEventTracker, InfoBarBase
from enigma import eTimer, eServiceReference, iPlayableService
from Screens.InfoBarGenerics import InfoBarSeek, InfoBarAudioSelection, InfoBarMoviePlayerSummarySupport, InfoBarSubtitleSupport, InfoBarNotifications
from Screens.MessageBox import MessageBox
from Screens.Screen import Screen
from Tools import Notifications
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


class XStreamity_CatchupPlayer(

    InfoBarBase,
    IPTVInfoBarShowHide,
    XStreamityCueSheetSupport,
    InfoBarSeek,
    InfoBarNotifications,
    InfoBarAudioSelection,
    IPTVInfoBarPVRState,
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
            InfoBarNotifications,
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

        skin_path = os.path.join(skin_directory, cfg.skin.value)
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
            "channelUp": self.pageUp,
            "channelDown": self.pageDown,
            "ok": self.refreshInfobar,
        }, -2)

        self.timerImage = eTimer()
        try:
            self.timerImage.callback.append(self.downloadImage)
        except:
            self.timerImage_conn = self.timerImage.timeout.connect(self.downloadImage)

        self.onFirstExecBegin.append(boundFunction(self.playStream, self.servicetype, self.streamurl))

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

    def refreshInfobar(self):
        IPTVInfoBarShowHide.OkPressed(self)

    def playStream(self, servicetype, streamurl):
        self._stopTimer("timerImage")

        if not streamurl:
            return

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
            self.timerImage.start(250, True)

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
            im = None
            try:
                im = Image.open(original)
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
            finally:
                if im is not None:
                    try:
                        im.close()
                    except:
                        pass

            try:
                os.remove(original)
            except:
                pass
        else:
            self.loadDefaultImage()

    def back(self):
        self._cleanupTimer("timerImage")

        glob.nextlist[-1]["index"] = glob.currentchannellistindex
        try:
            setResumePoint(self.session)
        except Exception as e:
            print(e)

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

    def pageUp(self):
        url = self.getdatetime(10)
        self.streamurl = url
        self.session.nav.stopService()
        self.playStream(self.servicetype, url)

    def pageDown(self):
        url = self.getdatetime(-10)
        self.streamurl = url
        self.session.nav.stopService()
        self.playStream(self.servicetype, url)

    def getdatetime(self, mins):
        # Split the URL by slashes
        url = self.streamurl

        # Use regex to extract the date and time part
        match = re.search(r'(\d{4}-\d{2}-\d{2}:\d{2}-\d{2})', url)
        if match:
            date_time_str = match.group(1)
        else:
            return url

        # Convert the extracted string to a datetime object
        dt = datetime.strptime(date_time_str, "%Y-%m-%d:%H-%M")

        # Add or subtract 15 minutes
        modified_dt = dt + timedelta(minutes=mins)

        # Format the datetime objects back to the same format
        formatted_modified_dt = modified_dt.strftime("%Y-%m-%d:%H-%M")

        modified_url = re.sub(r'(\d{4}-\d{2}-\d{2}:\d{2}-\d{2})', formatted_modified_dt, url)

        return modified_url
