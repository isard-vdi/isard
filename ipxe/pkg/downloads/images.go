package downloads

import (
	"fmt"
	"io"
	"io/ioutil"
	"net/http"
	"net/url"
	"os"
	"path"
	"path/filepath"
	"time"

	"github.com/isard-vdi/isard-ipxe/pkg/config"
	"github.com/isard-vdi/isard-ipxe/pkg/crypt"
)

// architectures contains all the architectures supported by Isard iPXE
var architectures = []string{"x86_64", "i386"}

// files contains all the files that are needed to download
var files = []string{"sha256sum.txt", "vmlinuz", "initrd", "netboot.ipxe"}

// client is the client that the downloadFile function is going to use. It's outside the function to facilitate the testing
var client = http.Client{}

// downloadFile downloads a specific file to a specific location
func downloadFile(url, dst string) error {
	f, err := os.Create(dst)
	if err != nil {
		return fmt.Errorf("error downloading %s: error creating the file: %v", dst, err)
	}
	defer f.Close()

	rsp, err := client.Get(url)
	if err != nil {
		return fmt.Errorf("error downloading %s: %v", dst, err)
	}

	if rsp.StatusCode != 200 {
		return fmt.Errorf("error downloading %s: HTTP Code %d", dst, rsp.StatusCode)
	}

	_, err = io.Copy(f, rsp.Body)
	if err != nil {
		return fmt.Errorf("error downloading %s: error copying the file: %v", dst, err)
	}

	return f.Sync()
}

// joinURL joins the arguments with the URL provided and returns the result as string
func joinURL(u url.URL, args ...string) string {
	args = append([]string{u.Path}, args...)
	u.Path = path.Join(args...)

	return u.String()
}

// CreateImagesDirectories creates all the required directories for storing the images
func CreateImagesDirectories() error {
	for _, arch := range architectures {
		if err := os.MkdirAll(filepath.Join("images", arch), 0755); err != nil {
			return fmt.Errorf("error creating the images directories: %v", err)
		}
	}

	return nil
}

// DownloadImages downloads all the images for all the architectures
// TODO: Add GPG check for SHA256 file
func DownloadImages() error {
	config := config.Config{}
	err := config.ReadConfig()
	if err != nil {
		return fmt.Errorf("error reading the configuration file: %v", err)
	}

	u, err := url.Parse(config.BuildsURL)
	if err != nil {
		return fmt.Errorf("error parsing the builds URL: %v", err)
	}

	for _, arch := range architectures {
		var sha256sum string

		for _, f := range files {
			fPath := filepath.Join("images", arch, f)
			if err = downloadFile(joinURL(*u, arch, "latest", f), fPath); err != nil {
				return err
			}

			sha256sumFile := filepath.Join("images", arch, "sha256sum.txt")

			if f == "sha256sum.txt" {
				sums, err := ioutil.ReadFile(sha256sumFile)
				if err != nil {
					return fmt.Errorf("error reading the sha256sum.txt file: %v", err)
				}

				sha256sum = string(sums)

			} else {
				sha256, err := crypt.GetSHA256(fPath)
				if err != nil {
					return err
				}

				if err = crypt.CheckSHA256Sum(sha256sum, f, sha256); err != nil {
					return err
				}
			}
		}
	}

	return ioutil.WriteFile(filepath.Join("images", ".downladed"), []byte(time.Now().String()), 0644)
}
