package ssh

import (
	"fmt"

	"golang.org/x/crypto/ssh"
)

func CombinedOutput(ssh *ssh.Client, cmd string) ([]byte, error) {
	sess, err := ssh.NewSession()
	if err != nil {
		return nil, fmt.Errorf("create SSH session: %w", err)
	}
	defer sess.Close()

	cmd = `PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin" ` + cmd

	return sess.CombinedOutput(cmd)
}

func WriteFile(ssh *ssh.Client, path string, b []byte) error {
	b, err := CombinedOutput(ssh, fmt.Sprintf(`echo '%s' > %s`, b, path))
	if err != nil {
		return fmt.Errorf("write to file '%s': %w: %s", path, err, b)
	}

	return nil
}

func MkdirAll(ssh *ssh.Client, path string) error {
	if b, err := CombinedOutput(ssh, fmt.Sprintf("mkdir -p %s", path)); err != nil {
		return fmt.Errorf("create directory '%s': %w: %s", path, err, b)
	}

	return nil
}
