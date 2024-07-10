'''
Ethernet learning switch in Python.

Note that this file currently has the code to implement a "hub"
in it, not a learning switch.  (I.e., it's currently a switch
that doesn't learn.)
'''
import switchyard
from switchyard.lib.userlib import *


def update_table(table, ethaddr, port, limit):
    if ethaddr in table:
        table[ethaddr]['volume'] += 1
        table[ethaddr]['port'] = port
        return 
    log_info(f"Add new rule {ethaddr}")
    if len(table) < limit:
        table[ethaddr] = {'port':port, 'volume':1}
        return
    else:
        min_volume = float('inf')
        for addr in table:
            if table[addr]['volume'] < min_volume:
                min_volume = table[addr]['volume']
                oldrule = addr
        log_info(f"delete a old rule {oldrule}")
        del table[oldrule]
        table[ethaddr] = {'port':port, 'volume':1}


def main(net: switchyard.llnetbase.LLNetBase):
    my_interfaces = net.interfaces()
    mymacs = [intf.ethaddr for intf in my_interfaces]
    switch_table = {}
    rule_limit = 5

    while True:
        try:
            _, fromIface, packet = net.recv_packet()
        except NoPackets:
            continue
        except Shutdown:
            break

        log_info (f"Recieve packet {packet} from {fromIface}")
        eth = packet.get_header(Ethernet)
        if eth is None:
            log_info("Received a non-Ethernet packet?!")
            return
        
        update_table(switch_table, eth.src, fromIface, rule_limit)
        if eth.dst in mymacs:
            log_info("Received a packet intended for me")
        elif eth.dst in switch_table:
            value = switch_table.get(eth.dst)
            log_info(f"Hit ! forward packet {packet} to {value['port']}")
            net.send_packet(value['port'], packet)
            value['volume'] += 1
        else:
            for intf in my_interfaces:
                if fromIface != intf.name:
                    log_info (f"Flooding packet {packet} to {intf.name}")
                    net.send_packet(intf, packet)

    net.shutdown()


# swyard -t testcases/myswitch_traffic_testscenario.srpy myswitch_traffic.py