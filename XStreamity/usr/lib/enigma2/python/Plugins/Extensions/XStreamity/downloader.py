# -*- coding: utf-8 -*-
from twisted.web import client
from twisted.internet import reactor, defer, ssl
import sys

# remove factory starting/stopping from logs
from twisted.internet.protocol import Factory
Factory.noisy = False

try:
    pythonVer = sys.version_info.major
except:
    pythonVer = 2


# https twisted client hack #
try:
    from urlparse import urlparse
except:
    from urllib.parse import urlparse

try:
    from twisted.internet._sslverify import ClientTLSOptions
    sslverify = True
except:
    sslverify = False

if sslverify:
    class SNIFactory(ssl.ClientContextFactory):
        def __init__(self, hostname=None):
            self.hostname = hostname

        def getContext(self):
            ctx = self._contextFactory(self.method)
            if self.hostname:
                ClientTLSOptions(self.hostname, ctx)
            return ctx


# convert byte data to strings
def convert(data):
    if isinstance(data, bytes):
        return data.decode()
    if isinstance(data, dict):
        return dict(map(convert, data.items()))
    if isinstance(data, tuple):
        return tuple(map(convert, data))
    return data


class HTTPProgressDownloader(client.HTTPDownloader):
    def __init__(self, url, outfile, headers=None):
        client.HTTPDownloader.__init__(self, url, outfile, headers=headers, agent="Enigma2", followRedirect=True, afterFoundGet=True)
        self.status = self.progress_callback = self.error_callback = self.end_callback = None
        self.deferred = defer.Deferred()

    def noPage(self, reason):
        if self.status.decode() == "304":
            print(reason.getErrorMessage())
            client.HTTPDownloader.page(self, "")
        else:
            client.HTTPDownloader.noPage(self, reason)
        if self.error_callback:
            self.error_callback(reason.getErrorMessage(), self.status.decode())

    def gotHeaders(self, headers):

        headers = convert(headers)
        if self.status.decode() == "200":
            if "content-length" in headers:
                self.totalbytes = int(headers["content-length"][0])
            else:
                self.totalbytes = 0
            self.currentbytes = 0.0
        return client.HTTPDownloader.gotHeaders(self, headers)

    def pagePart(self, packet):
        if self.status.decode() == "200":
            self.currentbytes += len(packet)
        if self.totalbytes and self.progress_callback:
            self.progress_callback(self.currentbytes, self.totalbytes)
        return client.HTTPDownloader.pagePart(self, packet)

    def pageEnd(self):
        ret = client.HTTPDownloader.pageEnd(self)
        if self.end_callback:
            self.end_callback()
        return ret


class downloadWithProgress:
    def __init__(self, url, outputfile, contextFactory=None, *args, **kwargs):

        parsed = urlparse(url)
        scheme = parsed.scheme
        host = parsed.hostname
        port = parsed.port or (443 if scheme == 'https' else 80)

        sniFactory = SNIFactory(host)

        if pythonVer == 3:
            url = url.encode()

        self.factory = HTTPProgressDownloader(url, outputfile, *args, **kwargs)

        if scheme == "https":
            self.connection = reactor.connectSSL(host, port, self.factory, sniFactory)
        else:
            try:
                self.connection = reactor.connectTCP(host, port, self.factory)
            except:
                self.connection = reactor.connectSSL(host, port, self.factory, sniFactory)

    def start(self):
        return self.factory.deferred

    def stop(self):
        if self.connection:
            self.factory.progress_callback = self.factory.end_callback = self.factory.error_callback = None
            self.connection.disconnect()

            # hack to force stop - disconnect doesn't stop download - need to find a better solution
            url = "http"
            if pythonVer == 3:
                url = url.encode()
            self.factory.setURL(url)
            self.connection.connect()

    def addProgress(self, progress_callback):
        self.factory.progress_callback = progress_callback

    def addEnd(self, end_callback):
        self.factory.end_callback = end_callback

    def addError(self, error_callback):
        # print(error_callback)
        self.factory.error_callback = error_callback
