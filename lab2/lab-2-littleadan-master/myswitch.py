'''
Ethernet learning switch in Python.

Note that this file currently has the code to implement a "hub"
in it, not a learning switch.  (I.e., it's currently a switch
that doesn't learn.)
'''
import switchyard
from switchyard.lib.userlib import *


def main(net: switchyard.llnetbase.LLNetBase):
    my_interfaces = net.interfaces()
    mymacs = [intf.ethaddr for intf in my_interfaces]
    switch_table = {}

    while True:
        try:
            _, fromIface, packet = net.recv_packet()
        except NoPackets:
            continue
        except Shutdown:
            break

        log_debug (f"In {net.name} received packet {packet} on {fromIface}")
        eth = packet.get_header(Ethernet)
        if eth is None:
            log_info("Received a non-Ethernet packet?!")
            return

        switch_table[eth.src] = {'port': fromIface}
        if eth.dst in mymacs:
            log_info("Received a packet intended for me")
        elif eth.dst in switch_table:
            value = switch_table.get(eth.dst)
            net.send_packet(value['port'], packet)
        else:
            for intf in my_interfaces:
                if fromIface != intf.name:
                    log_info (f"Flooding packet {packet} to {intf.name}")
                    net.send_packet(intf, packet)

    net.shutdown()


# swyard -t testcases/myswitch_to_testscenario.srpy myswitch.py