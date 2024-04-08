#!/usr/bin/python
# -*- coding: utf-8 -*-

import os

from time import time

try:
    import cPickle
except ImportError:
    import pickle as cPickle


def setResumePoint(session):
    global resumePointCache
    service = session.nav.getCurrentService()

    if not service:
        return

    ref = session.nav.getCurrentlyPlayingServiceReference()
    if not ref or "http" not in ref.toString():
        return

    seek = service.seek()
    if not seek:
        return

    pos = seek.getPlayPosition()
    if pos[0]:  # If seeking is not possible, return
        return

    if session.nav.getCurrentlyPlayingServiceReference():
        if "http" in session.nav.getCurrentlyPlayingServiceReference().toString():
            ref = session.nav.getCurrentlyPlayingServiceReference()

    key = ref.toString()
    lru = int(time())
    length = seek.getLength()
    if length:
        length = length[1]
    else:
        length = None

    resumePointCache[key] = [lru, pos[1], length]

    saveResumePoints()


def delResumePoint(ref):
    global resumePointCache
    try:
        del resumePointCache[ref.toString()]
    except KeyError:
        pass

    saveResumePoints()


def getResumePoint(session):
    global resumePointCache

    resumePointCache = loadResumePoints()

    ref = session.nav.getCurrentlyPlayingServiceReference()
    if ref and "http" in ref.toString() and ref.type != 1:
        try:
            entry = resumePointCache.get(ref.toString())
            if entry:
                entry[0] = int(time())  # Update LRU timestamp
                return entry[1]
        except KeyError:
            pass

    return None


def saveResumePoints():
    global resumePointCache
    try:
        with open(os.path.join("/etc/enigma2/xstreamity", "resumepoints.pkl"), "wb") as f:
            cPickle.dump(resumePointCache, f, cPickle.HIGHEST_PROTOCOL)
    except Exception as e:
        print("[XStreamity] Failed to write resumepoints:", e)


def loadResumePoints():
    try:
        with open(os.path.join("/etc/enigma2/xstreamity", "resumepoints.pkl"), "rb") as f:
            PickleFile = cPickle.load(f)
            return PickleFile
    except Exception as e:
        print("[XStreamity] Failed to load resumepoints:", e)
        return {}


def updateresumePointCache():
    global resumePointCache
    resumePointCache = loadResumePoints()


resumePointCache = loadResumePoints()
