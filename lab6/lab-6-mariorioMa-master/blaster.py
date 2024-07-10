#!/usr/bin/env python3

import time
from random import randint
import switchyard
from switchyard.lib.address import *
from switchyard.lib.packet import *
from switchyard.lib.userlib import *


class Blaster:
    def __init__(
            self,
            net: switchyard.llnetbase.LLNetBase,
            blasteeIp,
            num,
            length="100",
            senderWindow="5",
            timeout="300",
            recvTimeout="100"
    ):
        self.net = net
        # TODO: store the parameters
        self.blasteeIP = blasteeIp
        self.num = int(num)
        self.length = int(length)
        self.SW = int(senderWindow)
        self.timeout = float(timeout)
        self.recv_timeout = float(recvTimeout)
        self.LHS = 1
        self.RHS = 1
        self.resend_num = 0
        self.TOnum = 0
        self.totalbyte = 0
        self.goodbyte = 0
        self.finish = []
        ...

    def make_packet(self, th:int):
        pkt = Ethernet(src="10:00:00:00:00:01", dst="40:00:00:00:00:01") + \
            IPv4(src="192.168.100.1", dst="192.168.200.1") + UDP()
        pkt[1].protocol = IPProtocol.UDP
        pkt[UDP].src = 4444
        pkt[UDP].dst = 5555

        pkt.add_payload(RawPacketContents(th.to_bytes(4, 'big')))
        pkt.add_payload(RawPacketContents(self.length.to_bytes(2, 'big')))
        payload = bytes([0]*self.length)
        pkt.add_payload(RawPacketContents(payload))
        return pkt

    def handle_packet(self, recv: switchyard.llnetbase.ReceivedPacket):
        _, fromIface, packet = recv
        log_debug("I got a packet")
        praw = packet.to_bytes()
        eth_hdr = packet.get_header(Ethernet)
        ip_hdr = packet.get_header(IPv4)
        udp_hdr = packet.get_header(UDP)
        hdr_len = eth_hdr.size() + ip_hdr.size() + udp_hdr.size()
        seq_raw = praw[hdr_len:hdr_len+4]
        seq = int.from_bytes(seq_raw, 'big')
        
        if not seq in self.finish:
            self.finish.append(seq)
            if self.LHS == seq:
                while(1):
                    self.LHS += 1
                    if self.LHS not in self.finish:
                        break
                self.staytime = time.time()

        if self.LHS == self.num:
            self.totaltime = time.time() - self.start_time

        if self.RHS-self.LHS+1 < self.SW and self.RHS <= self.num:
            pkt = self.make_packet(self.RHS)
            self.net.send_packet("blaster-eth0", pkt)
            self.totalbyte += 1
            self.goodbyte += 1
            self.RHS += 1

    def handle_no_packet(self):
        log_debug("Didn't receive anything")
        if self.RHS == 1:
            self.start_time = time.time()

        if self.RHS-self.LHS+1 < self.SW and self.RHS <= self.num:
            pkt = self.make_packet(self.RHS)
            self.net.send_packet("blaster-eth0", pkt)

            self.totalbyte += 1
            self.goodbyte += 1
            if self.LHS==1 and self.RHS==1:
                self.staytime = time.time()
            self.RHS += 1

        if time.time()-self.staytime > self.timeout:
            for th in range(self.LHS, self.RHS-1):
                if not th in self.finish:
                    pkt = self.make_packet(th)
                    self.net.send_packet("blaster-eth0", pkt)
                    self.resend_num += 1
                    self.totalbyte += self.length
                    self.TOnum += 1
            
            self.staytime = time.time()
        ...

    def start(self):
        '''A running daemon of the blaster.
        Receive packets until the end of time.
        '''
        while True:
            try:
                recv = self.net.recv_packet(timeout=self.recv_timeout)
            except NoPackets:
                self.handle_no_packet()
                continue
            except Shutdown:
                break

            self.handle_packet(recv)

        self.shutdown()

    def shutdown(self):
        self.net.shutdown()
        print("%d", self.totaltime)
        print("%d", self.resend_num)
        print("%d", self.TOnum)
        print("%d", self.totalbyte / self.totaltime)
        print("%d", self.goodbyte / self.totaltime)

def main(net, **kwargs):
    blaster = Blaster(net, **kwargs)
    blaster.start()