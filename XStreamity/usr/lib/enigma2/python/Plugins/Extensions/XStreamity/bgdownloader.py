#!/usr/bin/python
# -*- coding: utf-8 -*-

from twisted.internet import threads
import twisted.python.runtime
import requests


def backgroundDownloader(self, url, location, timeout=5, callback=None, errback=None):
    try:
        d = threads.deferToThread(backgroundDownloaderUrl, url, location, timeout)
        if callback:
            d.addCallback(getattr(self, callback))
        if errback:
            d.addErrback(getattr(self, errback))
        else:
            d.addErrback(backgroundDownloaderError)
    except Exception as e:
        print(e)


def backgroundDownloaderUrl(url, location, timeout):
    print("backgroundDownloaderUrl %s" % url)
    try:
        with requests.get(url, stream=True, timeout=timeout) as r:
            r.raise_for_status()
            with open(location, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
    except Exception as e:
        print(e)


def backgroundDownloaderError(data=None):
    print("Download failed: %s" % data)
