<center><font size=6>LAB_4 实验报告</font></center>



**姓名：**甘思毅

**学号：**221900398

----------------------

### IP Forwarding Table 的初始化

对于一个路由器，iptable 即为 IP Forwarding 表。

表中的元素格式为：

```
ipkey = [prefix, mask, next hop, port name]
```

IP Forwarding 表的初始化应该在路由器工作之前。修改 main 函数：

```python
def main(net):
    '''
    Main entry point for router.  Just create Router
    object and get it going.
    '''
    router = Router(net)
    router.init_IPtable()     # 初始化函数
    router.start()
```

**下面是 router.init_IPtable() 函数的内容**

- 首先将路由器自身的端口添到表中：

```
# from ports
for info in self.net.interfaces():
    ipkey = [info.ipaddr, IPv4Address('255.255.0.0'), IPv4Address('0.0.0.0'), info.name]
    self.iptable.append(ipkey)
```

- 之后从 forwarding_table.txt 文件中读取信息：

```python
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
                    # 除了端口的名称使用字符串形式的数据，其他均保存为 IPv4Address 形式
                    if count == 4:
                        ipkey.append(str)
                    else:
                        ipkey.append(IPv4Address(str))
                # 加入
                self.iptable.append(ipkey)
```

至次，IP Forwarding Table 构建完毕



### 当路由器收到一个数据包

对于 ARP 类型的包，在 **LAB_3** 中已经介绍。对于非 ARP 类型的包，首先检测其是否是 IPv4 类型：

```python
iphdr = packet.get_header(IPv4)
if iphdr is None:
    return 
```

> 注意，在使用 mininet 时候难免会收到其他（非 ARP 非 IPv4）类型的包，路由器应当忽略它们

之后把数据包的 IP 目的地址与 IP forwarding 表中的前缀匹配。**考虑到可能有多个前缀匹配，将所有匹配的前缀存放在列表 matched **

```python
matched = []
for ipkey in self.iptable:
    # 判断是否匹配
    matches = (int(iphdr.dst) & int(ipkey[1])) == (int(ipkey[0]) & int(ipkey[1]))
    if matches:
        matched.append(ipkey)
    # 没有匹配
    if len(matched) == 0:
        return 
    # 有唯一前缀匹配
    elif len(matched) == 1:
        pair = matched[0]
    # 如果有多个匹配，选最长前缀
    elif len(matched) > 1:
        maxval = 0
        for ipkey in matched:
            val = int(iphdr.dst) & int(ipkey[0])
            if val > maxval:
                maxval = val
                pair = ipkey
```

经过匹配之后，变量 **pair **即为最终敲定的匹配项

按照 pair 项中的端口名称为包修改以太头的源地址。接着检查一下：**如果数据包的目的 ip 就是路由器自身的一个端口，则直接将其转发出去**

```python
# 修改 src 以太头
packet[0].src = self.get_eth(pair[3])
for info in self.net.interfaces():
    if iphdr.dst == info.ipaddr:
        packet[0].dst = info.ethaddr
        # 直接转发
        self.net.send_packet(info.name, packet)
        return 
```

否则，则将此数据包放入等待队列中，等候接下来的处理



### 路由器的待 forward 队列的设计

此队列中的数据包均需要通过 ARP 查询来获得下一步的以太网目的地址。因此它们需要维护几个信息，我设计了 WaitingPacket 类：

```python
class WaitingPacket():
    def __init__(self, packet: Packet, ifacename: str, senderpro: IPv4Address, targetpro: IPv4Address):
        # 数据包本身
        self.packet: Packet = packet
        # 为这个包发送过的 ARP 数量
        self.request_num: int = 0
        # 这个包的发送端口 （以太目的地址）
        self.port: str = ifacename
        # 上次发送 ARP 请求的时间
        # 这里初始为当前时间的前5秒，意外着路由器将立即为这个包发送 ARP 请求
        self.last_time = time.time() - 5
        # ARP 请求的源IP
        self.sendpro: IPv4Address = senderpro
        # ARP 请求的目的IP
        self.targetpro: IPv4Address = targetpro
    
    def get_packet(self):
        return self.packet
    
# 在路由器中维护一个等待队列
class Router :
   	self.queue: list[WaitingPacket] = []
```

对于一个数据包：

- 如果不存在 next hop ，其 ARP 包的发送 IP 应为包所匹配的前缀，目的 IP 为包自身的目的 IP
- 如果存在 next hop ，ARP 包的目的 IP 应为 next hop 地址，使用 next hop 在 IP Forwaring 表中匹配到的前缀才是发送 IP 

**考虑到 next hop 匹配到的前缀可能有下一个 next hop ，因此设计一个递归的函数 search_sendrpro 来搜索 ARP 的发送 IP **

```python
	def search_sendrpro(self, hop: IPv4Address):
        # 为参数地址匹配前缀
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
		# 如果匹配到的前缀还存在 next hop ，则递归的继续搜索
        if pair[2] != IPv4Address('0.0.0.0'):
            return self.search_sendrpro(pair[2])
        # 返回匹配的前缀
        return pair[0]
```

因此，对于一个需要添加到等到队列的包，路由器执行下面逻辑：

```python
if pair[2] != IPv4Address('0.0.0.0'):  # 存在下一跳
	pa = WaitingPacket(packet, pair[3], self.search_sendrpro(pair[2]), pair[2])
else:
	pa = WaitingPacket(packet, pair[3], pair[0], iphdr.dst)
self.queue.append(pa)
```



### 路由器等待队列的处理

每次遍历等待队列，对于队列中的每一个数据包：

