<center><font size=6>LAB2 实验报告</font></center>

**学号**：221900398

**姓名**：甘思毅

----------------

## Basic 交换机

以字典的数据结构构建交换机的交换表：

```python
switch_table = {}
```

在工作主循环中，按照如下基本工作逻辑：

1. 当收到一个数据帧，判断其是否具有以太网头（即此数据包可能并不完整）
2. 将此帧的信息添加到交换表中：

| MAC Adress     | Port         |
| -------------- | ------------ |
| 帧的以太源地址 | 帧的来源接口 |

- 若以太目的地址就是交换机的某一个接口的地址，不做任何事

- 若以太网目的地址在交换表中有匹配，将帧从对应的接口转发
- 若没有匹配，则将帧从除来源接口以外的所有接口中发出去

工作主循环：

```python
while True:
    try:
       _, fromIface, packet = net.recv_packet()
    except NoPackets:
       continue
    except Shutdown:
       break

    eth = packet.get_header(Ethernet)
    if eth is None:
        return
    # 更新交换表
    switch_table[eth.src] = {'port': fromIface}
    # 如果帧的目的就是交换机自己
    if eth.dst in mymacs:
    # 如果目的以太地址在表中匹配
    elif eth.dst in switch_table:
        value = switch_table.get(eth.dst)
        net.send_packet(value['port'], packet)
    # 否则将从所有接口中转发
    else:
        for intf in my_interfaces:
            if fromIface != intf.name:
                net.send_packet(intf, packet)
```



## Time Out 策略

在此策略下，交换表中的条目结构为

| MAC Adress       | Port       | Time             |
| ---------------- | ---------- | ---------------- |
| 帧的以太网源地址 | 来源的接口 | 此条目设立的时间 |

 这里使用一个条目的存活时间 `time_out` = 15 s。在每次收到一个帧并处理其之前要更新遍历交换表，将存活时间超过 15 秒的条目移除

```python
# update table 
current = time.time()
to_dele = []       # to_dele 是待从表中删除的条目
for addr in switch_table:
    if current - switch_table[addr]['time'] > time_out:
        # 将超时的条目加入到 to_dele
        to_dele.append(addr)
for addr in to_dele:
    del switch_table[addr]
        
# work
eth = packet.get_header(Ethernet)
if eth is None:
    return
# 将帧的信息添加到表中，设立时间为当前时间
switch_table[eth.src] = {'port': fromIface, 'time': time.time()}
if eth.dst in mymacs:
    pass
elif eth.dst in switch_table:
    value = switch_table.get(eth.dst)
    net.send_packet(value['port'], packet)
    # 刷新这一条目的时间
    value['time'] = time.time()
else:
    for intf in my_interfaces:
        if fromIface != intf.name:
            net.send_packet(intf, packet)
```



## LRU 策略

设置 `rule_limit = 5` 代表交换表的容量最大为 5 。

- 当新的条目被加入到交换表中时：若表已满，则选择一个距离上次使用时间最远（最近最不频繁使用）的条目删除。
- 当缓存命中时，被命中的条目更新最近使用的时间

在实验文档中，给出了一种思路：维护条目的 `age` 属性。每当一个新的信息被加入到表或被使用（命中），新条目的 `age` 是 0，而将旧条目的 `age` 增加。但这种方法面临效率低下的问题：每次遍历的时间复杂度都是 `N` , `N = rule_limit` 

我采用**“公元纪年”**的思想：交换机维护一个全局的时钟 `clock`，初始为 0 ，出现新的数据帧时便增加一。而每个条目记录最近一次使用的时间戳 `tamp` ：

| MAC Address | Port          | Tamp             |
| ----------- | ------------- | ---------------- |
| eth.src     | FromInterface | 最近使用的 clock |

工作主循环：

```python 
eth = packet.get_header(Ethernet)
if eth is None:
    return
# 时钟+1
clock += 1
# 函数 update_table 将新的条目加入到交换表
update_table(switch_table, eth.src, fromIface, clock, rule_limit)
if eth.dst in mymacs:
    pass
elif eth.dst in switch_table:
    value = switch_table.get(eth.dst)
    net.send_packet(value['port'], packet)
    # 更新命中的条目的时间戳
    value['tamp'] = clock
else:
    for intf in my_interfaces:
        if fromIface != intf.name:
            net.send_packet(intf, packet)
```

