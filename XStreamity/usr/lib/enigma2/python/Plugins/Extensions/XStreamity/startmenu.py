#!/usr/bin/python
# -*- coding: utf-8 -*-

# Standard library imports
import json
import os
from datetime import datetime

try:
    from http.client import HTTPConnection
    HTTPConnection.debuglevel = 0
except ImportError:
    from httplib import HTTPConnection
    HTTPConnection.debuglevel = 0

# Third-party imports
from requests.adapters import HTTPAdapter, Retry

# Enigma2 components
from Components.ActionMap import ActionMap
from Components.Sources.List import List
from Screens.Console import Console
from Screens.Screen import Screen
from enigma import eServiceReference, iPlayableService, eTimer
from Components.ServiceEventTracker import ServiceEventTracker
from Screens.MessageBox import MessageBox
from Components.Pixmap import Pixmap
from Components.config import configfile

# Local application/library-specific imports
from . import _
from . import xstreamity_globals as glob
from . import processfiles as loadfiles
from .plugin import cfg, downloads_json, hasConcurrent, hasMultiprocessing, pythonFull, skin_directory, version, InternetSpeedTest_installed, NetSpeedTest_installed, debugs, pythonVer, dir_tmp
from .xStaticText import StaticText
from .utils import _cleanup_epg_folders, _get_current_aspect_ratio

try:
    from enigma import eAVSwitch
except Exception:
    from enigma import eAVControl as eAVSwitch

hdr = {
    'User-Agent': str(cfg.useragent.value),
}


if pythonVer == 3:
    superscript_to_normal = str.maketrans(
        '⁰¹²³⁴⁵⁶⁷⁸⁹ᵃᵇᶜᵈᵉᶠᵍʰⁱʲᵏˡᵐⁿᵒᵖʳˢᵗᵘᵛʷˣʸᶻ'
        'ᴬᴮᴰᴱᴳᴴᴵᴶᴷᴸᴹᴺᴼᴾᴿᵀᵁⱽᵂ⁺⁻⁼⁽⁾',
        '0123456789abcdefghijklmnoprstuvwxyz'
        'ABDEGHIJKLMNOPRTUVW+-=()'
    )


def normalize_superscripts(text):
    return text.translate(superscript_to_normal)


def clean_names(streams):
    for item in streams:
        for field in ("name", "category_name"):
            if field in item and isinstance(item[field], str):
                item[field] = normalize_superscripts(item[field])
    return streams


playlists_json = cfg.playlists_json.value


