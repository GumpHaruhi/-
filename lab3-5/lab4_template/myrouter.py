#!/usr/bin/env python3

'''
Basic IPv4 router (static routing) in Python.
'''

import time
import switchyard
from switchyard.lib.userlib import *
import pdb


class WaitingPacket():
    def __init__(self, packet: Packet, ifacename: str, senderpro: IPv4Address, targetpro: IPv4Address):
        self.packet: Packet = packet
        self.request_num: int = 0
        self.port: str = ifacename
        self.last_time = time.time() - 5
        self.sendpro: IPv4Address = senderpro
        self.targetpro: IPv4Address = targetpro
    
    def get_packet(self):
        return self.packet


class Router(object):
    def __init__(self, net: switchyard.llnetbase.LLNetBase):
        self.net = net
        # other initialization stuff here
        self.arpcache = {}
        self.timelimit = 200
        self.iptable = []
        self.queue: list[WaitingPacket] = []
        self.hang_arp: list[IPv4Address] = []

    def handle_packet(self, recv: switchyard.llnetbase.ReceivedPacket):
        timestamp, ifaceName, packet = recv
        # TODO: your logic here
        self.updateArpCache()
        # 处理 ARP
        arp = packet.get_header(Arp)
        if arp is not None:
            self.arpcache[arp.senderprotoaddr] = {'m':arp.senderhwaddr, 't': time.time()}
            if arp.operation == ArpOperation.Request:
                ipeth = self.arpcache.get(arp.targetprotoaddr)
                if ipeth is not None:
                    arpreply = create_ip_arp_reply(ipeth['m'], arp.senderhwaddr, arp.targetprotoaddr, arp.senderprotoaddr)
                    self.net.send_packet(ifaceName, arpreply)
                    return
                else:
                    for intf in self.net.interfaces():
                        if intf.ipaddr == arp.targetprotoaddr:
                            arpreply = create_ip_arp_reply(intf.ethaddr, arp.senderhwaddr, arp.targetprotoaddr, arp.senderprotoaddr)
                            self.net.send_packet(ifaceName, arpreply)
                            break
    
            elif arp.operation == ArpOperation.Reply:
                return
        # 其他
        else:
            iphdr = packet.get_header(IPv4)
            if iphdr is None:
                return 
            # 开始匹配
            else:
                matched = []
                for ipkey in self.iptable:
                    matches = (int(iphdr.dst) & int(ipkey[1])) == (int(ipkey[0]) & int(ipkey[1]))
                    if matches:
                        log_info("one match perfix {}".format(ipkey[0]))
                        matched.append(ipkey)
                # 没有匹配
                if len(matched) == 0:
                    return 
                elif len(matched) == 1:
                    pair = matched[0]
                # 如果有多个匹配，选最长前缀
                elif len(matched) > 1:
                    log_info("more than one matched !")
                    maxval = 0
                    for ipkey in matched:
                        val = int(iphdr.dst) & int(ipkey[0])
                        log_info("perfix {} match {} bit".format(ipkey[0], val))
                        if val > maxval:
                            maxval = val
                            pair = ipkey
                # 此时 pair 即为匹配的表项
                log_info("src {} dst {} match perfix {} new dst {} port {}".format(iphdr.src, iphdr.dst, pair[0], pair[2], pair[3]))
                # 修改 src 以太头
                packet[0].src = self.get_eth(pair[3])
                for info in self.net.interfaces():
                    if iphdr.dst == info.ipaddr:
                        packet[0].dst = info.ethaddr
                        self.net.send_packet(info.name, packet)
                        return 
                # 如果存在下一跳
                if pair[2] != IPv4Address('0.0.0.0'):
                    pa = WaitingPacket(packet, pair[3], self.search_sendrpro(pair[2]), pair[2])
                else:
                    pa = WaitingPacket(packet, pair[3], pair[0], iphdr.dst)
                log_info("defined senderpro {} and targetpro {}".format(pa.sendpro, pa.targetpro))
                self.queue.append(pa)
        ...

    def start(self):
        '''A running daemon of the router.
        Receive packets until the end of time.
        '''
        while True:
            self.update_queue()
            try:
                recv = self.net.recv_packet(timeout=1.0)
            except NoPackets:
                continue
            except Shutdown:
                break
            
            self.handle_packet(recv)
            
        self.stop()

    def stop(self):
        self.net.shutdown()

    def updateArpCache(self):
        current = time.time()
        to_dele = []

        for key in self.arpcache:
            if current - self.arpcache[key]['t'] > self.timelimit:
                to_dele.append(key)

        for key in to_dele:
            del self.arpcache[key]

    def init_IPtable(self):
        # from ports
        for info in self.net.interfaces():
            ipkey = [info.ipaddr, IPv4Address('255.255.0.0'), IPv4Address('0.0.0.0'), info.name]
            self.iptable.append(ipkey)
            log_info("perfix {} mask {} next hop {} port {}".format(ipkey[0], ipkey[1], ipkey[2], ipkey[3]))
        # from txt file
        with open('forwarding_table.txt', 'r') as file:
            for line in file:
                # 去除行末的换行符
                line = line.strip()
                # 使用空格分割行内容
                parts = line.split(' ')
                # 处理每个部分
                ipkey = []
                count = 0
                for str in parts:
                    count += 1
                    if count == 4:
                        ipkey.append(str)
                    else:
                        ipkey.append(IPv4Address(str))
                # 加入
                self.iptable.append(ipkey)
                log_info("perfix {} mask {} next hop {} port {}".format(ipkey[0], ipkey[1], ipkey[2], ipkey[3]))

    def get_eth(self, ifname):
        for info in self.net.interfaces():
            if info.name == ifname:
                return info.ethaddr
        return None

    def check_self(self, ipdst):
        for info in self.net.interfaces():
            if ipdst == info.ipaddr:
                return 1
        return 0

    def update_queue(self):
        if len(self.queue) == 0:
            return 
        to_dele = []
        # 遍历队列
        for waitp in self.queue:
            log_info("find for dst {} port {}".format(waitp.targetpro, waitp.port))
            flag = 0
            # 先从 ARP 缓存表里查找
            for arpkey in self.arpcache:
                if waitp.targetpro == arpkey:
                    self.arpcache[arpkey]['t'] = time.time()
                    bag = waitp.packet
                    bag[0].dst = self.arpcache[arpkey]['m']
                    bag.get_header(IPv4).ttl -= 1
                    log_info("send packet Eth: {} to {} and ip: {} to {}".format(bag[0].src, bag[0].dst, bag[1].src, bag[1].dst))
                    self.net.send_packet(waitp.port, bag)
                    to_dele.append(waitp)
                    flag = 1
                    break
            # 已经找到了，下一位
            if flag == 1:
                continue
            # 判断是否已经发送5次ARP
            if waitp.request_num >= 5 and time.time() - waitp.last_time > 1:
                self.hang_arp.remove(waitp.targetpro)
                to_dele.append(waitp)
                continue
            # 发送 ARP 包
            if time.time() - waitp.last_time > 1 and (waitp.targetpro not in self.hang_arp or waitp.request_num > 0):
                if waitp.targetpro not in self.hang_arp:
                    self.hang_arp.append(waitp.targetpro)
                arprequest = create_ip_arp_request(waitp.packet[0].src, waitp.sendpro, waitp.targetpro)
                self.net.send_packet(waitp.port, arprequest)
                waitp.last_time = time.time()
                waitp.request_num += 1
        # 删除包
        for waitp in to_dele:
            self.queue.remove(waitp)


    def search_sendrpro(self, hop: IPv4Address):
        matched = []
        for ipkey in self.iptable:
            matches = (int(hop) & int(ipkey[1])) == (int(ipkey[0]) & int(ipkey[1]))
            if matches:
                matched.append(ipkey)
        # 没有匹配
        if len(matched) == 0:
            return hop
        elif len(matched) == 1:
            pair = matched[0]
        # 如果有多个匹配，选最长前缀
        elif len(matched) > 1:
            maxval = 0
            for ipkey in matched:
                val = int(hop) & int(ipkey[0])                  
                if val > maxval:
                    maxval = val
                    pair = ipkey

        if pair[2] != IPv4Address('0.0.0.0'):
            return self.search_sendrpro(pair[2])
        return pair[0]


def main(net):
    '''
    Main entry point for router.  Just create Router
    object and get it going.
    '''
    router = Router(net)
    router.init_IPtable()
    router.start()


# swyard -t testcases/myrouter1_testscenario.srpy myrouter.py

# swyard -t testcases/testscenario2.srpy myrouter.py
# swyard -t testcases/testscenario2_advanced.srpy myrouter.py