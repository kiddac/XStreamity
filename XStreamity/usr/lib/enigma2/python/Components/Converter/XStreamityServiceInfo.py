from Components.Converter.Converter import Converter
from enigma import iServiceInformation, iPlayableService
from Components.Element import cached
from Components.Converter.Poll import Poll
from os import path
from sys import version_info

WIDESCREEN = [1, 3, 4, 7, 8, 0xB, 0xC, 0xF, 0x10]

PY3 = version_info[0] == 3


class XStreamityServiceInfo(Poll, Converter):

    IS_MULTICHANNEL = 1
    AUDIO_STEREO = 2
    IS_WIDESCREEN = 3
    XRES = 4
    YRES = 5
    FRAMERATE = 6
    AUDIOTRACKS_AVAILABLE = 7
    SUBTITLES_AVAILABLE = 8
    IS_SD = 9
    IS_HD = 10
    IS_FHD = 11
    IS_UHD = 12

    def __init__(self, type):
        Poll.__init__(self)
        Converter.__init__(self, type)
        self.poll_interval = 1000
        self.poll_enabled = True
        self.type, self.interesting_events = {

            "IsMultichannel": (self.IS_MULTICHANNEL, (iPlayableService.evUpdatedInfo,)),
            "IsWidescreen": (self.IS_WIDESCREEN, (iPlayableService.evVideoSizeChanged,)),
            "VideoWidth": (self.XRES, (iPlayableService.evVideoSizeChanged,)),
            "VideoHeight": (self.YRES, (iPlayableService.evVideoSizeChanged,)),
            "Framerate": (self.FRAMERATE, (iPlayableService.evVideoSizeChanged, iPlayableService.evUpdatedInfo,)),
            "AudioTracksAvailable": (self.AUDIOTRACKS_AVAILABLE, (iPlayableService.evUpdatedInfo,)),
            "SubtitlesAvailable": (self.SUBTITLES_AVAILABLE, (iPlayableService.evUpdatedInfo,)),
            "IsSD": (self.IS_SD, (iPlayableService.evVideoSizeChanged,)),
            "IsHD": (self.IS_HD, (iPlayableService.evVideoSizeChanged,)),
            "IsFHD": (self.IS_FHD, (iPlayableService.evVideoSizeChanged,)),
            "IsUHD": (self.IS_UHD, (iPlayableService.evVideoSizeChanged,)),

        }[type]
        self.interesting_events += (iPlayableService.evStart,)

    def getServiceInfoString(self, info, what, convert=lambda x: "%d" % x):
        v = info.getInfo(what)
        if v == -1:
            return "N/A"
        if v == -2:
            return info.getInfoString(what)
        return convert(v)

    def getServiceInfoHexString(self, info, what, convert=lambda x: "%04x" % x):
        v = info.getInfo(what)
        if v == -1:
            return "N/A"
        if v == -2:
            return info.getInfoString(what)
        return convert(v)

    def _getProcVal(self, pathname, base=10):
        val = None
        try:
            f = open(pathname, "r")
            val = int(f.read(), base)
            f.close()
            if val >= 2 ** 31:
                val -= 2 ** 32
        except Exception as e:
            print(e)
            pass
        return val

    def _getVal(self, pathname, info, infoVal, base=10):
        val = self._getProcVal(pathname, base=base)
        return val if val is not None else info.getInfo(infoVal)

    def _getValInt(self, pathname, info, infoVal, base=10, default=-1):
        val = self._getVal(pathname, info, infoVal, base)
        return val if val is not None else default

    def _getValStr(self, pathname, info, infoVal, base=10, convert=lambda x: "%d" % x):
        val = self._getProcVal(pathname, base=base)
        return convert(val) if val is not None else self.getServiceInfoString(info, infoVal, convert)

    def _getVideoHeight(self, info):
        return self._getValInt("/proc/stb/vmpeg/0/yres", info, iServiceInformation.sVideoHeight, base=16)

    def _getVideoHeightStr(self, info, convert=lambda x: "%d" % x if x > 0 else "?"):
        return self._getValStr("/proc/stb/vmpeg/0/yres", info, iServiceInformation.sVideoHeight, base=16, convert=convert)

    def _getVideoWidth(self, info):
        return self._getValInt("/proc/stb/vmpeg/0/xres", info, iServiceInformation.sVideoWidth, base=16)

    def _getVideoWidthStr(self, info, convert=lambda x: "%d" % x if x > 0 else "?"):
        return self._getValStr("/proc/stb/vmpeg/0/xres", info, iServiceInformation.sVideoWidth, base=16, convert=convert)

    def _getFrameRate(self, info):
        return self._getValInt("/proc/stb/vmpeg/0/framerate", info, iServiceInformation.sFrameRate)

    def _getFrameRateStr(self, info, convert=lambda x: "%d" % x if x > 0 else ""):
        return self._getValStr("/proc/stb/vmpeg/0/framerate", info, iServiceInformation.sFrameRate, convert=convert)

    @cached
    def getBoolean(self):
        service = self.source.service
        info = service and service.info()
        if not info:
            return False

        video_height = None
        video_width = None
        video_aspect = None

        video_height = int(info.getInfo(iServiceInformation.sVideoHeight))
        video_width = int(info.getInfo(iServiceInformation.sVideoWidth))
        video_aspect = info.getInfo(iServiceInformation.sAspect)

        if not video_height:
            if path.exists("/proc/stb/vmpeg/0/yres"):
                f = open("/proc/stb/vmpeg/0/yres", "r")
                try:
                    video_height = int(f.read(), 16)
                except:
                    pass
                f.close()

        if not video_width:
            if path.exists("/proc/stb/vmpeg/0/xres"):
                f = open("/proc/stb/vmpeg/0/xres", "r")
                try:
                    video_width = int(f.read(), 16)
                except:
                    pass
                f.close()

        if not video_aspect:
            if path.exists("/proc/stb/vmpeg/0/aspect"):
                f = open("/proc/stb/vmpeg/0/aspect", "r")
                try:
                    video_aspect = int(f.read())
                except:
                    pass
                f.close()

        if self.type in (self.IS_MULTICHANNEL, self.AUDIO_STEREO):
            audio = service.audioTracks()
            if audio:
                n = audio.getNumberOfTracks()
                idx = 0
                while idx < n:
                    i = audio.getTrackInfo(idx)
                    description = i.getDescription()
                    if description and description.split()[0] in ("AC3", "AC-3", "AC3+", "DTS"):
                        if self.type == self.IS_MULTICHANNEL:
                            return True
                        elif self.type == self.AUDIO_STEREO:
                            return False
                    idx += 1
                if self.type == self.IS_MULTICHANNEL:
                    return False
                elif self.type == self.AUDIO_STEREO:
                    return True
            return False

        elif self.type == self.IS_WIDESCREEN:
            return video_aspect in WIDESCREEN

        elif self.type == self.AUDIOTRACKS_AVAILABLE:
            audio = service.audioTracks()
            return audio and audio.getNumberOfTracks() > 1

        elif self.type == self.SUBTITLES_AVAILABLE:
            try:
                subtitle = service and service.subtitle()
                subtitlelist = subtitle and subtitle.getSubtitleList()
                if subtitlelist:
                    return len(subtitlelist) > 0
                return False
            except:
                try:
                    subtitle = service and service.subtitleTracks()
                    return subtitle and subtitle.getNumberOfSubtitleTracks() > 0
                except:
                    return False

        elif self.type == self.IS_SD:
            return video_height < 720

        elif self.type == self.IS_HD:
            return video_height >= 720 and video_height <= 1079

        elif self.type == self.IS_FHD:
            return video_height >= 1080 and video_height < 2160 and video_width < 3840

        elif self.type == self.IS_UHD:
            return video_height >= 2160 or video_width >= 3840

        else:
            return False

    boolean = property(getBoolean)

    @cached
    def getText(self):

        service = self.source.service
        info = service and service.info()
        if not info:
            return ""

        if self.type == self.XRES:
            video_width = None
            if path.exists("/proc/stb/vmpeg/0/xres"):
                f = open("/proc/stb/vmpeg/0/xres", "r")
                try:
                    video_width = int(f.read(), 16)
                except:
                    pass
                f.close()
            if not video_width:
                try:
                    video_width = int(self.getServiceInfoString(info, iServiceInformation.sVideoWidth))
                except:
                    return ""
            return "%d" % video_width

        elif self.type == self.YRES:
            video_height = None
            if path.exists("/proc/stb/vmpeg/0/yres"):
                f = open("/proc/stb/vmpeg/0/yres", "r")
                try:
                    video_height = int(f.read(), 16)
                except:
                    pass
                f.close()
            if not video_height:
                try:
                    video_height = int(self.getServiceInfoString(info, iServiceInformation.sVideoHeight))

                except:
                    return ""
            return "%d" % video_height

        elif self.type == self.FRAMERATE:
            video_rate = None
            if path.exists("/proc/stb/vmpeg/0/framerate"):
                f = open("/proc/stb/vmpeg/0/framerate", "r")
                try:
                    video_rate = int(f.read())
                except:
                    pass
                f.close()
            elif path.exists("/proc/stb/vmpeg/0/frame_rate"):
                f = open("/proc/stb/vmpeg/0/frame_rate", "r")
                try:
                    video_rate = int(f.read())
                except:
                    pass
                f.close()
            elif path.exists("/proc/stb/vmpeg/0/fallback_framerate"):
                f = open("/proc/stb/vmpeg/0/fallback_framerate", "r")
                try:
                    video_rate = int(f.read())
                except:
                    pass
                f.close()

            if not video_rate:
                try:
                    video_rate = int(self.getServiceInfoString(info, iServiceInformation.sFrameRate))
                except:
                    return "fps -"
            if PY3:
                fps = str((video_rate + 500) // 1000)
            else:
                fps = str((video_rate + 500) / 1000)
            return str("fps ") + fps

        return ""

    text = property(getText)

    @cached
    def getValue(self):
        service = self.source.service
        info = service and service.info()
        if not info:
            return -1

        if self.type == self.XRES:
            video_width = None
            if path.exists("/proc/stb/vmpeg/0/xres"):
                f = open("/proc/stb/vmpeg/0/xres", "r")
                try:
                    video_width = int(f.read(), 16)
                except:
                    video_width = None
                f.close()
            if not video_width:
                video_width = info.getInfo(iServiceInformation.sVideoWidth)
            return str(video_width)

        elif self.type == self.YRES:
            video_height = None
            if path.exists("/proc/stb/vmpeg/0/yres"):
                f = open("/proc/stb/vmpeg/0/yres", "r")
                try:
                    video_height = int(f.read(), 16)
                except:
                    video_height = None
                f.close()
            if not video_height:
                video_height = info.getInfo(iServiceInformation.sVideoHeight)
            return str(video_height)

        elif self.type == self.FRAMERATE:
            video_rate = None
            if path.exists("/proc/stb/vmpeg/0/framerate"):
                f = open("/proc/stb/vmpeg/0/framerate", "r")
                try:
                    video_rate = int(f.read())
                except:
                    pass
                f.close()
            elif path.exists("/proc/stb/vmpeg/0/frame_rate"):
                f = open("/proc/stb/vmpeg/0/frame_rate", "r")
                try:
                    video_rate = int(f.read())
                except:
                    pass
                f.close()
            elif path.exists("/proc/stb/vmpeg/0/fallback_framerate"):
                f = open("/proc/stb/vmpeg/0/fallback_framerate", "r")
                try:
                    video_rate = int(f.read())
                except:
                    pass
                f.close()

            if not video_rate:
                video_rate = info.getInfo(iServiceInformation.sFrameRate)
            return str(video_rate)

        return -1

    value = property(getValue)

    def changed(self, what):
        if what[0] != self.CHANGED_SPECIFIC or what[1] in self.interesting_events:
            Converter.changed(self, what)
