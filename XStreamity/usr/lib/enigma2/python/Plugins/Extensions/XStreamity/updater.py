#!/usr/bin/python
# -*- coding: utf-8 -*-

import re
import sys

from Screens.Console import Console
from Screens.MessageBox import MessageBox

from . import _


PY3 = sys.version_info[0] == 3
INSTALLER_URL = "https://raw.githubusercontent.com/kiddac/XStreamity/master/installer.sh"
VERSION_URL = "https://raw.githubusercontent.com/kiddac/XStreamity/master/XStreamity/usr/lib/enigma2/python/Plugins/Extensions/XStreamity/version.txt"
USER_AGENT = "XStreamity online updater"


def urlread(url, timeout=10):
    """Return an HTTP response body while supporting Python 2 and Python 3."""
    if PY3:
        from urllib.request import Request, urlopen
    else:
        from urllib2 import Request, urlopen

    request = Request(url, headers={"User-Agent": USER_AGENT})
    try:
        import ssl
        response = urlopen(
            request,
            timeout=timeout,
            context=ssl._create_unverified_context()
        )
    except (ImportError, AttributeError, TypeError):
        response = urlopen(request, timeout=timeout)

    try:
        return response.read()
    finally:
        try:
            response.close()
        except Exception:
            pass


def parseInstaller(data):
    """Extract optional version metadata and the multiline description."""
    if PY3 and isinstance(data, bytes):
        data = data.decode("utf-8", "replace")

    version = None
    description = ""
    descriptionLines = None

    for line in data.splitlines():
        if descriptionLines is not None:
            if line.rstrip().endswith('"'):
                descriptionLines.append(line.rstrip()[:-1])
                description = "\n".join(descriptionLines).strip()
                descriptionLines = None
            else:
                descriptionLines.append(line)
            continue

        line = line.strip()
        if line.startswith("version="):
            version = line[len("version="):].strip("\"' ")
        elif line.startswith("description="):
            rest = line[len("description="):]
            if rest.startswith('"'):
                rest = rest[1:]
            if rest.endswith('"'):
                description = rest[:-1].strip()
            else:
                descriptionLines = [rest] if rest else []

    return version, description


def downloadUpdateInfo():
    """Return the remote version file and installer metadata."""
    versionData = urlread(VERSION_URL, 10)
    installerData = urlread(INSTALLER_URL, 10)
    return versionData, installerData


def decodeText(data):
    if PY3 and isinstance(data, bytes):
        return data.decode("utf-8", "replace")
    return data


def versionTuple(value):
    """Compare versions such as 1.78-20260928 numerically."""
    if value is None:
        return None
    parts = re.findall(r"\d+", str(value))
    if not parts:
        return None
    return tuple(int(part) for part in parts)


class OnlineUpdater(object):
    def __init__(self, session, currentVersion):
        self.session = session
        self.currentVersion = str(currentVersion).strip()
        self.closed = False

    def check(self):
        """Run the network request away from the Enigma2 GUI thread."""
        try:
            from twisted.internet import threads
            deferred = threads.deferToThread(downloadUpdateInfo)
            deferred.addCallbacks(self._checkFinished, self._checkFailed)
        except Exception as error:
            print("[XStreamity] Unable to start update check: %s" % error)

    def close(self):
        self.closed = True

    def _checkFailed(self, failure):
        try:
            message = failure.getErrorMessage()
        except Exception:
            message = str(failure)
        print("[XStreamity] Online update check failed: %s" % message)

    def _checkFinished(self, result):
        if self.closed:
            return

        versionData, installerData = result
        versionText = decodeText(versionData).strip()
        remoteVersion = versionText.splitlines()[0] if versionText else None
        description = parseInstaller(installerData)[1]
        remote = versionTuple(remoteVersion)
        current = versionTuple(self.currentVersion)

        if remote is None or current is None:
            print("[XStreamity] Online update version check failed")
            return
        if remote <= current:
            print("[XStreamity] No online update available")
            return

        message = "%s %s %s.\n\n%s\n\n%s" % (
            _("New version"),
            remoteVersion,
            _("is available"),
            description,
            _("Do you want to install it now?")
        )
        self.session.openWithCallback(
            self._install,
            MessageBox,
            message,
            MessageBox.TYPE_YESNO
        )

    def _install(self, answer=False):
        if not answer or self.closed:
            return

        command = "wget '%s' -O - | /bin/sh" % INSTALLER_URL
        self.session.open(
            Console,
            title=_("Installing XStreamity update"),
            cmdlist=[command],
            closeOnSuccess=False
        )