- 从 ARP cache 中查找是否有匹配的项。若有，则将此包转发，并从等待队列中删除
- 若没有找到：
  - 若已经发送了 5 次 ARP 请求且均未得到回应，则从队列中删除，丢弃此包
  - 若未达到五次，且距离上次 ARP 请求超过一秒，则再发送一次 ARP 请求

**注意，如果先后有多个包需要 ARP 请求同一个 IP 地址，不应该重复发送！**因此为路由器维护一个列表 

```python
class Router:
	self.hang_arp: list[IPv4Address] = []	
```

只有符合条件：

*距离上次发送已超过1秒 && ( hang_arp 中没有待请求的 IP  ||  当前包已经发送过 ARP 请求 )*

的数据包才可以发送 ARP 请求

使用函数 update_queue 来更新等待队列

```python
def update_queue(self):
    if len(self.queue) == 0:
        return 
    to_dele = []      # 存放需要删除的包
    # 遍历队列
    for waitp in self.queue:
        flag = 0
        # 先从 ARP 缓存表里查找
        for arpkey in self.arpcache:
            if waitp.targetpro == arpkey:
                # 如果找到了，将包转发，同时更新 ARP 缓存中的时间
                self.arpcache[arpkey]['t'] = time.time()
                bag = waitp.packet
                # 修改以太头
                bag[0].dst = self.arpcache[arpkey]['m']
                # 消减寿命
                bag.get_header(IPv4).ttl -= 1
                self.net.send_packet(waitp.port, bag)
                to_dele.append(waitp)
                flag = 1
                break
        # 已经找到了，下一位
        if flag == 1:
            continue
        # 判断是否已经发送5次ARP
        if waitp.request_num >= 5 and time.time() - waitp.last_time > 1:
            # 将超时的包删除，同时将其目的 IP 从 hang_arp 中移除
            self.hang_arp.remove(waitp.targetpro)
            to_dele.append(waitp)
            continue
        # 发送 ARP 包
        if time.time() - waitp.last_time > 1 and 
        	(waitp.targetpro not in self.hang_arp or waitp.request_num > 0):
            # 将新的请求 IP 添加到 hang 
            if waitp.targetpro not in self.hang_arp:
                self.hang_arp.append(wait.targetpro)
            # 构建并发送 ARP 请求
            arprequest = create_ip_arp_request(waitp.packet[0].src, waitp.sendpro, waitp.targetpro)
            self.net.send_packet(waitp.port, arprequest)
            waitp.last_time = time.time()
            waitp.request_num += 1
    # 删除包
    for waitp in to_dele:
        self.queue.remove(waitp)
```

路由器的等待队列应该不停的被更新，以便及时发送 ARP 请求，而不是在接收到一个新的包的时候才被动的更新。更改工作主循环 router.start ：

``` python
def start(self):
    while True:
        self.update_queue()     # 更新等待队列
        try:
            recv = self.net.recv_packet(timeout=1.0)
        except NoPackets:
            continue
        except Shutdown:
            break
            
        self.handle_packet(recv)
            
    self.stop()
```



### 实验结果

```
Results for test scenario IP forwarding and ARP requester tests: 31 passed, 0 failed, 0 pending


Passed:
1   IP packet to be forwarded to 172.16.42.2 should arrive on
    router-eth0
2   Router should send ARP request for 172.16.42.2 out router-
    eth2 interface
3   Router should receive ARP response for 172.16.42.2 on
    router-eth2 interface
4   IP packet should be forwarded to 172.16.42.2 out router-eth2
5   IP packet to be forwarded to 192.168.1.100 should arrive on
    router-eth2
6   Router should send ARP request for 192.168.1.100 out router-
    eth0
7   Router should receive ARP response for 192.168.1.100 on
    router-eth0
8   IP packet should be forwarded to 192.168.1.100 out router-
    eth0
9   Another IP packet for 172.16.42.2 should arrive on router-
    eth0
10  IP packet should be forwarded to 172.16.42.2 out router-eth2
    (no ARP request should be necessary since the information
    from a recent ARP request should be cached)
11  IP packet to be forwarded to 192.168.1.100 should arrive on
    router-eth2
12  IP packet should be forwarded to 192.168.1.100 out router-
    eth0 (again, no ARP request should be necessary since the
    information from a recent ARP request should be cached)
13  An IP packet from 10.100.1.55 to 172.16.64.35 should arrive
    on router-eth1
14  Router should send an ARP request for 10.10.1.254 on router-
    eth1
15  Application should try to receive a packet, but then timeout
16  Router should send another an ARP request for 10.10.1.254 on
    router-eth1 because of a slow response
17  Router should receive an ARP response for 10.10.1.254 on
    router-eth1
18  IP packet destined to 172.16.64.35 should be forwarded on
    router-eth1
19  An IP packet from 192.168.1.239 for 10.200.1.1 should arrive
    on router-eth0.  No forwarding table entry should match.
20  An IP packet from 192.168.1.239 for 10.10.50.250 should
    arrive on router-eth0.
21  Router should send an ARP request for 10.10.50.250 on
    router-eth1
22  Router should try to receive a packet (ARP response), but
    then timeout
23  Router should send an ARP request for 10.10.50.250 on
    router-eth1
24  Router should try to receive a packet (ARP response), but
    then timeout
25  Router should send an ARP request for 10.10.50.250 on
    router-eth1
26  Router should try to receive a packet (ARP response), but
    then timeout
27  Router should send an ARP request for 10.10.50.250 on
    router-eth1
28  Router should try to receive a packet (ARP response), but
    then timeout
29  Router should send an ARP request for 10.10.50.250 on
    router-eth1
30  Router should try to receive a packet (ARP response), but
    then timeout
31  Router should try to receive a packet (ARP response), but
    then timeout


All tests passed!

```

