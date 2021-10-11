#!/usr/bin/python
# -*- coding: utf-8 -*-

from . import _
from .plugin import skin_path, downloads_json, cfg, pythonVer
from .xStaticText import StaticText

from Components.ActionMap import ActionMap
from Components.Sources.List import List
from Screens.MessageBox import MessageBox
from Screens.Screen import Screen
from enigma import eTimer, eServiceReference

from Components.Task import Task, Job, job_manager as JobManager, Condition

# from twisted.web.client import downloadPage

try:
    from urlparse import urlparse
except:
    from urllib.parse import urlparse

import json
import math
import os
import re
import requests
# import sys
import time


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


def convert_size(size_bytes):
    if size_bytes == 0:
        return "0B"
    size_name = ("B", "KB", "MB", "GB", "TB")
    i = int(math.floor(math.log(size_bytes, 1024)))
    p = math.pow(1024, i)
    s = round(size_bytes / p, 2)
    return "%s %s" % (s, size_name[i])


class downloadJob(Job):
    def __init__(self, toolbox, cmdline, filename, filetitle):
        print("**** downloadJob init ***")
        Job.__init__(self, _('Download:') + ' %s' % filetitle)
        self.filename = filename
        self.toolbox = toolbox
        self.retrycount = 0
        downloadTask(self, cmdline, filename)

    def retry(self):
        self.retrycount += 1
        self.restart()

    def cancel(self):
        self.abort()


# downloadtask code borrowed from MyStreamVod
class downloadTask(Task):
    # print("***downloadTask***")
    if pythonVer == 3:
        ERROR_CORRUPT_FILE, ERROR_RTMP_ReadPacket, ERROR_SEGFAULT, ERROR_SERVER, ERROR_UNKNOWN = list(range(5))
    else:
        ERROR_CORRUPT_FILE, ERROR_RTMP_ReadPacket, ERROR_SEGFAULT, ERROR_SERVER, ERROR_UNKNOWN = range(5)

    def __init__(self, job, cmdline, filename):
        Task.__init__(self, job, _("Downloading ..."))
        self.postconditions.append(downloadTaskPostcondition())
        self.setCmdline(cmdline)
        self.filename = filename
        self.toolbox = job.toolbox
        self.error = None
        self.lasterrormsg = None
        return

    def processOutput(self, data):

        if pythonVer == 3:
            data = str(data)
        try:
            if data.endswith('%)'):
                startpos = data.rfind('sec (') + 5
                if startpos and startpos != -1:
                    self.progress = int(float(data[startpos:-4]))
            elif data.find('%') != -1:
                tmpvalue = data[:data.find('%')]
                tmpvalue = tmpvalue[tmpvalue.rfind(' '):].strip()
                tmpvalue = tmpvalue[tmpvalue.rfind('(') + 1:].strip()
                if pythonVer == 3:
                    tmpvalue = int(tmpvalue)
                self.progress = int(float(tmpvalue))
            else:
                Task.processOutput(self, data)
        except Exception as errormsg:
            print('Error processOutput: ' + str(errormsg))
            Task.processOutput(self, data)

    def processOutputLine(self, line):
        line = line[:-1]
        self.lasterrormsg = line
        if line.startswith('ERROR:'):
            if line.find('RTMP_ReadPacket') != -1:
                self.error = self.ERROR_RTMP_ReadPacket
            elif line.find('corrupt file!') != -1:
                self.error = self.ERROR_CORRUPT_FILE
                os.system('rm -f %s' % self.filename)
            else:
                self.error = self.ERROR_UNKNOWN
        elif line.startswith('wget:'):
            if line.find('server returned error') != -1:
                self.error = self.ERROR_SERVER
        elif line.find('Segmentation fault') != -1:
            self.error = self.ERROR_SEGFAULT

    def afterRun(self):
        print("**** after run ***")
        if self.getProgress() == 0:
            try:
                self.toolbox. download_failed()
            except:
                pass
        elif self.getProgress() == 100:
            try:
                self.toolbox.download_finished()
            except:
                pass
        pass


