package haproxysync

import (
	"os"
	"path/filepath"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// regularFile checks the certificate path before it is written, so the write itself has to
// refuse a symlink that appears in between.
func TestCertificateFilesAreNeverOpenedThroughASymlink(t *testing.T) {
	dir := t.TempDir()
	outside := filepath.Join(dir, "outside")
	require.NoError(t, os.WriteFile(outside, []byte("keep me"), 0o600))
	link := filepath.Join(dir, "brand.example.com.pem")
	require.NoError(t, os.Symlink(outside, link))

	assert.Error(t, writeFileNoFollow(link, []byte("certificate")))
	_, err := readFileNoFollow(link)
	assert.Error(t, err)

	content, err := os.ReadFile(outside)
	require.NoError(t, err)
	assert.Equal(t, "keep me", string(content))
}

func TestCertificateFilesAreWrittenPrivate(t *testing.T) {
	p := filepath.Join(t.TempDir(), "brand.example.com.pem")

	require.NoError(t, writeFileNoFollow(p, []byte("certificate")))

	fi, err := os.Stat(p)
	require.NoError(t, err)
	assert.Equal(t, os.FileMode(0o600), fi.Mode().Perm())
	content, err := readFileNoFollow(p)
	require.NoError(t, err)
	assert.Equal(t, "certificate", string(content))
}
