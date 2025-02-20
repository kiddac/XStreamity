#!/usr/bin/python
# -*- coding: utf-8 -*-

# Standard library imports
import json
import os

# Enigma2 components
from Components.Label import Label
from Components.ActionMap import ActionMap
from datetime import datetime
from Screens.Screen import Screen

# Local application/library-specific imports
from . import _
from . import xstreamity_globals as glob
from .plugin import skin_directory, cfg
from .xStaticText import StaticText


class XStreamity_UserInfo(Screen):
    ALLOW_SUSPEND = True

    def __init__(self, session):
        Screen.__init__(self, session)
        self.session = session

        skin_path = os.path.join(skin_directory, cfg.skin.value)
        skin = os.path.join(skin_path, "userinfo.xml")
        with open(skin, "r") as f:
            self.skin = f.read()

        self.setup_title = _("User Information")

        self["status"] = Label("")
        self["expiry"] = Label("")
        self["created"] = Label("")
        self["trial"] = Label("")
        self["activeconn"] = Label("")
        self["maxconn"] = Label("")
        self["formats"] = Label("")
        self["realurl"] = Label("")
        self["timezone"] = Label("")
        self["serveroffset"] = Label("")

        self["t_status"] = StaticText(_("Status:"))
        self["t_expiry"] = StaticText(_("Expiry Date:"))
        self["t_created"] = StaticText(_("Created At:"))
        self["t_trial"] = StaticText(_("Is Trial:"))
        self["t_activeconn"] = StaticText(_("Active Connections:"))
        self["t_maxconn"] = StaticText(_("Max Connections:"))
        self["t_formats"] = StaticText(_("Allowed Output Formats:"))
        self["t_realurl"] = StaticText(_("Real URL:"))
        self["t_timezone"] = StaticText(_("Timezone:"))
        self["t_serveroffset"] = StaticText(_("Server Offset:"))

        self["actions"] = ActionMap(["XStreamityActions"], {
            "ok": self.quit,
            "cancel": self.quit,
            "red": self.quit,
            "menu": self.quit}, -2)

        self["key_red"] = StaticText(_("Close"))

        self.onFirstExecBegin.append(self.createUserSetup)
        self.onLayoutFinish.append(self.__layoutFinished)

    def __layoutFinished(self):
        self.setTitle(self.setup_title)

    def createUserSetup(self):
        status_map = {
            "Active": _("Active"),
            "Banned": _("Banned"),
            "Disabled": _("Disabled"),
            "Expired": _("Expired")
        }

        user_info = glob.active_playlist.get("user_info", {})
        server_info = glob.active_playlist.get("server_info", {})
        player_info = glob.active_playlist.get("player_info", {})

        self["status"].setText(status_map.get(user_info.get("status"), _("Unknown")))

        exp_date = user_info.get("exp_date")
        self["expiry"].setText(datetime.fromtimestamp(int(exp_date)).strftime("%d-%m-%Y  %H:%M") if exp_date else "Null")

        created_at = user_info.get("created_at")
        self["created"].setText(datetime.fromtimestamp(int(created_at)).strftime("%d-%m-%Y  %H:%M") if created_at else "Null")

        self["trial"].setText(str(user_info.get("is_trial", "")))
        self["activeconn"].setText(str(user_info.get("active_cons", "")))
        self["maxconn"].setText(str(user_info.get("max_connections", "")))

        self["formats"].setText(str(json.dumps(user_info.get("allowed_output_formats", []))).lstrip("[").rstrip("]"))

        self["realurl"].setText(str(server_info.get("url", "")))
        self["timezone"].setText(str(server_info.get("timezone", "")))

        self["serveroffset"].setText(str(player_info.get("serveroffset", "")))

    def quit(self):
        self.close()