class downloadTaskPostcondition(Condition):
    # print("*** downloadTaskPostcondtion ***")
    RECOVERABLE = True

    def check(self, task):
        if task.returncode == 0 or task.error is None:
            return True
        else:
            return False
            return

    def getErrorMessage(self, task):
        # print("*** get error message ***")
        return {
            task.ERROR_CORRUPT_FILE: _("MOVIE DOWNLOAD FAILED!") + '\n\n' + _("DOWNLOADED FILE CORRUPTED:") + '\n%s' % task.lasterrormsg,
            task.ERROR_RTMP_ReadPacket: _("MOVIE DOWNLOAD FAILED!") + '\n\n' + _("COULD NOT READ RTMP PACKET:") + '\n%s' % task.lasterrormsg,
            task.ERROR_SEGFAULT: _("MOVIE DOWNLOAD FAILED!") + '\n\n' + _("SEGMENTATION FAULT:") + '\n%s' % task.lasterrormsg,
            task.ERROR_SERVER: _("MOVIE DOWNLOAD FAILED!") + '\n\n' + _("SERVER RETURNED ERROR:") + '\n%s' % task.lasterrormsg,
            task.ERROR_UNKNOWN: _("MOVIE DOWNLOAD FAILED!") + '\n\n' + _("UNKNOWN ERROR:") + '\n%s' % task.lasterrormsg
        }[task.error]


