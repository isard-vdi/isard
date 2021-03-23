//go:generate stringer -type=BootType -trimprefix=BootType

package model

type BootType int

const (
	BootTypeUnknown BootType = iota
	BootTypeDisk
	BootTypePXE
)
