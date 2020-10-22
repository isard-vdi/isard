package hyper

import (
	"os"
)

// Restore restores a saved desktop to its original running state, continuing the execution where it was left
func (h *Hyper) Restore(path string) error {
	_, err := os.Stat(path)
	if err != nil {
		return err
	}

	return h.conn.DomainRestore(path)
}
