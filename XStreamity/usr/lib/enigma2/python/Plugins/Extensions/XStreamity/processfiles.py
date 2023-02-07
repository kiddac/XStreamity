#!/usr/bin/python
# -*- coding: utf-8 -*-

from .plugin import playlists_json, playlist_file, cfg
from collections import OrderedDict

import json
import os
import re


try:
    from urlparse import urlparse, parse_qs
except:
    from urllib.parse import urlparse, parse_qs


def processfiles():
    # check if playlists.txt file exists in specified location
    if not os.path.isfile(playlist_file):
        open(playlist_file, "a").close()

    # check if x-playlists.json file exists in specified location
    if not os.path.isfile(playlists_json):
        open(playlists_json, "a").close()

    playlists_all = []
    if os.path.isfile(playlists_json):
        with open(playlists_json, "r") as f:
            try:
                playlists_all = json.load(f)
            except:
                os.remove(playlists_json)

    # check playlist.txt entries are valid
    with open(playlist_file, "r+") as f:
        lines = f.readlines()

    with open(playlist_file, "w") as f:
        for line in lines:
            line = re.sub(" +", " ", line)
            line = line.strip(" ")
            if not line.startswith("http://") and not line.startswith("https://") and not line.startswith("#"):
                line = "# " + line
            if "=mpegts" in line:
                line = line.replace("=mpegts", "=ts")
            if "=hls" in line:
                line = line.replace("=hls", "=m3u8")
            if line.strip() == "#":
                line = ""
            if line != "":
                f.write(line)

        # read entries from playlists.txt
        index = 0

        livetype = cfg.livetype.getValue()
        vodtype = cfg.vodtype.getValue()

        for line in lines:

            port = ""
            username = ""
            password = ""
            type = "m3u_plus"
            output = "ts"
            livehidden = []
            channelshidden = []
            vodhidden = []
            vodstreamshidden = []
            serieshidden = []
            seriestitleshidden = []
            seriesseasonshidden = []
            seriesepisodeshidden = []
            catchuphidden = []
            catchupchannelshidden = []

            showlive = True
            showvod = True
            showseries = True
            showcatchup = True
            livefavourites = []
            vodfavourites = []
            liverecents = []
            vodrecents = []
            vodwatched = []
            serieswatched = []

            live_streams = []
            catchup_checked = False
            last_check = ""

            serveroffset = 0
            epgoffset = 0
            epgalternative = False
            epgalternativeurl = ""

            directsource = "Standard"

            if not line.startswith("#") and line.startswith("http"):
                line = line.strip()

                parsed_uri = urlparse(line)

                protocol = parsed_uri.scheme + "://"

                if not (protocol == "http://" or protocol == "https://"):
                    continue

                domain = parsed_uri.hostname.lower()
                name = domain
                if line.partition(" #")[-1]:
                    name = line.partition(" #")[-1].strip()

                if parsed_uri.port:
                    port = parsed_uri.port

                    host = "%s%s:%s" % (protocol, domain, port)
                else:
                    host = "%s%s" % (protocol, domain)

                query = parse_qs(parsed_uri.query, keep_blank_values=True)

                if "username" in query:
                    username = query["username"][0].strip()
                else:
                    continue

                if "password" in query:
                    password = query["password"][0].strip()
                else:
                    continue

                if "type" in query:
                    type = query["type"][0].strip()

                if "output" in query:
                    output = query["output"][0].strip()

                if "timeshift" in query:
                    try:
                        epgoffset = int(query["timeshift"][0].strip())
                    except:
                        pass

                player_api = "%s/player_api.php?username=%s&password=%s" % (host, username, password)
                xmltv_api = "%s/xmltv.php?username=%s&password=%s" % (host, username, password)
                full_url = "%s/get.php?username=%s&password=%s&type=%s&output=%s" % (host, username, password, type, output)

                playlist_exists = False

                if playlists_all:
                    for playlist in playlists_all:

                        # extra check in case playlists.txt details have been amended
                        if "domain" in playlist["playlist_info"] and "username" in playlist["playlist_info"] and "password" in playlist["playlist_info"]:
                            if playlist["playlist_info"]["domain"] == domain and playlist["playlist_info"]["username"] == username and playlist["playlist_info"]["password"] == password:

                                playlist_exists = True

                                if "channelshidden" not in playlist["player_info"]:
                                    playlist["player_info"]["channelshidden"] = channelshidden

                                if "vodstreamshidden" not in playlist["player_info"]:
                                    playlist["player_info"]["vodstreamshidden"] = vodstreamshidden

                                if "seriestitleshidden" not in playlist["player_info"]:
                                    playlist["player_info"]["seriestitleshidden"] = seriestitleshidden

                                if "seriesseasonshidden" not in playlist["player_info"]:
                                    playlist["player_info"]["seriesseasonshidden"] = seriesseasonshidden

                                if "seriesepisodeshidden" not in playlist["player_info"]:
                                    playlist["player_info"]["seriesepisodeshidden"] = seriesepisodeshidden

                                if "catchuphidden" not in playlist["player_info"]:
                                    playlist["player_info"]["catchuphidden"] = catchuphidden

                                if "catchupchannelshidden" not in playlist["player_info"]:
                                    playlist["player_info"]["catchupchannelshidden"] = catchupchannelshidden

                                if "serveroffset" not in playlist["player_info"]:
                                    playlist["player_info"]["serveroffset"] = serveroffset

                                if "epgoffset" not in playlist["player_info"]:
                                    playlist["player_info"]["epgoffset"] = epgoffset

                                if "live_streams" not in playlist["data"]:
                                    playlist["data"]["live_streams"] = live_streams

                                if "catchup_checked" not in playlist["data"]:
                                    playlist["data"]["catchup_checked"] = catchup_checked

                                if "last_check" not in playlist["data"]:
                                    playlist["data"]["last_check"] = last_check

                                if "epgalternative" not in playlist["player_info"]:
                                    playlist["player_info"]["epgalternative"] = epgalternative

                                if "epgalternativeurl" not in playlist["player_info"]:
                                    playlist["player_info"]["epgalternativeurl"] = epgalternativeurl

                                if "liverecents" not in playlist["player_info"]:
                                    playlist["player_info"]["liverecents"] = liverecents

                                if "vodrecents" not in playlist["player_info"]:
                                    playlist["player_info"]["vodrecents"] = vodrecents

                                if "vodwatched" not in playlist["player_info"]:
                                    playlist["player_info"]["vodwatched"] = vodwatched

                                if "serieswatched" not in playlist["player_info"]:
                                    playlist["player_info"]["serieswatched"] = serieswatched

                                if "directsource" not in playlist["player_info"]:
                                    playlist["player_info"]["directsource"] = directsource

                                playlist["playlist_info"]["name"] = name
                                playlist["playlist_info"]["type"] = type
                                playlist["playlist_info"]["output"] = output
                                playlist["playlist_info"]["full_url"] = full_url  # get.php
                                playlist["playlist_info"]["index"] = index
                                playlist["data"]["data_downloaded"] = False
                                playlist["player_info"]["epgoffset"] = epgoffset

                                if playlist["player_info"]["epgalternative"] is True:
                                    if playlist["player_info"]["epgalternativeurl"]:
                                        playlist["playlist_info"]["xmltv_api"] = playlist["player_info"]["epgalternativeurl"]
                                else:
                                    playlist["playlist_info"]["xmltv_api"] = xmltv_api
                                index += 1
                                break

                if not playlist_exists:
                    playlists_all.append({
                        "playlist_info": dict([
                            ("index", index),
                            ("name", name),
                            ("protocol", protocol),
                            ("domain", domain),
                            ("port", port),
                            ("username", username),
                            ("password", password),
                            ("type", type),
                            ("output", output),
                            ("host", host),
                            ("player_api", player_api),
                            ("xmltv_api", xmltv_api),
                            ("full_url", full_url),
                        ]),

                        "player_info": OrderedDict([
                            ("livetype", livetype),
                            ("vodtype", vodtype),
                            ("livehidden", livehidden),
                            ("channelshidden", channelshidden),
                            ("vodhidden", vodhidden),
                            ("vodstreamshidden", vodstreamshidden),
                            ("serieshidden", serieshidden),
                            ("seriestitleshidden", seriestitleshidden),
                            ("seriesseasonshidden", seriesseasonshidden),
                            ("seriesepisodeshidden", seriesepisodeshidden),

                            ("catchuphidden", catchuphidden),
                            ("catchupchannelshidden", catchupchannelshidden),

                            ("livefavourites", livefavourites),
                            ("vodfavourites", vodfavourites),

                            ("liverecents", liverecents),
                            ("vodrecents", vodrecents),
                            ("vodwatched", vodwatched),
                            ("serieswatched", serieswatched),

                            ("showlive", showlive),
                            ("showvod", showvod),
                            ("showseries", showseries),
                            ("showcatchup", showcatchup),
                            ("serveroffset", serveroffset),
                            ("epgoffset", serveroffset),
                            ("epgalternative", epgalternative),
                            ("epgalternativeurl", epgalternativeurl),
                            ("directsource", directsource),
                        ]),

                        "data": dict([
                            ("live_categories", []),
                            ("vod_categories", []),
                            ("series_categories", []),
                            ("live_streams", []),
                            ("catchup", False),
                            ("catchup_checked", False),
                            ("last_check", ""),
                            ("epg_date", ""),
                            ("data_downloaded", False),
                            ("epg_importer_files", False)
                        ]),
                    })

                    index += 1

        # remove old playlists from x-playlists.json

        newList = []

        for playlist in playlists_all:
            for line in lines:
                if not line.startswith("#"):
                    if str(playlist["playlist_info"]["domain"]) in line and "username=" + str(playlist["playlist_info"]["username"]) in line and "password=" + str(playlist["playlist_info"]["password"]) in line:
                        newList.append(playlist)
                        break

        playlists_all = newList

    # write new x-playlists.json file
    with open(playlists_json, "w") as f:
        json.dump(playlists_all, f)

    return playlists_all
