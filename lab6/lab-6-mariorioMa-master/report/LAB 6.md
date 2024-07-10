# LAB 6

通过本次实验，我深入理解了以太网与IP协议的功能与工作原理，UDP可靠运输的一种逻辑实现

## middlebox

相较来说，middlebox的功能单一，实现简单

middlebox相当于中转路由器，其延迟为1.0（即几乎不延迟）。每当middlebox收到一个数据包，它将会做出如下反应：

- 如果包来自 *blaster* ，middlebox将会考虑是否丢包

```python
randnum = randint(0, 99)
weight = randnum / 100.0
if weight < self.dropRate:
    # 丢包
    pass
```

如果丢包，则什么都不做。如果不丢包，则将此包转发给blastee

转发给blastee之前，需要修改包的以太网头：将源MAC地址改为middlebox面向blastee的地址，将目的地址改为blastee的MAC地址

```python
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
```

- 如果包来自blastee，意味着这是由blastee 返回的ACK，则只需要修改以太网头后转发给blaster

```python
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
```

> middlebox所做的只需要在原有包上做改变即可。这里构建了一个新的包再复制实际上是一种copy行为，因为我在运行的时候，直接修改原有包会出现奇怪的错误，重新构建就不会出错

---------------

## blastee

blastee初始化接受两个参数：

```python
self.blasterIP = blasterIp
self.num = num
```

对于包的发送者blaster来说，blaster类似于客户，而blastee是服务器。因此不会特别的去加大blastee的时延（recvTimeout）。

当blastee接受到一个包时，blastee需要构建一个ACK，包含相应的以太网头、IP头、UDP头和一段四字节长的序列字，以及一段八字节的固定负载。

注意，虽然blastee需要将ACK发回给blaster，但包的实际来源是middlebox，所以blastee也需要通过middlebox发回ACK。具体表现为：

1. 以太网头（Ethernet）的源MAC地址是blastee的地址，目的MAC地址是middlebox面向blastee的地址
2. IPv4  的源地址是blastee的IP地址，目的地址是blater的IP地址
3. UDP  头的源端口号于目标端口号与收到的包相反

```python
    def handle_packet(self, recv: switchyard.llnetbase.ReceivedPacket):
        _, fromIface, packet = recv
        log_debug(f"I got a packet from {fromIface}")
        log_debug(f"Pkt: {packet}")
        udp_hdr = packet.get_header(UDP)

        ack = Ethernet(src="20:00:00:00:00:01", dst="40:00:00:00:00:02") + \
            IPv4(src="192.168.200.1", dst="192.168.100.1") + \
            UDP(src=udp_hdr.dst, dst=udp_hdr.src)
        ack[1].protocol = IPProtocol.UDP   # 指定为UDP协议

        hdr_len = ack.size()
        raw = packet.to_bytes()[hdr_len:]  
        # 添加数据包的序号
        ack.add_payload(RawPacketContents(raw[:4]))
        # 如果原包的可变负载长度不足 8，则补齐
        if len(raw) < 14:
            raw += bytes([0]*(14-len(raw)))
    	# 添加 8 字节负载
        ack.add_payload(RawPacketContents(raw[6:14]))
        
        self.net.send_packet("blastee-eth0", ack)
```

> blaster发送来的包的格式为：以太网头 + IP头 + UDP头 + 序列号（4字节）+ 负载长度（2字节）+负载
>
> 因此如果要保证负载长度大于8字节，序列号+负载长度+负载总共要大于14字节

-----------

## blaster

blaster的初始化需要维护很多值，并在必要的时候为其指定类型

```python
self.blasteeIP = blasteeIp 
self.num = int(num)                      #数据包数量
self.length = int(length)                #负载长度
self.SW = int(senderWindow)              #发射窗口的大小
self.timeout = float(timeout)            #等待（ACK）时延
self.recv_timeout = float(recvTimeout)   #发送时延
self.LHS = 1                             #左边界
self.RHS = 1                             #右边界
self.resend_num = 0                      #重发的次数
self.TOnum = 0                           #超时的次数
self.totalbyte = 0                       #总共发送的字节数
self.goodbyte = 0                        #发送的有效字节数
self.finish = []                         #已收到ACK的序号
        ...
```

blaster相当于客户端，因此需要发送时延（但至少blaster的发送时延要比等待时延短）