class XStreamity_DownloadManager(Screen):

    def __init__(self, session):
        Screen.__init__(self, session)

        self.session = session
        skin = skin_path + 'downloadmanager.xml'

        with open(skin, 'r') as f:
            self.skin = f.read()

        self.setup_title = (_('VOD Download Manager'))
        self.onChangedEntry = []

        self.list = []
        self.drawList = []
        self.downloading = False
        self.firstrun = True

        self.progress = 0
        self.downloading = False
        self.downloadfile = None

        self.timerDisplay = eTimer()

        self["downloadlist"] = List(self.drawList)
        self['downloadlist'].onSelectionChanged.append(self.selectionChanged)

        self["key_red"] = StaticText(_('Back'))
        self["key_green"] = StaticText(_('Download'))
        self['key_blue'] = StaticText(_('Remove'))

        self["diskspace"] = StaticText()

        self['actions'] = ActionMap(['XStreamityActions'], {
            'red': self.keyCancel,
            'cancel': self.keyCancel,
            'green': self.download,
            'ok': self.download,
            'blue': self.delete,
        }, -2)

        self.onFirstExecBegin.append(self.start)
        self.onLayoutFinish.append(self.__layoutFinished)

    def __layoutFinished(self):
        self.setTitle(self.setup_title)

    def start(self):
        self.readJsonFile()
        self.diskspace()
        self.getDownloadSize()
        self.checkactivedownloads()
        self.buildList()
        self.saveJson()

        try:
            self.timerDisplay.callback.append(self.updatescreen)
        except:
            self.timerDisplay_conn = self.timerDisplay.timeout.connect(self.updatescreen)

        self.timerDisplay.start(5000, False)

    def readJsonFile(self):
        if os.path.isfile(downloads_json):
            with open(downloads_json, "r") as f:
                try:
                    self.downloads_all = json.load(f)
                except:
                    pass

    def diskspace(self):
        try:
            stat = os.statvfs(cfg.downloadlocation.value)
            free = convert_size(float(stat.f_bfree * stat.f_bsize))
            total = convert_size(float(stat.f_blocks * stat.f_bsize))
        except Exception as e:
            print("** diskspace failed **")
            print(e)
            free = "-?-"
            total = "-?-"

        self["diskspace"].setText(_('Free Space:') + " " + str(free) + " " + _("of") + " " + str(total))

    def checkRedirect(self, url):
        # print("*** check redirect ***")
        try:
            x = requests.get(url, timeout=20, verify=False, stream=True)
            # print("**** redirect url 1 *** %s" % x.url)
            return str(x.url)
        except Exception as e:
            print(e)
            # print("**** redirect url 2 *** %s" % url)
            return str(url)

    def getDownloadSize(self):
        x = 0
        for video in self.downloads_all:
            url = video[2]

            url = self.checkRedirect(url)

            length = video[5]

            if length == 0:
                try:
                    r = requests.get(url, timeout=10, verify=False, stream=True)
                    video[5] = float(r.headers['content-length'])
                except Exception as e:
                    print(e)
                    self.session.open(MessageBox, _('Download Error') + "\n\n" + str(url) + "\n\n" + str(e), type=MessageBox.TYPE_ERROR)
                    video[5] = 0
                    continue
                x += 1
                if x == 3:
                    x = 0
                    time.sleep(1)
        self.saveJson()

    def checkactivedownloads(self):
        self.downloading = False
        x = 0
        for video in self.downloads_all:
            if video[3] == _("Downloading"):
                self.downloading = True

                try:
                    self.extension = str(os.path.splitext(video[2])[-1])
                except:
                    self.extension = ""

                self.filmtitle = video[1]

                cleanName = re.sub(r'[\<\>\:\"\/\\\|\?\*]', ' ', str(self.filmtitle))
                cleanName = re.sub(r'  ', ' ', cleanName)

                filename = str(cleanName) + str(self.extension)

                self.path = str(cfg.downloadlocation.getValue()) + str(filename)
                self.downloadingindex = x

                totalbytes = self.downloads_all[self.downloadingindex][5]
                recbytes = os.path.getsize(self.path)
                if totalbytes == recbytes:
                    self.downloads_all[self.downloadingindex][3] = _("Finished")
                    self.downloads_all[self.downloadingindex][4] = 100
                    self.downloading = False
                break

            x += 1

    def buildList(self):
        self.drawList = []
        self.drawList = [self.buildListEntry(x[0], x[1], x[2], x[3], x[4], x[5]) for x in self.downloads_all]
        self["downloadlist"].setList(self.drawList)

    def updatescreen(self):
        if self.downloading:
            self.diskspace()
            self.getprogress()

    def getprogress(self):
        if os.path.exists(self.path):
            totalbytes = self.downloads_all[self.downloadingindex][5]
            recbytes = os.path.getsize(self.path)
            if self.downloads_all[self.downloadingindex][5] != 0:
                self.progress = int(100 * (float(recbytes) / totalbytes))
                if self.progress == 100:
                    try:
                        self.download_finished()
                        return
                    except:
                        pass
                self.downloads_all[self.downloadingindex][4] = self.progress
                self.buildList()

    def saveJson(self):
        with open(downloads_json, 'w') as f:
            json.dump(self.downloads_all, f)

    def selectionChanged(self):
        if self["downloadlist"].getCurrent():
            currentindex = self["downloadlist"].getIndex()

            if self.downloads_all[currentindex][3] != _("Not Started"):
                self["key_green"].setText(_('Cancel'))
            else:
                self["key_green"].setText(_('Download'))

    def keyCancel(self, answer=None):
        self.saveJson()
        self.close()

    def cancelDownload(self, answer=None):
        if answer is None:
            self.session.openWithCallback(self.cancelDownload, MessageBox, _('Cancel this download?'))
        elif answer:
            self.download_cancelled()
        else:
            return

    def delete(self):
        if self["downloadlist"].getCurrent():
            currentindex = self["downloadlist"].getIndex()

            if self.downloads_all[currentindex][3] == _("Downloading"):
                self.download_cancelled()

            del self.downloads_all[currentindex]
            self.saveJson()
            self.start()

    def download_cancelled(self, data=None):
        self.progress = 0
        if self.downloading:
            if self.downloadfile:
                try:
                    self.downloadfile = None
                except Exception as e:
                    print(e)

        try:
            print("*** killing wget downloads ***")
            cmd = 'pkill -9 wget'
            os.popen(cmd)
        except Exception as e:
            print(e)

        try:
            os.remove(self.path)
        except:
            pass

        self.downloads_all[self.downloadingindex][3] = _("Not Started")
        self.downloads_all[self.downloadingindex][4] = 0
        self.downloading = False
        self.saveJson()
        self.buildList()

    def download(self):
        if not os.path.exists(cfg.downloadlocation.value) or cfg.downloadlocation.value is None:
            self.session.open(MessageBox, _('Vod Download folder location does not exist.\n\n' + str(cfg.downloadlocation.value) + 'Please set download folder in Main Settings.'), type=MessageBox.TYPE_WARNING)
            return

        if self["downloadlist"].getCurrent():
            self.url = self["downloadlist"].getCurrent()[2]

            currentindex = self["downloadlist"].getIndex()

            if self.downloads_all[currentindex][3] == _("Finished"):
                self.session.open(MessageBox, _('File already downloaded.'), type=MessageBox.TYPE_INFO)
                return

            parsed_uri = urlparse(self.url)
            video_domain = parsed_uri.hostname

            if self.session.nav.getCurrentlyPlayingServiceReference():
                playingstream = self.session.nav.getCurrentlyPlayingServiceReference().toString()

                if str(video_domain) in playingstream:
                    # stop iptv
                    if self.session.nav.getCurrentlyPlayingServiceReference():
                        self.session.nav.stopService()

            if self.downloading is False:
                if self.downloads_all[currentindex][3] == _("Not Started"):
                    self.downloads_all[currentindex][3] = _("Downloading")
                    self.downloads_all[currentindex][4] = 0

                    self.downloadingindex = currentindex

                    self.progress = 0
                    self.downloading = True

                    try:
                        self.extension = str(os.path.splitext(self.url)[-1])
                    except:
                        self.extension = ""

                    self.filmtitle = self["downloadlist"].getCurrent()[1]

                    cleanName = re.sub(r'[\<\>\:\"\/\\\|\?\*]', ' ', str(self.filmtitle))
                    cleanName = re.sub(r'  ', ' ', cleanName)
                    filename = str(cleanName) + str(self.extension)
                    self.shortpath = str(cfg.downloadlocation.getValue())
                    self.path = str(cfg.downloadlocation.getValue()) + str(filename)

                    self.buildList()

                    try:
                        cmd = "wget --tries=1 -c '%s' -O '%s%s'" % (self.url, self.shortpath, filename)
                        JobManager.AddJob(downloadJob(self, cmd, self.path, cleanName))
                        self.createMetaFile(filename, cleanName)
                    except Exception as e:
                        print("**** download error ***")
                        self.downloading = False
                        print(e)

            elif self.downloading is True:
                if self.downloads_all[currentindex][3] == _("Downloading"):
                    self.cancelDownload()
                elif self.downloads_all[currentindex][3] == _("Not Started"):
                    self.session.open(MessageBox, _('Multiple downloads not allowed. Please wait or cancel download.'), type=MessageBox.TYPE_INFO)
                    return

    def createMetaFile(self, filename, cleanName):
        try:
            serviceref = eServiceReference(4097, 0, self.shortpath + filename)
            metafile = open('%s/%s.meta' % (self.shortpath, filename), 'w')
            with open('%s/%s.meta' % (self.shortpath, filename), 'w') as f:
                f.write('%s\n%s\n%s\n%i\n' % (serviceref.toString(), cleanName, "", time.time()))
        except Exception as e:
            print(e)
            print('ERROR metaFile')
        return

    def download_failed(self, data=None):
        self.downloading = False
        if "400 Bad Request" not in str(data):
            self.session.openWithCallback(self.download_failed_error, MessageBox, _('Download Failed!\n') + str(data), MessageBox.TYPE_WARNING, timeout=5)

    def download_failed_error(self, data=None):
        print("**** download_failed_error %s" % data)
        self.download_cancelled()

    def download_finished(self, string=""):
        print("**** download finished ***")
        self.downloads_all[self.downloadingindex][3] = _("Finished")
        self.downloads_all[self.downloadingindex][4] = 100
        self.downloading = False
        self.saveJson()
        self.buildList()

    def buildListEntry(self, dtype, title, url, state, progress, length):
        progresspercent = str(progress) + "%"
        length = convert_size(length)
        return(str(dtype), str(title), str(url), str(state), int(progress), str(progresspercent), str(length))
