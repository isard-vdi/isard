// Mirrors `validate_ssh_public_key` in apiv4: a known key type, a base64 blob, an optional comment.
export const SSH_KEY_RE = /^(ssh-ed25519|ssh-rsa|ssh-dss|ecdsa-sha2-nistp(256|384|521)|sk-ssh-ed25519@openssh\.com|sk-ecdsa-sha2-nistp256@openssh\.com)\s+[A-Za-z0-9+/]+={0,3}(\s+\S.*)?$/

// 1-based numbers of the lines with an invalid key; blank lines and keys in `stored` pass.
export const invalidAuthorizedKeyLines = (text, stored = []) => {
  const known = stored.map(key => (key || '').trim())
  return (text || '').split(/\r?\n/).reduce((lines, line, index) => {
    const key = line.trim()
    if (key && !known.includes(key) && !SSH_KEY_RE.test(key)) {
      lines.push(index + 1)
    }
    return lines
  }, [])
}
