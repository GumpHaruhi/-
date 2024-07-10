#!/usr/bin/env python3

import time
import threading
from struct import pack
import switchyard
from switchyard.lib.address import *
from switchyard.lib.packet import *
from switchyard.lib.userlib import *


class Blastee:
    def __init__(
            self,
            net: switchyard.llnetbase.LLNetBase,
            blasterIp,
            num
    ):
        self.net = net
        # TODO: store the parameters
        self.blasterIP = blasterIp
        self.num = num
        ...

    def handle_packet(self, recv: switchyard.llnetbase.ReceivedPacket):
        _, fromIface, packet = recv
        log_debug(f"I got a packet from {fromIface}")
        log_debug(f"Pkt: {packet}")
        udp_hdr = packet.get_header(UDP)

        ack = Ethernet(src="20:00:00:00:00:01", dst="40:00:00:00:00:02") + \
            IPv4(src="192.168.200.1", dst="192.168.100.1") + \
            UDP(src=udp_hdr.dst, dst=udp_hdr.src)
        ack[1].protocol = IPProtocol.UDP

        hdr_len = ack.size()
        raw = packet.to_bytes()[hdr_len:]
        ack.add_payload(RawPacketContents(raw[:4]))
        if len(raw) < 14:
            raw += bytes([0]*(14-len(raw)))
    
        ack.add_payload(RawPacketContents(raw[6:14]))
        
        self.net.send_packet("blastee-eth0", ack)

    def start(self):
        '''A running daemon of the blastee.
        Receive packets until the end of time.
        '''
        while True:
            try:
                recv = self.net.recv_packet(timeout=1.0)
            except NoPackets:
                continue
            except Shutdown:
                break

            self.handle_packet(recv)

        self.shutdown()

    def shutdown(self):
        self.net.shutdown()


def main(net, **kwargs):
    blastee = Blastee(net, **kwargs)
    blastee.start()
