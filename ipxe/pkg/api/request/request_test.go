package request_test

import (
	"bytes"
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"os/exec"
	"reflect"
	"testing"

	"github.com/isard-vdi/isard-ipxe/pkg/api/request"
)

func prepareCerts() error {
	if err := os.Mkdir("certs", 0755); err != nil {
		return err
	}

	cmd1 := exec.Command("openssl", "genrsa", "-des3", "-passout", "pass:qwerty", "-out", "certs/ca.key", "512")
	cmd2 := exec.Command("openssl", "rsa", "-passin", "pass:qwerty", "-in", "certs/ca.key", "-out", "certs/ca.key")
	// The file is written to cert/server-cert.pem to avoid having to create a configuration file
	cmd3 := exec.Command("openssl", "req", "-x509", "-new", "-nodes", "-key", "certs/ca.key", "-sha256", "-days", "1", "-out", "certs/server-cert.pem", "-subj", "/CN=isard.domain.com")

	if err := cmd1.Run(); err != nil {
		return err
	}

	if err := cmd2.Run(); err != nil {
		return err
	}

	if err := cmd3.Run(); err != nil {
		return err
	}

	return nil
}

func TestGet(t *testing.T) {
	t.Run("should work as expected", func(t *testing.T) {
		if err := prepareCerts(); err != nil {
			t.Fatalf("error creating the certificates: %v", err)
		}

		request := request.Request{}

		ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			w.Header().Set("Content-Type", "application/json")
			fmt.Fprint(w, "{}")
		}))
		defer ts.Close()

		expectedCode := 200
		expectedRsp := []byte("{}")

		rsp, code, err := request.Get(ts.URL)
		if err != nil {
			t.Errorf("unexpected error: %v", err)
		}

		if code != expectedCode {
			t.Errorf("expecting code %d, but got %d", expectedCode, code)
		}

		if !reflect.DeepEqual(rsp, expectedRsp) {
			t.Errorf("expecting %v, but got %v", expectedRsp, rsp)
		}

		if err := os.RemoveAll("./certs"); err != nil {
			t.Fatalf("error finishing the test: %v", err)
		}
	})

	t.Run("should return an error when creating the HTTP Client", func(t *testing.T) {
		request := request.Request{}

		var expectedRsp []byte = nil
		expectedCode := 0
		expectedErr := "open ./certs/server-cert.pem: no such file or directory"

		rsp, code, err := request.Get("https://isard.domain.com")
		if err.Error() != expectedErr {
			t.Errorf("expecting %v, but got %v", expectedErr, err)
		}

		if code != expectedCode {
			t.Errorf("expecting %d, but got %d", expectedCode, code)
		}

		if !reflect.DeepEqual(rsp, expectedRsp) {
			t.Errorf("expecting %v, but got %v", expectedRsp, rsp)
		}
	})

	t.Run("should return an error when using http.Get", func(t *testing.T) {
		if err := prepareCerts(); err != nil {
			t.Fatalf("error creating the certificates: %v", err)
		}

		request := request.Request{}

		var expectedRsp []byte = nil
		expectedCode := 0
		expectedErr := `Get : unsupported protocol scheme ""`

		rsp, code, err := request.Get("")
		if err.Error() != expectedErr {
			t.Errorf("expecting %v, but got %v", expectedErr, err)
		}

		if code != expectedCode {
			t.Errorf("expecting %d, but got %d", expectedCode, code)
		}

		if !reflect.DeepEqual(rsp, expectedRsp) {
			t.Errorf("expecting %v, but got %v", expectedRsp, rsp)
		}

		if err := os.RemoveAll("./certs"); err != nil {
			t.Fatalf("error finishing the test: %v", err)
		}
	})

	// Clean the generated configuration file
	err := os.Remove("config.yml")
	if err != nil {
		t.Fatalf("error finishing the tests: %v", err)
	}
}

func TestPost(t *testing.T) {
	t.Run("should work as expected", func(t *testing.T) {
		if err := prepareCerts(); err != nil {
			t.Fatalf("error creating the certificates: %v", err)
		}

		request := request.Request{}

		ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			w.Header().Set("Content-Type", "application/json")
			fmt.Fprint(w, "{}")
		}))
		defer ts.Close()

		expectedCode := 200
		expectedRsp := []byte("{}")

		rsp, code, err := request.Post(ts.URL, bytes.NewReader([]byte("{}")))
		if err != nil {
			t.Errorf("unexpected error: %v", err)
		}

		if code != expectedCode {
			t.Errorf("expecting code %d, but got %d", expectedCode, code)
		}

		if !reflect.DeepEqual(rsp, expectedRsp) {
			t.Errorf("expecting %v, but got %v", expectedRsp, rsp)
		}

		if err := os.RemoveAll("./certs"); err != nil {
			t.Fatalf("error finishing the test: %v", err)
		}
	})

	t.Run("should return an error when creating the HTTP Client", func(t *testing.T) {
		request := request.Request{}

		var expectedRsp []byte = nil
		expectedCode := 0
		expectedErr := "open ./certs/server-cert.pem: no such file or directory"

		rsp, code, err := request.Post("https://isard.domain.com", bytes.NewReader([]byte("{}")))
		if err.Error() != expectedErr {
			t.Errorf("expecting %v, but got %v", expectedErr, err)
		}

		if code != expectedCode {
			t.Errorf("expecting %d, but got %d", expectedCode, code)
		}

		if !reflect.DeepEqual(rsp, expectedRsp) {
			t.Errorf("expecting %v, but got %v", expectedRsp, rsp)
		}
	})

	t.Run("should return an error when using http.Post", func(t *testing.T) {
		if err := prepareCerts(); err != nil {
			t.Fatalf("error creating the certificates: %v", err)
		}

		request := request.Request{}

		var expectedRsp []byte = nil
		expectedCode := 0
		expectedErr := `Post : unsupported protocol scheme ""`

		rsp, code, err := request.Post("", bytes.NewReader([]byte("{}")))
		if err.Error() != expectedErr {
			t.Errorf("expecting %v, but got %v", expectedErr, err)
		}

		if code != expectedCode {
			t.Errorf("expecting %d, but got %d", expectedCode, code)
		}

		if !reflect.DeepEqual(rsp, expectedRsp) {
			t.Errorf("expecting %v, but got %v", expectedRsp, rsp)
		}

		if err := os.RemoveAll("./certs"); err != nil {
			t.Fatalf("error finishing the test: %v", err)
		}
	})

	// Clean the generated configuration file
	err := os.Remove("config.yml")
	if err != nil {
		t.Fatalf("error finishing the tests: %v", err)
	}
}
