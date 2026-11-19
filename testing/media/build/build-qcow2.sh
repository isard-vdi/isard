#!/bin/sh
# SPDX-License-Identifier: AGPL-3.0-or-later
# Rebuilds testing/media/isard-test.qcow2: the smallest practical bootable disk
# image that, used as an IsardVDI desktop, exercises every viewer. It boots
# unattended on BIOS and UEFI from a virtio or SATA disk, DHCPs every NIC (incl.
# the isard-vpn wireguard overlay) and prints the leases to the serial and video
# consoles, runs qemu-guest-agent, a tiny console X session (for the SPICE
# viewer) and xrdp+xorgxrdp (for the RDP viewers). OS-backed companion of the
# 564 KB iPXE isard-test.iso, which cannot do RDP (it is not an OS).
#
#   docker run --rm --privileged -v "$PWD/testing/media:/w" alpine:3.24 sh /w/build/build-qcow2.sh
#
# The root is a read-only, compressed erofs; an in-image service overlays /etc
# /var /home /root with tmpfs. The kernel is built from a pinned kernel.org
# tarball with everything built in (no modules, no initramfs); set KERNEL_MODE=
# virt to use Alpine's linux-virt + an initramfs instead. --privileged is only
# for the loop fallback of the BIOS GRUB install. The Alpine mirror and
# kernel.org are the only external sources.
#
# Reproducible: erofs is built deterministically (sorted, fixed -T/-U/--all-root),
# the kernel build is pinned and timestamp-fixed, GRUB/qemu-img honour
# SOURCE_DATE_EPOCH, and all ids are fixed -> two consecutive builds give the
# same sha256. Package provenance (GPL) in the .packages.txt.
set -eu
export PATH="/usr/sbin:/usr/bin:/sbin:/bin"

# ---------------------------------------------------------------- pins --------
ALPINE_VER="${ALPINE_VER:-3.24.4}"; ALPINE_BRANCH="v${ALPINE_VER%.*}"
MIRROR="${MIRROR:-https://dl-cdn.alpinelinux.org/alpine}"
KERNEL_MODE="${KERNEL_MODE:-own}"              # own | virt
KVER="${KVER:-6.18.64}"
KSHA=020d45510c539972e6f14c5c71566878d3b7ef56fb082b3e09134f2ebaade562
# All pinned apk package versions live in THIS block (with ALPINE_VER and KVER/
# KSHA above). If a pin is gone from the mirror the build stops naming it; bump
# it here and re-run the test matrix -- see README "Updating to a new version".
PV_ALPINE_BASE="alpine-base=3.24.4-r0"
PV_FIRMWARE="linux-firmware-none=20260519-r0"
PV_XORG_SERVER="xorg-server=21.1.26-r0"
PV_XF86_LIBINPUT="xf86-input-libinput=1.5.0-r0"
PV_XINIT="xinit=1.4.4-r0"
PV_SETXKBMAP="setxkbmap=1.3.5-r0"
PV_XSETROOT="xsetroot=1.1.3-r1"
PV_XTERM="xterm=410-r0"
PV_FONT_MISC="font-misc-misc=1.1.3-r1"
PV_XRDP="xrdp=0.10.6-r0"
PV_XORGXRDP="xorgxrdp=0.10.5-r0"
PV_QEMU_GA="qemu-guest-agent=11.0.3-r0"
PV_LINUX_VIRT="linux-virt=6.18.64-r0"          # KERNEL_MODE=virt only
PV_MKINITFS="mkinitfs=3.14.1-r0"               # KERNEL_MODE=virt only
EROFS_COMP="${EROFS_COMP:-auto}"               # auto | lzma | lz4hc
QCOW2_COMP="${QCOW2_COMP:-zstd}"               # zstd | zlib
export SOURCE_DATE_EPOCH="${SOURCE_DATE_EPOCH:-1793491200}"
export TZ=UTC LC_ALL=C MTOOLS_SKIP_CHECK=1

ROOT_UUID="a5a5a5a5-0000-4000-8000-000000000001"
ESP_VOLID="15A4DEF1"
DISK_GUID="150a5d00-0000-4000-8000-000000000000"
P1_GUID="150a5d00-0000-4000-8000-000000000001"
P2_GUID="150a5d00-0000-4000-8000-000000000002"
P3_GUID="150a5d00-0000-4000-8000-000000000003"      # the kernel finds root by this PARTUUID
PW_SALT="isardtestsalt"

