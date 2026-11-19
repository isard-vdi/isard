#!/bin/sh
# SPDX-License-Identifier: AGPL-3.0-or-later
# In-chroot setup run by build-qcow2.sh; $1 is the fixed-salt crypt hash for isard.
# Must stay deterministic: no timestamps, no randomness, no network.
set -eu
HASH="$1"

mkdir -p /usr/local/sbin /etc/init.d /etc/isard
echo isard-test > /etc/hostname

# --- Identity: public test credentials isard / pirineus (the default IsardVDI
#     guest credentials in the codebase). xrdp authenticates PAM against this.
adduser -D -u 1000 -s /bin/sh -g IsardVDI isard
awk -v h="$HASH" -F: 'BEGIN{OFS=":"} $1=="isard"{$2=h;$3=20000} {print}' /etc/shadow > /etc/shadow.n
mv /etc/shadow.n /etc/shadow; chmod 600 /etc/shadow
sed -i 's#^root:[^:]*:#root:!:#' /etc/shadow

# --- isard-rw: make the writable dirs writable over the read-only erofs root by
#     overlaying each with a tmpfs upper (in /run). Runs in sysinit, before any
#     service reads or writes /etc, /var, /home or /root.
cat > /etc/init.d/isard-rw <<'EOF'
#!/sbin/openrc-run
description="tmpfs overlays for the writable dirs over the read-only erofs root"
depend() { need dev; before bootmisc hostname syslog isard-net isard-ipbanner xrdp xrdp-sesman; keyword -timeout; }
start() {
    ebegin "Overlaying /etc /var /home /root with tmpfs"
    for d in /etc /var /home /root; do
        u="/run/rw${d}/u"; w="/run/rw${d}/w"
        mkdir -p "$u" "$w"
        mount -t overlay overlay -o "lowerdir=$d,upperdir=$u,workdir=$w" "$d" || return 1
    done
    # erofs is built --all-root, so the isard HOME is root-owned on the lower.
    # Hand it back now that /home is writable, or the RDP session (uid 1000) can't
    # write .Xauthority and xorgxrdp's Xorg :10 dies waiting for RandR outputs.
    chown -R isard:isard /home/isard 2>/dev/null || true
    eend 0
}
EOF
chmod +x /etc/init.d/isard-rw
rc-update add isard-rw sysinit

cat > /etc/fstab <<'EOF'
tmpfs /tmp     tmpfs rw,nosuid,nodev,mode=1777 0 0
tmpfs /dev/shm tmpfs rw,nosuid,nodev,mode=1777 0 0
EOF

# --- DHCP on every ethernet NIC (default NAT NIC + the isard-vpn wireguard
#     overlay), applying the DHCP MTU (1386 on the overlay). No DNS needed.
cat > /etc/init.d/isard-net <<'EOF'
#!/sbin/openrc-run
description="DHCP on every ethernet NIC (incl. the isard-vpn wireguard overlay)"
depend() { need isard-rw; after bootmisc; provide net; }
start() {
    ebegin "Bringing up every ethernet NIC with DHCP"
    for d in /sys/class/net/eth*; do
        [ -e "$d" ] || continue
        n=${d##*/}; ip link set "$n" up
        udhcpc -i "$n" -b -t 6 -A 3 -p "/run/udhcpc.$n.pid" -x hostname:isard-test >/dev/null 2>&1 || true
    done
    eend 0
}
stop() { for p in /run/udhcpc.eth*.pid; do [ -e "$p" ] && kill "$(cat "$p")" 2>/dev/null; done; return 0; }
EOF
chmod +x /etc/init.d/isard-net
rc-update add isard-net default

# --- IP banner to the serial (ttyS0, which IsardVDI logs) and video consoles.
cat > /usr/local/sbin/isard-ipbanner <<'EOF'
#!/bin/sh
banner() {
    nl='
'
    out="==================================================$nl  IsardVDI test desktop is UP  (user: isard)$nl"
    for d in /sys/class/net/*; do
        n=${d##*/}; [ "$n" = lo ] && continue
        ip=$(ip addr show "$n" 2>/dev/null | awk '/inet /{printf "%s,",$2}')
        out="$out  $n  ip ${ip:-none}  mac $(cat "$d/address" 2>/dev/null)  mtu $(cat "$d/mtu" 2>/dev/null)$nl"
    done
    out="$out==================================================$nl"
    for c in /dev/tty0 /dev/ttyS0 /dev/console; do [ -w "$c" ] && printf '%s' "$out" > "$c" 2>/dev/null || true; done
}
if [ "${1:-}" = "--watch" ]; then
    last=""
    while :; do now=$(ip -o addr 2>/dev/null); [ "$now" != "$last" ] && { banner; last="$now"; }; sleep 60; banner; done
else banner; fi
EOF
chmod +x /usr/local/sbin/isard-ipbanner
cat > /etc/init.d/isard-ipbanner <<'EOF'
#!/sbin/openrc-run
description="IsardVDI IP banner to serial and video consoles"
command="/usr/local/sbin/isard-ipbanner"
command_args="--watch"
command_background=true
pidfile="/run/isard-ipbanner.pid"
depend() { after isard-net; }
EOF
chmod +x /etc/init.d/isard-ipbanner
rc-update add isard-ipbanner default

# --- qemu-guest-agent: IsardVDI reads the guest IP through it.
rc-update add qemu-guest-agent default 2>/dev/null || true

