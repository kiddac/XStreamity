# -*- coding: utf-8 -*-
# Shared HTTPS (SNI) helper for the Twisted client, used by all XStreamity screens.

try:
    from twisted.internet import ssl
    from twisted.internet.abstract import isIPAddress, isIPv6Address
    from OpenSSL import SSL
    sslverify = True
except ImportError:
    sslverify = False
    SNIFactory = None  # callers check sslverify before using it


if sslverify:
    def _set_sni(ctx, hostname):
        # Twisted 24+ changed ClientTLSOptions(); set SNI on the context directly.
        if isinstance(hostname, bytes):
            hostname = hostname.decode("ascii", "ignore")
        if not hostname or isIPAddress(hostname) or isIPv6Address(hostname):
            return
        try:
            sni = hostname.encode("idna")
        except Exception:
            sni = hostname.encode("ascii", "ignore")

        def _cb(conn, where, ret):
            if where & SSL.SSL_CB_HANDSHAKE_START:
                conn.set_tlsext_host_name(sni)
        ctx.set_info_callback(_cb)

    class SNIFactory(ssl.ClientContextFactory):
        def __init__(self, hostname=None):
            self.hostname = hostname

        def getContext(self):
            ctx = self._contextFactory(self.method)
            if self.hostname:
                _set_sni(ctx, self.hostname)
            return ctx
