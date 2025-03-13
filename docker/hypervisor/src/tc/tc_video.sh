#!/bin/bash

# Clear existing rules
iptables -t mangle -F
tc qdisc del dev eth0 root 2>/dev/null
tc qdisc del dev ifb0 root 2>/dev/null
tc qdisc del dev eth0 ingress 2>/dev/null

if [ "$DISABLE_TRAFFIC_PRIORITIZATION" = "true" ]; then
    echo "Traffic prioritization is disabled. Exiting."
    exit 0
fi

# Detect if CAKE is available
tc qdisc add dev eth0 root cake bandwidth 100kbit diffserv4 flows wash ingress rtt 20ms 2>/dev/null
if [ $? -eq 0 ]; then
    echo "✅ CAKE is available. Using DSCP for classification."
    USE_CAKE=true
    tc qdisc del dev eth0 root 2>/dev/null  # Remove test qdisc
else
    echo "❌ CAKE is not available. Falling back to HTB + fq_codel."
    USE_CAKE=false
fi

# Set either DSCP or MARK based on CAKE availability
if [ "$USE_CAKE" = "true" ]; then
    # 🎯 CAKE uses DSCP for priority classification
    iptables -t mangle -A OUTPUT -p tcp --sport 2022 -j DSCP --set-dscp-class CS6    # Priority 1 (Highest)
    iptables -t mangle -A PREROUTING -p tcp --dport 2022 -j DSCP --set-dscp-class CS6

    iptables -t mangle -A OUTPUT -p tcp --sport 5900:7899 -j DSCP --set-dscp-class AF41  # Video/RDP
    iptables -t mangle -A PREROUTING -p tcp --dport 5900:7899 -j DSCP --set-dscp-class AF41
    iptables -t mangle -A OUTPUT -p tcp --dport 3389 -j DSCP --set-dscp-class AF41
    iptables -t mangle -A PREROUTING -p tcp --sport 3389 -j DSCP --set-dscp-class AF41

    iptables -t mangle -A OUTPUT -p tcp --dport 80 -j DSCP --set-dscp-class AF21   # Web Browsing/DNS
    iptables -t mangle -A OUTPUT -p tcp --dport 443 -j DSCP --set-dscp-class AF21
    iptables -t mangle -A OUTPUT -p udp --dport 53 -j DSCP --set-dscp-class AF21

    iptables -t mangle -A OUTPUT -m mark --mark 0 -j DSCP --set-dscp-class BE  # Default (Best Effort)
    iptables -t mangle -A PREROUTING -m mark --mark 0 -j DSCP --set-dscp-class BE
else
    # 🎯 HTB uses MARK for priority classification
    iptables -t mangle -A OUTPUT -p tcp --sport 2022 -j MARK --set-mark 1  # Priority 1 (Highest)
    iptables -t mangle -A PREROUTING -p tcp --dport 2022 -j MARK --set-mark 1

    iptables -t mangle -A OUTPUT -p tcp --sport 5900:7899 -j MARK --set-mark 2  # Video/RDP
    iptables -t mangle -A PREROUTING -p tcp --dport 5900:7899 -j MARK --set-mark 2
    iptables -t mangle -A OUTPUT -p tcp --dport 3389 -j MARK --set-mark 2
    iptables -t mangle -A PREROUTING -p tcp --sport 3389 -j MARK --set-mark 2

    iptables -t mangle -A OUTPUT -p tcp --dport 80 -j MARK --set-mark 3   # Web Browsing/DNS
    iptables -t mangle -A OUTPUT -p tcp --dport 443 -j MARK --set-mark 3
    iptables -t mangle -A OUTPUT -p udp --dport 53 -j MARK --set-mark 3

    iptables -t mangle -A OUTPUT -m mark --mark 0 -j MARK --set-mark 4  # Default (Best Effort)
    iptables -t mangle -A PREROUTING -m mark --mark 0 -j MARK --set-mark 4
fi

# Determine bandwidth limits
if [ -n "$NETWORK_MAX_DOWNLOAD_BANDWIDTH" ] && [ -n "$NETWORK_MAX_UPLOAD_BANDWIDTH" ]; then
    DOWNLOAD_BANDWIDTH=$(($NETWORK_MAX_DOWNLOAD_BANDWIDTH * 1000 * 95 / 100))
    UPLOAD_BANDWIDTH=$(($NETWORK_MAX_UPLOAD_BANDWIDTH * 1000 * 95 / 100))
    echo "Using custom bandwidth limits: Download: $DOWNLOAD_BANDWIDTH kbps, Upload: $UPLOAD_BANDWIDTH kbps"
else
    echo "Checking Internet connection bandwidth..."
    RESULT=$(speedtest-cli --simple --secure 2>/dev/null)
    echo "$RESULT"
    if [ $? -eq 0 ]; then
        DOWNLOAD_BANDWIDTH=$(echo "$RESULT" | awk '/Download/{print int($2*1000*0.95)}')
        UPLOAD_BANDWIDTH=$(echo "$RESULT" | awk '/Upload/{print int($2*1000*0.95)}')
        echo "Speed applied: Download: $DOWNLOAD_BANDWIDTH kbps, Upload: $UPLOAD_BANDWIDTH kbps"
    else
        echo "WARNING!! Speedtest failed. Traffic control will not be applied!"
        exit 0
    fi
fi

ip link set dev ifb0 up 2>/dev/null || ip link add ifb0 type ifb && ip link set dev ifb0 up
tc qdisc add dev eth0 handle ffff: ingress
tc filter add dev eth0 parent ffff: protocol all prio 10 u32 match u32 0 0 flowid 1:1 action mirred egress redirect dev ifb0

# Apply traffic shaping based on available method
if [ "$USE_CAKE" = "true" ]; then
    tc qdisc add dev eth0 root cake bandwidth ${UPLOAD_BANDWIDTH}kbit diffserv4 flows wash ingress rtt 20ms
    tc qdisc add dev ifb0 root cake bandwidth ${DOWNLOAD_BANDWIDTH}kbit diffserv4 flows wash rtt 20ms
else
    tc qdisc add dev eth0 root handle 1: htb default 40
    tc class add dev eth0 parent 1: classid 1:1 htb rate ${UPLOAD_BANDWIDTH}kbit ceil ${UPLOAD_BANDWIDTH}kbit

    for i in 1 2 3 4; do
        RATE=$((UPLOAD_BANDWIDTH / (5 - i)))
        tc class add dev eth0 parent 1:1 classid 1:${i}0 htb rate ${RATE}kbit ceil ${UPLOAD_BANDWIDTH}kbit prio ${i}
        tc qdisc add dev eth0 parent 1:${i}0 handle ${i}0: fq_codel
        tc filter add dev eth0 protocol ip parent 1: handle ${i} fw flowid 1:${i}0
    done
fi


# Show configuration
# echo "Egress Traffic control configuration:"
# tc -s qdisc show dev eth0
# tc -s class show dev eth0
# echo -e "\nIngress Traffic control configuration:"
# tc -s qdisc show dev ifb0
# tc -s class show dev ifb0