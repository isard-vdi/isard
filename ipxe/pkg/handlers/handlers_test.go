package handlers_test

import (
	"bytes"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"testing"

	"github.com/isard-vdi/isard-ipxe/pkg/client/list"
	"github.com/isard-vdi/isard-ipxe/pkg/client/request"
	"github.com/isard-vdi/isard-ipxe/pkg/handlers"
)

// Should work as expected
func TestLoginHandler(t *testing.T) {
	r, err := http.NewRequest("GET", "/pxe/boot/login", nil)
	if err != nil {
		t.Fatalf("error preparing the test: %v", err)
	}

	w := httptest.NewRecorder()

	expected := []byte(`#!ipxe
set username
set password
login
chain https://isard.domain.com/pxe/boot/auth?usr=${username:uristring}&pwd=${password:uristring}`)

	handlers.LoginHandler(w, r)

	if w.Code != http.StatusOK {
		t.Errorf("expecting %d, but got %d", http.StatusOK, w.Code)
	}

	if !bytes.Equal(w.Body.Bytes(), expected) {
		t.Errorf("expecting %s, but got %s", expected, w.Body.Bytes())
	}

	if err := os.Remove("config.yml"); err != nil {
		t.Fatalf("error finishing the test: %v", err)
	}
}

// Should return an error menu
func TestLoginHandlerErr(t *testing.T) {
	initialFolder, err := os.Getwd()
	if err != nil {
		t.Fatalf("error preparing the test %v", err)
	}

	err = os.Chdir("/")
	if err != nil {
		t.Fatalf("error preparing the test %v", err)
	}

	r, err := http.NewRequest("GET", "/pxe/boot/login", nil)
	if err != nil {
		t.Fatalf("error preparing the test: %v", err)
	}

	w := httptest.NewRecorder()

	expected := []byte(`#!ipxe
echo There was an error reading the configuration file. If this error persists, contact your IsardVDI administrator.
prompt Press any key to try again
reboot`)

	handlers.LoginHandler(w, r)

	// Code needs to be 200, since iPXE doesn't boot 500's
	if w.Code != http.StatusOK {
		t.Errorf("expecting %d, but got %d", http.StatusOK, w.Code)
	}

	if !bytes.Equal(w.Body.Bytes(), expected) {
		t.Errorf("expecting %s, but got %s", expected, w.Body.Bytes())
	}

	if err := os.Chdir(initialFolder); err != nil {
		t.Fatalf("error finishing the test: %v", err)
	}
}

type testWebRequestList struct{}

func (testWebRequestList) Get(url string) ([]byte, int, error) {
	return endpointsList[url].Body, endpointsList[url].Code, endpointsList[url].Err
}

func (testWebRequestList) Post(url string, body io.Reader) ([]byte, int, error) {
	return nil, 500, nil
}

var jsonEmptyListList, _ = json.Marshal(&list.VMList{})

var endpointsList = map[string]endpointKeyList{
	"https://isard.domain.com/pxe/list?tkn=ShibAWD6OKjA8950vRIPUEZu848Ke0Rzp3Oxtye_V1c": {
		Body: []byte(`{
					"vms": [
						{
							"id": "_nefix_KDE_Neon_5",
							"name": "KDE Neon 5",
							"description": "This is a VM that's using KDE Neon 5"
						},
						{
							"id": "_nefix_Debian_9",
							"name": "Debian 9",
							"description": "This is a VM that's using Debian 9"
						},
						{
							"id": "_nefix_Arch_Linux",
							"name": "Arch Linux",
							"description": "This is a VM that's using Arch Linux"
						}
					]
				}`),
		Code: 200,
		Err:  nil,
	},
	"https://isard.domain.com/pxe/list?tkn=invalidtoken": {
		Body: jsonEmptyListList,
		Code: 403,
		Err:  nil,
	},
}

type endpointKeyList struct {
	Body []byte
	Code int
	Err  error
}

