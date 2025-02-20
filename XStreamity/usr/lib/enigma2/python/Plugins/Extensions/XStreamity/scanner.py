#!/usr/bin/python
# -*- coding: utf-8 -*-

from __future__ import division

# Standard library imports
import json
import os
import base64
import zlib
import random

try:
    from urlparse import urlparse, parse_qsl  # Python 2
    from urllib import urlencode  # Python 2
except:
    from urllib.parse import urlparse, parse_qsl, urlencode  # Python 3

try:
    from http.client import HTTPConnection
    HTTPConnection.debuglevel = 0
except ImportError:
    from httplib import HTTPConnection
    HTTPConnection.debuglevel = 0

# Third-party imports
import requests

# Enigma2 components
from Components.ActionMap import ActionMap
from Components.Pixmap import Pixmap
from Components.Sources.List import List
from datetime import datetime
from enigma import eTimer

from Screens.MessageBox import MessageBox
from Screens.Screen import Screen
from Tools.LoadPixmap import LoadPixmap

# Local application/library-specific imports
from . import _
from . import checkinternet
from . import xstreamity_globals as glob
from .plugin import skin_directory, cfg, common_path, version, hasConcurrent, hasMultiprocessing
from .xStaticText import StaticText


epgimporter = os.path.isdir("/usr/lib/enigma2/python/Plugins/Extensions/EPGImport")

hdr = {
    'User-Agent': str(cfg.useragent.value),
    'Accept-Encoding': 'gzip, deflate'
}

location = cfg.location.value

badurls_file = "/tmp/scans/badurls.txt"

original_playlist_file = cfg.playlist_file.value
original_playlists_json = cfg.playlists_json.value

scanner_playlist_file = "/tmp/scans/playlists.txt"
scanner_playlists_json = "/tmp/scans/x-playlists.json"

compressed_base_url = b'x\x9c\xb3\xf5\xcc\xf2\xcd\t4\xf0\xcd\t\rO\xca0\xcdM\xce\xf1\x8bHq\xf7\x0b\xf1r\t\x0b\xf1*\xcfpO.\r\x8c\x88\xca\xf3\x02\xaaq\x04bW\x98\xba\xf0\xa8\xe2\x9c\xdc(KW\xe3\x80\xb2t\xa3\xc8J\xb7\xf0\xa8*\xcb`_#\xcb\xe0\xc4r7#\x9f\xb2\x9c\\\x9fR7\xa3\xc8\xaa\x8a\xdcdC\xcbJ\x1f3_\x8fd\x83 \x8fD\x00\xcc\xd4$a'


def get_base_url():
    reversed_encoded = zlib.decompress(compressed_base_url).decode('utf-8')
    encoded = reversed_encoded[::-1]
    original_url = base64.b64decode(encoded).decode('utf-8')
    return original_url


