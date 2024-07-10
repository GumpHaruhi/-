#!/usr/bin/env python3

import time
import threading
from random import randint

import switchyard
from switchyard.lib.address import *
from switchyard.lib.packet import *
from switchyard.lib.userlib import *


class Middlebox:
    def __init__(
            self,
            net: switchyard.llnetbase.LLNetBase,
            dropRate="0.19"
    ):
        self.net = net
        self.dropRate = float(dropRate)

    def handle_packet(self, recv: switchyard.llnetbase.ReceivedPacket):
        _, fromIface, packet = recv
        if fromIface == "middlebox-eth0":
            log_debug("Received from blaster")
            '''
            Received data packet
            Should I drop it?
            If not, modify headers & send to blastee
            '''
            randnum = randint(0, 99)
            weight = randnum / 100.0
            if weight < self.dropRate:
                # 丢包
                pass
            else :
                ip_hdr = packet.get_header(IPv4)
                udp_hdr = packet.get_header(UDP)
                trans = Ethernet(src="40:00:00:00:00:02", dst="20:00:00:00:00:01") + \
                    IPv4(src=ip_hdr.src, dst=ip_hdr.dst) + \
                    UDP(src=udp_hdr.src, dst=udp_hdr.dst)
                trans[1].protocol = IPProtocol.UDP

                hdr_len = len(trans.to_bytes())
                op_raw = packet.to_bytes()
                loadraw = op_raw[hdr_len:]
                trans.add_header(RawPacketContents(loadraw))
                self.net.send_packet("middlebox-eth1", trans)
        elif fromIface == "middlebox-eth1":
            log_debug("Received from blastee")
            '''
            Received ACK
            Modify headers & send to blaster. Not dropping ACK packets!
            net.send_packet("middlebox-eth0", pkt)
            '''
            ip_hdr = packet.get_header(IPv4)
            udp_hdr = packet.get_header(UDP)
            trans = Ethernet(src="40:00:00:00:00:01", dst="10:00:00:00:00:01") + \
                    IPv4(src=ip_hdr.src, dst=ip_hdr.dst) + \
                    UDP(src=udp_hdr.src, dst=udp_hdr.dst)
            trans[1].protocol = IPProtocol.UDP
                
            hdr_len = len(trans.to_bytes())
            op_raw = packet.to_bytes()
            loadraw = op_raw[hdr_len:]
            trans.add_header(RawPacketContents(loadraw))
        
            self.net.send_packet("middlebox-eth0", trans)
        else:
            log_debug("Oops :))")

    def start(self):
        '''A running daemon of the router.
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
    middlebox = Middlebox(net, **kwargs)
    middlebox.start()
