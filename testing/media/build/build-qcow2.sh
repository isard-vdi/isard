#!/bin/sh
# SPDX-License-Identifier: AGPL-3.0-or-later
# Rebuilds testing/media/isard-test.qcow2: the smallest practical Alpine Linux
# desktop image that boots unattended on BIOS and UEFI (virtio or SATA disk),
# DHCPs every NIC (incl. the isard-vpn wireguard overlay), runs
# qemu-guest-agent, a tiny console X session (so the SPICE viewer shows an
# image) and xrdp+xorgxrdp (so the RDP viewers work). OS-backed companion of
# the 564 KB iPXE isard-test.iso, which cannot do RDP (it is not an OS).
#
#   docker run --rm --privileged -v "$PWD/testing/media:/w" alpine:3.24 sh /w/build/build-qcow2.sh
#
# --privileged is only used as a fallback for the BIOS GRUB install (a loop
# device, if grub-bios-setup's image-file mode is refused). Otherwise only the
# Alpine mirror is needed.
#
# Reproducible: Alpine release branch AND every top-level package are pinned;
# SOURCE_DATE_EPOCH is fixed; the account password is a fixed-salt hash; the
# filesystems are built mount-free with fixed UUIDs; GRUB and qemu-img honour
# SOURCE_DATE_EPOCH; free space is zero by construction (sparse image) so
# qemu-img convert -c compresses it away. Two consecutive runs on the same
# builder give the same sha256. Package provenance (GPL) in the .packages.txt.
set -eu
export PATH="/usr/sbin:/usr/bin:/sbin:/bin"

# ---------------------------------------------------------------- pins --------
ALPINE_VER="${ALPINE_VER:-3.24.4}"
ALPINE_BRANCH="v${ALPINE_VER%.*}"                      # v3.24
MIRROR="${MIRROR:-https://dl-cdn.alpinelinux.org/alpine}"
export SOURCE_DATE_EPOCH="${SOURCE_DATE_EPOCH:-1793491200}"   # 2026-11-01T00:00:00Z, fixed
export TZ=UTC LC_ALL=C MTOOLS_SKIP_CHECK=1

# Pinned top-level packages (transitive deps are pinned by the branch; exact
# versions recorded in the .packages.txt provenance file).
P_BASE="alpine-base=3.24.4-r0 linux-firmware-none=20260519-r0 kmod"
P_KERNEL="linux-virt=6.18.64-r0 mkinitfs=3.14.1-r0"
P_XORG="xorg-server=21.1.26-r0 xf86-input-libinput=1.5.0-r0 xinit=1.4.4-r0 xkeyboard-config setxkbmap=1.3.5-r0 xsetroot=1.1.3-r1"
P_TERM="xterm=410-r0 font-misc-misc=1.1.3-r1"
P_RDP="xrdp=0.10.6-r0 xorgxrdp=0.10.5-r0 openssl"
P_AGENT="qemu-guest-agent=11.0.3-r0"

# Fixed identifiers so the partition table and filesystems are byte-stable.
ROOT_UUID="a5a5a5a5-0000-4000-8000-000000000001"
ESP_VOLID="15A4DEF1"                                   # FAT serial -> 15A4-DEF1
DISK_GUID="150a5d00-0000-4000-8000-000000000000"
P1_GUID="150a5d00-0000-4000-8000-000000000001"
P2_GUID="150a5d00-0000-4000-8000-000000000002"
P3_GUID="150a5d00-0000-4000-8000-000000000003"
PW_SALT="isardtestsalt"                                # fixed salt -> deterministic hash

OUT=/w/isard-test.qcow2
PKGLIST=/w/isard-test.qcow2.packages.txt
SIZES=/w/isard-test.qcow2.sizes.txt
ROOTDIR=/tmp/root
WORK=/w/.buildtmp                                      # on the host bind-mount, not overlayfs
FILES=/w/build/qcow2-files
rm -rf "$ROOTDIR" "$WORK"; mkdir -p "$WORK"
: > "$SIZES"

