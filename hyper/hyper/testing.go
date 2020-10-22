package hyper

import (
	"fmt"
	"io/ioutil"
	"math/rand"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"libvirt.org/libvirt-go"
)

func init() {
}

// TestLibvirtDriver returns the URI connection for libvirt using the test driver and the defaults located at `testdata/test_default_conn.xml`
func TestLibvirtDriver(t *testing.T) string {
	xmlPath, err := filepath.Abs("testdata/test_default_conn.xml")
	if err != nil {
		t.Errorf("get xml path: %v", err)
		return ""
	}

	return fmt.Sprintf("test://%s", xmlPath)
}

// TestMinDesktopXML returns the XML of a desktop with the minimum attributes to start. You can also specify the domain type
func TestMinDesktopXML(t *testing.T, domTypes ...string) string {
	var domType string
	if len(domTypes) == 0 {
		domType = "test"
	} else {
		domType = domTypes[0]
	}

	minDesktop, err := ioutil.ReadFile("testdata/min_desktop.xml")
	if err != nil {
		t.Errorf("get minimum domain XML definition: %v", err)
		return ""
	}

	rand.Seed(time.Now().UnixNano())
	name := fmt.Sprintf("isard-test-desktop-%d", rand.Intn(9999))

	return fmt.Sprintf(string(minDesktop), domType, name)
}

// TestDesktopsCleanup removes all the desktops that have been created for testing Isard in the qemu:///system libvirt daemon (used for functions not supported by the test driver)
func TestDesktopsCleanup(t *testing.T) {
	conn, err := libvirt.NewConnect("qemu:///system")
	if err != nil {
		t.Errorf("connect to libvirt: %v", err)
		return
	}

	desktops, err := conn.ListAllDomains(libvirt.CONNECT_LIST_DOMAINS_ACTIVE | libvirt.CONNECT_LIST_DOMAINS_INACTIVE)
	if err != nil {
		t.Errorf("list all domains: %v", err)
		return
	}

	for _, desktop := range desktops {
		name, err := desktop.GetName()
		if err != nil {
			t.Errorf("get desktop name: %v", err)
			return
		}

		if strings.HasPrefix(name, "isard-test-") {
			if err := desktop.Destroy(); err != nil {
				t.Errorf("destroy desktop: %v", err)
				return
			}
		}
	}
}
