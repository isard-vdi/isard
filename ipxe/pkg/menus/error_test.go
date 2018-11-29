package menus_test

import (
	"testing"

	"github.com/isard-vdi/isard-ipxe/pkg/menus"
)

func TestGenerateError(t *testing.T) {
	expected := `#!ipxe
echo There was an error during tests. If this error persists, contact your IsardVDI administrator.
prompt Press any key to try again
reboot`

	menu, err := menus.GenerateError("during tests")
	if err != nil {
		t.Errorf("unexpected error %v", err)
	}

	if menu != expected {
		t.Errorf("expecting %s, but got %s", expected, menu)
	}
}