# ----------------------------------------------- builder from the branch ------
printf '%s/%s/main\n%s/%s/community\n' "$MIRROR" "$ALPINE_BRANCH" "$MIRROR" "$ALPINE_BRANCH" > /etc/apk/repositories
apk update -q
apk add -q qemu-img grub grub-bios grub-efi e2fsprogs e2fsprogs-extra dosfstools mtools sfdisk openssl kmod tar
GRUB_BIOS_SETUP="$(command -v grub-bios-setup || echo /usr/lib/grub/i386-pc/grub-bios-setup)"
echo "ALPINE $ALPINE_VER ($ALPINE_BRANCH)  SOURCE_DATE_EPOCH=$SOURCE_DATE_EPOCH"

# --------------------------------------------- bootstrap the root filesystem --
mkdir -p "$ROOTDIR/etc/apk"
printf '%s/%s/main\n%s/%s/community\n' "$MIRROR" "$ALPINE_BRANCH" "$MIRROR" "$ALPINE_BRANCH" > "$ROOTDIR/etc/apk/repositories"
cp -a /etc/apk/keys "$ROOTDIR/etc/apk/keys"
mkdir -p /tmp/apkcache
APK="apk add --root $ROOTDIR --repositories-file $ROOTDIR/etc/apk/repositories --cache-dir /tmp/apkcache"
prev=0
layer() {  # $1 label, rest packages
    _l="$1"; shift
    $APK "$@" >/dev/null
    now=$(du -sk "$ROOTDIR" | cut -f1)
    printf '%-10s +%4d MiB  (running total %4d MiB)\n' "$_l" "$(((now-prev+512)/1024))" "$(((now+512)/1024))" | tee -a "$SIZES"
    prev=$now
}
$APK --initdb $P_BASE >/dev/null; now=$(du -sk "$ROOTDIR"|cut -f1); printf '%-10s +%4d MiB  (running total %4d MiB)\n' base "$(((now+512)/1024))" "$(((now+512)/1024))" | tee -a "$SIZES"; prev=$now
layer kernel $P_KERNEL
layer xorg   $P_XORG
layer term   $P_TERM
layer rdp    $P_RDP
layer agent  $P_AGENT