`update_table` 函数：

```python
def update_table(table, ethaddr, port, clock, limit):
   	if ethaddr in table:
        # 如果当前条目本就在表中，更新表的时间戳和端口
        table[ethaddr]['tamp'] = clock
        table[ethaddr]['port'] = port
        return
    if len(table) < limit:
        # 如果表还未满载，直接加入条目
        table[ethaddr] = {'port':port, 'tamp':clock}
        return
    else:
        # 遍历表，找出距离上次使用时间最久远的一项
        max_age = 0
        for addr in table:
            age = clock - table[addr]['tamp']
            if age > max_age:
                max_age = age
                oldrule = addr
        # 删除旧项，添加新项
        del table[oldrule]
        table[ethaddr] = {'port':port, 'tamp':clock}
```

这样，交换机的所有条目只需记忆一个时间戳，而依靠全局时钟 `clock` 公元，每次增加条目都不必更新所有项的 `age`



## Traffic 策略

每一个条目维护一个属性 `volume` 代表来自这个以太地址经过当前交换机的帧的数量，也就是流量。条目结构：

| MAC Address | Port           | Volume               |
| ----------- | -------------- | -------------------- |
| eth.src     | from interface | total traffic volume |

主循环与 **LRU 策略** 相似，被命中的条目 `volume` 属性增加 1 。

交换表更新函数和工作主循环：

```python
# 交换表更新函数
def update_table(table, ethaddr, port, limit):
    if ethaddr in table:
        # 条目原本就在表中
        table[ethaddr]['volume'] += 1
        table[ethaddr]['port'] = port
        return 
    if len(table) < limit:
        # 表未填满
        table[ethaddr] = {'port':port, 'volume':1}
        return
    else:
        # 遍历找出流量最少的
        min_volume = float('inf')
        for addr in table:
            if table[addr]['volume'] < min_volume:
                min_volume = table[addr]['volume']
                oldrule = addr
        # 删除旧条目，添加新条目
        del table[oldrule]
        table[ethaddr] = {'port':port, 'volume':1}

        
# 工作主循环的部分内容
eth = packet.get_header(Ethernet)
if eth is None:
    return
# 向表中添加新条目
update_table(switch_table, eth.src, fromIface, rule_limit)
if eth.dst in mymacs:
    return 
elif eth.dst in switch_table:
    value = switch_table.get(eth.dst)
    net.send_packet(value['port'], packet)
    # “流量”增加 1
    value['volume'] += 1
else:
    for intf in my_interfaces:
        if fromIface != intf.name:
            net.send_packet(intf, packet)
```



## 实验总结

对于三种不同策略的尝试，各有弊端：

- **TO**：如果数据帧的交换是：集中爆发、平时稀少的情况（事实上，这种情况可能非常常见），无法很好的提供稳定效果。由于不确定交换表的具体（存储）大小，对于硬件的要求较高，稳定性差
- **Traffic**：假如交换机面临这种情况：在一段时间内 10:00:00:16 to 40:00:00:05 等集中出现，在下一段时间 30:00:02:123 to 20:00:16:18 集中出现，traffic 策略在面对这种情况，缓存表的更新存在滞后性，效率低下
- **LRU**：这种策略不遵循**“栈算法”属性**，对于表的大小和实际情况的把控要求较高。考虑以下情况

| 1     | 2     | 3     | 4     | 5     | 6     | 7     | 8     | 9     |
| ----- | ----- | ----- | ----- | ----- | ----- | ----- | ----- | ----- |
| eth_1 | eth_1 | eth_1 | eth_4 | eth_4 | eth_4 | eth_3 | eth_3 | eth_3 |
|       | eth_2 | eth_2 | eth_2 | eth_1 | eth_1 | eth_1 | eth_4 | eth_4 |
|       |       | eth_3 | eth_3 | eth_3 | eth_2 | eth_2 | eth_2 | eth_1 |

会发现非常糟糕