# LAB 3

对于传进路由器的数据包，判断其是否为 ARP Rquest 类型包，如果不是，先丢弃

self.arpcache 即为 arp 缓存表

- 如果是 ARP reply ：

  将它丢弃，把这个ARP包中的包含的（申请到的）ip-eth 信息添加到 arp cache 中

- 如果是ARP request ：

​	将这个包的来源信息添加到 arp cache 中，之后对 arp.targetprotoaddr 匹配

​	先从已有的 arp cache 中查找是否有匹配的项

​	再从路由器自身的接口中匹配

​	若都没有匹配，则丢弃。否则构建 arp reply 并发送

```python
arp = packet.get_header(Arp)
# 如果含有 ARP 头，说明这是一个ARP包
if arp is not None:
    # 如果是请求包
    if arp.operation == ArpOperation.Request:
        # 更新到 ARP 缓存
        self.arpcache[arp.senderprotoaddr] = {'m':arp.senderhwaddr, 't': time.time()}
        # 先尝试在缓存表中匹配
        ipeth = self.arpcache.get(arp.targetprotoaddr)
        if ipeth is not None:
            # 匹配成功
            arpreply = create_ip_arp_reply(ipeth['m'], arp.senderhwaddr, arp.targetprotoaddr, arp.senderprotoaddr)
            self.net.send_packet(ifaceName, arpreply)
            return
        # 缓存表中没有，从路由器接口中查找
        else:
            for intf in self.net.interfaces():
            if intf.ipaddr == arp.targetprotoaddr:
                # 匹配成功
                arpreply = create_ip_arp_reply(intf.ethaddr, arp.senderhwaddr, arp.targetprotoaddr, arp.senderprotoaddr)
                self.net.send_packet(ifaceName, arpreply)
                break
    
elif arp.operation == ArpOperation.Reply:
    # 如果是 reply 包，将其信息更新到缓存表中
    self.arpcache[arp.senderprotoaddr] = {'m':arp.senderhwaddr, 't': time.time()}
    return
```

ARP 缓存表的结构是一个字典：

| key     | value 'm'    | value 't'              |
| ------- | ------------ | ---------------------- |
| IP 地址 | 以太物理地址 | 这一项的最近更新时间戳 |

因此更新表的逻辑是（其中 self.timelimit 规定了表项的存活时间，设置为200s）：

```python
def updateArpCache(self):
    current = time.time()
    to_dele = []   # to_dele 是待删除的项
	# 遍历缓存表，删除超时的项
    for key in self.arpcache:
        if current - self.arpcache[key]['t'] > self.timelimit:
        to_dele.append(key)

    for key in to_dele:
        del self.arpcache[key]
```

之后在每一次收到 ARP 包时都调用一次 self.updateArpCache()  来更新缓存表