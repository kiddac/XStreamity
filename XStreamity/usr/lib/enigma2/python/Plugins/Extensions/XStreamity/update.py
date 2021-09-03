#!/usr/bin/python
# -*- coding: utf-8 -*-


from .plugin import playlists_json, dir_etc
from Screens.Screen import Screen
from time import time
from xml.etree.cElementTree import iterparse
from twisted.internet import reactor, threads
from twisted.web.client import downloadPage

import calendar
import json
import os
import sys
import time
import twisted.python.runtime

try:
    pythonVer = sys.version_info.major
except:
    pythonVer = 2

# https twisted client hack #
try:
    from twisted.internet import ssl
    from twisted.internet._sslverify import ClientTLSOptions
    sslverify = True
except:
    sslverify = False

if sslverify:
    try:
        from urlparse import urlparse
    except:
        from urllib.parse import urlparse

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
        values = timestring.split(' ')
        tm = fdateparse(values[0])
        timegm = calendar.timegm(tm)
        timegm -= (3600 * int(values[1]) / 100)
        return timegm
    except Exception as e:
        print("[XMLTVConverter] get_time_utc error:", e)
        return 0


class XStreamity_Update:

    def __init__(self):

        # self.session = session

        self.epgfolder = ""
        self.epgxmlfile = ""
        self.epgjsonfile = ""

        # print("********** updating ***")

        self.processJsonFile()

    def processJsonFile(self):
        with open(playlists_json, "r") as f:
            self.playlists_all = json.load(f)

        self.urllist = []

        for playlist in self.playlists_all:
            if "auth" in playlist["user_info"]:
                if str(playlist["user_info"]["auth"]) == "1":
                    domain = playlist["playlist_info"]["domain"]
                    xmltv = playlist["playlist_info"]["xmltv_api"]
                    epgfolder = str(dir_etc) + "epg/" + str(domain)
                    epgxmlfile = str(epgfolder) + "/" + str("epg.xml")
                    epgjsonfile = str(epgfolder) + "/" + str("epg.json")
                    self.urllist.append([domain, xmltv, epgxmlfile, epgjsonfile])

            if not os.path.exists(epgfolder):
                os.makedirs(epgfolder)

        self.processPlaylist()

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

        try:
            if url.startswith("https") and sslverify:
                parsed_uri = urlparse(url)
                domain = parsed_uri.hostname
                sniFactory = SNIFactory(domain)
                if pythonVer == 3:
                    url = url.encode()
                downloadPage(url, epgxmlfile, sniFactory, timeout=120).addCallback(self.downloadComplete).addErrback(self.downloadFailed)

            else:
                if pythonVer == 3:
                    url = url.encode()
                downloadPage(url, epgxmlfile, timeout=120).addCallback(self.downloadComplete).addErrback(self.downloadFailed)

        except Exception as e:
            print(e)
            try:
                os.remove(epgxmlfile)
            except Exception as e:
                print(e)

            self.downloadFailed()

    def downloadComplete(self, data=None):
        # print("**** DreamOS downloadComplete ***")
        if os.path.exists('/var/lib/dpkg/status'):
            try:
                d = reactor.callFromThread(self.buildjson)
            except Exception as e:
                print(e)
                try:
                    self.buildjson()
                except Exception as e:
                    print(e)
                    self.createJsonFail(e)

        else:
            if twisted.python.runtime.platform.supportsThreads():
                # print("**** downloadComplete ***")
                try:
                    d = threads.deferToThread(self.buildjson)
                    d.addErrback(self.createJsonFail)
                except Exception as e:
                    print(e)
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
        else:
            return

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
        else:
            return

    def buildjson(self):
        # print("**** buildjson ***")
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

        if epgitems and epgitems != {}:
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

        for event, elem in iterparse(fileobj):

            if elem.tag == 'channel':
                elem.clear()

            if elem.tag == 'programme':
                channel = elem.get('channel')
                if channel:
                    try:
                        start = elem.get('start')
                        stop = elem.get('stop')
                    except:
                        continue

                    try:
                        title = elem.find('title').text
                    except:
                        title = ''

                    try:
                        desc = elem.find('desc').text
                    except:
                        desc = ''

                    if channel and start and stop:
                        yield channel.lower(), start, stop, title or "", desc or ""
                elem.clear()