OUT=/w/isard-test.qcow2; PKGLIST=/w/isard-test.qcow2.packages.txt; SIZES=/w/isard-test.qcow2.sizes.txt
ROOTDIR=/tmp/root; WORK=/w/.buildtmp; FILES=/w/build/qcow2-files; KCACHE="${KCACHE:-}"
rm -rf "$ROOTDIR" "$WORK"; mkdir -p "$WORK"; : > "$SIZES"

# ----------------------------------------------- builder from the branch ------
printf '%s/%s/main\n%s/%s/community\n' "$MIRROR" "$ALPINE_BRANCH" "$MIRROR" "$ALPINE_BRANCH" > /etc/apk/repositories
apk update -q
apk add -q qemu-img grub grub-bios grub-efi dosfstools mtools sfdisk openssl kmod erofs-utils >/dev/null
GRUB_BIOS_SETUP="$(command -v grub-bios-setup || echo /usr/lib/grub/i386-pc/grub-bios-setup)"
echo "ALPINE $ALPINE_VER  KERNEL_MODE=$KERNEL_MODE  KVER=$KVER  SOURCE_DATE_EPOCH=$SOURCE_DATE_EPOCH"

# ------------------------------------------------- own kernel (kernel.org) ----
build_own_kernel() {
    csha="$(sha256sum "$FILES/kernel.config" | cut -c1-16)"
    cached="${KCACHE:+$KCACHE/vmlinuz-$KVER-$csha}"
    if [ -n "$cached" ] && [ -f "$cached" ]; then cp "$cached" "$WORK/vmlinuz"; echo "cached kernel $cached" >&2; return; fi
    apk add -q build-base linux-headers bison flex openssl-dev elfutils-dev bc perl xz curl diffutils findutils gawk >/dev/null
    export KBUILD_BUILD_TIMESTAMP="@$SOURCE_DATE_EPOCH" KBUILD_BUILD_USER=isard KBUILD_BUILD_HOST=isard-test LC_ALL=C TZ=UTC
    cd /tmp
    if ! curl -fsS -O "https://cdn.kernel.org/pub/linux/kernel/v${KVER%%.*}.x/linux-$KVER.tar.xz"; then
        echo "FATAL: cannot download linux-$KVER.tar.xz from kernel.org (removed or renamed?)." >&2
        echo "       Update KVER and KSHA in the pinned-versions block, then re-run the test matrix." >&2
        exit 1
    fi
    if ! echo "$KSHA  linux-$KVER.tar.xz" | sha256sum -c - >/dev/null 2>&1; then
        echo "FATAL: linux-$KVER.tar.xz sha256 mismatch (got $(sha256sum "linux-$KVER.tar.xz" | cut -d' ' -f1))." >&2
        echo "       Fix KSHA in the pinned-versions block (or the download is corrupt), then re-run." >&2
        exit 1
    fi
    tar xf "linux-$KVER.tar.xz"; cd "linux-$KVER"
    make tinyconfig >/dev/null 2>&1
    ./scripts/kconfig/merge_config.sh -m -O . .config "$FILES/kernel.config" >/dev/null 2>&1
    make olddefconfig >/dev/null 2>&1
    for o in EROFS_FS VIRTIO_BLK SATA_AHCI BLK_DEV_SD VIRTIO_NET PACKET DRM_QXL INPUT_EVDEV EFI_PARTITION FILE_LOCKING; do
        grep -q "^CONFIG_$o=y" .config || { echo "FATAL: kernel CONFIG_$o not enabled"; exit 1; }
    done
    make -j"$(nproc)" bzImage >/tmp/kbuild.out 2>&1 || { tail -20 /tmp/kbuild.out; echo "FATAL: kernel build failed"; exit 1; }
    cp arch/x86/boot/bzImage "$WORK/vmlinuz"
    [ -n "$cached" ] && cp "$WORK/vmlinuz" "$cached"
    cd /; rm -rf "/tmp/linux-$KVER"
}
if [ "$KERNEL_MODE" = own ]; then build_own_kernel; echo "kernel: own $KVER ($(stat -c %s "$WORK/vmlinuz") bytes)"; fi

