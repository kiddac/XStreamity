#!/usr/bin/python
# -*- coding: utf-8 -*-

# Standard library imports
from __future__ import division
import calendar
import json
import os
import time
from time import time as rtime
from xml.etree.cElementTree import iterparse

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
import requests
from requests.adapters import HTTPAdapter, Retry
import twisted.python.runtime
from twisted.web.client import downloadPage

# Local application/library-specific imports
from . import xstreamity_globals as glob
from .plugin import pythonVer, cfg

# https twisted client hack #
sslverify = False
try:
    from twisted.internet import ssl
    from twisted.internet._sslverify import ClientTLSOptions
    sslverify = True
except ImportError:
    pass

if sslverify:
    class SNIFactory(ssl.ClientContextFactory):
        def __init__(self, hostname=None):
            self.hostname = hostname

        def getContext(self):
            ctx = self._contextFactory(self.method)
            if self.hostname:
                ClientTLSOptions(self.hostname, ctx)
            return ctx


def quickptime(str):
    return time.struct_time((int(str[0:4]), int(str[4:6]), int(str[6:8]), int(str[8:10]), int(str[10:12]), 0, 1, -1, 0))


def get_time_utc(timestring, fdateparse):
    try:
        values = timestring.split(" ")
        tm = fdateparse(values[0])
        timegm = calendar.timegm(tm)
        timegm -= (3600 * int(values[1]) / 100)
        return timegm
    except Exception as e:
        print("[XMLTVConverter] get_time_utc error:", e)
        return 0


hdr = {
    'User-Agent': str(cfg.useragent.value),
    'Accept-Encoding': 'gzip, deflate'
}

playlists_json = cfg.playlists_json.value