class XStreamity_StartMenu(Screen):
    ALLOW_SUSPEND = True

    def __init__(self, session):
        if debugs:
            print("*** __init__ ***")
        Screen.__init__(self, session)
        self.session = session

        skin_path = os.path.join(
            skin_directory,
            cfg.interface.value,
            cfg.skin.value
        )

        if not os.path.exists(skin_path):
            skin_path = os.path.join(
                skin_directory,
                cfg.interface.value,
                "default"
            )

        skin = os.path.join(skin_path, "startmenu.xml")

        with open(skin, "r") as f:
            self.skin = f.read()

        self.list = []
        self.drawList = []
        self["list"] = List(self.drawList, enableWrapAround=True)

        self.setup_title = _("Main Menu")

        self["splash"] = Pixmap()
        self["splash"].show()
        self["background"] = StaticText("")
        self["version"] = StaticText(version)

        self["list1-bg"] = Pixmap()
        self["list2-bg"] = Pixmap()

        self["list1-bg"].show()
        self["list2-bg"].hide()

        actions = {
            "green": self.__next__,
            "ok": self.__next__,
            "left": self.goUp,
            "right": self.goDown,
            "menu": self.mainSettings,
            "help": self.resetData,
            "blue": self.resetData,
            "up": self.switchList,
            "down": self.switchList,
        }

        if not cfg.boot.value:
            actions.update({"red": self.quit, "cancel": self.quit})

        self["actions"] = ActionMap(["XStreamityActions"], actions, -2)

        self.list2 = []
        self.drawList2 = []
        self["playlists"] = List(self.drawList2, enableWrapAround=True)

        self.toggle = False

        self.playlists_all = loadfiles.process_files()

        _cleanup_epg_folders(self.playlists_all, cfg, dir_tmp)

        for playlist in self.playlists_all:
            playlist["data"]["live_categories"] = []
            playlist["data"]["live_streams"] = []
            playlist["data"]["vod_categories"] = []
            playlist["data"]["series_categories"] = []

        glob.active_playlist = []

        try:
            glob.currentPlayingServiceRef = self.session.nav.getCurrentlyPlayingServiceReference()
            glob.currentPlayingServiceRefString = self.session.nav.getCurrentlyPlayingServiceReference().toString()
            glob.newPlayingServiceRef = self.session.nav.getCurrentlyPlayingServiceReference()
            glob.newPlayingServiceRefString = glob.newPlayingServiceRef.toString()
        except:
            pass

        glob.original_aspect_ratio = _get_current_aspect_ratio()

        self.tracker = ServiceEventTracker(screen=self, eventmap={
            iPlayableService.evEOF: self.onEOF
        })

        self.onLayoutFinish.append(self.__layoutFinished)
        self.onFirstExecBegin.append(self.check_dependencies)

    def __layoutFinished(self):
        self.setTitle(self.setup_title)

    def switchList(self):
        if debugs:
            print("*** switchList ***")

        if not cfg.startmenuplaylists.value:
            return

        self.toggle = not self.toggle
        instance1 = self["list"].master.master.instance
        instance2 = self["playlists"].master.master.instance
        if not self.toggle:
            instance1.setSelectionEnable(1)
            instance2.setSelectionEnable(0)
            self["list1-bg"].show()
            self["list2-bg"].hide()
        else:
            instance1.setSelectionEnable(0)
            instance2.setSelectionEnable(1)
            self["list1-bg"].hide()
            self["list2-bg"].show()

    def check_dependencies(self):
        if debugs:
            print("*** check_dependencies ***")

        try:
            import requests
            from PIL import Image
            if pythonFull < 3.9:
                from multiprocessing.pool import ThreadPool
            self.start()
        except Exception as e:
            print(e)
            os.chmod("/usr/lib/enigma2/python/Plugins/Extensions/XStreamity/dependencies.sh", 0o0755)
            cmd = ". /usr/lib/enigma2/python/Plugins/Extensions/XStreamity/dependencies.sh"
            self.session.openWithCallback(self.start, Console, title="Checking Python Dependencies", cmdlist=[cmd], closeOnSuccess=True)

    def start(self, answer=None):
        if debugs:
            print("*** start ***")

        self["playlists"].master.master.instance.setSelectionEnable(0)

        if not self.playlists_all:
            if cfg.introvideo.value:
                self.playVideo()
            else:
                self["background"].setText("True")

            self.createSetupOptions()
            # self.close()
        else:
            self.delayedDownload()

    def delayedDownload(self):
        if debugs:
            print("*** delayedDownload ***")

        self.timer = eTimer()
        try:
            self.timer_conn = self.timer.timeout.connect(self.makePlaylistUrlList)
        except:
            try:
                self.timer.callback.append(self.makePlaylistUrlList)
            except:
                self.makePlaylistUrlList()
        self.timer.start(20, True)

    def makePlaylistUrlList(self):
        if debugs:
            print("*** makePlaylistUrlList ***")

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
            self.processPlaylistDownloads()

    def processPlaylistDownloads(self):
        if debugs:
            print("*** processPlaylistDownloads ***")

        threads = min(len(self.url_list), 20)

        if hasConcurrent:
            self.concurrent_download(threads)

        elif hasMultiprocessing:
            self.multiprocessing_download(threads)

        else:
            self.sequential_download()

        self.buildPlaylistList()

    def concurrent_download(self, threads):
        if debugs:
            print("*** concurrent_download ***")

        from concurrent.futures import ThreadPoolExecutor
        try:
            with ThreadPoolExecutor(max_workers=threads) as executor:
                results = list(executor.map(self.downloadUrl, self.url_list))
            self.update_playlists_with_results(results)
        except Exception as e:
            print("Concurrent execution error:", e)

    def multiprocessing_download(self, threads):
        if debugs:
            print("*** multiprocessing_download ***")

        from multiprocessing.pool import ThreadPool
        try:
            pool = ThreadPool(threads)
            results = pool.imap_unordered(self.downloadUrl, self.url_list)
            pool.close()
            pool.join()

            # Convert iterator to list
            results_list = list(results)

            self.update_playlists_with_results(results_list)
        except Exception as e:
            print("Multiprocessing execution error:", e)

    def sequential_download(self):
        if debugs:
            print("*** sequential_download ***")

        for url in self.url_list:
            results = self.downloadUrl(url)
            self.update_playlists_with_results(results)

    def downloadUrl(self, url):
        if debugs:
            print("*** downloadUrl ***")

        import requests
        index = url[1]
        response = None

        retries = Retry(total=1, backoff_factor=1)
        adapter = HTTPAdapter(max_retries=retries)

        with requests.Session() as http:
            http.mount("http://", adapter)
            http.mount("https://", adapter)

            try:
                r = http.get(url[0], headers=hdr, timeout=6, verify=False)
                r.raise_for_status()

                # Get Content-Type from headers
                content_type = r.headers.get('Content-Type', '')

                # Handle JSON content directly
                if 'application/json' in content_type:
                    try:
                        response = r.json()
                        if pythonVer == 3:
                            response = clean_names(response)

                    except ValueError as e:
                        print("Error decoding JSON:", e, url)
                        return index, None

                # Handle text/html content
                elif 'text/html' in content_type:
                    try:
                        # Attempt to parse the HTML body as JSON
                        response_text = r.text
                        response = json.loads(response_text)
                    except ValueError as e:
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

    def update_playlists_with_results(self, results):
        if debugs:
            print("*** update_playlists_with_results ***", results)

        for index, response in results:
            if response:
                self.playlists_all[index].update(response)
            else:
                self.playlists_all[index]["user_info"] = {}

    def buildPlaylistList(self):
        if debugs:
            print("*** buildPlaylistList ***")

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
        self.createSetupPlaylists()

    def writeJsonFile(self):
        if debugs:
            print("*** writeJsonFile ***")

        with open(playlists_json, "w") as f:
            json.dump(self.playlists_all, f, indent=4)

    def createSetupPlaylists(self):
        if debugs:
            print("*** createSetupPlaylists ***")
        if cfg.introvideo.value:
            self.playVideo()
        else:
            self["background"].setText("True")

        self.list2 = []

        for playlist in self.playlists_all:
            name = playlist["playlist_info"].get("name", playlist["playlist_info"].get("domain", ""))
            url = playlist["playlist_info"].get("host", "")
            activenum = ""
            maxnum = ""
            index = playlist["playlist_info"]["index"]

            user_info = playlist.get("user_info", {})
            if "auth" in user_info:

                if str(user_info["auth"]) == "1":
                    user_status = user_info.get("status", "")

                    if user_status == "Active":
                        activenum = playlist["user_info"]["active_cons"]

                        try:
                            activenum = int(activenum)
                        except:
                            activenum = 0

                        maxnum = playlist["user_info"]["max_connections"]

                        try:
                            maxnum = int(maxnum)
                        except:
                            maxnum = 0

                        self.list2.append([index, name, url, activenum, maxnum])

            if playlist.get("data", {}).get("fail_count", 0) > 5:
                self.session.open(MessageBox, _("You have dead playlists that are slowing down loading.\n\nPress Yellow button to soft delete dead playlists"), MessageBox.TYPE_WARNING)
                for playlist in self.playlists_all:
                    playlist["data"]["fail_count"] = 0
                with open(playlists_json, "w") as f:
                    json.dump(self.playlists_all, f, indent=4)

        self.drawList2 = [self.buildPlalyistListEntry(x[0], x[1], x[2], x[3], x[4]) for x in self.list2]

        activeplaylists = any(
            "user_info" in playlist and "status" in playlist["user_info"] and playlist["user_info"]["status"] == "Active"
            for playlist in self.playlists_all
        )

        if activeplaylists:
            self["splash"].hide()
            self.set_last_playlist()
            self.makeUrlCategoryList()
        else:
            self["splash"].hide()
            self.addServer()
            self.close()

    def set_last_playlist(self):
        if debugs:
            print("*** set_last_playlist ***")

        activeindex = 0
        found = False

        for playlist in self.playlists_all:
            playlist_name = playlist["playlist_info"]["name"]

            if "user_info" in playlist and playlist["user_info"] and "status" in playlist["user_info"] and playlist["user_info"]["status"] == "Active":

                if playlist_name == cfg.lastplaylist.value:
                    glob.active_playlist = playlist
                    glob.current_active_playlist_selection = activeindex
                    self.original_active_playlist = glob.active_playlist
                    found = True
                    break

                activeindex += 1

        # If no match found, fall back to the first playlist in list2

        if not found:

            activeindex = 0

            for playlist in self.playlists_all:

                playlist_name = playlist["playlist_info"]["name"]

                if "user_info" in playlist and playlist["user_info"] and "status" in playlist["user_info"] and playlist["user_info"]["status"] == "Active":
                    glob.active_playlist = playlist
                    glob.current_active_playlist_selection = activeindex
                    cfg.lastplaylist.setValue(playlist_name)
                    cfg.save()
                    configfile.save()
                    break

                activeindex += 1

        glob.active_playlist["data"]["live_streams"] = []
        self.original_active_playlist = glob.active_playlist
        self["playlists"].setList(self.drawList2)
        self["playlists"].setIndex(glob.current_active_playlist_selection)

        if not cfg.startmenuplaylists.value:
            self.drawList2 = []
            self["playlists"].setList(self.drawList2)

    def buildPlalyistListEntry(self, index, name, url, activenum, maxnum):
        text = str(name) + "   " + _("Active:") + str(activenum) + " " + _("Max:") + str(maxnum)
        return (index, text, str(url))

    def getCurrentEntry(self):
        if debugs:
            print("*** getCurrentEntry ***")
        if self.list2:
            self["list"].setIndex(0)
            glob.active_playlist["data"]["live_categories"] = []
            glob.active_playlist["data"]["live_streams"] = []
            glob.active_playlist["data"]["vod_categories"] = []
            glob.active_playlist["data"]["series_categories"] = []

            glob.current_active_playlist_selection = self["playlists"].getIndex()

            current_playlist_selection = self["playlists"].getCurrent()[0]

            glob.active_playlist = self.playlists_all[current_playlist_selection]

            self.original_active_playlist = glob.active_playlist

            cfg.lastplaylist.setValue(glob.active_playlist["playlist_info"]["name"])
            cfg.save()
            configfile.save()

            self.makeUrlCategoryList()

    def makeUrlCategoryList(self):
        if debugs:
            print("*** makeUrlCategoryList ***")

        self.url_list = []
        glob.active_playlist["data"]["live_categories"] = []
        glob.active_playlist["data"]["vod_categories"] = []
        glob.active_playlist["data"]["series_categories"] = []
        glob.active_playlist["data"]["live_streams"] = []
        glob.active_playlist["data"]["catchup"] = False
        glob.active_playlist["data"]["customsids"] = False

        self.active_player_api = glob.active_playlist["playlist_info"]["player_api"]
        self.active_live_categories_url = str(self.active_player_api) + "&action=get_live_categories"
        self.active_vod_categories_url = str(self.active_player_api) + "&action=get_vod_categories"
        self.active_series_categories_url = str(self.active_player_api) + "&action=get_series_categories"
        self.active_live_streams_url = str(self.active_player_api) + "&action=get_live_streams"

        show_live = glob.active_playlist["player_info"].get("showlive", False)
        show_vod = glob.active_playlist["player_info"].get("showvod", False)
        show_series = glob.active_playlist["player_info"].get("showseries", False)
        show_catchup = glob.active_playlist["player_info"].get("showcatchup", False)

        full_url = str(glob.active_playlist["playlist_info"].get("full_url", ""))
        domain = str(glob.active_playlist["playlist_info"].get("domain", ""))
        username = str(glob.active_playlist["playlist_info"].get("username", ""))
        password = str(glob.active_playlist["playlist_info"].get("password", ""))

        if "get.php" in full_url and domain and username and password:
            if show_live:
                self.url_list.append([self.active_live_categories_url, 1])
            if show_vod:
                self.url_list.append([self.active_vod_categories_url, 2])
            if show_series:
                self.url_list.append([self.active_series_categories_url, 3])
            if show_catchup:
                self.url_list.append([self.active_live_streams_url, 4])

        self.processApiDownloads()

    def processApiDownloads(self):
        if debugs:
            print("*** processApiDownloads ***")

        threads = min(len(self.url_list), 4)

        if hasConcurrent:
            self.concurrent_api_download(threads)

        elif hasMultiprocessing:
            self.multiprocessing_api_download(threads)

        else:
            self.sequential_api_download()

        self.createSetupOptions()

    def concurrent_api_download(self, threads):
        if debugs:
            print("*** concurrent_api_download ***")

        from concurrent.futures import ThreadPoolExecutor
        try:
            with ThreadPoolExecutor(max_workers=threads) as executor:
                results = list(executor.map(self.downloadUrl, self.url_list))
            self.update_playlists_with_api_results(results)
        except Exception as e:
            print("Concurrent execution error:", e)

    def multiprocessing_api_download(self, threads):
        if debugs:
            print("*** multiprocessing_api_download ***")

        from multiprocessing.pool import ThreadPool
        try:
            pool = ThreadPool(threads)
            results = pool.imap_unordered(self.downloadUrl, self.url_list)
            pool.close()
            pool.join()

            # Convert iterator to list
            results_list = list(results)

            self.update_playlists_with_api_results(results_list)
        except Exception as e:
            print("Multiprocessing execution error:", e)

    def sequential_api_download(self):
        if debugs:
            print("*** sequential_api_download ***")

        for url in self.url_list:
            results = self.downloadUrl(url)
            self.update_playlists_with_api_results(results)

    def update_playlists_with_api_results(self, results):
        if debugs:
            print("*** update_playlists_with_api_results ***")

        for index, response in results:
            if response:
                if index == 1:
                    glob.active_playlist["data"]["live_categories"] = response

                if index == 2:
                    glob.active_playlist["data"]["vod_categories"] = response

                if index == 3:
                    glob.active_playlist["data"]["series_categories"] = response

                if index == 4:
                    glob.active_playlist["data"]["live_streams"] = response

    def createSetupOptions(self):
        if debugs:
            print("*** createSetupOptions ***")

        self["list"].setIndex(0)
        self.index = 0
        downloads_all = []

        if os.path.isfile(downloads_json) and os.stat(downloads_json).st_size > 0:
            try:
                with open(downloads_json, "r") as f:
                    downloads_all = json.load(f)
            except Exception as e:
                print(e)

        if self.playlists_all:
            show_live = glob.active_playlist["player_info"].get("showlive", False)
            show_vod = glob.active_playlist["player_info"].get("showvod", False)
            show_series = glob.active_playlist["player_info"].get("showseries", False)
            show_catchup = glob.active_playlist["player_info"].get("showcatchup", False)

            content = glob.active_playlist["data"]["live_streams"]

            has_catchup = any(str(item.get("tv_archive", "0")) == "1" for item in content if "tv_archive" in item)
            has_custom_sids = any(item.get("custom_sid", False) for item in content if "custom_sid" in item)

            glob.active_playlist["data"]["live_streams"] = []

            if has_custom_sids:
                glob.active_playlist["data"]["customsids"] = True

            if has_catchup:
                glob.active_playlist["data"]["catchup"] = True

            if show_live and glob.active_playlist["data"]["live_categories"]:
                self.list.append(["", _("Live TV"), 0])

            if show_vod and glob.active_playlist["data"]["vod_categories"]:
                self.list.append(["", _("Movies"), 1])

            if show_series and glob.active_playlist["data"]["series_categories"]:
                self.list.append(["", _("Series"), 2])

            if show_catchup and glob.active_playlist["data"]["catchup"]:
                self.list.append(["", _("Catch Up TV"), 3])

        self.list.append(["", _("Add Playlist"), 9])

        if self.playlists_all:
            if cfg.manageplaylists.value:
                self.list.append(["", _("Manage Playlists"), 6])

        self.list.append(["", _("Global Settings"), 4])

        if downloads_all:
            self.list.append(["", _("Download Manager"), 5])

        if cfg.boot.value:
            self.list.append(["", _("Reboot GUI"), 7])

        if cfg.speedtest.value and (InternetSpeedTest_installed is True or NetSpeedTest_installed is True):
            self.list.append(["", _("Speed Test"), 8])

        self["splash"].hide()

        self.drawList = [self.buildListEntry(x[0], x[1], x[2]) for x in self.list]
        self["list"].setList(self.drawList)

        if self.playlists_all:
            playlistindex = glob.active_playlist["playlist_info"]["index"]
            try:
                self.playlists_all[playlistindex] = glob.active_playlist
            except:
                glob.active_playlist["playlist_info"]["index"] = 0
                self.playlists_all[0] = glob.active_playlist

            self.writeJsonFile()

    def buildListEntry(self, index, title, num):
        return index, str(title), num

    def __next__(self):
        if debugs:
            print("*** __next__ ***")

        if cfg.introvideo.value:

            try:
                if glob.currentPlayingServiceRefString:
                    self.session.nav.playService(eServiceReference(glob.currentPlayingServiceRefString))
            except Exception as e:
                print(e)

        current_entry = self["list"].getCurrent()

        if self.playlists_all:
            glob.current_selection = glob.active_playlist["playlist_info"]["index"]

        if current_entry:
            index = current_entry[2]
            if index == 0:
                self.showLive()
            elif index == 1:
                self.showVod()
            elif index == 2:
                self.showSeries()
            elif index == 3:
                self.showCatchup()
            elif index == 4:
                self.mainSettings()
            elif index == 5:
                self.downloadManager()
            elif index == 6:
                self.showPlaylists()
            elif index == 7:
                self.ExecuteRestart()
            elif index == 8:
                self.runSpeedTest()
            elif index == 9:
                self.addServer()

    def runSpeedTest(self):
        if debugs:
            print("*** runSpeedTest ***")

        if InternetSpeedTest_installed:
            from Plugins.Extensions.InternetSpeedTest.plugin import internetspeedtest
            self.session.openWithCallback(self.reload, internetspeedtest)
        elif NetSpeedTest_installed:
            from Plugins.Extensions.NetSpeedTest.default import NetSpeedTestScreen
            self.session.openWithCallback(self.reload, NetSpeedTestScreen)

    def ExecuteRestart(self, result=None):
        from Screens import Standby
        Standby.quitMainloop(3)

    def showLive(self):
        from . import live
        self.session.openWithCallback(self.reload, live.XStreamity_Live_Categories)

    def showVod(self):
        from . import vod
        self.session.openWithCallback(self.reload, vod.XStreamity_Vod_Categories)

    def showSeries(self):
        from . import series
        self.session.openWithCallback(self.reload, series.XStreamity_Series_Categories)

    def showCatchup(self):
        from . import catchup
        self.session.openWithCallback(self.reload, catchup.XStreamity_Catchup_Categories)

    def mainSettings(self):
        from . import settings
        self.session.openWithCallback(self.noreload, settings.XStreamity_Settings)

    def downloadManager(self):
        from . import downloadmanager
        self.session.openWithCallback(self.reload, downloadmanager.XStreamity_DownloadManager)

    def showPlaylists(self):
        from . import playlists
        self.session.openWithCallback(self.reload, playlists.XStreamity_Playlists)

    def addServer(self):
        from . import server
        self.session.openWithCallback(self.noreload, server.XStreamity_AddServer)

    def quit(self, data=None):
        self.playOriginalChannel()

    def playOriginalChannel(self):
        if debugs:
            print("*** playOriginalChannel ***")

        try:
            if glob.currentPlayingServiceRefString:
                self.session.nav.playService(eServiceReference(glob.currentPlayingServiceRefString))
        except Exception as e:
            print(e)

        self["splash"].hide()

        try:
            if glob.original_aspect_ratio is not None:
                eAVSwitch.getInstance().setAspectRatio(glob.original_aspect_ratio)
        except Exception:
            pass

        self.close()

    def playVideo(self, result=None):
        if debugs:
            print("*** playVideo ***")

        self["background"].setText("")
        self.local_video_path = cfg.introvideoselection.value
        service = eServiceReference(4097, 0, self.local_video_path)
        try:
            self.session.nav.playService(service)
        except:
            pass

    def onEOF(self):
        if debugs:
            print("*** onEOF ***")

        if cfg.introvideo.value and cfg.introloop.value:
            self["background"].setText("")
            service = self.session.nav.getCurrentService()
            seek = service and service.seek()
            if seek:
                seek.seekTo(0)
        else:
            self["background"].setText("True")

    def goUp(self):
        instance1 = self["list"].master.master.instance
        instance2 = self["playlists"].master.master.instance
        if self.toggle is False:
            instance1.moveSelection(instance1.moveUp)
        else:
            instance2.moveSelection(instance2.moveUp)
            self.getCurrentEntry()

    def goDown(self):
        instance1 = self["list"].master.master.instance
        instance2 = self["playlists"].master.master.instance
        if self.toggle is False:
            instance1.moveSelection(instance1.moveDown)
        else:
            instance2.moveSelection(instance2.moveDown)
            self.getCurrentEntry()

    def resetData(self, answer=None):
        if debugs:
            print("*** resetData ***")

        if answer is None:
            self.session.openWithCallback(self.resetData, MessageBox, _("Warning: delete stored json data for all playlists... Settings, favourites etc. \nPlaylists will not be deleted.\nDo you wish to continue?"))
        elif answer:
            try:
                os.remove(playlists_json)
                with open(playlists_json, "a"):
                    pass
            except OSError as e:
                print("Error deleting or recreating JSON file:", e)
            self.quit()

    def reload(self, Answer=None):
        if debugs:
            print("*** reload ***")

        self["list"].setIndex(0)

        if cfg.introvideo.value:
            self.playVideo()
        else:
            self["background"].setText("True")

        if self.playlists_all and self.original_active_playlist != glob.active_playlist:
            self.original_active_playlist = glob.active_playlist
            self["splash"].show()
            self["background"] = StaticText("")
            self.createSetupPlaylists()

        else:
            self.createSetupOptions()

    def noreload(self, Answer=None):
        self.playlists_all = loadfiles.process_files()
        _cleanup_epg_folders(self.playlists_all, cfg, dir_tmp)
        self.start()