# --------------------------------------------- bootstrap the root filesystem --
mkdir -p "$ROOTDIR/etc/apk"; mkdir -p /tmp/apkcache
printf '%s/%s/main\n%s/%s/community\n' "$MIRROR" "$ALPINE_BRANCH" "$MIRROR" "$ALPINE_BRANCH" > "$ROOTDIR/etc/apk/repositories"
cp -a /etc/apk/keys "$ROOTDIR/etc/apk/keys"
APK="apk add --root $ROOTDIR --repositories-file $ROOTDIR/etc/apk/repositories --cache-dir /tmp/apkcache"
# Install pinned packages; stop with a clear message if a pin is gone from the mirror.
apk_pinned() {
    if $APK "$@" >/dev/null 2>/tmp/apkerr; then return 0; fi
    cat /tmp/apkerr >&2
    echo "FATAL: a pinned package version above is no longer in the Alpine mirror." >&2
    echo "       Bump the version(s) it names in the pinned-versions block at the top of this" >&2
    echo "       script, then re-run the test matrix (README: Updating to a new version)." >&2
    exit 1
}
prev=0
layer() { _l="$1"; shift; apk_pinned "$@"; now=$(du -sk "$ROOTDIR"|cut -f1); printf '%-10s +%4d MiB  (total %4d MiB)\n' "$_l" "$(((now-prev+512)/1024))" "$(((now+512)/1024))" | tee -a "$SIZES"; prev=$now; }
apk_pinned --initdb $PV_ALPINE_BASE $PV_FIRMWARE
now=$(du -sk "$ROOTDIR"|cut -f1); printf '%-10s +%4d MiB  (total %4d MiB)\n' base "$(((now+512)/1024))" "$(((now+512)/1024))" | tee -a "$SIZES"; prev=$now
[ "$KERNEL_MODE" = virt ] && layer kernel $PV_LINUX_VIRT $PV_MKINITFS kmod
layer xorg $PV_XORG_SERVER $PV_XF86_LIBINPUT $PV_XINIT $PV_SETXKBMAP $PV_XSETROOT
layer term $PV_XTERM $PV_FONT_MISC
layer rdp  $PV_XRDP $PV_XORGXRDP openssl
layer agent $PV_QEMU_GA

# ------------------------------------------------ configure (in the chroot) ---
HASH="$(openssl passwd -6 -salt "$PW_SALT" pirineus)"
cp "$FILES/configure.sh" "$ROOTDIR/configure.sh"
chroot "$ROOTDIR" /bin/sh /configure.sh "$HASH"
rm -f "$ROOTDIR/configure.sh"

# --------------------------------------------------- trim size (JM: minimum) --
rm -rf "$ROOTDIR"/usr/share/man "$ROOTDIR"/usr/share/doc "$ROOTDIR"/usr/share/info \
       "$ROOTDIR"/usr/share/licenses "$ROOTDIR"/usr/share/locale "$ROOTDIR"/usr/share/vulkan 2>/dev/null || true
# Drop the heavy llvm-backed gallium stack (unused by a 2D xterm; GLX disabled).
glbefore=$(du -sk "$ROOTDIR"|cut -f1)
rm -f  "$ROOTDIR"/usr/lib/libLLVM.so* "$ROOTDIR"/usr/lib/libLLVM-* \
       "$ROOTDIR"/usr/lib/libgallium*.so* "$ROOTDIR"/usr/lib/libvulkan*.so* \
       "$ROOTDIR"/usr/lib/libxatracker*.so* "$ROOTDIR"/usr/lib/libSPIRV-Tools*.so* \
       "$ROOTDIR"/usr/lib/xorg/modules/libglamoregl.so 2>/dev/null || true
rm -rf "$ROOTDIR"/usr/lib/dri "$ROOTDIR"/usr/lib/xorg/modules/dri 2>/dev/null || true
# Keep both DDXs the sessions use: modesetting (console X on QXL) and xrdpdev
# (xorgxrdp's RDP X); drop every other DDX. Deleting xrdpdev_drv.so breaks RDP.
find "$ROOTDIR"/usr/lib/xorg/modules/drivers -name '*_drv.so' \
    ! -name 'modesetting_drv.so' ! -name 'xrdpdev_drv.so' -delete 2>/dev/null || true
rm -f  "$ROOTDIR"/usr/lib/xorg/modules/extensions/libglx.so 2>/dev/null || true
rm -rf "$ROOTDIR"/usr/share/fonts/X11/100dpi "$ROOTDIR"/usr/share/fonts/X11/75dpi \
       "$ROOTDIR"/usr/share/fonts/X11/Type1 "$ROOTDIR"/usr/share/fonts/X11/cyrillic 2>/dev/null || true
glafter=$(du -sk "$ROOTDIR"|cut -f1)
printf '%-10s -%4d MiB  (total %4d MiB)\n' trim "$(((glbefore-glafter+512)/1024))" "$(((glafter+512)/1024))" | tee -a "$SIZES"