```python
recv = self.net.recv_packet(timeout=self.recv_timeout
```

- blaster 需要按照顺序构建所有需要发送的包，并发送，即为num个包赋值序号，填写序号等重要信息，序号的范围是 [1, num] 。下面的函数用来构建一个序号为 **th** 的数据包
  - 以太网头：源地址为 blaster 的MAC地址，目的地址为 middlebox 的MAC地址
  - IP头：源地址为 blaster 的IP，目的地址为 blastee 的IP
  - UDP：随意分配的端口号
  - 序号：th 转换为 4 字节的大端形式
  - 负载长度： self.length 的 2 字节大端形式

```python
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
```

blaster每次发送时延内会面临两种情况：

- 没有收到任何包
  - 可能是因为 blaster 还没有发送过任何包，故收不到ACK
  - 出现了丢包，或ACK未及时发回

```python
    def handle_no_packet(self):
        log_debug("Didn't receive anything")
        if self.RHS == 1:
            #此时还没发送过任何包，交流刚刚开始，记录下开始的时间
            self.start_time = time.time()

        # 当前窗口仍有空挡，且存在未发送过的包
        if self.RHS-self.LHS+1 < self.SW and self.RHS <= self.num:
            pkt = self.make_packet(self.RHS)
            self.net.send_packet("blaster-eth0", pkt)
			# 此时发送的包都是第一次发送
            self.totalbyte += 1
            self.goodbyte += 1
            # 如果右边界是 1，代表这是发送的第一个包，重置等待时间
            if self.LHS==1 and self.RHS==1:
                self.staytime = time.time()
            self.RHS += 1

        # 等待时间大于等待时延，说明出现了丢包或者ACK未及时发回
        if time.time()-self.staytime > self.timeout:
            # 遍历所有已经发送过但还没收到ACK的包，重新发送
            for th in range(self.LHS, self.RHS-1):
                if not th in self.finish:
                    pkt = self.make_packet(th)
                    self.net.send_packet("blaster-eth0", pkt)
                    self.resend_num += 1
                    self.totalbyte += self.length
                    self.TOnum += 1
            # 重置等待时间
            self.staytime = time.time()
```

- 收到了ACK
  - 获得ACK中的序号，加入到finish列表
  - 维护左边界的值

```python
	def handle_packet(self, recv: switchyard.llnetbase.ReceivedPacket):
        _, fromIface, packet = recv
        log_debug("I got a packet")
        praw = packet.to_bytes()
        eth_hdr = packet.get_header(Ethernet)
        ip_hdr = packet.get_header(IPv4)
        udp_hdr = packet.get_header(UDP)
        hdr_len = eth_hdr.size() + ip_hdr.size() + udp_hdr.size()
        #seq_raw是 4 字节序列号，转化为整数即序号
        seq_raw = praw[hdr_len:hdr_len+4]
        seq = int.from_bytes(seq_raw, 'big')
        
        #如果seq不在finish中，则将其加入，并维护finish的值
        #这里考虑到可能会重复收到同一个包的ACK
        if not seq in self.finish:
            self.finish.append(seq)
            #如果seq是左边界，则移动左边界。否则不改变左边界
            if self.LHS == seq:
                #移动左边界直到指向一个已发送未ACK的包
                while(1):
                    self.LHS += 1
                    if self.LHS not in self.finish:
                        break
                self.staytime = time.time()
		
        #此时全部包都已发送完毕，记录下总时长
        if self.LHS == self.num:
            self.totaltime = time.time() - self.start_time
		#如果窗口有空间，可以发送新的包
        if self.RHS-self.LHS+1 < self.SW and self.RHS <= self.num:
            pkt = self.make_packet(self.RHS)
            self.net.send_packet("blaster-eth0", pkt)
            self.totalbyte += 1
            self.goodbyte += 1
            self.RHS += 1
```

>无论是否收到ACK，blaster都是可以考虑发送一个新的包
>
>收到一个ACK的时候，可能要移动左边界不止一步

最后，打印出各项参数

```python
print("%d", self.totaltime)                    # 总时长
print("%d", self.resend_num)                   # 重发次数
print("%d", self.TOnum)                        # 超时次数
print("%d", self.totalbyte / self.totaltime)   # 吞吐量
print("%d", self.goodbyte / self.totaltime)    # Goodput
```

-----

