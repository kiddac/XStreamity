#!/usr/bin/python
# -*- coding: utf-8 -*-

# Standard library imports
from __future__ import division

import json
import glob as pythonglob
import os
import re
import shutil
from datetime import datetime

try:
    from http.client import HTTPConnection
    HTTPConnection.debuglevel = 0
except ImportError:
    from httplib import HTTPConnection
    HTTPConnection.debuglevel = 0

# Third-party imports
import requests
from requests.adapters import HTTPAdapter, Retry

# Enigma2 components
from Components.ActionMap import ActionMap
from Components.Pixmap import Pixmap
from Components.Sources.List import List
from enigma import eTimer
from Screens.MessageBox import MessageBox
from Screens.Screen import Screen
from Tools.LoadPixmap import LoadPixmap

# Local application/library-specific imports
from . import _
from . import xstreamity_globals as glob
from .plugin import skin_directory, cfg, common_path, version, hasConcurrent, hasMultiprocessing
from .xStaticText import StaticText
from . import checkinternet


epgimporter = os.path.isdir("/usr/lib/enigma2/python/Plugins/Extensions/EPGImport")

hdr = {
    'User-Agent': str(cfg.useragent.value),
    'Accept-Encoding': 'gzip, deflate'
}


class XStreamity_Playlists(Screen):
    ALLOW_SUSPEND = True

    def __init__(self, session):
        Screen.__init__(self, session)
        self.session = session

        skin_path = os.path.join(skin_directory, cfg.skin.value)
        skin = os.path.join(skin_path, "playlists.xml")
        with open(skin, "r") as f:
            self.skin = f.read()

        self.playlist_file = cfg.playlist_file.value
        self.playlists_json = cfg.playlists_json.value

        self.setup_title = _("Manage Playlists")

        self["key_red"] = StaticText(_("Back"))
        self["key_green"] = StaticText(_("OK"))
        self["key_yellow"] = StaticText(_("Delete"))
        self["key_blue"] = StaticText(_("Info"))
        self["version"] = StaticText(version)

        self.list = []
        self.drawList = []
        self["playlists"] = List(self.drawList, enableWrapAround=True)
        self["playlists"].onSelectionChanged.append(self.getCurrentEntry)
        self["splash"] = Pixmap()
        self["splash"].show()
        self["scroll_up"] = Pixmap()
        self["scroll_down"] = Pixmap()
        self["scroll_up"].hide()
        self["scroll_down"].hide()

        self._http = requests.Session()
        retries = Retry(total=1, backoff_factor=1)
        adapter = HTTPAdapter(max_retries=retries)
        self._http.mount("http://", adapter)
        self._http.mount("https://", adapter)

        self["actions"] = ActionMap(["XStreamityActions"], {
            "red": self.quit,
            "green": self.getStreamTypes,
            "cancel": self.quit,
            "ok": self.getStreamTypes,
            "blue": self.openUserInfo,
            "info": self.openUserInfo,
            "yellow": self.deleteServer,
            "0": self.goTop
        }, -2)

        self.onFirstExecBegin.append(self.start)
        self.onLayoutFinish.append(self.__layoutFinished)
        self.onClose.append(self.__onClose)

    def __onClose(self):
        try:
            self._http.close()
        except:
            pass
        self._http = None

    def clear_caches(self):
        try:
            with open("/proc/sys/vm/drop_caches", "w") as drop_caches:
                drop_caches.write("1\n2\n3\n")
        except IOError:
            pass

    def __layoutFinished(self):
        self.setTitle(self.setup_title)

    def start(self):

        if glob.original_playlist_file and glob.original_playlist_file:
            cfg.playlist_file.setValue(glob.original_playlist_file)
            cfg.playlists_json.setValue(glob.original_playlists_json)
            glob.current_selection = 0
            cfg.save()
            glob.original_playlist_file = ""
            glob.original_playlists_json = ""

        self.playlist_file = cfg.playlist_file.value
        self.playlists_json = cfg.playlists_json.value

        self.checkinternet = checkinternet.check_internet()
        if not self.checkinternet:
            self.session.openWithCallback(self.quit, MessageBox, _("No internet."), type=MessageBox.TYPE_ERROR, timeout=5)

        if epgimporter:
            self.epgimportcleanup()

        self.playlists_all = []

        # check if playlists.json file exists in specified location
        if os.path.isfile(self.playlists_json):
            with open(self.playlists_json, "r") as f:
                try:
                    self.playlists_all = json.load(f)
                    self.playlists_all.sort(key=lambda e: e["playlist_info"]["index"], reverse=False)
                except:
                    os.remove(self.playlists_json)

        if self.playlists_all and os.path.isfile(self.playlist_file) and os.path.getsize(self.playlist_file) > 0:
            self.delayedDownload()
        else:
            self.close()

        self.clear_caches()

    def delayedDownload(self):
        self.timer = eTimer()
        try:
            self.timer_conn = self.timer.timeout.connect(self.makeUrlList)
        except:
            try:
                self.timer.callback.append(self.makeUrlList)
            except:
                self.makeUrlList()
        self.timer.start(10, True)

    def makeUrlList(self):
        self.url_list = []
        for index, playlists in enumerate(self.playlists_all):
            player_api = str(playlists["playlist_info"].get("player_api", ""))
            full_url = str(playlists["playlist_info"].get("full_url", ""))
            domain = str(playlists["playlist_info"].get("domain", ""))
            username = str(playlists["playlist_info"].get("username", ""))
            password = str(playlists["playlist_info"].get("password", ""))
            if "get.php" in full_url and domain and username and password:
                self.url_list.append([player_api, index])

        if self.url_list:
            self.process_downloads()

    def download_url(self, url):
        index = url[1]
        response = None

        http = self._http
        try:
            with http.get(url[0], headers=hdr, timeout=6, verify=False) as r:
                r.raise_for_status()

                # Get Content-Type from headers
                content_type = r.headers.get('Content-Type', '')

                # Handle JSON content directly
                if 'application/json' in content_type:
                    try:
                        response = r.json()
                    except ValueError as e:
                        print("Error decoding JSON:", e, url)
                        return index, None

                # Handle text/html content
                elif 'text/html' in content_type:
                    try:
                        # Attempt to parse the HTML body as JSON
                        response_text = r.text
                        response = json.loads(response_text)
                    except json.JSONDecodeError as e:
                        print("Error decoding JSON from HTML content:", e, url)
                        return index, None

                else:
                    print("Final response is non-JSON content:", r.url)
                    return index, None

        except requests.exceptions.RequestException as e:
            print("Request error:", e)
        except Exception as e:
            print("Unexpected error:", e)

        return index, response

    def process_downloads(self):
        threads = min(len(self.url_list), 5)

        if hasConcurrent or hasMultiprocessing:
            if hasConcurrent:
                # print("******* trying concurrent futures ******")
                try:
                    from concurrent.futures import ThreadPoolExecutor
                    with ThreadPoolExecutor(max_workers=threads) as executor:
                        results = list(executor.map(self.download_url, self.url_list))
                except Exception as e:
                    print("Concurrent execution error:", e)

            elif hasMultiprocessing:
                # print("********** trying multiprocessing threadpool *******")
                try:
                    from multiprocessing.pool import ThreadPool
                    pool = ThreadPool(threads)
                    results = pool.imap_unordered(self.download_url, self.url_list)
                    pool.close()
                    pool.join()
                except Exception as e:
                    print("Multiprocessing execution error:", e)

            for index, response in results:
                if response:
                    self.playlists_all[index].update(response)
                else:
                    self.playlists_all[index]["user_info"] = {}

        else:
            # print("********** trying sequential download *******")
            for url in self.url_list:
                result = self.download_url(url)
                index = result[0]
                response = result[1]
                if response:
                    self.playlists_all[index].update(response)
                else:
                    self.playlists_all[index]["user_info"] = []

        self.buildPlaylistList()

    def buildPlaylistList(self):
        for playlists in self.playlists_all:
            if "user_info" in playlists:
                user_info = playlists["user_info"]

                if "message" in user_info:
                    del user_info["message"]

                server_info = playlists.get("server_info", {})
                if "https_port" in server_info:
                    del server_info["https_port"]
                if "rtmp_port" in server_info:
                    del server_info["rtmp_port"]

                if "time_now" in server_info:
                    time_formats = ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H-%M-%S", "%Y-%m-%d-%H:%M:%S", "%Y- %m-%d %H:%M:%S"]

                    for time_format in time_formats:
                        try:
                            time_now_datestamp = datetime.strptime(str(server_info["time_now"]), time_format)
                            offset = datetime.now().hour - time_now_datestamp.hour
                            # print("*** offset ***", offset)
                            playlists["player_info"]["serveroffset"] = offset
                            break
                        except ValueError:
                            pass

                if "timestamp_now" in server_info:
                    try:
                        timestamp = int(server_info["timestamp_now"])
                        timestamp_dt = datetime.utcfromtimestamp(timestamp)

                        # Get the current system time
                        current_dt = datetime.now()

                        # Calculate the difference
                        time_difference = current_dt - timestamp_dt
                        hour_difference = int(time_difference.total_seconds() / 3600)
                        catchupoffset = hour_difference
                        # print("hour_difference:", hour_difference)
                        playlists["player_info"]["catchupoffset"] = catchupoffset
                    except:
                        pass

                auth = user_info.get("auth", 1)
                if not isinstance(auth, int):
                    user_info["auth"] = 1

                if "status" in user_info:
                    valid_statuses = {"Active", "Banned", "Disabled", "Expired"}
                    if user_info["status"] not in valid_statuses:
                        user_info["status"] = "Active"

                    if user_info["status"] == "Active":
                        playlists["data"]["fail_count"] = 0
                    else:
                        playlists["data"]["fail_count"] += 1

                if "active_cons" in user_info and not user_info["active_cons"]:
                    user_info["active_cons"] = 0

                if "max_connections" in user_info and not user_info["max_connections"]:
                    user_info["max_connections"] = 0

                if 'allowed_output_formats' in user_info:
                    allowed_formats = user_info['allowed_output_formats'] or []  # Ensure it's always a list
                    output_format = playlists["playlist_info"]["output"]

                    if output_format not in allowed_formats:
                        playlists["playlist_info"]["output"] = str(allowed_formats[0]) if allowed_formats else "ts"

            else:
                playlists["data"]["fail_count"] += 1

            playlists.pop("available_channels", None)

        self.writeJsonFile()

    def writeJsonFile(self):
        with open(self.playlists_json, "w") as f:
            json.dump(self.playlists_all, f, indent=4)
        self.createSetup()

    def createSetup(self):
        self["splash"].hide()
        self.list = []
        fail_count_check = False
        index = 0

        for playlist in self.playlists_all:
            name = playlist["playlist_info"].get("name", playlist["playlist_info"].get("domain", ""))
            url = playlist["playlist_info"].get("host", "")
            status = _("Server Not Responding")

            active = ""
            activenum = ""
            maxc = ""
            maxnum = ""
            expires = ""

            user_info = playlist.get("user_info", {})
            if "auth" in user_info:
                status = _("Not Authorised")

                if str(user_info["auth"]) == "1":
                    user_status = user_info.get("status", "")
                    status_map = {
                        "Active": _("Active"),
                        "Banned": _("Banned"),
                        "Disabled": _("Disabled"),
                        "Expired": _("Expired")
                    }
                    status = status_map.get(user_status, status)

                    if user_status == "Active":
                        exp_date = user_info.get("exp_date")
                        if exp_date:
                            try:
                                expires = _("Expires: ") + datetime.fromtimestamp(int(exp_date)).strftime("%d-%m-%Y")
                            except:
                                expires = _("Expires: ") + "Null"
                        else:
                            expires = _("Expires: ") + "Null"

                        active = str(_("Active Conn:"))
                        activenum = playlist["user_info"]["active_cons"]

                        try:
                            activenum = int(activenum)
                        except:
                            activenum = 0

                        maxc = str(_("Max Conn:"))
                        maxnum = playlist["user_info"]["max_connections"]

                        try:
                            maxnum = int(maxnum)
                        except:
                            maxnum = 0

            if playlist.get("data", {}).get("fail_count", 0) > 5:
                fail_count_check = True

            self.list.append([index, name, url, expires, status, active, activenum, maxc, maxnum])
            index += 1

        self.drawList = [self.buildListEntry(x[0], x[1], x[2], x[3], x[4], x[5], x[6], x[7], x[8]) for x in self.list]
        self["playlists"].setList(self.drawList)

        if len(self.list) == 1 and cfg.skipplaylistsscreen.value and "user_info" in self.playlists_all[0] and "status" in self.playlists_all[0]["user_info"] and self.playlists_all[0]["user_info"]["status"] == "Active":
            self.getStreamTypes()

        if fail_count_check:
            self.session.open(MessageBox, _("You have dead playlists that are slowing down loading.\n\nPress Yellow button to soft delete dead playlists"), MessageBox.TYPE_WARNING)
            for playlist in self.playlists_all:
                playlist["data"]["fail_count"] = 0
            with open(self.playlists_json, "w") as f:
                json.dump(self.playlists_all, f, indent=4)

    def buildListEntry(self, index, name, url, expires, status, active, activenum, maxc, maxnum):
        if status == _("Active"):
            pixmap = LoadPixmap(cached=True, path=os.path.join(common_path, "led_green.png"))

            if int(activenum) >= int(maxnum) and int(maxnum) != 0:
                pixmap = LoadPixmap(cached=True, path=os.path.join(common_path, "led_yellow.png"))
        else:
            if status == _("Banned"):
                pixmap = LoadPixmap(cached=True, path=os.path.join(common_path, "led_red.png"))
            elif status == _("Expired"):
                pixmap = LoadPixmap(cached=True, path=os.path.join(common_path, "led_grey.png"))
            elif status == _("Disabled"):
                pixmap = LoadPixmap(cached=True, path=os.path.join(common_path, "led_grey.png"))
            elif status == _("Server Not Responding"):
                pixmap = LoadPixmap(cached=True, path=os.path.join(common_path, "led_red.png"))
            elif status == _("Not Authorised"):
                pixmap = LoadPixmap(cached=True, path=os.path.join(common_path, "led_red.png"))

        return (index, str(name), str(url), str(expires), str(status), pixmap, str(active), str(activenum), str(maxc), str(maxnum))

    def quit(self, answer=None):
        self.close()

    def deleteServer(self, answer=None):
        if self.list != []:
            self.currentplaylist = glob.active_playlist.copy()

            if answer is None:
                self.session.openWithCallback(self.deleteServer, MessageBox, _("Delete selected playlist?"))
            elif answer:
                with open(self.playlist_file, "r+") as f:
                    lines = f.readlines()
                    f.seek(0)
                    f.truncate()
                    for line in lines:
                        if str(self.currentplaylist["playlist_info"]["domain"]) in line and "username=" + str(self.currentplaylist["playlist_info"]["username"]) in line:
                            line = "#%s" % line
                        f.write(line)
                x = 0
                for playlist in self.playlists_all:
                    if playlist == self.currentplaylist:
                        del self.playlists_all[x]
                        break
                    x += 1
                self.writeJsonFile()
                self.deleteEpgData()

    def deleteEpgData(self, data=None):
        self["splash"].show()
        playlist_name = str(self.currentplaylist["playlist_info"]["name"])
        epglocation = str(cfg.epglocation.value)
        epgfolder = os.path.join(epglocation, playlist_name)

        try:
            shutil.rmtree(epgfolder)
        except Exception as e:
            print("Error deleting EPG data:", e)
        self.start()

    def getCurrentEntry(self):
        if self.list:
            glob.current_selection = self["playlists"].getIndex()
            glob.active_playlist = self.playlists_all[glob.current_selection]

            num_playlists = self["playlists"].count()
            if num_playlists > 5:
                self["scroll_up"].show()
                self["scroll_down"].show()

                if glob.current_selection < 5:
                    self["scroll_up"].hide()

                elif glob.current_selection + 1 > ((self["playlists"].count() // 5) * 5):
                    self["scroll_down"].hide()
        else:
            glob.current_selection = 0
            glob.active_playlist = {}

    def openUserInfo(self):
        if self.list:
            current_playlist = glob.active_playlist

            if "user_info" in current_playlist and "auth" in current_playlist["user_info"] and str(current_playlist["user_info"]["auth"]) == "1":
                from . import serverinfo
                self.session.open(serverinfo.XStreamity_UserInfo)

    def getStreamTypes(self):
        if "user_info" in glob.active_playlist:
            if "auth" in glob.active_playlist["user_info"]:
                if str(glob.active_playlist["user_info"]["auth"]) == "1" and glob.active_playlist["user_info"]["status"] == "Active":
                    from . import menu
                    self.session.openWithCallback(self.checkoneplaylist, menu.XStreamity_Menu)

    def checkoneplaylist(self):
        if len(self.list) == 1 and cfg.skipplaylistsscreen.value is True:
            self.quit()

    def epgimportcleanup(self):
        channelfilelist = []
        oldchannelfiles = pythonglob.glob("/etc/epgimport/xstreamity.*.channels.xml")

        with open(self.playlists_json, "r") as f:
            self.playlists_all = json.load(f)

        for playlist in self.playlists_all:
            cleanName = re.sub(r'[\'\<\>\:\"\/\\\|\?\*\(\)\[\]]', "_", str(playlist["playlist_info"]["name"]))
            cleanName = re.sub(r" +", "_", cleanName)
            cleanName = re.sub(r"_+", "_", cleanName)
            channelfilelist.append(cleanName)

        for filePath in oldchannelfiles:
            if not any(cfile in filePath for cfile in channelfilelist):
                try:
                    os.remove(filePath)
                except Exception as e:
                    print("Error while deleting file:", filePath, e)

        sourcefile = "/etc/epgimport/xstreamity.sources.xml"

        if os.path.isfile(sourcefile):
            try:
                import xml.etree.ElementTree as ET
                tree = ET.parse(sourcefile, parser=ET.XMLParser(encoding="utf-8"))
                root = tree.getroot()

                for elem in root.findall(".//source"):
                    description = elem.find("description").text
                    if not any(cfile in description for cfile in channelfilelist):
                        root.remove(elem)

                tree.write(sourcefile)
            except Exception as e:
                print("Error:", e)

    def goTop(self):
        self["playlists"].setIndex(0)
