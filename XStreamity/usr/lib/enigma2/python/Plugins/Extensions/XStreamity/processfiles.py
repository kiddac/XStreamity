
from .plugin import json_file, playlist_path, cfg
from collections import OrderedDict

import json
import os


try:
    from urlparse import urlparse, parse_qs
except:
    from urllib.parse import urlparse, parse_qs


def processfiles():
    # load x-playlists.json file
    playlists_all = []
    if os.path.isfile(json_file):
        with open(json_file, "r") as f:
            try:
                playlists_all = json.load(f)
            except:
                os.remove(json_file)

    # check playlist.txt entries are valid
    with open(playlist_path, 'r+') as f:
        lines = f.readlines()
        f.seek(0)
        f.writelines((line.strip(' ') for line in lines if line.strip()))
        f.seek(0)
        for line in lines:
            if not line.startswith('http://') and not line.startswith('https://') and not line.startswith('#'):
                line = '# ' + line
            if "=mpegts" in line:
                line = line.replace("=mpegts", "=ts")
            if "=hls" in line:
                line = line.replace("=hls", "=m3u8")
            if line.strip() == "#":
                line = ""
            f.write(line)
        f.seek(0)

        # read entries from playlists.txt
        index = 0
        port = 80
        username = ''
        password = ''
        type = 'm3u_plus'
        output = 'ts'
        livetype = cfg.livetype.getValue()
        vodtype = cfg.vodtype.getValue()
        catchuptype = cfg.catchuptype.getValue()
        epgshift = 0
        catchupshift = 0
        livehidden = []
        vodhidden = []
        serieshidden = []
        channelshidden = []

        showlive = True
        showvod = True
        showseries = True
        showcatchup = True
        # epgquickshift = 0
        livefavourites = []
        vodfavourites = []
        serveroffset = 0

        for line in lines:

            if not line.startswith("#") and line.startswith('http'):
                line = line.strip()

                parsed_uri = urlparse(line)

                protocol = parsed_uri.scheme + "://"

                if not (protocol == "http://" or protocol == "https://"):
                    continue

                domain = parsed_uri.hostname
                name = domain
                if line.partition(" #")[-1]:
                    name = line.partition(" #")[-1]

                if parsed_uri.port:
                    port = parsed_uri.port

                host = "%s%s:%s" % (protocol, domain, port)

                query = parse_qs(parsed_uri.query, keep_blank_values=True)

                if "username" in query:
                    username = query['username'][0].strip()
                else:
                    continue

                if "password" in query:
                    password = query['password'][0].strip()
                else:
                    continue

                if "type" in query:
                    type = query['type'][0].strip()

                if "output" in query:
                    output = query['output'][0].strip()

                epgshiftexists = False
                if "timeshift" in query:
                    try:
                        epgshiftexists = True
                        epgshift = int(query['timeshift'][0].strip())
                    except:
                        pass

                player_api = "%s/player_api.php?username=%s&password=%s" % (host, username, password)
                enigma2_api = "%s/enigma2.php?username=%s&password=%s" % (host, username, password)
                xmltv_api = "%s/xmltv.php?username=%s&password=%s" % (host, username, password)
                full_url = "%s/get.php?username=%s&password=%s&type=%s&output=%s" % (host, username, password, type, output)

                playlist_exists = False

                if playlists_all:
                    for playlists in playlists_all:

                        # extra check in case playlists.txt details have been amended
                        if "domain" in playlists["playlist_info"] and "username" in playlists["playlist_info"] and "password" in playlists["playlist_info"]:
                            if playlists["playlist_info"]["domain"] == domain and playlists["playlist_info"]["username"] == username and playlists["playlist_info"]["password"] == password:

                                playlist_exists = True

                                if "channelshidden" not in playlists["player_info"]:
                                    playlists["player_info"]["channelshidden"] = channelshidden

                                if "serveroffset" not in playlists["player_info"]:
                                    playlists["player_info"]["serveroffset"] = serveroffset

                                if "catchupshift" not in playlists["player_info"]:
                                    playlists["player_info"]["catchupshift"] = catchupshift

                                playlists["playlist_info"]["name"] = name
                                playlists["playlist_info"]["type"] = type
                                playlists["playlist_info"]["output"] = output
                                playlists["playlist_info"]["full_url"] = full_url  # get.php
                                playlists["playlist_info"]["index"] = index
                                playlists["data"]["data_downloaded"] = False
                                if epgshiftexists:
                                    playlists["player_info"]["epgshift"] = epgshift

                                """
                                if "epgtype" not in playlists["player_info"]:
                                    playlists["player_info"]["epgtype"] = epgtype

                                if "epgquickshift" not in playlists["player_info"]:
                                    playlists["player_info"]["epgquickshift"] = epgquickshift
                                    """
                                # break

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
                            ("enigma2_api", enigma2_api),
                            ("xmltv_api", xmltv_api),
                            ("full_url", full_url),
                        ]),
                        "player_info": OrderedDict([
                            ("livetype", livetype),
                            ("vodtype", vodtype),
                            ("catchuptype", catchuptype),
                            ("epgshift", epgshift),
                            ("catchupshift", catchupshift),
                            ("livehidden", livehidden),
                            ("vodhidden", vodhidden),
                            ("serieshidden", serieshidden),
                            ("channelshidden", channelshidden),
                            ("livefavourites", livefavourites),
                            ("vodfavourites", vodfavourites),
                            ("showlive", showlive),
                            ("showvod", showvod),
                            ("showseries", showseries),
                            ("showcatchup", showcatchup),
                            ("serveroffset", serveroffset),
                        ]),

                        "data": dict([
                            ("live_categories", []),
                            ("vod_categories", []),
                            ("series_categories", []),
                            ("live_streams", []),
                            ("catchup", False),
                            ("catchup_checked", False),
                            ("last_check", ''),
                            ("epg_date", ''),
                            ("data_downloaded", False),
                            ("epg_importer_files", False)
                        ]),
                    })

            index += 1

        # remove old playlists from x-playlists.json
        f.seek(0)

        if playlists_all:
            newList = []

            for playlist in playlists_all:
                for line in lines:
                    if not line.startswith('#'):
                        if str(playlist["playlist_info"]["domain"]) in line and 'username=' + str(playlist["playlist_info"]["username"]) in line and 'password=' + str(playlist["playlist_info"]["password"]) in line:
                            newList.append(playlist)

            playlists_all = newList

    # write new x-playlists.json file
    with open(json_file, 'w') as f:
        json.dump(playlists_all, f)

    return playlists_all