if [ "$KERNEL_MODE" = own ]; then
    # Own kernel is fully built in: the image carries no kernel and no modules.
    rm -rf "$ROOTDIR"/lib/modules "$ROOTDIR"/boot 2>/dev/null || true
else
    # linux-virt: keep a whitelist of modules + an initramfs that mounts the
    # erofs root (erofs + virtio + ata), load af_packet/qxl/etc. at boot.
    KV="$(basename "$(ls -d "$ROOTDIR"/lib/modules/* | head -1)")"
    printf 'features="base ata scsi virtio erofs"\n' > "$ROOTDIR/etc/mkinitfs/mkinitfs.conf"
    printf 'kernel/fs/erofs/erofs.ko*\n' > "$ROOTDIR/etc/mkinitfs/features.d/erofs.modules"
    printf 'af_packet\nvirtio_pci\nvirtio_net\nvirtio_console\nqxl\nvirtio_gpu\nbochs\nsd_mod\nahci\n' > "$ROOTDIR/etc/modules"
    chroot "$ROOTDIR" rc-update add modules boot 2>/dev/null || true
    chroot "$ROOTDIR" /sbin/mkinitfs -o /boot/initramfs-virt "$KV"
    cp "$ROOTDIR"/boot/vmlinuz-virt "$WORK/vmlinuz"
    cp "$ROOTDIR"/boot/initramfs-virt "$WORK/initramfs"
    rm -rf "$ROOTDIR"/boot
fi

# ------------------------------------------------------ root erofs (ro) -------
# erofs is deterministic (sorted entries, fixed timestamp/uuid/owner) -> the
# root fs is bit-reproducible. Pick the smaller of lzma/lz4hc.
mkerofs() { mkfs.erofs -z"$1" -T "$SOURCE_DATE_EPOCH" -U "$ROOT_UUID" --all-root -C1048576 "$2" "$ROOTDIR" >/dev/null 2>&1; }
if [ "$EROFS_COMP" = auto ]; then
    mkerofs lzma "$WORK/root.lzma.erofs" 2>/dev/null && L=$(stat -c %s "$WORK/root.lzma.erofs" 2>/dev/null || echo 0) || L=0
    mkerofs lz4hc "$WORK/root.lz4.erofs"; Z=$(stat -c %s "$WORK/root.lz4.erofs")
    if [ "$L" -gt 0 ] && [ "$L" -le "$Z" ]; then EROFS_COMP=lzma; mv "$WORK/root.lzma.erofs" "$WORK/root.erofs"; rm -f "$WORK/root.lz4.erofs"
    else EROFS_COMP=lz4hc; mv "$WORK/root.lz4.erofs" "$WORK/root.erofs"; rm -f "$WORK/root.lzma.erofs"; fi
else mkerofs "$EROFS_COMP" "$WORK/root.erofs"; fi
EROFS_SZ=$(stat -c %s "$WORK/root.erofs")
printf '%-10s %4d MiB  (erofs root, %s)\n' erofs "$(((EROFS_SZ+1048575)/1048576))" "$EROFS_COMP" | tee -a "$SIZES"

# --------------------------------------------------------- sizes & layout -----
SEC=512; P1_START=2048; P1_SIZE=2048
P2_START=4096; P2_SIZE=$(( 48*1024*1024/SEC )); P3_START=$(( P2_START + P2_SIZE ))
P3_SIZE=$(( (EROFS_SZ + SEC - 1)/SEC )); P3_SIZE=$(( (P3_SIZE + 2047)/2048*2048 ))   # round to 1 MiB
TOTAL_SEC=$(( P3_START + P3_SIZE + 34 ))

# ------------------------------------------------- GRUB images (read the ESP) -
printf 'search --no-floppy --label ISARDEFI --set=root\nset prefix=($root)/grub\n' > "$WORK/early.cfg"
GMODS="part_gpt part_msdos fat normal linux search search_label search_fs_uuid echo test configfile gzio loadenv"
grub-mkimage -O i386-pc    -c "$WORK/early.cfg" -p /grub -o "$WORK/core.img"    biosdisk $GMODS
grub-mkimage -O x86_64-efi -c "$WORK/early.cfg" -p /grub -o "$WORK/bootx64.efi" $GMODS efi_gop efi_uga all_video
cp /usr/lib/grub/i386-pc/boot.img "$WORK/boot.img"

INITRD_LINE=""; [ -f "$WORK/initramfs" ] && INITRD_LINE="    initrd /initramfs"
cat > "$WORK/grub.cfg" <<EOF
set timeout=0
set default=0
menuentry 'IsardVDI minimal test desktop' {
    linux  /vmlinuz root=PARTUUID=$P3_GUID rootfstype=erofs ro console=tty0 console=ttyS0,115200 net.ifnames=0 biosdevname=0
$INITRD_LINE
}
EOF

# ------------------------------------------------------ EFI system partition --
# Holds GRUB (both platforms), its config and the kernel (+initramfs for virt).
truncate -s "$(( P2_SIZE * SEC ))" "$WORK/esp.img"
mkfs.fat -F 32 -n ISARDEFI --invariant "$WORK/esp.img" >/dev/null
mmd -i "$WORK/esp.img" ::/EFI ::/EFI/BOOT ::/grub
for f in "$WORK/bootx64.efi:EFI/BOOT/BOOTX64.EFI" "$WORK/grub.cfg:grub/grub.cfg" "$WORK/vmlinuz:vmlinuz"; do
    src=${f%%:*}; dst=${f#*:}; touch -d "@$SOURCE_DATE_EPOCH" "$src"; mcopy -i "$WORK/esp.img" "$src" "::/$dst"
done
[ -f "$WORK/initramfs" ] && { touch -d "@$SOURCE_DATE_EPOCH" "$WORK/initramfs"; mcopy -i "$WORK/esp.img" "$WORK/initramfs" ::/initramfs; }

# --------------------------------------------------------- assemble GPT disk --
RAW="$WORK/disk.raw"; truncate -s "$(( TOTAL_SEC * SEC ))" "$RAW"
sfdisk --no-tell-kernel "$RAW" >/dev/null <<EOF
label: gpt
label-id: $DISK_GUID
unit: sectors
start=$P1_START, size=$P1_SIZE, type=21686148-6449-6E6F-744E-656564454649, uuid=$P1_GUID, name="BIOS boot"
start=$P2_START, size=$P2_SIZE, type=C12A7328-F81F-11D2-BA4B-00A0C93EC93B, uuid=$P2_GUID, name="EFI system"
start=$P3_START, size=$P3_SIZE, type=0FC63DAF-8483-4772-8E79-3D69D8477DE4, uuid=$P3_GUID, name="root"
EOF
dd if="$WORK/esp.img"   of="$RAW" bs=$SEC seek=$P2_START conv=notrunc status=none
dd if="$WORK/root.erofs" of="$RAW" bs=$SEC seek=$P3_START conv=notrunc status=none
if ! "$GRUB_BIOS_SETUP" -d "$WORK" -b boot.img -c core.img "$RAW" 2>"$WORK/biossetup.log"; then
    echo "grub-bios-setup file mode failed, retrying via loop:"; cat "$WORK/biossetup.log"
    LOOP="$(losetup -fP --show "$RAW")"; "$GRUB_BIOS_SETUP" -d "$WORK" -b boot.img -c core.img "$LOOP"; losetup -d "$LOOP"
fi

# ------------------------------------------------------------- to qcow2 -------
rm -f "$OUT"
qemu-img convert -f raw -O qcow2 -c -o "compat=1.1,compression_type=$QCOW2_COMP" "$RAW" "$OUT"

# ----------------------------------------------- provenance (GPL) & report ----
{
    echo "# IsardVDI minimal test desktop image - binary package provenance"
    echo "# Alpine Linux $ALPINE_VER ($ALPINE_BRANCH, main+community): $MIRROR/$ALPINE_BRANCH/{main,community}"
    echo "# Kernel: linux-$KVER from kernel.org (sha256 $KSHA), config in build/qcow2-files/kernel.config"
    echo "# Source of any (L)GPL binary: git.alpinelinux.org/aports + each APKBUILD upstream, or apk fetch --source."
    echo "# SOURCE_DATE_EPOCH=$SOURCE_DATE_EPOCH  KERNEL_MODE=$KERNEL_MODE  erofs=$EROFS_COMP"
    echo "#"
    apk --root "$ROOTDIR" info -v 2>/dev/null | LC_ALL=C sort
} > "$PKGLIST"
rm -rf "$WORK"

echo "=================================================================="
echo "image : $OUT"
echo "size  : $(stat -c %s "$OUT") bytes ($(du -h "$OUT" | cut -f1))"
qemu-img info "$OUT" | sed 's/^/        /'
echo "--- size breakdown ---"; cat "$SIZES"
sha256sum "$OUT"
echo "packages: $(grep -vc '^#' "$PKGLIST")"
echo "=================================================================="
