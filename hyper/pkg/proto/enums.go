package proto

func DesktopStartRequestDesktopTypeString(t DesktopStartRequest_DesktopType) string {
	switch t {
	case DesktopStartRequest_DESKTOP_TYPE_KVM:
		return "kvm"

	default:
		return "unknown"
	}
}

func DesktopStartRequestDesktopOSTypeArchString(t DesktopStartRequest_DesktopOS_DesktopOSType_Arch) string {
	switch t {
	case DesktopStartRequest_DesktopOS_DesktopOSType_DESKTOP_OS_TYPE_ARCH_X86_64:
		return "x86_64"

	default:
		return "unknown"
	}
}

func DesktopStartRequestDesktopOSTypeMachineString(t DesktopStartRequest_DesktopOS_DesktopOSType_Machine) string {
	switch t {
	case DesktopStartRequest_DesktopOS_DesktopOSType_DESKTOP_OS_TYPE_MACHINE_PC_i44FX_4_2:
		return "pc_i44FX_4.2"

	default:
		return "unknown"
	}
}

func DesktopStartRequestDesktopOSTypeTypeString(t DesktopStartRequest_DesktopOS_DesktopOSType_Type) string {
	switch t {
	case DesktopStartRequest_DesktopOS_DesktopOSType_DESKTOP_OS_TYPE_TYPE_HVM:
		return "x86_64"

	default:
		return "unknown"
	}
}
func DesktopStartRequestDesktopDeviceInputTypeString(t DesktopStartRequest_DesktopDevices_DesktopDeviceInput_DesktopDeviceInputType) string {
	switch t {
	case DesktopStartRequest_DesktopDevices_DesktopDeviceInput_DESKTOP_DEVICE_INPUT_TYPE_KEYBOARD:
		return "keyboard"

	default:
		return "unknown"
	}
}

func DesktopStartRequestDesktopDeviceInputBusString(t DesktopStartRequest_DesktopDevices_DesktopDeviceInput_DesktopDeviceInputBus) string {
	switch t {
	case DesktopStartRequest_DesktopDevices_DesktopDeviceInput_DESKTOP_DEVICE_INPUT_BUS_PS2:
		return "ps2"

	default:
		return "unknown"
	}
}

func DesktopStartRequestDesktopDeviceVideoModelTypeString(t DesktopStartRequest_DesktopDevices_DesktopDeviceVideo_DesktopDeviceVideoModel_DesktopDeviceVideoModelType) string {
	switch t {
	case DesktopStartRequest_DesktopDevices_DesktopDeviceVideo_DesktopDeviceVideoModel_DESKTOP_DEVICE_VIDEO_MODEL_TYPE_QXL:
		return "qxl"

	default:
		return "unknown"
	}
}