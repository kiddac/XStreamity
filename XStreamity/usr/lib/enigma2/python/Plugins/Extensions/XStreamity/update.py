#!/usr/bin/python
# -*- coding: utf-8 -*-


from .plugin import playlists_json, pythonVer, cfg, hdr
from . import xstreamity_globals as glob
from xml.etree.cElementTree import iterparse
from twisted.web.client import downloadPage
from requests.adapters import HTTPAdapter, Retry
try:
    from urlparse import urlparse
except:
    from urllib.parse import urlparse

import calendar
import json
import os
import requests
import time
import twisted.python.runtime
from time import time as rtime


try:
    from http.client import HTTPConnection
    HTTPConnection.debuglevel = 0
except:
    from httplib import HTTPConnection
    HTTPConnection.debuglevel = 0

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


class XStreamity_Update:
    def __init__(self, session=None, mode=None):
        # print("****** update ****")
        self.mode = mode
        recordings = ""
        next_rec_time = -1

        recordings = session.nav.getRecordings()
        if not recordings:
            next_rec_time = session.nav.RecordTimer.getNextRecordingTime()

        if recordings or (next_rec_time > 0 and (next_rec_time - rtime()) < 360):
            print("*** recording in progress ***")

        else:
            self.epgfolder = ""
            self.epgxmlfile = ""
            self.epgjsonfile = ""
            self.processJsonFile()

    def clear_caches(self):
        try:
            with open("/proc/sys/vm/drop_caches", "w") as drop_caches:
                drop_caches.write("1\n2\n3\n")
        except IOError:
            pass

    def checkRedirect(self, url):
        # print("*** check redirect ***")
        x = ""
        retries = Retry(total=3, backoff_factor=1)
        adapter = HTTPAdapter(max_retries=retries)
        http = requests.Session()
        http.mount("http://", adapter)
        http.mount("https://", adapter)
        try:
            x = http.get(url, headers=hdr, timeout=30, verify=False, stream=True)
            url = x.url
            x.close()
            return str(url)
        except Exception as e:
            print(e)
            return str(url)

    def processJsonFile(self):
        # print("*** processJsonFile ***")
        try:
            with open(playlists_json, "r") as f:
                self.playlists_all = json.load(f)
        except Exception as e:
            print(e)
            return

        self.urllist = []

        if self.mode == "manual":
            playlist = glob.current_playlist
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

                    exists = any(str(domain) == str(x[0]) for x in self.urllist)
                    if exists:
                        continue
                    self.urllist.append([domain, xmltv, epgxmlfile, epgjsonfile])

                    if not os.path.exists(epgfolder):
                        os.makedirs(epgfolder)

        self.processPlaylist()
        self.clear_caches()

    def processPlaylist(self):
        # print("*** processPlaylist ***")
        if self.urllist:
            xmltv = self.urllist[0][1]
            try:
                self.downloadxmltv(str(xmltv))
            except Exception as e:
                print(e)

    # new epg code
    def downloadxmltv(self, url):
        # print("**** downloadxmltv ***")
        epgxmlfile = self.urllist[0][2]

        url = self.checkRedirect(url)
        time.sleep(1)

        try:
            parsed = urlparse(url)
            domain = parsed.hostname
            scheme = parsed.scheme

            if pythonVer == 3:
                url = url.encode()

            if scheme == "https" and sslverify:
                sniFactory = SNIFactory(domain)
                downloadPage(url, epgxmlfile, sniFactory, timeout=120).addCallback(self.downloadComplete).addErrback(self.downloadFailed)
            else:
                downloadPage(url, epgxmlfile, timeout=120).addCallback(self.downloadComplete).addErrback(self.downloadFailed)

        except Exception as e:
            print(e)
            try:
                os.remove(epgxmlfile)
            except Exception as e:
                print(e)

            self.downloadFailed()

    def downloadComplete(self, data=None):
        # print("**** downloadComplete ***")
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
        # print("*** downloadFailed ***")
        print(data)
        self.urllist.pop(0)
        if self.urllist:
            self.processPlaylist()
        else:
            return

    def createJsonFail(self, data=None):
        # print("**** createjsonfail ***")
        epgjsonfile = self.urllist[0][3]
        print(("Create Json failed:", data))
        try:
            os.remove(epgjsonfile)
        except:
            pass
        self.urllist.pop(0)
        if self.urllist:
            self.processPlaylist()
        else:
            return

    def buildjson(self):
        # print("*** buildjson ***")
        epgitems = {}
        nowtime = calendar.timegm(time.gmtime())
        epgjsonfile = self.urllist[0][3]
        epgxmlfile = self.urllist[0][2]

        for channel, start, stop, title, desc in self.buildjson2():
            start = get_time_utc(start, quickptime)
            stop = get_time_utc(stop, quickptime)

            if start < nowtime + (3600 * 24) and stop > start and stop > nowtime:
                if channel in epgitems:
                    epgitems[channel].append([start, stop, title, desc])
                else:
                    epgitems[channel] = [[start, stop, title, desc]]

        with open(epgjsonfile, "w") as jsonFile:
            json.dump(epgitems, jsonFile, ensure_ascii=False)

        try:
            os.remove(epgxmlfile)
        except:
            pass
        epgitems.clear()
        self.urllist.pop(0)
        if self.urllist:
            self.processPlaylist()
        else:
            return

    def buildjson2(self):
        # print("***** buildjson2 *****")
        fileobj = self.urllist[0][2]
        try:
            for event, elem in iterparse(fileobj):

                if elem.tag == "channel":
                    elem.clear()

                if elem.tag == "programme":
                    channel = elem.get("channel")
                    if channel:
                        try:
                            start = elem.get("start")
                            stop = elem.get("stop")
                        except:
                            continue

                        try:
                            title = elem.find("title").text
                        except:
                            title = ""

                        try:
                            desc = elem.find("desc").text
                        except:
                            desc = ""

                        if channel and start and stop:
                            yield channel.lower(), start, stop, title or "", desc or ""
                    elem.clear()
        except Exception as e:
            print("*** bad data in xml file *** %s" % fileobj)
            print(e)