class XStreamity_Scanner(Screen):
    ALLOW_SUSPEND = True

    def __init__(self, session):
        Screen.__init__(self, session)
        self.session = session

        skin_path = os.path.join(skin_directory, cfg.skin.value)
        skin = os.path.join(skin_path, "playlists.xml")
        with open(skin, "r") as f:
            self.skin = f.read()

        self.setup_title = _("Select Playlist")

        self["key_red"] = StaticText(_("Back"))
        self["key_green"] = StaticText(_("OK"))
        self["key_yellow"] = StaticText()
        self["key_blue"] = StaticText()
        self["version"] = StaticText()

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

        self["actions"] = ActionMap(["XStreamityActions"], {
            "red": self.quit,
            "green": self.getStreamTypes,
            "cancel": self.quit,
            "ok": self.getStreamTypes,
        }, -2)

        self.onFirstExecBegin.append(self.start)
        self.onLayoutFinish.append(self.__layoutFinished)

    def clear_caches(self):
        try:
            with open("/proc/sys/vm/drop_caches", "w") as drop_caches:
                drop_caches.write("1\n2\n3\n")
        except IOError:
            pass

    def __layoutFinished(self):
        self.setTitle(self.setup_title)

    def start(self):
        cfg.playlist_file.setValue(scanner_playlist_file)
        cfg.playlists_json.setValue(scanner_playlists_json)
        cfg.save()

        self.checkinternet = checkinternet.check_internet()
        if not self.checkinternet:
            self.session.openWithCallback(self.quit, MessageBox, _("No internet."), type=MessageBox.TYPE_ERROR, timeout=5)

        self["version"].setText(version)

        self.playlists_all = []

        scans_dir = "/tmp/scans"
        if os.path.exists(scans_dir):
            for file_name in ["playlists.txt", "x-playlists.json"]:
                file_path = os.path.join(scans_dir, file_name)
                if os.path.exists(file_path):
                    os.remove(file_path)

        self.scantimer = eTimer()
        try:
            self.scantimer_conn = self.scantimer.timeout.connect(self.makeScanUrlData)
        except:
            try:
                self.scantimer.callback.append(self.makeScanUrlData)
            except:
                self.makeScanUrlData()
        self.scantimer.start(10, True)

        self.clear_caches()

    def makeScanUrlData(self):
        base_url = get_base_url()
        search_after = None
        output_dir = "/tmp/scans"

        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

        bad_urls = set()

        if os.path.exists(badurls_file):
            with open(badurls_file, "r") as f:
                bad_urls = set(line.strip() for line in f)

        final_urls_to_write_set = set()  # Use a set to store unique URLs

        for i in range(5):
            if not search_after:
                url = base_url
            else:
                url = "{}&search_after={}".format(base_url, search_after)

            response = self.download_url([url, i])

            if not response:
                continue

            index, data = response

            if not data or not data.get("results"):
                continue

            for task in data["results"]:
                if "files" in task and len(task["files"]) > 0:
                    task_url = task["files"][0]["url"]

                    parsed_url = urlparse(task_url)

                    query_params = dict(parse_qsl(parsed_url.query))

                    query_params.pop("type", None)
                    query_params.pop("output", None)

                    query_params["type"] = "m3u"
                    query_params["output"] = "ts"

                    new_query = urlencode(query_params)
                    task_url = parsed_url._replace(query=new_query).geturl()

                    url_without_server = task_url.split(" ")[0]

                    if url_without_server.strip() in bad_urls:
                        continue

                    if "/get.php?" in task_url:
                        final_urls_to_write_set.add((task_url, parsed_url.hostname))

            last_task = data["results"][-1]
            if "sort" in last_task and len(last_task["sort"]) > 0:
                search_after = "{},{}".format(last_task["sort"][0], last_task["sort"][1])
            else:
                break

        # Convert the set back to a list and shuffle to randomize the order
        final_urls_to_write = list(final_urls_to_write_set)
        random.shuffle(final_urls_to_write)

        with open(scanner_playlist_file, "a") as f:
            for url, domain in final_urls_to_write:
                f.write(url + " #" + str(domain) + "\n")

        from . import processscanfiles as loadfiles
        self.playlists_all = loadfiles.process_files()

        if self.playlists_all and os.path.isfile(scanner_playlist_file) and os.path.getsize(scanner_playlist_file) > 0:
            self.delayedDownload()
        else:
            self.close()

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
        # print("*** url ***", url)
        index = url[1]
        response = None

        with requests.Session() as http:
            try:
                r = http.get(url[0], headers=hdr, timeout=5, verify=False)
                r.raise_for_status()
                content_type = r.headers.get('Content-Type', '')
                if 'application/json' in content_type:
                    try:
                        response = r.json()
                    except ValueError:
                        return index, None
                elif 'text/html' in content_type:
                    try:
                        response_text = r.text
                        response = json.loads(response_text)
                    except json.JSONDecodeError:
                        return index, None

                else:
                    return index, None

            except requests.exceptions.RequestException:
                pass
            except Exception:
                pass

        return index, response

    def process_downloads(self):
        # threads = min(len(self.url_list), 15)
        threads = len(self.url_list)
        results = []

        # Load existing bad URLs into a set for quick lookup
        if os.path.exists(badurls_file):
            with open(badurls_file, "r") as f:
                bad_urls = set(line.strip() for line in f)
        else:
            bad_urls = set()

        if hasConcurrent or hasMultiprocessing:
            if hasConcurrent:
                try:
                    from concurrent.futures import ThreadPoolExecutor
                    with ThreadPoolExecutor(max_workers=threads) as executor:
                        results = list(executor.map(self.download_url, self.url_list))
                except Exception as e:
                    print("Concurrent execution error:", e)

            elif hasMultiprocessing:
                try:
                    from multiprocessing.pool import ThreadPool
                    pool = ThreadPool(threads)
                    results = list(pool.imap_unordered(self.download_url, self.url_list))
                    pool.close()
                    pool.join()
                except Exception as e:
                    print("Multiprocessing execution error:", e)

        else:
            for url in self.url_list:
                result = self.download_url(url)
                results.append(result)

        indices_to_remove = []

        for index, response in results:
            if response:
                self.playlists_all[index].update(response)
            else:
                indices_to_remove.append(index)
                bad_url = self.playlists_all[index]["playlist_info"]["full_url"]
                if bad_url not in bad_urls:
                    with open(badurls_file, "a") as f:
                        f.write(bad_url + "\n")
                    bad_urls.add(bad_url)

        # Remove invalid playlists after the loop
        self.playlists_all = [
            playlist for i, playlist in enumerate(self.playlists_all)
            if i not in indices_to_remove
        ]

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
                            playlists["player_info"]["serveroffset"] = offset
                            break
                        except ValueError:
                            pass

                if "timestamp_now" in server_info:
                    timestamp = server_info["timestamp_now"]
                    timestamp_dt = datetime.utcfromtimestamp(timestamp)
                    current_dt = datetime.now()
                    time_difference = current_dt - timestamp_dt
                    hour_difference = int(time_difference.total_seconds() / 3600)
                    catchupoffset = hour_difference
                    playlists["player_info"]["catchupoffset"] = catchupoffset

                auth = user_info.get("auth", 1)
                if not isinstance(auth, int):
                    user_info["auth"] = 1

                if "status" in user_info:
                    valid_statuses = {"Active", "Banned", "Disabled", "Expired"}
                    if user_info["status"] not in valid_statuses:
                        user_info["status"] = "Active"

                if "active_cons" in user_info and not user_info["active_cons"]:
                    user_info["active_cons"] = 0

                if "max_connections" in user_info and not user_info["max_connections"]:
                    user_info["max_connections"] = 0

                if 'allowed_output_formats' in user_info:
                    allowed_formats = user_info['allowed_output_formats']
                    output_format = playlists["playlist_info"]["output"]
                    if output_format not in allowed_formats:
                        playlists["playlist_info"]["output"] = str(allowed_formats[0]) if allowed_formats else "ts"

            playlists.pop("available_channels", None)

        self.writeJsonFile()

    def writeJsonFile(self):
        with open(scanner_playlists_json, "w") as f:
            json.dump(self.playlists_all, f)
        self.createSetup()

    def createSetup(self):
        self["splash"].hide()
        self.list = []

        for playlist in self.playlists_all:
            name = playlist["playlist_info"].get("name", playlist["playlist_info"].get("domain", ""))
            url = playlist["playlist_info"].get("host", "")
            status = _("Server Not Responding")
            index = playlist["playlist_info"].get("index", 0)

            active = ""
            activenum = ""
            maxc = ""
            maxnum = ""
            expires = ""

            user_info = playlist.get("user_info", {})

            if "auth" in user_info:

                if str(user_info["auth"]) == "0":
                    continue

                if "active_cons" in user_info and "max_connections" in user_info:
                    try:
                        if int(user_info["active_cons"]) >= int(user_info["max_connections"]):
                            continue
                    except:
                        pass

                if "status" in user_info:
                    if playlist["user_info"]["status"] != "Active":
                        continue

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

            self.list.append([index, name, url, expires, status, active, activenum, maxc, maxnum])

        self.drawList = [self.buildListEntry(x[0], x[1], x[2], x[3], x[4], x[5], x[6], x[7], x[8]) for x in self.list]
        self["playlists"].setList(self.drawList)

        if len(self.list) == 1 and cfg.skipplaylistsscreen.value and "user_info" in self.playlists_all[0] and "status" in self.playlists_all[0]["user_info"] and self.playlists_all[0]["user_info"]["status"] == "Active":
            self.getStreamTypes()

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

        scans_dir = "/tmp/scans"
        if os.path.exists(scans_dir):
            for file_name in ["playlists.txt", "x-playlists.json"]:
                file_path = os.path.join(scans_dir, file_name)
                if os.path.exists(file_path):
                    os.remove(file_path)

        cfg.playlist_file.setValue(original_playlist_file)
        cfg.playlists_json.setValue(original_playlists_json)
        glob.current_selection = 0
        cfg.save()

        self.close()

    def getCurrentEntry(self):
        if self.list:
            # index = self["playlists"].getIndex()
            index = self["playlists"].getCurrent()[0]
            for idx, playlists in enumerate(self.playlists_all):
                if playlists["playlist_info"]["index"] == index:
                    glob.current_selection = idx
                    break

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

    def getStreamTypes(self):
        from . import menu
        if "user_info" in glob.active_playlist:
            if "auth" in glob.active_playlist["user_info"]:
                if str(glob.active_playlist["user_info"]["auth"]) == "1" and glob.active_playlist["user_info"]["status"] == "Active":
                    self.session.open(menu.XStreamity_Menu)