KVER="$(basename "$(ls -d "$ROOTDIR"/lib/modules/* | head -1)")"
echo "kernel modules dir: $KVER"

# ------------------------------------------------ configure (in the chroot) ---
HASH="$(openssl passwd -6 -salt "$PW_SALT" pirineus)"
cp "$FILES/configure.sh" "$ROOTDIR/configure.sh"
chroot "$ROOTDIR" /bin/sh /configure.sh "$HASH"
rm -f "$ROOTDIR/configure.sh"

# --------------------------------------------------- trim size (JM: minimum) --
# Alpine ships no man/doc/locale by default; strip any that slipped in.
rm -rf "$ROOTDIR"/usr/share/man "$ROOTDIR"/usr/share/doc "$ROOTDIR"/usr/share/info \
       "$ROOTDIR"/usr/share/licenses "$ROOTDIR"/usr/share/locale 2>/dev/null || true
# Drop the heavy llvm-backed gallium stack: a 2D xterm over modesetting/
# xorgxrdp never creates a GL context (GLX disabled in xorg.conf.d), so libLLVM
# (~170 MiB), the gallium DRI drivers, libxatracker, Vulkan and the SPIR-V tools
# are dead weight. KEEP the small libgbm/libGL/libEGL/libepoxy — the modesetting
# driver NEEDs libgbm.so.1 (and the xorg-server binary links libGL.so.1).
glbefore=$(du -sk "$ROOTDIR"|cut -f1)
rm -f  "$ROOTDIR"/usr/lib/libLLVM.so* "$ROOTDIR"/usr/lib/libLLVM-* \
       "$ROOTDIR"/usr/lib/libgallium*.so* "$ROOTDIR"/usr/lib/libvulkan*.so* \
       "$ROOTDIR"/usr/lib/libxatracker*.so* "$ROOTDIR"/usr/lib/libSPIRV-Tools*.so* \
       "$ROOTDIR"/usr/lib/xorg/modules/libglamoregl.so 2>/dev/null || true
rm -rf "$ROOTDIR"/usr/lib/dri "$ROOTDIR"/usr/lib/xorg/modules/dri "$ROOTDIR"/usr/share/vulkan 2>/dev/null || true
glafter=$(du -sk "$ROOTDIR"|cut -f1)
printf '%-10s -%4d MiB  (running total %4d MiB)\n' noGL "$(((glbefore-glafter+512)/1024))" "$(((glafter+512)/1024))" | tee -a "$SIZES"

# Kernel: keep ONLY the modules a KVM/IsardVDI guest needs; delete the rest.
# The keep-set is the dependency closure of a whitelist (modprobe resolves deps
# from modules.dep); then every other .ko is dropped and depmod rebuilt. Also
# drop the runtime-useless System.map and kernel config.
rm -f "$ROOTDIR"/boot/System.map-* "$ROOTDIR"/boot/config-* 2>/dev/null || true
kbefore=$(du -sk "$ROOTDIR"|cut -f1)
WL="virtio virtio_pci virtio_mmio virtio_ring virtio_blk virtio_scsi virtio_net \
virtio_console virtio_rng virtio_balloon virtio_input virtio_dma_buf virtio-gpu \
ahci libahci libata ata_piix ata_generic sata_sil sata_sil24 sata_nv sata_via \
sd_mod sr_mod scsi_mod \
e1000 e1000e 8139cp 8139too mii af_packet \
qxl bochs drm drm_kms_helper drm_shmem_helper drm_ttm_helper ttm \
ext4 jbd2 mbcache crc32c_generic crc16 crc32c_intel \
vfat fat nls_cp437 nls_iso8859-1 nls_ascii nls_utf8 \
xhci_pci xhci_hcd usbhid hid hid_generic evdev atkbd psmouse i8042 serio_raw"
KEEP="$WORK/keep.list"
# Keep-set as module BASENAMES (robust to the modprobe path prefix and the
# .ko.gz compression suffix, which a full-path match got wrong and silently
# dropped ext4 -> unbootable).
# NOTE: `|| true` is essential — under `set -e`, a modprobe that can't find a
# whitelist name (some are absent in this kernel) would otherwise kill the
# loop's subshell mid-list and silently drop every later module (incl. ext4).
for m in $WL; do modprobe -d "$ROOTDIR" -S "$KVER" --show-depends "$m" 2>/dev/null || true; done \
    | awk '/^insmod/{print $2}' | while IFS= read -r p; do b=${p##*/}; echo "${b%%.ko*}"; done \
    | sort -u > "$KEEP"
if [ "$(wc -l < "$KEEP")" -lt 8 ]; then
    echo "WARNING: module keep-list too small ($(wc -l < "$KEEP")) - skipping module prune"
