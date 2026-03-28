#!/usr/bin/python
# -*- coding: utf-8 -*-

import os


def _cleanup_epg_folders(playlists_all, cfg, dir_tmp):
    import shutil
    epg_root = os.path.join(str(cfg.epglocation.value).rstrip("/"), "iptv-epg")

    if "iptv-epg" not in epg_root:
        return

    if os.path.isdir(epg_root):
        valid_playlists = set()
        for playlist in playlists_all:
            try:
                valid_playlists.add(str(playlist["playlist_info"]["name"]))
            except Exception:
                pass
        for folder_name in os.listdir(epg_root):
            epgfolder = os.path.join(epg_root, folder_name)
            if not os.path.isdir(epgfolder):
                continue
            if folder_name not in valid_playlists:
                try:
                    shutil.rmtree(epgfolder)
                except Exception:
                    pass
                continue
            try:
                for filename in os.listdir(epgfolder):
                    if filename.lower().endswith(".xml"):
                        try:
                            os.remove(os.path.join(epgfolder, filename))
                        except Exception:
                            pass
            except Exception:
                pass

    try:
        if os.path.isdir(dir_tmp):
            for item in os.listdir(dir_tmp):
                path = os.path.join(dir_tmp, item)
                try:
                    if os.path.isdir(path):
                        shutil.rmtree(path)
                    else:
                        os.remove(path)
                except Exception:
                    pass
    except Exception:
        pass
