package request

import (
	"crypto/tls"
	"crypto/x509"
	"io/ioutil"
	"net/http"
	"os"
	"os/exec"
	"reflect"
	"testing"
)

func prepareCerts() error {
	if err := os.Mkdir("certs", 0755); err != nil {
		return err
	}

	cmd1 := exec.Command("openssl", "genrsa", "-des3", "-passout", "pass:qwerty", "-out", "certs/ca.key", "512")
	cmd2 := exec.Command("openssl", "rsa", "-passin", "pass:qwerty", "-in", "certs/ca.key", "-out", "certs/ca.key")
	cmd3 := exec.Command("openssl", "req", "-x509", "-new", "-nodes", "-key", "certs/ca.key", "-sha256", "-days", "1", "-out", "certs/ca.pem", "-subj", "/CN=isard.domain.com")

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

func TestCreateClient(t *testing.T) {
	t.Run("should work as expected", func(t *testing.T) {
		if err := prepareCerts(); err != nil {
			t.Fatalf("error creating the certificates: %v", err)
		}

		caCert, err := ioutil.ReadFile("certs/ca.pem")
		if err != nil {
			t.Fatalf("error preparing the test: %v", err)
		}

		rootCAs := x509.NewCertPool()
		rootCAs.AppendCertsFromPEM(caCert)

		expectedRsp := &http.Client{
			Transport: &http.Transport{
				TLSClientConfig: &tls.Config{
					RootCAs: rootCAs,
				},
			},
		}

		client, err := createClient()
		if err != nil {
			t.Errorf("unexpected error: %v", err)
		}

		if !reflect.DeepEqual(client, expectedRsp) {
			t.Errorf("expecting %+v, but got %+v", expectedRsp, client)
		}

		if err := os.RemoveAll("./certs"); err != nil {
			t.Fatalf("error finishing the test: %v", err)
		}
	})

	t.Run("there was an error reading the configuration file", func(t *testing.T) {
		initialFolder, err := os.Getwd()
		if err != nil {
			t.Fatalf("error preparing the test %v", err)
		}

		err = os.Chdir("/")
		if err != nil {
			t.Fatalf("error preparing the test %v", err)
		}

		var expectedRsp *http.Client
		expectedErr := "open config.yml: permission denied"

		client, err := createClient()
		if err.Error() != expectedErr {
			t.Errorf("expecting %s, but got %v", expectedErr, err)
		}

		if !reflect.DeepEqual(client, expectedRsp) {
			t.Errorf("expecting %v, but got %v", expectedRsp, client)
		}

		err = os.Chdir(initialFolder)
		if err != nil {
			t.Fatalf("error finishing the test %v", err)
		}
	})

	t.Run("there was an error reading the CA certificate", func(t *testing.T) {
		var expectedRsp *http.Client
		expectedErr := "open ./certs/ca.pem: no such file or directory"

		client, err := createClient()
		if err.Error() != expectedErr {
			t.Errorf("expecting %s, but got %v", expectedErr, err)
		}

		if !reflect.DeepEqual(client, expectedRsp) {
			t.Errorf("expecting %v, but got %v", expectedRsp, client)
		}
	})

	// Clean the generated configuration file
	err := os.Remove("config.yml")
	if err != nil {
		t.Fatalf("error finishing the tests: %v", err)
	}
}
