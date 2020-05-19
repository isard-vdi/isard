package proto

func GetXmlRequestDesktopTypeString(t GetXmlRequest_DesktopType) string {
	switch t {
	case GetXmlRequest_DESKTOP_TYPE_KVM:
		return "kvm"

	default:
		return "unknown"
	}
}

func GetXmlRequestDesktopOSTypeArchString(t GetXmlRequest_DesktopOS_DesktopOSType_Arch) string {
	switch t {
	case GetXmlRequest_DesktopOS_DesktopOSType_DESKTOP_OS_TYPE_ARCH_X86_64:
		return "x86_64"

	default:
		return "unknown"
	}
}

func GetXmlRequestDesktopOSTypeMachineString(t GetXmlRequest_DesktopOS_DesktopOSType_Machine) string {
	switch t {
	case GetXmlRequest_DesktopOS_DesktopOSType_DESKTOP_OS_TYPE_MACHINE_PC:
		return "pc"

	case GetXmlRequest_DesktopOS_DesktopOSType_DESKTOP_OS_TYPE_MACHINE_Q35:
		return "q35"

	default:
		return "unknown"
	}
}

func GetXmlRequestDesktopOSTypeTypeString(t GetXmlRequest_DesktopOS_DesktopOSType_Type) string {
	switch t {
	case GetXmlRequest_DesktopOS_DesktopOSType_DESKTOP_OS_TYPE_TYPE_HVM:
		return "hvm"

	default:
		return "unknown"
	}
}
func GetXmlRequestDesktopDeviceInputTypeString(t GetXmlRequest_DesktopDevices_DesktopDeviceInput_DesktopDeviceInputType) string {
	switch t {
	case GetXmlRequest_DesktopDevices_DesktopDeviceInput_DESKTOP_DEVICE_INPUT_TYPE_KEYBOARD:
		return "keyboard"

	default:
		return "unknown"
	}
}

func GetXmlRequestDesktopDeviceInputBusString(t GetXmlRequest_DesktopDevices_DesktopDeviceInput_DesktopDeviceInputBus) string {
	switch t {
	case GetXmlRequest_DesktopDevices_DesktopDeviceInput_DESKTOP_DEVICE_INPUT_BUS_PS2:
		return "ps2"

	default:
		return "unknown"
	}
}

func GetXmlRequestDesktopDeviceVideoModelTypeString(t GetXmlRequest_DesktopDevices_DesktopDeviceVideo_DesktopDeviceVideoModel_DesktopDeviceVideoModelType) string {
	switch t {
	case GetXmlRequest_DesktopDevices_DesktopDeviceVideo_DesktopDeviceVideoModel_DESKTOP_DEVICE_VIDEO_MODEL_TYPE_QXL:
		return "qxl"

	default:
		return "unknown"
	}
}

func GetXmlRequestDesktopDeviceGraphicTypeString(t GetXmlRequest_DesktopDevices_DesktopDeviceGraphic_DesktopDeviceGraphicType) string {
	switch t {
	case GetXmlRequest_DesktopDevices_DesktopDeviceGraphic_DESKTOP_DEVICE_GRAPHIC_TYPE_SPICE:
		return "spice"

	default:
		return "unknown"
	}
}
