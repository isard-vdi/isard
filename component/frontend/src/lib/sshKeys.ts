// Mirrors `validate_ssh_public_key` in apiv4: a known key type, a base64 blob, an optional comment.
export const SSH_KEY_RE =
  /^(ssh-ed25519|ssh-rsa|ssh-dss|ecdsa-sha2-nistp(256|384|521)|sk-ssh-ed25519@openssh\.com|sk-ecdsa-sha2-nistp256@openssh\.com)\s+[A-Za-z0-9+/]+={0,3}(\s+\S.*)?$/

// SSH_KEY_RE's trailing comment would swallow a second key pasted on the same line.
const SSH_KEY_TYPE_RE =
  /(?:^|\s)(?:ssh-ed25519|ssh-rsa|ssh-dss|ecdsa-sha2-nistp(?:256|384|521)|sk-ssh-ed25519@openssh\.com|sk-ecdsa-sha2-nistp256@openssh\.com)\s/g

export const countKeyTypes = (value: string) => (` ${value} `.match(SSH_KEY_TYPE_RE) || []).length

export const isValidSshPublicKey = (value: string) => {
  const key = value.trim()
  return SSH_KEY_RE.test(key) && countKeyTypes(key) === 1
}

/** 1-based numbers of the lines with an invalid key; blank lines and stored keys pass. */
export const invalidAuthorizedKeyLines = (text: string, storedText = ''): number[] => {
  const stored = new Set(storedText.split('\n').map((line) => line.trim()))
  return text.split('\n').flatMap((line, index) => {
    const key = line.trim()
    return !key || stored.has(key) || isValidSshPublicKey(key) ? [] : [index + 1]
  })
}
