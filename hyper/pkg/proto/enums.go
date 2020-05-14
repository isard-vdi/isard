package proto

func DesktopStartRequestDesktopTypeString(t DesktopStartRequest_DesktopType) string {
	switch t {
	case DesktopStartRequest_DESKTOP_TYPE_KVM:
		return "kvm"

	default:
		return "unknown"
	}
}
