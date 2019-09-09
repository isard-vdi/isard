package guac

type ClientInfo struct {
	OptimalScreenWidth  int
	OptimalScreenHeight int
	OptimalResolution   int
	AudioMimetypes      []string
	VideoMimetypes      []string
	ImageMimetypes      []string
}

// NewGuacamoleClientInformation Construct function
func NewGuacamoleClientInformation() *ClientInfo {
	return &ClientInfo{
		OptimalScreenWidth:  1024,
		OptimalScreenHeight: 768,
		OptimalResolution:   96,
		AudioMimetypes:      make([]string, 0, 1),
		VideoMimetypes:      make([]string, 0, 1),
		ImageMimetypes:      make([]string, 0, 1),
	}
}