// Should work as expected
func TestVMListHandler(t *testing.T) {
	handlers.WebRequest = testWebRequestList{}

	r, err := http.NewRequest("GET", "/pxe/boot/list?tkn=ShibAWD6OKjA8950vRIPUEZu848Ke0Rzp3Oxtye_V1c", nil)
	if err != nil {
		t.Fatalf("error preparing the test: %v", err)
	}

	w := httptest.NewRecorder()

	expected := []byte(`#!ipxe
set tkn ShibAWD6OKjA8950vRIPUEZu848Ke0Rzp3Oxtye_V1c
menu IsardVDI - 
item _nefix_KDE_Neon_5 KDE Neon 5 -->
item _nefix_Debian_9 Debian 9 -->
item _nefix_Arch_Linux Arch Linux -->
item
item --gap -- ---- Actions ----
item bootFromDisk Boot from disk -->
item reboot Reboot -->
item poweroff Poweroff -->
choose target && goto ${target}
:_nefix_KDE_Neon_5
chain https://isard.domain.com/pxe/boot/start?tkn=${tkn:uristring}&id=_nefix_KDE_Neon_5
:_nefix_Debian_9
chain https://isard.domain.com/pxe/boot/start?tkn=${tkn:uristring}&id=_nefix_Debian_9
:_nefix_Arch_Linux
chain https://isard.domain.com/pxe/boot/start?tkn=${tkn:uristring}&id=_nefix_Arch_Linux
:bootFromDisk
sanboot --no-describe --drive 0x80
:reboot
reboot
:poweroff
poweroff`)

	handlers.VMListHandler(w, r)

	if w.Code != http.StatusOK {
		t.Errorf("expecting %d, but got %d", http.StatusOK, w.Code)
	}

	if !bytes.Equal(w.Body.Bytes(), expected) {
		t.Errorf("expecting %s, but got %s", expected, w.Body.Bytes())
	}

	if err := os.Remove("config.yml"); err != nil {
		t.Fatalf("error finishing the test: %v", err)
	}
}

// Should return a login menu
func TestVMListHandlerErrAuth(t *testing.T) {
	handlers.WebRequest = testWebRequestList{}

	r, err := http.NewRequest("GET", "/pxe/boot/list?tkn=invalidtoken", nil)
	if err != nil {
		t.Fatalf("error preparing the test: %v", err)
	}

	w := httptest.NewRecorder()

	expected := []byte(`#!ipxe
set username
set password
login
chain https://isard.domain.com/pxe/boot/auth?usr=${username:uristring}&pwd=${password:uristring}`)

	handlers.VMListHandler(w, r)

	if w.Code != http.StatusForbidden {
		t.Errorf("expecting %d, but got %d", http.StatusForbidden, w.Code)
	}

	if !bytes.Equal(w.Body.Bytes(), expected) {
		t.Errorf("expecting %s, but got %s", expected, w.Body.Bytes())
	}

	if err := os.Remove("config.yml"); err != nil {
		t.Fatalf("error finishing the test: %v", err)
	}
}

// Should return an error menu
func TestVMListHandlerErr(t *testing.T) {
	handlers.WebRequest = request.Request{}

	r, err := http.NewRequest("GET", "/pxe/boot/list", nil)
	if err != nil {
		t.Fatalf("error preparing the test: %v", err)
	}

	w := httptest.NewRecorder()

	expected := []byte(`#!ipxe
echo There was an error calling the API. If this error persists, contact your IsardVDI administrator.
prompt Press any key to try again
reboot`)

	handlers.VMListHandler(w, r)

	// Code needs to be 200, since iPXE doesn't boot 500's
	if w.Code != http.StatusOK {
		t.Errorf("expecting %d, but got %d", http.StatusOK, w.Code)
	}

	if !bytes.Equal(w.Body.Bytes(), expected) {
		t.Errorf("expecting %s, but got %s", expected, w.Body.Bytes())
	}

	if err := os.Remove("config.yml"); err != nil {
		t.Fatalf("error finishing the test: %v", err)
	}
}
