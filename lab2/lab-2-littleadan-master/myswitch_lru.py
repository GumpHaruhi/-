'''
Ethernet learning switch in Python.

Note that this file currently has the code to implement a "hub"
in it, not a learning switch.  (I.e., it's currently a switch
that doesn't learn.)
'''
import switchyard
from switchyard.lib.userlib import *


def update_table(table, ethaddr, port, clock, limit):
    if ethaddr in table:
        table[ethaddr]['tamp'] = clock
        table[ethaddr]['port'] = port
        return
    if len(table) < limit:
        table[ethaddr] = {'port':port, 'tamp':clock}
        return
    else:
        max_age = 0
        for addr in table:
            age = clock - table[addr]['tamp']
            if age > max_age:
                max_age = age
                oldrule = addr
        log_info(f"delete a old rule {oldrule}")
        del table[oldrule]
        table[ethaddr] = {'port':port, 'tamp':clock}


def main(net: switchyard.llnetbase.LLNetBase):
    my_interfaces = net.interfaces()
    mymacs = [intf.ethaddr for intf in my_interfaces]
    switch_table = {}
    rule_limit = 5
    clock = 0

    while True:
        try:
            _, fromIface, packet = net.recv_packet()
        except NoPackets:
            continue
        except Shutdown:
            break

        log_debug (f"Recieve packet {packet} from {fromIface}")
        eth = packet.get_header(Ethernet)
        if eth is None:
            log_info("Received a non-Ethernet packet?!")
            return
        
        clock += 1
        update_table(switch_table, eth.src, fromIface, clock, rule_limit)
        if eth.dst in mymacs:
            log_info("Received a packet intended for me")
        elif eth.dst in switch_table:
            value = switch_table.get(eth.dst)
            log_info(f"Hit ! forward packet {packet} to {value['port']}")
            net.send_packet(value['port'], packet)
            value['tamp'] = clock
        else:
            for intf in my_interfaces:
                if fromIface != intf.name:
                    log_info (f"Flooding packet {packet} to {intf.name}")
                    net.send_packet(intf, packet)

    net.shutdown()


# swyard -t testcases/myswitch_lru_testscenario.srpy myswitch_lru.py