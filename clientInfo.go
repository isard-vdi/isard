package guac

// ClientInfo *
//  * An abstract representation of Guacamole client information, including all
//  * information required by the Guacamole protocol during the preamble.
type ClientInfo struct {
	/**
	 * The optimal screen width requested by the client, in pixels.
	 */
	optimalScreenWidth int

	/**
	 * The optimal screen height requested by the client, in pixels.
	 */
	optimalScreenHeight int

	/**
	 * The resolution of the optimal dimensions given, in DPI.
	 */
	optimalResolution int

	/**
	 * The list of audio mimetypes reported by the client to be supported.
	 */
	audioMimetypes []string

	/**
	 * The list of video mimetypes reported by the client to be supported.
	 */
	videoMimetypes []string

	/**
	 * The list of image mimetypes reported by the client to be supported.
	 */
	imageMimetypes []string
}

// NewGuacamoleClientInformation Construct function
func NewGuacamoleClientInformation() (ret ClientInfo) {
	ret.optimalScreenWidth = 1024
	ret.optimalScreenHeight = 768
	ret.optimalResolution = 96
	ret.audioMimetypes = make([]string, 0, 1)
	ret.videoMimetypes = make([]string, 0, 1)
	ret.imageMimetypes = make([]string, 0, 1)
	return
}

// GetOptimalScreenWidth Returns the optimal screen width requested by the client, in pixels.
// @return The optimal screen width requested by the client, in pixels.
func (opt *ClientInfo) GetOptimalScreenWidth() int {
	return opt.optimalScreenWidth
}

// SetOptimalScreenWidth Sets the client's optimal screen width.
// * @param optimalScreenWidth The optimal screen width of the client.
func (opt *ClientInfo) SetOptimalScreenWidth(optimalScreenWidth int) {
	opt.optimalScreenWidth = optimalScreenWidth
}

// GetOptimalScreenHeight *
// * Returns the optimal screen height requested by the client, in pixels.
// * @return The optimal screen height requested by the client, in pixels.
func (opt *ClientInfo) GetOptimalScreenHeight() int {
	return opt.optimalScreenHeight
}

// SetOptimalScreenHeight *
//      * Sets the client's optimal screen height.
//      * @param optimalScreenHeight The optimal screen height of the client.
func (opt *ClientInfo) SetOptimalScreenHeight(optimalScreenHeight int) {
	opt.optimalScreenHeight = optimalScreenHeight
}

// GetOptimalResolution *
//  * Returns the resolution of the screen if the optimal width and height are
//  * used, in DPI.
//  *
//  * @return The optimal screen resolution.
func (opt *ClientInfo) GetOptimalResolution() int {
	return opt.optimalResolution
}

// SetOptimalResolution *
//  * Sets the resolution of the screen if the optimal width and height are
//  * used, in DPI.
//  *
//  * @param optimalResolution The optimal screen resolution in DPI.
func (opt *ClientInfo) SetOptimalResolution(optimalResolution int) {
	opt.optimalResolution = optimalResolution
}

// GetAudioMimetypes *
//  * Returns the list of audio mimetypes supported by the client. To add or
//  * removed supported mimetypes, the list returned by this function can be
//  * modified.
//  *
//  * @return The set of audio mimetypes supported by the client.
func (opt *ClientInfo) GetAudioMimetypes() []string {
	return opt.audioMimetypes
}

// GetVideoMimetypes *
//  * Returns the list of video mimetypes supported by the client. To add or
//  * removed supported mimetypes, the list returned by this function can be
//  * modified.
//  *
//  * @return The set of video mimetypes supported by the client.
func (opt *ClientInfo) GetVideoMimetypes() []string {
	return opt.videoMimetypes
}

// GetImageMimetypes *
//  * Returns the list of image mimetypes supported by the client. To add or
//  * removed supported mimetypes, the list returned by this function can be
//  * modified.
//  *
//  * @return
//  *     The set of image mimetypes supported by the client.
func (opt *ClientInfo) GetImageMimetypes() []string {
	return opt.imageMimetypes
}
