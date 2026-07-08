#!/usr/bin/python
# -*- coding: utf-8 -*-

# Standard library imports
from collections import OrderedDict
import json
import os
import re

try:
    from urllib.parse import urlparse, parse_qs
except ImportError:
    from urlparse import urlparse, parse_qs

# Local application/library-specific imports
from .plugin import cfg, dir_tmp


def dedupe_playlists(playlists):
    seen = set()
    unique = []

    for p in playlists:
        pi = p.get("playlist_info", {})
        key = (
            str(pi.get("domain", "")).lower(),
            str(pi.get("username", "")).strip(),
            str(pi.get("password", "")).strip()
        )

        if key in seen:
            continue

        seen.add(key)
        unique.append(p)

    return unique


def process_files():
    scans_dir = os.path.join(dir_tmp, "scans")
    scanner_playlist_file = os.path.join(scans_dir, "playlists.txt")
    scanner_playlists_json = os.path.join(scans_dir, "x-playlists.json")

    # Check if playlists.txt file exists in specified location
    if not os.path.isfile(scanner_playlist_file):
        with open(scanner_playlist_file, "a"):
            pass

    # Check if x-playlists.json file exists in specified location
    if not os.path.isfile(scanner_playlists_json):
        with open(scanner_playlists_json, "a"):
            pass

    playlists_all = []
    if os.path.isfile(scanner_playlists_json):
        with open(scanner_playlists_json, "r") as f:
            try:
                playlists_all = json.load(f)
            except ValueError:
                os.remove(scanner_playlists_json)

    # Check playlist.txt entries are valid
    with open(scanner_playlist_file, "r+") as f:
        lines = f.readlines()

    cleaned_lines = []

    with open(scanner_playlist_file, "w") as f:
        for line in lines:
            line = re.sub(" +", " ", line)
            line = line.strip(" ")

            if not line.startswith(("http://", "https://", "#")):
                line = "# " + line

            if "=mpegts" in line:
                line = line.replace("=mpegts", "=ts")

            if "=hls" in line:
                line = line.replace("=hls", "=m3u8")

            if line.strip() == "#":
                line = ""

            if line != "":
                f.write(line)
                cleaned_lines.append(line)

    lines = cleaned_lines

    # Read entries from playlists.txt
    index = 0
    livetype = cfg.livetype.value
    vodtype = cfg.vodtype.value

    for line in lines:
        if line.startswith("http"):
            port = ""
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
            seriesfavourites = []
            liverecents = []
            vodrecents = []
            vodwatched = []
            serieswatched = []
            serveroffset = 0
            catchupoffset = 0
            epgoffset = 0
            epgalternative = False
            epgalternativeurl = ""

            line = line.strip(" ")
            parsed_uri = urlparse(line)
            protocol = parsed_uri.scheme + "://"

            if not (protocol == "http://" or protocol == "https://"):
                continue

            if not parsed_uri.hostname:
                continue

            domain = parsed_uri.hostname.lower()
            name = domain

            if line.partition(" #")[-1]:
                name = line.partition(" #")[-1].strip()

            if parsed_uri.port:
                port = parsed_uri.port
                host = protocol + domain + ":" + str(port)
            else:
                host = protocol + domain

            query = parse_qs(parsed_uri.query, keep_blank_values=True)

            if "username" not in query or "password" not in query:
                continue

            username = query["username"][0].strip()
            password = query["password"][0].strip()

            if "type" in query:
                media_type = query["type"][0].strip()
            else:
                media_type = "m3u_plus"

            if media_type not in ["m3u", "m3u_plus"]:
                media_type = "m3u_plus"

            if "output" in query:
                output = query["output"][0].strip()
            else:
                output = "ts"

            if output not in ["ts", "m3u8", "mpegts", "hls"]:
                output = "ts"

            if output == "mpegts":
                output = "ts"

            if output == "hls":
                output = "m3u8"

            player_api = host + "/player_api.php?username=" + username + "&password=" + password
            xmltv_api = host + "/xmltv.php?username=" + username + "&password=" + password
            full_url = host + "/get.php?username=" + username + "&password=" + password + "&type=" + media_type + "&output=" + output

            playlists_all.append({
                "playlist_info": {
                    "index": index,
                    "name": name,
                    "protocol": protocol,
                    "domain": domain,
                    "port": port,
                    "username": username,
                    "password": password,
                    "type": media_type,
                    "output": output,
                    "host": host,
                    "player_api": player_api,
                    "xmltv_api": xmltv_api,
                    "full_url": full_url,
                },
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
                    ("seriesfavourites", seriesfavourites),
                    ("liverecents", liverecents),
                    ("vodrecents", vodrecents),
                    ("vodwatched", vodwatched),
                    ("serieswatched", serieswatched),
                    ("showlive", showlive),
                    ("showvod", showvod),
                    ("showseries", showseries),
                    ("showcatchup", showcatchup),
                    ("serveroffset", serveroffset),
                    ("catchupoffset", catchupoffset),
                    ("epgoffset", epgoffset),
                    ("epgalternative", epgalternative),
                    ("epgalternativeurl", epgalternativeurl),
                ]),

                "data": {
                    "live_categories": [],
                    "vod_categories": [],
                    "series_categories": [],
                    "live_streams": [],
                    "catchup": False,
                    "customsids": False,
                    "epg_date": "",
                    "data_downloaded": False,
                    "fail_count": 0
                },
            })

            index += 1

    # Write new x-playlists.json file
    with open(scanner_playlists_json, "w") as f:
        playlists_all = dedupe_playlists(playlists_all)
        json.dump(playlists_all, f, indent=4)

    return playlists_all
