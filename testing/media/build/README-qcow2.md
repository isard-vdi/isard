<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
# IsardVDI minimal test desktop image (`isard-test.qcow2`)

The smallest practical **bootable** disk image for exercising IsardVDI desktops
and **every viewer** end-to-end. It is the operating-system companion of the
iPXE `testing/media/isard-test.iso`: that ISO proves network boot but cannot do
RDP because it is not an operating system.

Built by [`build-qcow2.sh`](./build-qcow2.sh) (+ [`qcow2-files/configure.sh`](./qcow2-files/configure.sh)
and [`qcow2-files/kernel.config`](./qcow2-files/kernel.config)):

```sh
docker run --rm --privileged -v "$PWD/testing/media:/w" alpine:3.24 sh /w/build/build-qcow2.sh
```

`--privileged` is only a fallback for the BIOS GRUB install (a loop device, if
`grub-bios-setup`'s image-file mode is refused); otherwise only the Alpine
mirror and kernel.org are used. The build prints the final size, the sha256 and
a per-layer size breakdown, and writes `isard-test.qcow2.packages.txt` (exact
version of every binary package — the GPL source provenance).

Set `KERNEL_MODE=virt` to build with Alpine's `linux-virt` + an initramfs
instead of the own kernel (larger, but no kernel compile); the default
`KERNEL_MODE=own` builds a pinned kernel.org kernel with everything built in.

## What it does when it boots as a desktop

1. **Boots unattended** on BIOS (SeaBIOS) and UEFI (OVMF), from a **virtio** or
   a **SATA** disk — one image, GRUB installed for both `i386-pc` and
   `x86_64-efi` (removable-media path, no NVRAM entry needed).
2. **DHCPs every ethernet NIC** — the default NAT NIC and the isard-vpn
   `wireguard` overlay NIC — and applies the DHCP-provided MTU (1386 on the
   overlay). The leases are printed to the **serial console** (`ttyS0`, which
   IsardVDI logs) and the **video console**.
3. Runs **`qemu-guest-agent`** — IsardVDI reads the guest IP through it.
4. Runs a **minimal console X session** (Xorg `modesetting` on the QXL
   framebuffer + an `xterm`) so the **SPICE viewer** shows an image.
5. Runs **`xrdp` + `xorgxrdp`**, authenticating the default IsardVDI guest
   account, so the **RDP viewers** (file-rdpgw, file-rdpvpn, browser-rdp) work.

## Validation

Besides booting on every BIOS/UEFI × virtio/SATA combination, the image is
exercised end to end by the project's own viewer tooling — the I+D RDP probe
(direct X.224 to the guest's xrdp **and** the full RD-Gateway/MS-TSGU chain
through rdpgw) and the per-viewer byte counters — and every viewer connects to
the running desktop with a passing negative control: SPICE (first image), RDP
over the VPN and through the gateway, browser RDP (Guacamole) and browser noVNC.
It is therefore a real end-to-end fixture for the viewer tests that today rely
on a fake in-process RDP guest.

| user | password |
|------|----------|
| `isard` | `pirineus` |

These are the default IsardVDI guest credentials used throughout the codebase.
This is a **public test image**; the password is stored as a fixed-salt SHA-512
crypt hash so the build stays byte-reproducible. Do not reuse these anywhere
real. Set a desktop's `guest_properties.credentials` to `isard`/`pirineus` and
xrdp authenticates its local PAM account against them. `root` is locked.

## Architecture

**Read-only erofs root + tmpfs overlays.** The root filesystem is a compressed,
read-only **erofs** (lz4hc). An early OpenRC service (`isard-rw`, sysinit)
overlays `/etc`, `/var`, `/home` and `/root` with a tmpfs upper so the running
system can write there; `/` and `/usr` stay read-only. `/tmp` and `/dev/shm`
are tmpfs. This makes the root bit-reproducible (erofs is built deterministically)
and needs no initramfs — the kernel mounts the erofs root directly by PARTUUID.

**Own kernel, everything built in.** The kernel is built from a pinned
kernel.org tarball (verified by sha256) with `make tinyconfig` + a small
[`kernel.config`](./qcow2-files/kernel.config) fragment, so every driver the
guest needs is built in (`=y`): virtio blk/net/pci/console/scsi/rng/balloon/input,
AHCI/SATA + `sd_mod`, e1000/e1000e/8139, `af_packet`, QXL/bochs/virtio-gpu + a
minimal DRM, `erofs`, EFI stub + GPT, evdev/hid, vfat for the ESP. No loadable
modules, no initramfs. The result is **~2.8 MiB** versus Alpine's ~12 MiB
`linux-virt`.

**No llvm/gallium GL stack (the single biggest size win).** Alpine's
`xorg-server` hard-links `libGL.so.1 → mesa`, and `mesa`'s gallium DRI driver
pulls `libLLVM` (~170 MiB). `xorg-server` is mandatory (xrdp's RDP video driver
is an Xorg DDX). A 2D `xterm` over `modesetting`/`xorgxrdp` never creates a GL
context, so the build **disables GLX/glamor** and **deletes `libLLVM`, the
gallium DRI drivers, Vulkan and the SPIR-V tools** (the small `libgbm`/`libGL`
loader is kept — `modesetting_drv.so` needs `libgbm`).

**X audit.** The image keeps exactly two Xorg video drivers: `modesetting`
(console X on the QXL framebuffer) and `xrdpdev` (xorgxrdp's own DDX for the RDP
session). Every other DDX, the GLX extension and the unused X font directories
(100dpi/75dpi/Type1/cyrillic) are removed; the bitmap `misc` fonts that
`xterm -fn fixed` uses are kept. Docs, man pages, locales and the fontconfig
cache are stripped too.

## Size

Absolute priority is size. The image is **Alpine Linux** (musl + busybox +
OpenRC, no systemd, no dbus), the own kernel, `linux-firmware-none`, and only
the packages the five jobs above need.

```
<!-- SIZES: regenerated by the build into isard-test.qcow2.sizes.txt -->
base       +  11 MiB   (alpine-base, busybox/OpenRC, linux-firmware-none)
xorg       + 262 MiB   (xorg-server pulls mesa -> llvm; stripped below)
term       +   2 MiB   (xterm + font-misc-misc)
rdp        +   9 MiB   (xrdp + xorgxrdp + openssl)
agent      +   8 MiB   (qemu-guest-agent)
trim       - 229 MiB   (delete llvm/gallium GL, extra DDX, docs/locales/fontcache)
                        final installed rootfs ~63 MiB
erofs        ~30 MiB   (lz4hc-compressed read-only root)
own kernel  2.8 MiB    (vmlinuz on the ESP; no modules, no initramfs)
final qcow2  28.3 MiB   (29,697,024 bytes; zstd-compressed, the ESP free space is zero)
```

The dominant installed layer is Xorg's `mesa→llvm`; removing the GL stack
(unused by a 2D session) is what makes the image small. The own kernel replaces
the ~12 MiB `linux-virt` + ~6 MiB initramfs with a single ~2.8 MiB `vmlinuz`.

## Reproducibility — bit-for-bit

**Two consecutive builds produce an identical sha256**
(`679664120cf1bb382030969d05dd17e9091a91c15872388434646b326af244f7`). How:

- The Alpine release branch (`v3.24`) **and every top-level package version**
  are pinned; the kernel is pinned by tarball **sha256**.
- `SOURCE_DATE_EPOCH` is fixed, and the kernel build exports
  `KBUILD_BUILD_TIMESTAMP`/`USER`/`HOST` so the kernel carries no wall-clock,
  user or host.
- The erofs root is built mount-free and deterministically (`mkfs.erofs` with a
  fixed `-T` timestamp, fixed `-U` UUID, `--all-root`, sorted entries); the ESP
  is `mkfs.fat --invariant` + `mcopy`; the GPT uses fixed GUIDs; the account
  password uses a fixed salt; GRUB (`grub-mkimage`) and `qemu-img` honour
  `SOURCE_DATE_EPOCH`.
- The one class of install-time randomness is removed at build time and
  **regenerated on first boot** into the writable `/etc` overlay: xrdp's
  post-install bakes a random RSA key (`rsakeys.ini`) and a random self-signed
  TLS cert; both are deleted from the image and recreated by the
  `isard-xrdp-cert` service at boot (via `openssl` + `xrdp-keygen`). The
  fontconfig cache and logs are dropped too.

Caveat (cross-time): Alpine has no `snapshot.debian.org`-style time-pinned
mirror, so cross-time reproducibility is bounded by the `v3.24` branch receiving
package updates; the exact versions built against are recorded in
`isard-test.qcow2.packages.txt` (GPL source provenance: `git.alpinelinux.org/aports`
+ each APKBUILD's upstream, or `apk fetch --source <pkg>`).

## Updating to a new version

Pinned versions are not archived anywhere, so when one disappears from the
Alpine mirror (or the kernel tarball is removed from kernel.org) the build
**stops with a clear message naming the version that is gone**. To recover:

1. **Everything to bump is in one block** at the top of
   [`build-qcow2.sh`](./build-qcow2.sh): `ALPINE_VER`, `KVER` + `KSHA` (the
   kernel tarball sha256), and the `PV_*` package pins. Nothing else hardcodes a
   version.
2. Find the new version on the mirror
   (`https://dl-cdn.alpinelinux.org/alpine/v3.24/<main|community>/x86_64/`) or,
   for a new Alpine branch, bump `ALPINE_VER` (the branch is derived from it).
   For the kernel, pick a new `KVER` from kernel.org and set `KSHA` to the
   published `sha256sum` of `linux-<KVER>.tar.xz`.
3. Edit only that block and re-run the build.
4. **Re-run the full test matrix** on the rebuilt image (this is what the build
   verifies functionally): BIOS and UEFI boot × virtio and SATA disk; DHCP on
   both NICs incl. the overlay MTU; SPICE channel + first image; RDP over the
   VPN and through the gateway (with a bad-password negative control); browser
   RDP; browser noVNC with a real user session; and two consecutive builds give
   the same sha256.
