#!/bin/sh
# SPDX-License-Identifier: AGPL-3.0-or-later
# In-chroot configuration for the IsardVDI minimal test desktop image (Alpine).
# Run by build-qcow2.sh inside the freshly-bootstrapped rootfs. $1 is a
# pre-computed, fixed-salt SHA-512 crypt hash for the isard account (passed in
# so the build stays deterministic; the password itself is the public test
# credential "pirineus"). Keep every action deterministic: no timestamps, no
# randomness, no network. Target shell is busybox ash.
set -eu
HASH="$1"

mkdir -p /usr/local/sbin /usr/local/bin /etc/init.d
echo isard-test > /etc/hostname

# --- Identity: public test credentials (NOT a secret). These are the default
#     IsardVDI guest credentials used across the codebase (engine upgrade v30,
#     testing/src/isardvdi_testing/data/domains.json): isard / pirineus. xrdp
#     authenticates PAM against this local account.
adduser -D -u 1000 -s /bin/sh -g IsardVDI isard
awk -v h="$HASH" -F: 'BEGIN{OFS=":"} $1=="isard"{$2=h;$3=20000} {print}' /etc/shadow > /etc/shadow.n
mv /etc/shadow.n /etc/shadow
chmod 600 /etc/shadow
sed -i 's#^root:[^:]*:#root:!:#' /etc/shadow            # lock root

# --- DHCP on every ethernet NIC: the default NAT NIC, the isard-vpn wireguard
#     overlay NIC, and any future one. udhcpc's default.script applies the
#     DHCP-provided MTU (1386 on the overlay) and routes.
cat > /etc/init.d/isard-net <<'EOF'
#!/sbin/openrc-run
description="DHCP on every ethernet NIC (incl. the isard-vpn wireguard overlay)"
depend() { need localmount; after modules hwdrivers; provide net; }
start() {
    ebegin "Bringing up every ethernet NIC with DHCP"
    for d in /sys/class/net/eth*; do
        [ -e "$d" ] || continue
        n=${d##*/}
        ip link set "$n" up
        udhcpc -i "$n" -b -t 6 -A 3 -p "/run/udhcpc.$n.pid" -x hostname:isard-test >/dev/null 2>&1 || true
    done
    eend 0
}
stop() { for p in /run/udhcpc.eth*.pid; do [ -e "$p" ] && kill "$(cat "$p")" 2>/dev/null; done; return 0; }
EOF
chmod +x /etc/init.d/isard-net
rc-update add isard-net default

# --- IP banner: write every NIC's address to the serial console (ttyS0, which
#     IsardVDI logs) and the video console (tty0) on change and every 60 s.
cat > /usr/local/sbin/isard-ipbanner <<'EOF'
#!/bin/sh
banner() {
    nl='
'
    out="==================================================$nl"
    out="$out  IsardVDI test desktop is UP  (user: isard)$nl"
    for d in /sys/class/net/*; do
        n=${d##*/}; [ "$n" = lo ] && continue
        ip=$(ip addr show "$n" 2>/dev/null | awk '/inet /{printf "%s,",$2}')
        mac=$(cat "$d/address" 2>/dev/null); mtu=$(cat "$d/mtu" 2>/dev/null)
        out="$out  $n  ip ${ip:-none}  mac $mac  mtu $mtu$nl"
    done
    out="$out==================================================$nl"
    for c in /dev/tty0 /dev/ttyS0 /dev/console; do
        [ -w "$c" ] && printf '%s' "$out" > "$c" 2>/dev/null || true
    done
}
if [ "${1:-}" = "--watch" ]; then
    last=""
    while :; do
        now=$(ip -o addr 2>/dev/null)
        [ "$now" != "$last" ] && { banner; last="$now"; }
        sleep 60; banner
    done
else
    banner
fi
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

# --- Minimal console X session so the SPICE viewer shows an image. tty1
#     auto-logs in as root (avoids Alpine's non-root-X seat setup) and root's
#     profile runs startx; .xinitrc paints a background and opens a terminal
#     showing the IP banner on the QXL framebuffer.
cat > /usr/local/sbin/isard-autologin <<'EOF'
#!/bin/sh
exec /bin/login -f root
EOF
chmod +x /usr/local/sbin/isard-autologin
sed -i 's#^tty1::respawn:.*#tty1::respawn:/sbin/getty -n -l /usr/local/sbin/isard-autologin 38400 tty1 linux#' /etc/inittab
grep -q '^ttyS0::' /etc/inittab || echo 'ttyS0::respawn:/sbin/getty -L 115200 ttyS0 vt100' >> /etc/inittab

