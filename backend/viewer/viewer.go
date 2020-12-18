package viewer

import (
	"fmt"
)

func GenerateVirtViewer() string {
	return fmt.Sprintf(`[virt-viewer]
type=%s
host=%s
tls-port=%s
password=%s
title=%s

delete-this-file=1
enable-usbredir=1
enable-usb-autoshare=1
secure-channels=main;display;inputs;cursor;playback;record;usbredir

tls-ciphers=HIGH
`)
}
