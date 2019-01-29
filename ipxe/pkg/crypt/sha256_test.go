package crypt_test

import (
	"io/ioutil"
	"os"
	"testing"

	"github.com/isard-vdi/isard-ipxe/pkg/crypt"
)

func TestGetSHA256(t *testing.T) {
	t.Run("should return the correct SHA256", func(t *testing.T) {
		quote := []byte(`Children do not constitute anyone's property:
they are neither the property of their parents nor even of society.
They belong only to their own future freedom.

Mikhail Bakunin`)
		if err := ioutil.WriteFile("test.txt", quote, 0644); err != nil {
			t.Fatalf("error preparing the test: %v", err)
		}

		expectedSHA256 := "d87897871262bf343c537bb87ae1043d25adab291ec68ae2f8c617219ce34f6d"

		sha256, err := crypt.GetSHA256("test.txt")
		if err != nil {
			t.Errorf("unexpected error: %v", err)
		}

		if sha256 != expectedSHA256 {
			t.Errorf("expecting %s, but got %s", expectedSHA256, sha256)
		}

		if err = os.Remove("test.txt"); err != nil {
			t.Fatalf("error finishing the test: %v", err)
		}
	})

	t.Run("should return an error when failing reading the file", func(t *testing.T) {
		initialFolder, err := os.Getwd()
		if err != nil {
			t.Fatalf("error preparing the test: %v", err)
		}

		if err = os.Chdir("/"); err != nil {
			t.Fatalf("error preparing the test: %v", err)
		}

		expectedSHA256 := ""
		expectedErr := "error checking the SHA256: error reading test.txt: open test.txt: no such file or directory"

		sha256, err := crypt.GetSHA256("test.txt")
		if err.Error() != expectedErr {
			t.Errorf("expecting %s, but got %v", expectedErr, err)
		}

		if sha256 != expectedSHA256 {
			t.Errorf("expecting %s, but got %s", expectedSHA256, sha256)
		}

		if err = os.Chdir(initialFolder); err != nil {
			t.Fatalf("error finishing the test: %v", err)
		}
	})
}

func TestCheckSHA256Sum(t *testing.T) {
	t.Run("should return no error when the check is correct", func(t *testing.T) {
		sha256sum := `d87897871262bf343c537bb87ae1043d25adab291ec68ae2f8c617219ce34f6d *test.txt`

		if err := crypt.CheckSHA256Sum(sha256sum, "test.txt", "d87897871262bf343c537bb87ae1043d25adab291ec68ae2f8c617219ce34f6d"); err != nil {
			t.Errorf("unexpected error: %v", err)
		}
	})

	t.Run("should an error when the SHA256 signatures don't match", func(t *testing.T) {
		sha256sum := `a378f556fca27f0bee2c2444d95e0f22d3c0d560867d5ebc54cc7774a4d1caad *test.txt`

		expectedErr := "error checking the SHA256 in the sha256sum: test.txt: the signatures don't match"

		if err := crypt.CheckSHA256Sum(sha256sum, "test.txt", "d87897871262bf343c537bb87ae1043d25adab291ec68ae2f8c617219ce34f6d"); err.Error() != expectedErr {
			t.Errorf("expecting %s, but got %v", expectedErr, err)
		}
	})

	t.Run("should an error when the file isn't found in the SHA256 sum", func(t *testing.T) {
		expectedErr := "error getting the SHA256 in the sha256sum: test.txt: not found"

		if err := crypt.CheckSHA256Sum("", "test.txt", "d87897871262bf343c537bb87ae1043d25adab291ec68ae2f8c617219ce34f6d"); err.Error() != expectedErr {
			t.Errorf("expecting %s, but got %v", expectedErr, err)
		}
	})
}