cat > /root/.profile <<'EOF'
if [ "$(tty)" = /dev/tty1 ] && [ -z "${DISPLAY:-}" ] && command -v startx >/dev/null; then
    exec startx -- -nolisten tcp vt1 >/dev/null 2>&1
fi
EOF
cat > /root/.xinitrc <<'EOF'
#!/bin/sh
# Only bitmap fonts are installed (font-misc-misc), so use -fn fixed, never a
# scalable -fa alias. A keep-alive holder makes the X session persist (so the
# SPICE viewer always shows an image) even if the terminal ever exits.
xsetroot -solid "#1b3a5b" 2>/dev/null || true
( xterm -fn fixed -T "IsardVDI test desktop (isard / pirineus)" \
    -e sh -c '/usr/local/sbin/isard-ipbanner; echo; echo "IsardVDI minimal test desktop (console / SPICE)."; exec sh' & ) 2>/dev/null
exec sh -c 'while :; do sleep 3600; done'
EOF
chmod +x /root/.xinitrc

# Disable GLX/glamor so Xorg never touches libGL -> the ~170 MiB llvm-backed
# mesa gallium driver is dead weight for a 2D xterm and is deleted from the
# image by build-qcow2.sh. modesetting drives the QXL framebuffer in software.
mkdir -p /etc/X11/xorg.conf.d
cat > /etc/X11/xorg.conf.d/10-isard-noglx.conf <<'EOF'
Section "ServerFlags"
    Option "AutoAddGPU" "off"
EndSection
Section "Module"
    Disable "glx"
    Disable "glamoregl"
    Disable "dri"
    Disable "dri2"
EndSection
Section "Device"
    Identifier "qxl0"
    Driver "modesetting"
    Option "AccelMethod" "none"
EndSection
EOF

# --- RDP: xrdp + xorgxrdp. The RDP session reuses the same tiny terminal.
#     xrdp authenticates PAM against the local isard account.
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

# xrdp TLS: Alpine ships xrdp.ini with an empty certificate=/key_file=, so the
# TLS-preferring clients (FreeRDP3, guacd, rdpgw) can't negotiate. Point xrdp
# at a self-signed cert generated on FIRST BOOT - kept out of the image so the
# build stays byte-reproducible and no private key is committed. It is a
# throwaway test cert for a public test image, not a secret.
sed -i 's#^certificate=.*#certificate=/etc/xrdp/cert.pem#; s#^key_file=.*#key_file=/etc/xrdp/key.pem#' /etc/xrdp/xrdp.ini 2>/dev/null || true
cat > /etc/init.d/isard-xrdp-cert <<'EOF'
#!/sbin/openrc-run
description="Generate the xrdp TLS certificate on first boot (public test image)"
depend() { before xrdp xrdp-sesman sesman; }
start() {
    [ -s /etc/xrdp/cert.pem ] && return 0
    ebegin "Generating xrdp TLS certificate"
    openssl req -x509 -newkey rsa:2048 -nodes -keyout /etc/xrdp/key.pem \
        -out /etc/xrdp/cert.pem -days 3650 -subj "/CN=isard-test" >/dev/null 2>&1
    chmod 644 /etc/xrdp/cert.pem /etc/xrdp/key.pem
    eend $?
}
EOF
chmod +x /etc/init.d/isard-xrdp-cert
rc-update add isard-xrdp-cert default 2>/dev/null || true

# --- initramfs: guarantee the root-disk drivers for BOTH buses (virtio + SATA)
#     and ext4 are present, whichever bus the hypervisor gives the disk.
mkdir -p /etc/mkinitfs
cat > /etc/mkinitfs/mkinitfs.conf <<'EOF'
features="base ata scsi virtio ext4"
EOF

# --- Kernel modules to load at boot: VM disk/net/console/video.
cat > /etc/modules <<'EOF'
virtio_pci
virtio_blk
virtio_scsi
virtio_net
virtio_console
af_packet
ahci
sd_mod
qxl
virtio_gpu
EOF

# --- OpenRC runlevels: the minimum to boot, coldplug, net and shut down.
for s in devfs dmesg mdev; do rc-update add "$s" sysinit 2>/dev/null || true; done
for s in hwdrivers modules sysctl bootmisc hostname syslog; do rc-update add "$s" boot 2>/dev/null || true; done
rc-update add local default 2>/dev/null || true
for s in mount-ro killprocs; do rc-update add "$s" shutdown 2>/dev/null || true; done

# --- Determinism / cleanup: no logs, caches, seeds or history; empty machine-id.
rm -rf /var/cache/apk/* /root/.ash_history /var/log/* 2>/dev/null || true
: > /etc/machine-id 2>/dev/null || true
rm -f /etc/ssh/ssh_host_* 2>/dev/null || true
