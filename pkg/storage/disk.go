package storage

import "path/filepath"

func DiskPath(basePath, etyUUID, usrUUID, dskUUID string) string {
	return filepath.Join(basePath, etyUUID, usrUUID, dskUUID)
}
