#!/usr/bin/python
# -*- coding: utf-8 -*-


from time import time

try:
    import cPickle
except:
    import pickle as cPickle


def setResumePoint(session):
    global resumePointCache
    service = session.nav.getCurrentService()

    ref = None
    if session.nav.getCurrentlyPlayingServiceReference():
        if "http" in session.nav.getCurrentlyPlayingServiceReference().toString():
            ref = session.nav.getCurrentlyPlayingServiceReference()

    if (service is not None) and (ref is not None):
        seek = service.seek()
        if seek:
            pos = seek.getPlayPosition()
            if not pos[0]:
                key = ref.toString()
                lru = int(time())
                l = seek.getLength()
                if l:
                    l = l[1]
                else:
                    l = None
                resumePointCache[key] = [lru, pos[1], l]
                saveResumePoints()


def getResumePoint(session, failed=False):
    global resumePointCache
    resumePointCache = loadResumePoints()

    ref = None
    if session.nav.getCurrentlyPlayingServiceReference():
        if "http" in session.nav.getCurrentlyPlayingServiceReference().toString():
            ref = session.nav.getCurrentlyPlayingServiceReference()

    if (ref is not None) and (ref.type != 1):
        entry = resumePointCache[ref.toString()]
        entry[0] = int(time())  # update LRU timestamp
        return entry[1]


def saveResumePoints():
    global resumePointCache
    try:
        f = open("/etc/enigma2/xstreamity/resumepoints.pkl", "wb")
        cPickle.dump(resumePointCache, f, cPickle.HIGHEST_PROTOCOL)
        f.close()
    except Exception as e:
        print("[XStreamity] Failed to write resumepoints:", e)


def loadResumePoints():
    try:
        f = open("/etc/enigma2/xstreamity/resumepoints.pkl", "rb")
        PickleFile = cPickle.load(f)
        f.close()
        return PickleFile
    except Exception as e:
        print("[XStreamity] Failed to load resumepoints:", e)
        return {}


resumePointCache = {}
