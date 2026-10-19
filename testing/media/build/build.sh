#!/bin/sh
# SPDX-License-Identifier: AGPL-3.0-or-later
# Rebuilds testing/media/isard-test.iso:
#   docker run --rm -v "$PWD/testing/media:/w" ubuntu:24.04 sh /w/build/build.sh
# iPXE (GPL-2.0) source of the binaries: https://github.com/ipxe/ipxe/tree/12798ec29aa8a64d8675c4378b99f5fe28447afb
# syslinux (GPL-2.0) source of isolinux.bin and ldlinux.c32: https://launchpad.net/ubuntu/+source/syslinux/3:6.04~git20190206.bf6db5b4+dfsg1-3ubuntu3
set -eu
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq >/dev/null
apt-get install -y -qq git gcc make perl liblzma-dev mtools xorriso isolinux=3:6.04~git20190206.bf6db5b4+dfsg1-3ubuntu3 syslinux-common=3:6.04~git20190206.bf6db5b4+dfsg1-3ubuntu3 dosfstools >/dev/null
rm -rf /tmp/ipxe
git clone -q --depth 1 --branch v2.0.0 https://github.com/ipxe/ipxe.git /tmp/ipxe
cd /tmp/ipxe/src
test "$(git rev-parse HEAD)" = 12798ec29aa8a64d8675c4378b99f5fe28447afb
export SOURCE_DATE_EPOCH="$(git log -1 --format=%ct)"
cp /w/build/general.h config/local/general.h
make -s -j"$(nproc)" bin/virtio-net--intel.lkrn bin-x86_64-efi/virtio-net--intel.efi \
  EMBED=/w/build/isard.ipxe NO_WERROR=1 >/tmp/make.log 2>&1 || { tail -30 /tmp/make.log; exit 1; }

T=/tmp/isoroot
rm -rf $T
mkdir -p $T/isolinux
cp /usr/lib/ISOLINUX/isolinux.bin /usr/lib/syslinux/modules/bios/ldlinux.c32 $T/isolinux/
cp bin/virtio-net--intel.lkrn $T/ipxe.lkrn
printf 'DEFAULT ipxe\nLABEL ipxe\n KERNEL /ipxe.lkrn\n' > $T/isolinux/isolinux.cfg
kb=$(( $(stat -c %s bin-x86_64-efi/virtio-net--intel.efi) / 1024 + 64 ))
mkfs.fat --invariant -C -n ISARDEFI $T/efi.img $kb >/dev/null
mmd -i $T/efi.img ::/EFI ::/EFI/BOOT
mcopy -i $T/efi.img bin-x86_64-efi/virtio-net--intel.efi ::/EFI/BOOT/BOOTX64.EFI
find $T -exec touch -h -d @"$SOURCE_DATE_EPOCH" {} +
# CD-ROM boot only: isohybrid would pad the image to 1 MiB for USB boot
xorriso -as mkisofs -quiet -V ISARDTEST -o /w/isard-test.iso \
  -b isolinux/isolinux.bin -c isolinux/boot.cat -no-emul-boot -boot-load-size 4 -boot-info-table \
  -eltorito-alt-boot -e efi.img -no-emul-boot -no-pad $T
sha256sum /w/isard-test.iso
