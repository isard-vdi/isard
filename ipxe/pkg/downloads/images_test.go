package downloads_test

import (
	"fmt"
	"io/ioutil"
	"net/http"
	"net/http/httptest"
	"os"
	"path"
	"testing"

	"github.com/isard-vdi/isard-ipxe/pkg/downloads"
)

func TestCreateImagesDirectories(t *testing.T) {
	t.Run("should create all the directories", func(t *testing.T) {
		if err := downloads.CreateImagesDirectories(); err != nil {
			t.Errorf("unexpected error: %v", err)
		}

		if _, err := os.Stat("images"); err != nil {
			t.Errorf("unexpected error: %v", err)
		}

		if _, err := os.Stat("images/i386"); err != nil {
			t.Errorf("unexpected error: %v", err)
		}

		if _, err := os.Stat("images/x86_64"); err != nil {
			t.Errorf("unexpected error: %v", err)
		}

		if err := os.RemoveAll("images"); err != nil {
			t.Fatalf("error finishing the test: %v", err)
		}
	})

	t.Run("should fail if there's an error creating the directories", func(t *testing.T) {
		initialFolder, err := os.Getwd()
		if err != nil {
			t.Fatalf("error preparing the test %v", err)
		}

		err = os.Chdir("/")
		if err != nil {
			t.Fatalf("error preparing the test %v", err)
		}

		expectedErr := "error creating the images directories: mkdir images: permission denied"

		if err := downloads.CreateImagesDirectories(); err.Error() != expectedErr {
			t.Errorf("expecting %s, but got %s", expectedErr, err)
		}

		if err := os.Chdir(initialFolder); err != nil {
			t.Fatalf("error finishing the test: %v", err)
		}
	})
}

