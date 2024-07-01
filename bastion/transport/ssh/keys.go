package ssh

import (
	"crypto/rand"
	"crypto/rsa"
	"encoding/pem"
	"errors"
	"fmt"
	"os"
	"path/filepath"

	"golang.org/x/crypto/ssh"
)

func initKey(path string, size int) (ssh.Signer, error) {
	dir := filepath.Dir(path)
	if _, err := os.Stat(dir); err != nil {
		if !errors.Is(err, os.ErrNotExist) {
			return nil, fmt.Errorf("check if the SSH private key directory exists: %w", err)
		}

		if err := os.MkdirAll(dir, 0755); err != nil {
			return nil, fmt.Errorf("create the SSH private key directory: %w", err)
		}
	}

	if _, err := os.Stat(path); err != nil {
		if !errors.Is(err, os.ErrNotExist) {
			return nil, fmt.Errorf("check if the SSH private key exists: %w", err)
		}

		priv, err := rsa.GenerateKey(rand.Reader, size)
		if err != nil {
			return nil, fmt.Errorf("generate SSH private key: %w", err)
		}

		block, err := ssh.MarshalPrivateKey(priv, "")
		if err != nil {
			return nil, fmt.Errorf("marshal SSH private key: %w", err)
		}

		f, err := os.OpenFile(path, os.O_RDWR|os.O_CREATE|os.O_TRUNC, 0600)
		if err != nil {
			return nil, fmt.Errorf("create the SSH private key file: %w", err)
		}
		defer f.Close()

		if err := pem.Encode(f, block); err != nil {
			return nil, fmt.Errorf("write the SSH private key: %w", err)
		}

		sign, err := ssh.NewSignerFromKey(priv)
		if err != nil {
			return nil, fmt.Errorf("create signer from generated SSH private key: %w", err)
		}

		return sign, nil
	}

	b, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("read the SSH private key: %w", err)
	}

	priv, err := ssh.ParsePrivateKey(b)
	if err != nil {
		return nil, fmt.Errorf("parse SSH private key: %w", err)
	}

	return priv, nil
}