else
    find "$ROOTDIR/lib/modules/$KVER/kernel" -type f -name '*.ko*' | while IFS= read -r f; do
        b=${f##*/}; grep -qxF "${b%%.ko*}" "$KEEP" || rm -f "$f"
    done
    find "$ROOTDIR/lib/modules/$KVER/kernel" -type d -empty -delete 2>/dev/null || true
    depmod -b "$ROOTDIR" "$KVER" 2>/dev/null || true
fi
# Hard-assert the boot-critical drivers survived as a kept module OR are built
# into the kernel (built-ins have no .ko and need no keeping).
BUILTIN="$ROOTDIR/lib/modules/$KVER/modules.builtin"
for need in ext4 virtio_blk virtio_net qxl ahci sd_mod af_packet; do
    if find "$ROOTDIR/lib/modules/$KVER/kernel" -name "$need.ko*" | grep -q .; then
        :   # kept as module
    elif grep -qE "/$need\.ko\$" "$BUILTIN" 2>/dev/null; then
        echo "note: $need is built into the kernel"
    else
        echo "FATAL: required driver '$need' is neither a kept module nor built-in"; exit 1
    fi
done
kafter=$(du -sk "$ROOTDIR"|cut -f1)
printf '%-10s -%4d MiB  (kept %s .ko, running total %4d MiB)\n' modprune \
    "$(((kbefore-kafter+512)/1024))" "$(wc -l < "$KEEP")" "$(((kafter+512)/1024))" | tee -a "$SIZES"

# (Re)build the initramfs so it matches the pruned module set. vmlinuz-virt and
# initramfs-virt are version-independent names (used verbatim by grub.cfg).
chroot "$ROOTDIR" /sbin/mkinitfs -o /boot/initramfs-virt "$KVER"

# ------------------------------------------------- boot config (needs UUIDs) --
mkdir -p "$ROOTDIR/boot/efi"
cat > "$ROOTDIR/etc/fstab" <<EOF
UUID=$ROOT_UUID /         ext4 rw,relatime 0 1
UUID=${ESP_VOLID%????}-${ESP_VOLID#????} /boot/efi vfat umask=0077,nofail 0 0
EOF

mkdir -p "$ROOTDIR/boot/grub"
cat > "$ROOTDIR/boot/grub/grub.cfg" <<EOF
set timeout=0
set default=0
menuentry 'IsardVDI minimal test desktop' {
    search --no-floppy --fs-uuid --set=root $ROOT_UUID
    linux  /boot/vmlinuz-virt root=UUID=$ROOT_UUID rootfstype=ext4 ro console=tty0 console=ttyS0,115200 modules=sd-mod,usb-storage,ext4,virtio_blk,virtio_pci,ahci
    initrd /boot/initramfs-virt
}
EOF

# ------------------------------------------------------- GRUB images (both) ---
printf 'search.fs_uuid %s root\nset prefix=($root)/boot/grub\n' "$ROOT_UUID" > "$WORK/early.cfg"
GMODS="part_gpt part_msdos fat ext2 normal linux search search_fs_uuid echo test configfile gzio loadenv"
grub-mkimage -O i386-pc    -c "$WORK/early.cfg" -p /boot/grub -o "$WORK/core.img"    biosdisk $GMODS
grub-mkimage -O x86_64-efi -c "$WORK/early.cfg" -p /boot/grub -o "$WORK/bootx64.efi" $GMODS efi_gop efi_uga all_video
cp /usr/lib/grub/i386-pc/boot.img "$WORK/boot.img"

# --------------------------------------------------------- sizes & layout -----
SEC=512; P1_START=2048; P1_SIZE=2048; P2_START=4096; P2_SIZE=98304; P3_START=102400
USED_K="$(du -sk "$ROOTDIR" | cut -f1)"
ROOT_MB="$(( ( (USED_K * 135 / 100 / 1024) + 63) / 64 * 64 ))"
[ "$ROOT_MB" -lt 256 ] && ROOT_MB=256
P3_SIZE="$(( ROOT_MB * 1024 * 1024 / SEC ))"
TOTAL_SEC="$(( P3_START + P3_SIZE + 34 ))"

# --------------------------------------------------- root ext4 (mount-free) ---
# Restage the tree in a canonical (name-sorted) order onto the host-backed $WORK
# before mke2fs: mke2fs -d allocates inodes in the source readdir order, and the
# bootstrap rootfs lives on the container overlayfs whose readdir order differs
# between runs -> the inode table was the last non-reproducible region. Extracting
# an identical name-sorted stream onto the same host fs makes it deterministic.
STAGE="$WORK/stage"; mkdir -p "$STAGE"
( cd "$ROOTDIR" && tar --sort=name --numeric-owner --xattrs -cf - . ) | ( cd "$STAGE" && tar -xpf - )
truncate -s "$(( P3_SIZE * SEC ))" "$WORK/root.img"
# hash_seed is pinned (mke2fs randomises it otherwise); SOURCE_DATE_EPOCH fixes
# the mkfs/inode times; the sorted restage fixes inode-allocation order.
mke2fs -q -t ext4 -b 4096 -U "$ROOT_UUID" \
    -E lazy_itable_init=0,lazy_journal_init=0,hash_seed="$ROOT_UUID" -O ^resize_inode \
    -d "$STAGE" -F "$WORK/root.img" >/dev/null

# ------------------------------------------------------ EFI system partition --
truncate -s "$(( P2_SIZE * SEC ))" "$WORK/esp.img"
mkfs.fat -F 32 -n ISARDEFI -i "$ESP_VOLID" --invariant "$WORK/esp.img" >/dev/null
mmd -i "$WORK/esp.img" ::/EFI ::/EFI/BOOT
touch -d "@$SOURCE_DATE_EPOCH" "$WORK/bootx64.efi"
mcopy -i "$WORK/esp.img" "$WORK/bootx64.efi" ::/EFI/BOOT/BOOTX64.EFI

# --------------------------------------------------------- assemble GPT disk --
RAW="$WORK/disk.raw"
truncate -s "$(( TOTAL_SEC * SEC ))" "$RAW"
sfdisk --no-tell-kernel "$RAW" >/dev/null <<EOF
label: gpt
label-id: $DISK_GUID
unit: sectors
start=$P1_START, size=$P1_SIZE, type=21686148-6449-6E6F-744E-656564454649, uuid=$P1_GUID, name="BIOS boot"
start=$P2_START, size=$P2_SIZE, type=C12A7328-F81F-11D2-BA4B-00A0C93EC93B, uuid=$P2_GUID, name="EFI system"
start=$P3_START, size=$P3_SIZE, type=0FC63DAF-8483-4772-8E79-3D69D8477DE4, uuid=$P3_GUID, name="root"
EOF
dd if="$WORK/esp.img"  of="$RAW" bs=$SEC seek=$P2_START conv=notrunc status=none
dd if="$WORK/root.img" of="$RAW" bs=$SEC seek=$P3_START conv=notrunc status=none

# BIOS boot: write boot.img (MBR) + core.img (BIOS boot partition). $WORK is on
# /w (host fs), so grub-bios-setup can canonicalize the backing device.
if ! "$GRUB_BIOS_SETUP" -d "$WORK" -b boot.img -c core.img "$RAW" 2>"$WORK/biossetup.log"; then
    echo "grub-bios-setup file mode failed, retrying via loop device:"; cat "$WORK/biossetup.log"
    LOOP="$(losetup -fP --show "$RAW")"
    "$GRUB_BIOS_SETUP" -d "$WORK" -b boot.img -c core.img "$LOOP"
    losetup -d "$LOOP"
fi

# ------------------------------------------------------------- to qcow2 -------
rm -f "$OUT"
# zstd compresses smaller than zlib and is read by this VM's qemu/qemu-img
# (hypervisor 11.0.3, storage 10.2.2). Override with QCOW2_COMP=zlib if needed.
qemu-img convert -f raw -O qcow2 -c -o "compat=1.1,compression_type=${QCOW2_COMP:-zstd}" "$RAW" "$OUT"

# ----------------------------------------------- provenance (GPL) & report ----
{
    echo "# IsardVDI minimal test desktop image - binary package provenance"
    echo "# Alpine Linux $ALPINE_VER, branch $ALPINE_BRANCH, main+community."
    echo "# Each package below is the exact version served by:"
    echo "#   $MIRROR/$ALPINE_BRANCH/{main,community}"
    echo "# Source of any (L)GPL binary: https://git.alpinelinux.org/aports + the"
    echo "# upstream in each APKBUILD; or apk fetch --source <pkg> from the branch."
    echo "# SOURCE_DATE_EPOCH=$SOURCE_DATE_EPOCH  kernel_modules=$KVER"
    echo "#"
    apk --root "$ROOTDIR" info -v 2>/dev/null | LC_ALL=C sort
} > "$PKGLIST"
rm -rf "$WORK"

echo "=================================================================="
echo "image : $OUT"
echo "size  : $(stat -c %s "$OUT") bytes ($(du -h "$OUT" | cut -f1))"
echo "root  : $ROOT_MB MiB fs, $(( TOTAL_SEC * SEC / 1024 / 1024 )) MiB disk"
qemu-img info "$OUT" | sed 's/^/        /'
echo "--- boot components (uncompressed) ---"
du -h "$ROOTDIR"/boot/vmlinuz-virt "$ROOTDIR"/boot/initramfs-virt 2>/dev/null
du -sh "$ROOTDIR"/lib/modules/"$KVER" 2>/dev/null
echo "--- per-layer installed size ---"; cat "$SIZES"
sha256sum "$OUT"
echo "packages: $(grep -vc '^#' "$PKGLIST") (see $PKGLIST)"
echo "=================================================================="
