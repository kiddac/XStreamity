#!/usr/bin/python
# -*- coding: utf-8 -*-

import os

from time import time

try:
    import cPickle
except ImportError:
    import pickle as cPickle


def setResumePoint(session):
    service = session.nav.getCurrentService()
    ref = session.nav.getCurrentlyPlayingServiceReference()

    if not service or not ref or "http" not in ref.toString():
        return

    seek = service.seek()

    if not seek:
        return

    pos = seek.getPlayPosition()

    if pos[0]:
        return

    ref_string = ref.toString()
    lru = int(time())
    length = seek.getLength()

    if length:
        length = length[1]
    else:
        length = None

    resume_data = [lru, pos[1], length]
    resumePointCache[ref_string] = resume_data

    parts = ref_string.split(":", 1)

    if len(parts) == 2:
        ref_body = parts[1]

        for streamtype in ("4097", "5001", "5002", "8193"):
            key = str(streamtype) + ":" + ref_body
            resumePointCache[key] = resume_data

    clearOldResumePoints(14)

    saveResumePoints()


def delResumePoint(ref):
    try:
        del resumePointCache[ref.toString()]
    except KeyError:
        pass

    saveResumePoints()


def getResumePoint(session):
    global resumePointCache
    resumePointCache = loadResumePoints()

    ref = None
    if session.nav.getCurrentlyPlayingServiceReference():
        if "http" in session.nav.getCurrentlyPlayingServiceReference().toString():
            ref = session.nav.getCurrentlyPlayingServiceReference()

    if (ref is not None) and (ref.type != 1):
        try:
            entry = resumePointCache[ref.toString()]
            entry[0] = int(time())  # update LRU timestamp
            return entry[1]
        except KeyError:
            return None


def saveResumePoints():
    try:
        with open(os.path.join("/etc/enigma2/xstreamity", "resumepoints.pkl"), "wb") as f:
            cPickle.dump(resumePointCache, f, cPickle.HIGHEST_PROTOCOL)
    except Exception as e:
        print("[XStreamity] Failed to write resumepoints:", e)


def loadResumePoints():
    try:
        with open(os.path.join("/etc/enigma2/xstreamity", "resumepoints.pkl"), "rb") as f:
            data = cPickle.load(f)
            return data
    except Exception as e:
        print("[XStreamity] Failed to load resumepoints:", e)
        return {}


def clearOldResumePoints(max_age_days=14):
    now = int(time())
    max_age = int(max_age_days) * 24 * 60 * 60

    for key in list(resumePointCache.keys()):
        try:
            entry = resumePointCache[key]
            lru = int(entry[0])
        except Exception:
            try:
                del resumePointCache[key]
            except KeyError:
                pass
            continue

        if now - lru > max_age:
            try:
                del resumePointCache[key]
            except KeyError:
                pass


resumePointCache = loadResumePoints()
