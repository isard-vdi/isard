package downloads

import (
	"bytes"
	"io/ioutil"
	"net/http"
	"net/http/httptest"
	"net/url"
	"os"
	"testing"
)

func TestDownloadFile(t *testing.T) {
	t.Run("should download the file correctly", func(t *testing.T) {
		quote := []byte(` Freedom, morality, and the human dignity of the individual consists precisely in this; that he does good not because he is forced to do so, but because he freely conceives it, wants it, and loves it.

Mikhail Bakunin `)

		ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			if err := ioutil.WriteFile("test.txt", quote, 0644); err != nil {
				t.Fatalf("error preparing the test: %v", err)
			}

			http.ServeFile(w, r, "test.txt")
		}))
		defer ts.Close()

		if err := downloadFile(ts.URL, "netboot.ipxe"); err != nil {
			t.Errorf("unexpected error: %v", err)
		}

		f, err := ioutil.ReadFile("netboot.ipxe")
		if err != nil {
			t.Fatalf("error during the test: %v", err)
		}

		if !bytes.Equal(quote, f) {
			t.Errorf("expecting %s, but got %s", quote, f)
		}

		if err := os.Remove("test.txt"); err != nil {
			t.Fatalf("error finishing the test: %v", err)
		}
	})

	t.Run("should fail if there's an error creating a file", func(t *testing.T) {
		initialFolder, err := os.Getwd()
		if err != nil {
			t.Fatalf("error preparing the test %v", err)
		}

		err = os.Chdir("/")
		if err != nil {
			t.Fatalf("error preparing the test %v", err)
		}

		expectedErr := "error downloading netboot.ipxe: error creating the file: open netboot.ipxe: permission denied"

		if err := downloadFile("https://builds.isardvdi.com/i386/latest/netboot.ipxe", "netboot.ipxe"); err.Error() != expectedErr {
			t.Errorf("expecting %s, but got %s", expectedErr, err)
		}

		if err := os.Chdir(initialFolder); err != nil {
			t.Fatalf("error finishing the test: %v", err)
		}
	})

	t.Run("should fail if there's an error downloading the file", func(t *testing.T) {
		ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			w.WriteHeader(http.StatusInternalServerError)
		}))
		defer ts.Close()

		expectedErr := "error downloading netboot.ipxe: HTTP Code 500"

		if err := downloadFile(ts.URL, "netboot.ipxe"); err.Error() != expectedErr {
			t.Errorf("expecting %s, but got %v", expectedErr, err)
		}
	})

	t.Run("should fail if there's an error calling the server", func(t *testing.T) {
		expectedErr := `error downloading netboot.ipxe: Get : unsupported protocol scheme ""`

		if err := downloadFile("", "netboot.ipxe"); err.Error() != expectedErr {
			t.Errorf("expecting %s, but got %v", expectedErr, err)
		}
	})

	if err := os.Remove("netboot.ipxe"); err != nil {
		t.Fatalf("error finishing the test: %v", err)
	}

}

func TestJoinURL(t *testing.T) {
	t.Run("should return the path joined", func(t *testing.T) {
		expectedURL := "https://builds.isardvdi.com/x86_64/latest/initrd"

		u, err := url.Parse("https://builds.isardvdi.com/")
		if err != nil {
			t.Fatalf("error preparing the test: %v", err)
		}

		if rsp := joinURL(*u, "x86_64", "latest", "initrd"); rsp != expectedURL {
			t.Errorf("expecting %s, but got %v", expectedURL, rsp)
		}
	})
}