func TestDownloadImages(t *testing.T) {
	t.Run("should download all the files correctly", func(t *testing.T) {
		quote := []byte(`If voting changed anything, they'd make it illegal.

Emma Goldman`)

		sha256sum := []byte(`caa5991958576cadc3da74c38c9fbdf78ae103d2def3065a318da6498044ec8b *vmlinuz
caa5991958576cadc3da74c38c9fbdf78ae103d2def3065a318da6498044ec8b *initrd
caa5991958576cadc3da74c38c9fbdf78ae103d2def3065a318da6498044ec8b *netboot.ipxe`)

		if err := ioutil.WriteFile("test.txt", quote, 0644); err != nil {
			t.Fatalf("error preparing the test: %v", err)
		}

		if err := ioutil.WriteFile("sha256sum.txt", sha256sum, 0644); err != nil {
			t.Fatalf("error preparing the test: %v", err)
		}

		ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			if path.Base(r.URL.String()) == "sha256sum.txt" {
				http.ServeFile(w, r, "sha256sum.txt")
				return
			}

			http.ServeFile(w, r, "test.txt")
		}))

		cfg := []byte(fmt.Sprintf("builds_url: %s", ts.URL))

		if err := ioutil.WriteFile("config.yml", cfg, 0644); err != nil {
			t.Fatalf("error preparing the test: %v", err)
		}

		if err := downloads.CreateImagesDirectories(); err != nil {
			t.Fatalf("error preparing the test: %v", err)
		}

		if err := downloads.DownloadImages(); err != nil {
			t.Errorf("unexpected error: %v", err)
		}

		if err := os.RemoveAll("images"); err != nil {
			t.Fatalf("error finishing the test: %v", err)
		}

		if err := os.Remove("config.yml"); err != nil {
			t.Fatalf("error finishing the test: %v", err)
		}

		if err := os.Remove("sha256sum.txt"); err != nil {
			t.Fatalf("error finishing the test: %v", err)
		}

		if err := os.Remove("test.txt"); err != nil {
			t.Fatalf("error finishing the test: %v", err)
		}
	})

	t.Run("should fail if there's an error reading the configuration", func(t *testing.T) {
		initialFolder, err := os.Getwd()
		if err != nil {
			t.Fatalf("error preparing the test %v", err)
		}

		err = os.Chdir("/")
		if err != nil {
			t.Fatalf("error preparing the test %v", err)
		}

		expectedErr := "error reading the configuration file: open config.yml: permission denied"

		if err := downloads.DownloadImages(); err.Error() != expectedErr {
			t.Errorf("expecting %s, but got %s", expectedErr, err)
		}

		if err := os.Chdir(initialFolder); err != nil {
			t.Fatalf("error finishing the test: %v", err)
		}
	})

	t.Run("should fail if there's an error parsing the URL from the configuration", func(t *testing.T) {
		cfg := []byte("builds_url: f&#(*&(&#^%*&$^%&#Y))")

		if err := ioutil.WriteFile("config.yml", cfg, 0644); err != nil {
			t.Fatalf("error preparing the test: %v", err)
		}

		expectedErr := `error parsing the builds URL: parse f&#(*&(&#^%*&$^%&#Y)): invalid URL escape "%*&"`

		if err := downloads.DownloadImages(); err.Error() != expectedErr {
			t.Errorf("expecting %s, but got %s", expectedErr, err)
		}

		if err := os.Remove("config.yml"); err != nil {
			t.Fatalf("error finishing the test: %v", err)
		}
	})

	t.Run("should fail if there's an error downloading a file", func(t *testing.T) {
		ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			http.ServeFile(w, r, "test.txt")
		}))

		cfg := []byte(fmt.Sprintf("builds_url: %s", ts.URL))

		if err := ioutil.WriteFile("config.yml", cfg, 0644); err != nil {
			t.Fatalf("error preparing the test: %v", err)
		}

		if err := downloads.CreateImagesDirectories(); err != nil {
			t.Fatalf("error preparing the test: %v", err)
		}

		expectedErr := "error downloading images/x86_64/sha256sum.txt: HTTP Code 404"

		if err := downloads.DownloadImages(); err.Error() != expectedErr {
			t.Errorf("expecting %s, but got %v", expectedErr, err)
		}

		if err := os.RemoveAll("images"); err != nil {
			t.Fatalf("error finishing the test: %v", err)
		}

		if err := os.Remove("config.yml"); err != nil {
			t.Fatalf("error finishing the test: %v", err)
		}
	})

	t.Run("should fail if there's a SHA256 sum doesn't match", func(t *testing.T) {
		quote := []byte(`If voting changed anything, they'd make it illegal.

Emma Goldman`)

		sha256sum := []byte(`0000000000000000000000000000000000000000000000000000000000000000 *vmlinuz
0000000000000000000000000000000000000000000000000000000000000000 *initrd
0000000000000000000000000000000000000000000000000000000000000000 *netboot.ipxe`)

		if err := ioutil.WriteFile("test.txt", quote, 0644); err != nil {
			t.Fatalf("error preparing the test: %v", err)
		}

		if err := ioutil.WriteFile("sha256sum.txt", sha256sum, 0644); err != nil {
			t.Fatalf("error preparing the test: %v", err)
		}

		ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			if path.Base(r.URL.String()) == "sha256sum.txt" {
				http.ServeFile(w, r, "sha256sum.txt")
				return
			}

			http.ServeFile(w, r, "test.txt")
		}))

		cfg := []byte(fmt.Sprintf("builds_url: %s", ts.URL))

		if err := ioutil.WriteFile("config.yml", cfg, 0644); err != nil {
			t.Fatalf("error preparing the test: %v", err)
		}

		if err := downloads.CreateImagesDirectories(); err != nil {
			t.Fatalf("error preparing the test: %v", err)
		}

		expectedErr := "error checking the SHA256 in the sha256sum: vmlinuz: the signatures don't match"

		if err := downloads.DownloadImages(); err.Error() != expectedErr {
			t.Errorf("expecting %s, but got %v", expectedErr, err)
		}

		if err := os.RemoveAll("images"); err != nil {
			t.Fatalf("error finishing the test: %v", err)
		}

		if err := os.Remove("config.yml"); err != nil {
			t.Fatalf("error finishing the test: %v", err)
		}

		if err := os.Remove("sha256sum.txt"); err != nil {
			t.Fatalf("error finishing the test: %v", err)
		}

		if err := os.Remove("test.txt"); err != nil {
			t.Fatalf("error finishing the test: %v", err)
		}
	})
}