class XStreamity_Update:
    def __init__(self, session=None, mode=None):
        self.mode = mode
        self.session = session
        self.urllist = []
        if not self.check_recordings_in_progress():
            self.process_json_file()

    def check_recordings_in_progress(self):
        recordings = self.session.nav.getRecordings()
        next_rec_time = -1

        if not recordings:
            next_rec_time = self.session.nav.RecordTimer.getNextRecordingTime()

        if recordings or (next_rec_time > 0 and (next_rec_time - rtime()) < 360):
            return True
        else:
            return False

    def clear_caches(self):
        try:
            with open("/proc/sys/vm/drop_caches", "w") as drop_caches:
                drop_caches.write("1\n2\n3\n")
        except IOError:
            pass

    def check_redirect(self, url):
        retries = Retry(total=3, backoff_factor=1)
        adapter = HTTPAdapter(max_retries=retries)

        with requests.Session() as http:
            http.mount("http://", adapter)
            http.mount("https://", adapter)

            try:
                response = http.get(url, headers=hdr, timeout=30, verify=False, stream=True)
                url = response.url
                return str(url)
            except Exception as e:
                print(e)
                return str(url)

    def process_json_file(self):
        try:
            with open(playlists_json, "r") as f:
                self.playlists_all = json.load(f)
        except Exception as e:
            print("Error loading playlists JSON file:", e)
            return

        self.urllist = []

        if self.mode == "manual":
            playlist = glob.active_playlist
            if "user_info" in playlist and "auth" in playlist["user_info"] and str(playlist["user_info"]["auth"]) == "1":
                domain = playlist["playlist_info"]["domain"]
                name = playlist["playlist_info"]["name"]
                xmltv = playlist["playlist_info"]["xmltv_api"]
                epglocation = str(cfg.epglocation.value)
                epgfolder = os.path.join(epglocation, str(name))
                epgxmlfile = os.path.join(epgfolder, "epg.xml")
                epgjsonfile = os.path.join(epgfolder, "epg.json")

                self.urllist.append([domain, xmltv, epgxmlfile, epgjsonfile])

                if not os.path.exists(epgfolder):
                    os.makedirs(epgfolder)
        else:
            for playlist in self.playlists_all:
                if "user_info" in playlist and "auth" in playlist["user_info"] and str(playlist["user_info"]["auth"]) == "1":
                    domain = playlist["playlist_info"]["domain"]
                    name = playlist["playlist_info"]["name"]
                    xmltv = playlist["playlist_info"]["xmltv_api"]
                    epglocation = str(cfg.epglocation.value)
                    epgfolder = os.path.join(epglocation, str(name))
                    epgxmlfile = os.path.join(epgfolder, "epg.xml")
                    epgjsonfile = os.path.join(epgfolder, "epg.json")

                    if xmltv in [x[1] for x in self.urllist]:
                        continue

                    self.urllist.append([domain, xmltv, epgxmlfile, epgjsonfile])

                    if not os.path.exists(epgfolder):
                        os.makedirs(epgfolder)

        self.processPlaylist()
        self.clear_caches()

    def processPlaylist(self):
        if self.urllist:
            xmltv = self.urllist[0][1]
            try:
                self.downloadxmltv(str(xmltv))
            except Exception as e:
                print(e)

    def downloadxmltv(self, url):
        epgxmlfile = self.urllist[0][2]

        url = self.check_redirect(url)
        time.sleep(1)

        try:
            parsed = urlparse(url)
            domain = parsed.hostname
            scheme = parsed.scheme

            if pythonVer == 3:
                url = url.encode()

            if scheme == "https" and sslverify:
                sniFactory = SNIFactory(domain)
                downloadPage(url, epgxmlfile, sniFactory).addCallback(self.downloadComplete).addErrback(self.downloadFailed)
            else:
                downloadPage(url, epgxmlfile).addCallback(self.downloadComplete).addErrback(self.downloadFailed)

        except Exception as e:
            print(e)
            try:
                os.remove(epgxmlfile)
            except Exception as e:
                print(e)

            self.downloadFailed(str(e))

    def downloadComplete(self, data=None):
        if twisted.python.runtime.platform.supportsThreads():
            from twisted.internet import threads
            try:
                d = threads.deferToThread(self.buildjson)
                d.addErrback(self.createJsonFail)
            except Exception as e:
                print(e)

                try:
                    self.buildjson()
                except Exception as e:
                    print(e)
                    self.createJsonFail(e)
        else:
            try:
                self.buildjson()
            except Exception as e:
                print(e)
                self.createJsonFail(e)

    def downloadFailed(self, data=None):
        print(data)
        self.urllist.pop(0)
        if self.urllist:
            self.processPlaylist()

    def createJsonFail(self, data=None):
        epgjsonfile = self.urllist[0][3]
        print(("Create Json failed:", data))
        try:
            os.remove(epgjsonfile)
        except:
            pass
        self.urllist.pop(0)
        if self.urllist:
            self.processPlaylist()

    def buildjson(self):
        epgitems = {}
        nowtime = calendar.timegm(time.gmtime())
        epgjsonfile = self.urllist[0][3]
        epgxmlfile = self.urllist[0][2]

        for channel, start, stop, title, desc in self.buildjson2():
            start = get_time_utc(start, quickptime)
            stop = get_time_utc(stop, quickptime)

            if start < nowtime + (3600 * 24) and stop > start and stop > nowtime:
                epgitems.setdefault(channel, []).append([start, stop, title, desc])

        with open(epgjsonfile, "w") as jsonFile:
            json.dump(epgitems, jsonFile, ensure_ascii=False, indent=4)

        if os.path.exists(epgxmlfile):
            os.remove(epgxmlfile)

        epgitems.clear()
        self.urllist.pop(0)
        if self.urllist:
            self.processPlaylist()

    def buildjson2(self):
        fileobj = self.urllist[0][2]
        try:
            for event, elem in iterparse(fileobj):

                if elem.tag == "channel":
                    elem.clear()

                if elem.tag == "programme":
                    channel = elem.get("channel")
                    if channel:
                        start = elem.get("start", "")
                        stop = elem.get("stop", "")
                        title = elem.findtext("title") or ""
                        desc = elem.findtext("desc") or ""

                        if start and stop:
                            yield channel.lower(), start, stop, title, desc
                    elem.clear()
        except Exception as e:
            print(e)
