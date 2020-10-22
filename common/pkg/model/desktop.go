//go:generate stringer -type=DesktopTypeEnum -trimprefix=DesktopTypeEnum
//go:generate stringer -type=DesktopOSType -trimprefix=DesktopOSType
//go:generate stringer -type=DesktopFirmwareType -trimprefix=DesktopFirmwareType
//go:generate stringer -type=DesktopBootType -trimprefix=DesktopBootType

package model

import "time"

type Desktop struct {
	ID string

	Type     DesktopTypeEnum
	TypeBIOS *DesktopTypeBIOS

	VCPUs uint `pg:"vcpus"`
	RAM   uint // Size in MB

	ExtraXML string

	CreatedAt time.Time
	UpdatedAt time.Time
	DeletedAt time.Time `pg:",soft_delete"`
}

type DesktopTypeEnum int

const (
	DesktopTypeEnumUnknown DesktopTypeEnum = iota
	DesktopTypeEnumBIOS
)

type DesktopTypeBIOS struct {
	FirmwareType DesktopFirmwareType
	OSType       DesktopOSType
	Arch         string
	Machine      string
	Boot         []DesktopBootType
}

type DesktopOSType int

const (
	DesktopOSTypeUnknown DesktopOSType = iota
	DesktopOSTypeXEN
	DesktopOSTypeXENPVH
	DesktopOSTypeHVM
	DesktopOSTypeEXE
)

type DesktopFirmwareType int

const (
	DesktopFirmwareTypeUnknown DesktopFirmwareType = iota
	DesktopFirmwareTypeBIOS
	DesktopFirmwareTypeEFI
)

type DesktopBootType int

const (
	DesktopBootTypeUnknown DesktopBootType = iota
	DesktopBootTypeFD
	DesktopBootTypeHD
	DesktopBootTypeCDROM
	DesktopBootTypeNetwork
)
