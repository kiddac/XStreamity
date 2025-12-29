#!/usr/bin/python
# -*- coding: utf-8 -*-

# Standard library imports
from collections import OrderedDict
import json
import os
import re

try:
    from urllib.parse import urlparse, parse_qs, quote, unquote
except ImportError:
    from urlparse import urlparse, parse_qs
    from urllib import quote, unquote

# Local application/library-specific imports
from .plugin import cfg


def process_files():
    playlist_file = cfg.playlist_file.value
    playlists_json = cfg.playlists_json.value

    # Check if playlists.txt file exists in specified location
    if not os.path.isfile(playlist_file):
        with open(playlist_file, "a"):
            pass

    # Check if x-playlists.json file exists in specified location
    if not os.path.isfile(playlists_json):
        with open(playlists_json, "a"):
            pass

    playlists_all = []
    if os.path.isfile(playlists_json):
        with open(playlists_json, "r") as f:
            try:
                playlists_all = json.load(f)
            except ValueError:
                os.remove(playlists_json)

    # Check playlist.txt entries are valid
    with open(playlist_file, "r+") as f:
        lines = f.readlines()

    with open(playlist_file, "w") as f:
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

    # Read entries from playlists.txt
    index = 0
    livetype = cfg.livetype.value
    vodtype = cfg.vodtype.value

    for line in lines:
        port = ""
        username = ""
        password = ""
        media_type = ""
        output = ""
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
        live_streams = []
        serveroffset = 0
        catchupoffset = 0
        epgoffset = 0
        epgalternative = False
        epgalternativeurl = ""
        customsids = False
        fail_count = 0

        if line.startswith("http"):
            line = line.strip(" ")
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
                host = protocol + domain + ":" + str(port)
            else:
                host = protocol + domain

            query = parse_qs(parsed_uri.query, keep_blank_values=True)

            if "username" not in query or "password" not in query:
                continue

            username = query["username"][0].strip()
            password = query["password"][0].strip()

            # Make username/password URL-safe (Twisted rejects non-ASCII URIs)
            try:
                username = quote(username.decode("utf-8").encode("utf-8"), safe="")
            except Exception:
                username = quote(username, safe="")

            try:
                password = quote(password.decode("utf-8").encode("utf-8"), safe="")
            except Exception:
                password = quote(password, safe="")

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

            if "timeshift" in query:
                try:
                    epgoffset = int(query["timeshift"][0].strip())
                except ValueError:
                    pass

            player_api = host + "/player_api.php?username=" + username + "&password=" + password
            xmltv_api = host + "/xmltv.php?username=" + username + "&password=" + password
            full_url = host + "/get.php?username=" + username + "&password=" + password + "&type=" + media_type + "&output=" + output

            playlist_exists = False

            for playlist in playlists_all:
                # Extra check in case playlists.txt details have been amended
                if ("domain" in playlist["playlist_info"]
                        and "username" in playlist["playlist_info"]):
                    if (playlist["playlist_info"]["domain"] == domain
                            and playlist["playlist_info"]["username"] == username):

                        playlist_exists = True

                        # Dictionary containing keys and default values for playlist["player_info"] and playlist["data"]
                        default_values = {
                            "player_info": {
                                "channelshidden": channelshidden,
                                "vodstreamshidden": vodstreamshidden,
                                "seriestitleshidden": seriestitleshidden,
                                "seriesseasonshidden": seriesseasonshidden,
                                "seriesepisodeshidden": seriesepisodeshidden,
                                "catchuphidden": catchuphidden,
                                "catchupchannelshidden": catchupchannelshidden,
                                "serveroffset": serveroffset,
                                "catchupoffset": catchupoffset,
                                "epgoffset": epgoffset,
                                "epgalternative": epgalternative,
                                "epgalternativeurl": epgalternativeurl,
                                "liverecents": liverecents,
                                "vodrecents": vodrecents,
                                "vodwatched": vodwatched,
                                "serieswatched": serieswatched,
                                "seriesfavourites": seriesfavourites,
                            },
                            "data": {
                                "live_streams": live_streams,
                                "customsids": customsids,
                                "fail_count": fail_count
                            }
                        }

                        # Iterate over keys and default values and update playlist
                        for key, value in default_values.items():
                            for sub_key, sub_value in value.items():
                                if sub_key not in playlist[key]:
                                    playlist[key][sub_key] = sub_value

                        playlist["playlist_info"]["name"] = name
                        playlist["playlist_info"]["type"] = media_type
                        playlist["playlist_info"]["output"] = output
                        playlist["playlist_info"]["full_url"] = full_url
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

    # Remove old playlists from x-playlists.json
    new_list = []

    for playlist in playlists_all:
        for line in lines:
            if not line.startswith("#"):
                username = str(playlist["playlist_info"]["username"])
                username_unquote = unquote(username)

                if (str(playlist["playlist_info"]["domain"]) in line
                        and (("username=" + username) in line or ("username=" + username_unquote) in line)):
                    new_list.append(playlist)
                    break

    playlists_all = new_list

    # Write new x-playlists.json file
    with open(playlists_json, "w") as f:
        json.dump(playlists_all, f, indent=4)

    return playlists_all
