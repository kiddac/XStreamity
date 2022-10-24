#!/usr/bin/python
# -*- coding: utf-8 -*-

# https://mkvtoolnix.download/samples/
# https://github.com/OpenSPA/TVWeb/blob/master/usr/lib/enigma2/python/Plugins/Extensions/TVweb/plugin.py
# https://github.com/openatv/enigma2/blob/7.0/lib/python/Components/Task.py
# https://github.com/openatv/enigma2/blob/7.0/lib/python/Screens/TaskView.py

from . import _
from .plugin import skin_path, downloads_json, cfg, pythonVer, hdr
from .xStaticText import StaticText

from Components.ActionMap import ActionMap
from Components.Sources.List import List
from Screens.MessageBox import MessageBox
from Screens.Screen import Screen
from enigma import eTimer, eServiceReference
from requests.adapters import HTTPAdapter

from Components.Task import job_manager as JobManager
from Components.Task import Task, Job, Condition

try:
    from urlparse import urlparse
except:
    from urllib.parse import urlparse

import json
import math
import os
import re
import requests
import subprocess
import time

ui = False


def convert_size(size_bytes):
    if size_bytes == 0:
        return "0B"
    size_name = ("B", "KB", "MB", "GB", "TB")
    i = int(math.floor(math.log(size_bytes, 1024)))
    p = math.pow(1024, i)
    s = round(size_bytes / p, 2)
    return "%s %s" % (s, size_name[i])


class downloadJob(Job):
    def __init__(self, toolbox, cmdline, filename, filmtitle):
        Job.__init__(self, filmtitle)
        self.filename = filename
        self.toolbox = toolbox
        self.retrycount = 0
        downloadTask(self, cmdline, filename, filmtitle)

    def retry(self):
        self.retrycount += 1
        self.restart()

    def cancel(self):
        self.abort()
        # os.system("rm -f %s" % self.filename)


# downloadtask code borrowed from old video plugins
class downloadTask(Task):

    if pythonVer == 3:
        ERROR_CORRUPT_FILE, ERROR_RTMP_ReadPacket, ERROR_SEGFAULT, ERROR_SERVER, ERROR_UNKNOWN = list(range(5))
    else:
        ERROR_CORRUPT_FILE, ERROR_RTMP_ReadPacket, ERROR_SEGFAULT, ERROR_SERVER, ERROR_UNKNOWN = range(5)

    def __init__(self, job, cmdline, filename, filmtitle):
        Task.__init__(self, job, filmtitle)
        self.postconditions.append(downloadTaskPostcondition())
        self.toolbox = job.toolbox
        self.setCmdline(cmdline)
        self.filename = filename
        self.filmtitle = filmtitle
        self.error = None
        self.lasterrormsg = None
        self.progress = 0
        self.lastprogress = 0
        self.firstrun = True

    def processOutput(self, data):
        global ui
        if pythonVer == 3:
            data = str(data)
        try:
            if data.find("%") != -1:
                tmpvalue = re.findall(r'(\d+?%)', data)[-1].rstrip("%")
                self.progress = int(float(tmpvalue))

                if self.firstrun:
                    self.firstrun = False
                    if ui:
                        self.toolbox.updatescreen()

                if self.progress == 100 or self.progress != self.lastprogress:
                    self.lastprogress = self.progress
                    if ui:
                        self.toolbox.updatescreen()

                else:
                    Task.processOutput(self, data)

        except Exception as errormsg:
            print("Error processOutput: " + str(errormsg))
            Task.processOutput(self, data)

    def processOutputLine(self, line):
        pass

    def afterRun(self):
        if self.getProgress() == 100 or self.progress == 100:
            try:
                self.toolbox.download_finished(self.filename, self.filmtitle)
            except Exception as e:
                print(e)


class downloadTaskPostcondition(Condition):
    RECOVERABLE = True

    def check(self, task):
        if task.returncode == 0 or task.error is None:
            return True
        else:
            return False

    def getErrorMessage(self, task):
        return {
            task.ERROR_CORRUPT_FILE: _("Video Download Failed!\n\nCorrupted Download File:\n%s" % task.lasterrormsg),
            task.ERROR_RTMP_ReadPacket: _("Video Download Failed!\n\nCould not read RTMP-Packet:\n%s" % task.lasterrormsg),
            task.ERROR_SEGFAULT: _("Video Download Failed!\n\nSegmentation fault:\n%s" % task.lasterrormsg),
            task.ERROR_SERVER: _("Video Download Failed!\n\nServer returned error:\n%s" % task.lasterrormsg),
            task.ERROR_UNKNOWN: _("Video Download Failed!\n\nUnknown Error:\n%s" % task.lasterrormsg)
        }[task.error]


