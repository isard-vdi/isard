/*
 * Copyright (C) 2019 Néfix Estrada <nefixestrada@gmail.com>
 * Author: Néfix Estrada <nefixestrada@gmail.com>
 *
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU Affero General Public License as
 * published by the Free Software Foundation, either version 3 of the
 * License, or (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU Affero General Public License for more details.
 *
 * You should have received a copy of the GNU Affero General Public License
 * along with this program.  If not, see <http://www.gnu.org/licenses/>.
 */

package crypt

import (
	"crypto/sha256"
	"fmt"
	"io"
	"os"
	"strings"
)

// GetSHA256 calculates the SHA256 of a file and returns it
func GetSHA256(src string) (string, error) {
	f, err := os.Open(src)
	if err != nil {
		return "", fmt.Errorf("error checking the SHA256: error reading %s: %v", src, err)
	}
	defer f.Close()

	h := sha256.New()
	if _, err := io.Copy(h, f); err != nil {
		return "", fmt.Errorf("error checking the SHA256: %v", err)
	}

	return fmt.Sprintf("%x", h.Sum(nil)), nil
}

// CheckSHA256Sum checks if the SHA256 is valid. If it does, returns nil. If not, returns an error
func CheckSHA256Sum(sha256sum, f, sha256 string) error {
	s := strings.Split(sha256sum, "\n")
	for _, l := range s {
		if l != "" {
			s := strings.Split(l, " *")

			if len(s) > 1 {
				if s[1] == f {
					if s[0] == sha256 {
						return nil
					}

					return fmt.Errorf("error checking the SHA256 in the sha256sum: %s: the signatures don't match", f)
				}
			}
		}
	}

	return fmt.Errorf("error getting the SHA256 in the sha256sum: %s: not found", f)
}