# --- Minimal console X on the QXL framebuffer so the SPICE viewer shows an
#     image. tty1 auto-logs in as root (/root is a writable overlay) and runs
#     startx; .xinitrc paints a background and keeps a terminal open.
cat > /usr/local/sbin/isard-autologin <<'EOF'
#!/bin/sh
exec /bin/login -f root
EOF
chmod +x /usr/local/sbin/isard-autologin
sed -i 's#^tty1::respawn:.*#tty1::respawn:/sbin/getty -n -l /usr/local/sbin/isard-autologin 38400 tty1 linux#' /etc/inittab
grep -q '^ttyS0::' /etc/inittab || echo 'ttyS0::respawn:/sbin/getty -L 115200 ttyS0 vt100' >> /etc/inittab

cat > /root/.profile <<'EOF'
if [ "$(tty)" = /dev/tty1 ] && [ -z "${DISPLAY:-}" ] && command -v startx >/dev/null; then
    exec startx /etc/isard/xinitrc -- -nolisten tcp vt1 >/dev/null 2>&1
fi
EOF
cat > /etc/isard/xinitrc <<'EOF'
#!/bin/sh
xsetroot -solid "#1b3a5b" 2>/dev/null || true
( xterm -fn fixed -T "IsardVDI test desktop (isard / pirineus)" \
    -e sh -c '/usr/local/sbin/isard-ipbanner; echo; echo "IsardVDI minimal test desktop (console / SPICE)."; exec sh' & ) 2>/dev/null
exec sh -c 'while :; do sleep 3600; done'
EOF
chmod +x /etc/isard/xinitrc

# modesetting drives the QXL framebuffer; disable GLX/glamor so Xorg never
# needs libGL (the llvm/gallium stack is stripped from the image).
mkdir -p /etc/X11/xorg.conf.d
cat > /etc/X11/xorg.conf.d/10-isard.conf <<'EOF'
Section "ServerFlags"
    Option "AutoAddGPU" "off"
EndSection
Section "Module"
    Disable "glx"
    Disable "glamoregl"
EndSection
Section "Device"
    Identifier "qxl0"
    Driver "modesetting"
    Option "AccelMethod" "none"
EndSection
EOF

# --- RDP: xrdp + xorgxrdp. The RDP session (user isard, HOME on the writable
#     /home overlay) reuses the same tiny terminal. PAM auth against isard.
if [ -f /etc/xrdp/startwm.sh ]; then
    cat > /etc/xrdp/startwm.sh <<'EOF'
#!/bin/sh
xsetroot -solid "#1b3a5b" 2>/dev/null || true
( xterm -fn fixed -T "IsardVDI test desktop via RDP (isard)" \
    -e sh -c 'echo "IsardVDI minimal test desktop over RDP. User: isard"; exec sh' & ) 2>/dev/null
exec sh -c 'while :; do sleep 3600; done'
EOF
    chmod +x /etc/xrdp/startwm.sh
fi
for svc in xrdp xrdp-sesman sesman; do
    [ -f "/etc/init.d/$svc" ] && rc-update add "$svc" default 2>/dev/null || true
done
# xrdp TLS: Alpine ships an empty certificate=/key_file=. Point xrdp at a
# self-signed cert generated on first boot into the writable /etc overlay
# (kept out of the image -> reproducible, no key committed). A throwaway test
# cert for a public test image, not a secret.
sed -i 's#^certificate=.*#certificate=/etc/xrdp/cert.pem#; s#^key_file=.*#key_file=/etc/xrdp/key.pem#' /etc/xrdp/xrdp.ini 2>/dev/null || true
cat > /etc/init.d/isard-xrdp-cert <<'EOF'
#!/sbin/openrc-run
description="Generate the xrdp TLS cert and RSA keys on first boot (public test image)"
depend() { need isard-rw; before xrdp xrdp-sesman sesman; }
start() {
    ebegin "Generating xrdp TLS certificate and RSA keys"
    [ -s /etc/xrdp/cert.pem ] || openssl req -x509 -newkey rsa:2048 -nodes \
        -keyout /etc/xrdp/key.pem -out /etc/xrdp/cert.pem -days 3650 -subj "/CN=isard-test" >/dev/null 2>&1
    chmod 644 /etc/xrdp/cert.pem /etc/xrdp/key.pem 2>/dev/null
    [ -s /etc/xrdp/rsakeys.ini ] || xrdp-keygen xrdp auto >/dev/null 2>&1
    eend $?
}
EOF
chmod +x /etc/init.d/isard-xrdp-cert
rc-update add isard-xrdp-cert default 2>/dev/null || true

# --- OpenRC runlevels: the minimum to boot, coldplug, net and shut down.
for s in devfs dmesg mdev; do rc-update add "$s" sysinit 2>/dev/null || true; done
for s in hwdrivers bootmisc hostname; do rc-update add "$s" boot 2>/dev/null || true; done
rc-update add local default 2>/dev/null || true
for s in killprocs mount-ro; do rc-update add "$s" shutdown 2>/dev/null || true; done

# --- Determinism / cleanup. Drop install-time-random files so the erofs root is
#     bit-reproducible (xrdp's post-install bakes a RANDOM cert + RSA key; both
#     are regenerated on first boot by isard-xrdp-cert).
rm -rf /var/cache/apk/* /root/.ash_history /var/log/* /var/cache/fontconfig/* 2>/dev/null || true
rm -f /etc/xrdp/rsakeys.ini /etc/xrdp/cert.pem /etc/xrdp/key.pem /etc/resolv.conf 2>/dev/null || true
: > /etc/machine-id 2>/dev/null || true
rm -f /etc/ssh/ssh_host_* 2>/dev/null || true