class XStreamity_DownloadManager(Screen):

    def __init__(self, session):
        global ui
        ui = True
        Screen.__init__(self, session)

        self.session = session
        skin = skin_path + "downloadmanager.xml"

        with open(skin, "r") as f:
            self.skin = f.read()

        self.setup_title = (_("VOD Download Manager"))
        self.onChangedEntry = []

        self.list = []
        self.drawList = []
        self.firstrun = True

        self.progress = 0
        self.timerDisplay = eTimer()

        self["downloadlist"] = List(self.drawList)
        self["downloadlist"].onSelectionChanged.append(self.selectionChanged)

        self["key_red"] = StaticText(_("Back"))
        self["key_green"] = StaticText(_("Download"))
        self["key_blue"] = StaticText(_("Remove"))

        self["diskspace"] = StaticText()

        self["actions"] = ActionMap(["XStreamityActions"], {
            "red": self.keyCancel,
            "cancel": self.keyCancel,
            "green": self.download,
            "ok": self.download,
            "blue": self.delete,
        }, -2)

        self.onFirstExecBegin.append(self.start)
        self.onLayoutFinish.append(self.__layoutFinished)

    def __layoutFinished(self):
        self.setTitle(self.setup_title)

    def cleantitle(self, title):
        cleanName = re.sub(r'[\'\<\>\:\"\/\\\|\?\*\(\)\[\]]', "", str(title))
        cleanName = re.sub(r"   ", " ", cleanName)
        cleanName = re.sub(r"  ", " ", cleanName)
        cleanName = re.sub(r" ", "-", cleanName)
        cleanName = cleanName.strip()
        return cleanName

    def start(self):
        self.readJsonFile()
        self.diskspace()
        self.getDownloadSize()
        self.checkactivedownloads()
        self.resumeDownloads()

    def readJsonFile(self):
        if os.path.isfile(downloads_json):
            with open(downloads_json, "r") as f:
                try:
                    self.downloads_all = json.load(f)
                except Exception as e:
                    print(e)

    def diskspace(self):
        try:
            stat = os.statvfs(cfg.downloadlocation.value)
            free = convert_size(float(stat.f_bfree * stat.f_bsize))
            total = convert_size(float(stat.f_blocks * stat.f_bsize))
        except Exception as e:
            print(e)
            free = "-?-"
            total = "-?-"
        self["diskspace"].setText(_("Free Space:") + " " + str(free) + " " + _("of") + " " + str(total))

    def getDownloadSize(self):
        x = 0
        templist = []
        for video in self.downloads_all:
            video[1] = self.cleantitle(video[1])  # make safe filename
            url = video[2]
            # length = video[5]
            adapter = HTTPAdapter()
            http = requests.Session()
            http.mount("http://", adapter)
            http.mount("https://", adapter)

            try:
                r = http.get(url, headers=hdr, timeout=10, verify=False, stream=True)
                # print("response", r)
                video[5] = float(r.headers["content-length"])
                templist.append(video)
                r.close()
            except Exception as e:
                print(e)
                video[5] = 0
                templist.append(video)
            x += 1
            if x == 5:
                x = 0
                time.sleep(1)

        self.downloads_all[:] = templist

    def checkactivedownloads(self):
        # x = 0
        templist = []
        for video in self.downloads_all:
            recbytes = 0
            filmtitle = str(video[1])

            try:
                extension = str(os.path.splitext(video[2])[-1])
            except Exception as e:
                print(e)
                extension = ""

            filename = str(filmtitle) + str(extension)
            path = str(cfg.downloadlocation.getValue()) + str(filename)
            totalbytes = video[5]

            if os.path.exists(path):
                recbytes = os.path.getsize(path)
                if int(totalbytes) != int(recbytes):
                    templist.append(video)
            else:
                templist.append(video)

        self.downloads_all[:] = templist
        self.buildList()
        self.saveJson()

    def resumeDownloads(self):

        jobs = JobManager.getPendingJobs()
        if len(jobs) >= 1:
            for jobentry in jobs:
                try:
                    JobManager.active_jobs.remove(jobentry)
                except:
                    pass

                try:
                    jobentry.cancel()
                except:
                    pass

            try:
                os.system("killall -9 wget")
            except:
                pass

        for video in self.downloads_all:
            filmtitle = str(video[1])
            try:
                extension = str(os.path.splitext(video[2])[-1])
            except Exception as e:
                print(e)
                extension = ""

            filename = str(filmtitle) + str(extension)
            shortpath = str(cfg.downloadlocation.getValue())
            path = str(cfg.downloadlocation.getValue()) + str(filename)
            url = video[2]
            state = video[3]

            parsed_uri = urlparse(url)
            video_domain = parsed_uri.hostname

            if state != "Not Started":

                if self.session.nav.getCurrentlyPlayingServiceReference():
                    playingstream = self.session.nav.getCurrentlyPlayingServiceReference().toString()

                    if str(video_domain) in playingstream:
                        # stop iptv
                        if self.session.nav.getCurrentlyPlayingServiceReference():
                            self.session.nav.stopService()

                cmd = "wget -U 'Enigma2 - XStreamity Plugin' -c '%s' -O '%s%s'" % (url, shortpath, filename)

                if "https" in str(url):
                    cmd = "wget --no-check-certificate -U 'Enigma2 - XStreamity Plugin' -c '%s' -O '%s%s'" % (url, shortpath, filename)

                try:
                    JobManager.AddJob(downloadJob(self, cmd, path, filmtitle))
                except Exception as e:
                    print(e)

        self.updatescreen()

    def buildList(self):
        self.drawList = []
        self.drawList = [self.buildListEntry(x[0], x[1], x[2], _(x[3]), x[4], x[5]) for x in self.downloads_all]
        self["downloadlist"].setList(self.drawList)

    def updatescreen(self):
        self.diskspace()
        self.getprogress()

    def sortlist(self):
        order = {"In progress": 0, "Waiting": 1, "Not Started": 2}
        self.downloads_all.sort(key=lambda x: order[x[3]])
        self.buildList()

    def getprogress(self):
        jobs = JobManager.getPendingJobs()
        if len(jobs) >= 1:
            for jobentry in jobs:
                jobname = str(jobentry.name)
                for video in self.downloads_all:
                    title = str(video[1])
                    if title == jobname:
                        video[3] = jobentry.getStatustext()
                        video[4] = jobentry.progress
                        self.buildList()
                        break

    def saveJson(self):
        with open(downloads_json, "w") as f:
            json.dump(self.downloads_all, f)

    def selectionChanged(self):
        if self["downloadlist"].getCurrent():
            # currentindex = self["downloadlist"].getIndex()

            if self["downloadlist"].getCurrent()[3] != _("Not Started"):
                self["key_green"].setText(_("Cancel"))
            else:
                self["key_green"].setText(_("Download"))

    def keyCancel(self, answer=None):
        global ui
        ui = False
        self.saveJson()
        self.close()

    def download(self):
        if not os.path.exists(cfg.downloadlocation.value) or cfg.downloadlocation.value is None:
            self.session.open(MessageBox, _("Vod Download folder location does not exist.\n\n" + str(cfg.downloadlocation.value) + _("Please set download folder in Main Settings.")), type=MessageBox.TYPE_WARNING)
            return

        if self["downloadlist"].getCurrent():

            filmtitle = self["downloadlist"].getCurrent()[1]

            self.url = self["downloadlist"].getCurrent()[2]

            try:
                self.extension = str(os.path.splitext(self.url)[-1])
            except:
                self.extension = ""

            filename = str(filmtitle) + str(self.extension)
            self.shortpath = str(cfg.downloadlocation.getValue())
            self.path = str(cfg.downloadlocation.getValue()) + str(filename)

            parsed_uri = urlparse(self.url)
            video_domain = parsed_uri.hostname

            if self["downloadlist"].getCurrent()[3] == _("Not Started"):

                if self.session.nav.getCurrentlyPlayingServiceReference():
                    playingstream = self.session.nav.getCurrentlyPlayingServiceReference().toString()

                    if str(video_domain) in playingstream:
                        # stop iptv
                        if self.session.nav.getCurrentlyPlayingServiceReference():
                            self.session.nav.stopService()

                cmd = "wget -U 'Enigma2 - XStreamity Plugin' -c '%s' -O '%s%s'" % (self.url, self.shortpath, filename)

                if "https" in str(self.url):
                    checkcmd = "strings $(which wget) | grep no-check-certificate"
                    if pythonVer == 2:
                        result = subprocess.call(checkcmd, shell=True)
                        if result == 0:
                            cmd = "wget --no-check-certificate -U 'Enigma2 - XStreamity Plugin' -c '%s' -O '%s%s'" % (self.url, self.shortpath, filename)
                        else:
                            self.session.open(MessageBox, _("Please update your wget library to download https lines\n\nopkg update\nopkg install wget"), type=MessageBox.TYPE_INFO)
                    else:
                        result = subprocess.run(checkcmd, shell=True)
                        if result.returncode == 0:
                            cmd = "wget --no-check-certificate -U 'Enigma2 - XStreamity Plugin' -c '%s' -O '%s%s'" % (self.url, self.shortpath, filename)
                        else:
                            self.session.open(MessageBox, _("Please update your wget library to download https lines\n\nopkg update\nopkg install wget"), type=MessageBox.TYPE_INFO)

                try:
                    JobManager.AddJob(downloadJob(self, cmd, self.path, filmtitle))
                except Exception as e:
                    print(e)

                try:
                    self.updatescreen()
                    self.sortlist()
                    self["downloadlist"].setIndex(0)
                    self.saveJson()
                except Exception as e:
                    print(e)

            else:
                if self["downloadlist"].getCurrent()[3] == _("Waiting"):
                    self.cancelJob(filmtitle)
                elif self["downloadlist"].getCurrent()[3] == _("In progress"):
                    self.cancelDownload()

    def cancelJob(self, filmtitle):
        jobs = JobManager.getPendingJobs()
        if len(jobs) >= 1:
            for job in jobs:
                jobname = str(job.name)
                if filmtitle == jobname:
                    JobManager.active_jobs.remove(job)
                    break

            for video in self.downloads_all:
                if str(video[1]) == str(filmtitle):
                    video[3] = "Not Started"

            self.buildList()
            self.saveJson()

    def cancelDownload(self, answer=None):
        if answer is None:
            self.session.openWithCallback(self.cancelDownload, MessageBox, _("Cancel this download?"))
        elif answer:
            self.download_cancelled()
        else:
            return

    def download_cancelled(self, data=None):
        jobs = JobManager.getPendingJobs()
        if len(jobs) >= 1:
            activejob = jobs[0]
            jobname = str(activejob.name)
            activejob.cancel()
            for video in self.downloads_all:
                filmtitle = str(video[1])

                if filmtitle == str(jobname):
                    video[3] = "Not Started"
                    break

        self.sortlist()

    def delete(self):
        if self["downloadlist"].getCurrent():
            currentindex = self["downloadlist"].getIndex()

            if self.downloads_all[currentindex][3] == "In progress":
                self.download_cancelled()
            else:
                self.delete_entry()

    def delete_entry(self, answer=None):
        if answer is None:
            self.session.openWithCallback(self.delete_entry, MessageBox, _("Delete this entry?"))
        elif answer:
            currentindex = self["downloadlist"].getIndex()
            del self.downloads_all[currentindex]
            self.saveJson()
            self.buildList()
        else:
            return

    def createMetaFile(self, filename, filmtitle):
        try:
            serviceref = eServiceReference(4097, 0, filename)
            with open("%s.meta" % (filename), "w") as f:
                f.write("%s\n%s\n%s\n%i\n" % (serviceref.toString(), filmtitle, "", time.time()))
        except Exception as e:
            print(e)
        return

    def download_finished(self, filename, filmtitle):
        global ui
        if os.path.isfile(downloads_json):
            with open(downloads_json, "r") as f:
                try:
                    self.downloads_all = json.load(f)
                except Exception as e:
                    print(e)

        x = 0
        for video in self.downloads_all:
            if str(video[1]) == str(filmtitle):
                break
            x += 1
        del self.downloads_all[x]
        self.createMetaFile(filename, filmtitle)
        if ui:
            self.buildList()
        self.saveJson()

    def buildListEntry(self, dtype, title, url, state, progress, length):
        progresspercent = str(progress) + "%"
        length = convert_size(length)
        return (str(dtype), str(title), str(url), str(state), int(progress), str(progresspercent), str(length))
