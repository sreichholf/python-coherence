# Licensed under the MIT license
# http://opensource.org/licenses/mit-license.php
#
# Copyright (C) 2006 Fluendo, S.A. (www.fluendo.com).
# Copyright 2006, Frank Scholz <coherence@beebits.net>

from __future__ import absolute_import
import socket
import time

import six

from twisted.internet.protocol import DatagramProtocol
from twisted.internet import reactor
from twisted.internet import task

from coherence.upnp.core import utils

import coherence.extern.louie as louie

SSDP_PORT = 1900
SSDP_ADDR = '239.255.255.250'
SSDP_ADDR_6 = 'FF05::C'

from coherence import log

class MSearch(DatagramProtocol, log.Loggable):
    logCategory = 'msearch'

    def __init__(self, ssdp_server, ipv6=False, test=False):
        self.ssdp_server = ssdp_server
        self._isIPv6 = ipv6
        if test == False:
            iface = '::' if self._isIPv6 else ''
            self.port = reactor.listenUDP(0, self, interface=iface)

            self.double_discover_loop = task.LoopingCall(self.double_discover)
            self.double_discover_loop.start(120.0)

    def datagramReceived(self, data, addr):
        (host, port) = addr
        data = six.ensure_str(data)
        cmd, headers = utils.parse_http_response(data)
        self.info('datagramReceived from %s:%d, protocol %s code %s' % (host, port, cmd[0], cmd[1]))
        if cmd[0].startswith('HTTP/1.') and cmd[1] == '200':
            self.msg('for %r', headers['usn'])
            if not self.ssdp_server.isKnown(headers['usn']):
                self.info('register as remote %s, %s, %s' % (headers['usn'], headers['st'], headers['location']))
                self.ssdp_server.register('remote',
                                            headers['usn'], headers['st'],
                                            headers['location'],
                                            headers['server'],
                                            headers['cache-control'],
                                            host=host)
            else:
                self.ssdp_server.known[headers['usn']]['last-seen'] = time.time()
                self.debug('updating last-seen for %r' % headers['usn'])

        # make raw data available
        # send out the signal after we had a chance to register the device
        louie.send('UPnP.SSDP.datagram_received', None, data, host, port)

    def double_discover(self):
        " Because it's worth it (with UDP's reliability) "
        self.info('send out discovery for ssdp:all')
        self.discover()
        self.discover()

    def _discover(self, addr, port):
        req = [ 'M-SEARCH * HTTP/1.1',
                'HOST: %s:%d' % (addr, port),
                'MAN: "ssdp:discover"',
                'MX: 5',
                'ST: ssdp:all',
                'USER-AGENT: Coherence UDAP/2.0',
                '','']
        req = six.ensure_binary('\r\n'.join(req))
        try:
            self.transport.write(req, (addr, port))
        except socket.error as msg:
            self.info("failure sending out the discovery message: %r" % msg)

    def discover(self):
        if self._isIPv6:
            self._discover(SSDP_ADDR_6, SSDP_PORT)
        else:
            self._discover(SSDP_ADDR, SSDP_PORT)
