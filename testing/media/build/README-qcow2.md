<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
# IsardVDI minimal test desktop image (`isard-test.qcow2`)

The smallest practical **bootable** disk image for exercising IsardVDI desktops
and **every viewer** end-to-end. It is the operating-system companion of the
564 KB iPXE `testing/media/isard-test.iso`: that ISO proves network boot but
cannot do RDP because it is not an operating system.

Built by [`build-qcow2.sh`](./build-qcow2.sh) (+ [`qcow2-files/configure.sh`](./qcow2-files/configure.sh)):

```sh
docker run --rm --privileged -v "$PWD/testing/media:/w" alpine:3.24 sh /w/build/build-qcow2.sh
```

`--privileged` is only a fallback for the BIOS GRUB install (a loop device, if
`grub-bios-setup`'s image-file mode is refused); otherwise only the Alpine
mirror is needed. The build prints the final size, the sha256 and a per-layer
size breakdown, and writes `isard-test.qcow2.packages.txt` (exact version of
every binary package — the GPL source provenance).

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

## Credentials — PUBLIC TEST VALUES, not a secret

| user | password |
|------|----------|
| `isard` | `pirineus` |

These are the default IsardVDI guest credentials used throughout the codebase
(the engine `upgrade.py` v30 migration, `testing/src/isardvdi_testing/data/domains.json`,
the redaction tests). This is a **public test image**; the password is stored
as a fixed-salt SHA-512 crypt hash so the build stays byte-reproducible. Do not
reuse these anywhere real. Set a desktop's `guest_properties.credentials` to
`isard`/`pirineus` and xrdp authenticates its local PAM account against them.
`root` is locked.

## Size

Absolute priority is size. The image is **Alpine Linux** (musl + busybox +
OpenRC, no systemd, no dbus), `linux-virt` kernel, `linux-firmware-none`, and
only the packages the five jobs above need. The one large unavoidable layer is
Xorg: Alpine's `xorg-server` hard-links `libGL.so.1` → `mesa` → `llvm*-libs`
(~170–220 MiB). A 2D `xterm` over `modesetting`/`xorgxrdp` never creates a GL
context, so the build **disables GLX** (`xorg.conf.d`) and **deletes `libLLVM`
and the gallium DRI drivers** from the image, keeping the small `libGL.so.1`
loader to satisfy the link. Docs/man/locale and KVM-irrelevant kernel modules
are stripped; free space is zero by construction (sparse image) so
`qemu-img convert -c` compresses it away. See `REPORT.md` for the measured
per-layer numbers and the final size/sha256.

## Reproducibility

The Alpine release branch (`v3.24`) **and every top-level package version** are
pinned; `SOURCE_DATE_EPOCH` is fixed; the account password hash uses a fixed
salt; the filesystems are built mount-free (`mke2fs -d`, `mkfs.fat --invariant`)
with fixed UUIDs + ext4 `hash_seed`; GRUB (`grub-mkimage`) and `qemu-img` honour
`SOURCE_DATE_EPOCH`. Two consecutive builds produce an **identical size and
identical file contents** (and identical GPT/ESP/BIOS/superblock); the sha256 is
not yet bit-identical because `mke2fs -d` does not canonicalise ext4 inode-table
allocation (~3.4 KiB varies — see `REPORT.md`). Alpine has no
`snapshot.debian.org`-style time-pinned mirror, so
long-term reproducibility is bounded by the `v3.24` branch moving; the exact
versions built against are recorded in `isard-test.qcow2.packages.txt`.
