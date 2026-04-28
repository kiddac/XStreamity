#!/usr/bin/python
# -*- coding: utf-8 -*-

import os

try:
    from enigma import eAVSwitch
except Exception:
    from enigma import eAVControl as eAVSwitch

hasAVSwitch = False
try:
    from Components.AVSwitch import avSwitch
    hasAVSwitch = True
except Exception:
    pass


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


def _get_current_aspect_ratio():

    current_ar = None

    # 1 Fallback to proc (ATV / BH / VTi etc)
    if current_ar is None:
        try:
            if os.path.exists("/proc/stb/video/aspect"):
                with open("/proc/stb/video/aspect", "r") as f:
                    aspect = f.read().strip()

                with open("/proc/stb/video/policy", "r") as f:
                    policy = f.read().strip()

                if aspect == "4:3":
                    if policy == "letterbox":
                        current_ar = 0
                    elif policy == "panscan":
                        current_ar = 1

                elif aspect == "16:9":
                    if policy == "letterbox":
                        current_ar = 6
                    elif policy == "panscan":
                        current_ar = 3
                    else:
                        current_ar = 2

                elif aspect == "16:10":
                    if policy == "letterbox":
                        current_ar = 4
                    elif policy == "panscan":
                        current_ar = 5

        except Exception as e:
            print("*** proc read failed ***", e)

    # 2 Try eAVSwitch (if available)
    if current_ar is None:
        try:
            inst = eAVSwitch.getInstance()
            if hasattr(inst, "getAspectRatio"):
                current_ar = int(inst.getAspectRatio())
        except Exception as e:
            print("*** eAVSwitch failed ***", e)

    # 3 DreamOS fallback
    if current_ar is None:
        try:
            if os.path.exists("/sys/class/video/screen_mode"):
                with open("/sys/class/video/screen_mode", "r") as f:
                    mode = f.read().strip()

                print("*** AR via DreamOS ***", mode)

                if "letterbox" in mode:
                    current_ar = 0
                elif "panscan" in mode:
                    current_ar = 1
                elif "16:9" in mode:
                    current_ar = 2

        except Exception as e:
            print("*** DreamOS read failed ***", e)

    # 4 Final fallback - config settings
    if current_ar is None:
        try:
            if hasAVSwitch:
                current_ar = int(avSwitch.getAspectRatioSetting())
        except Exception as e:
            print("*** avSwitch failed ***", e)

    return current_ar
