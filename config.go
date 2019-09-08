package guac

const serialVersionUID = 1

// Config *
//  * All information necessary to complete the initial protocol handshake of a
//  * Guacamole session.
type Config struct {
	/**
	 * The ID of the connection being joined. If this value is present,
	 * the protocol need not be specified.
	 */
	connectionID string

	/**
	 * The name of the protocol associated with this configuration.
	 */
	protocol string

	/**
	 * Map of all associated parameter values, indexed by parameter name.
	 */
	parameters map[string]string
}

// NewGuacamoleConfiguration Construct funtion
func NewGuacamoleConfiguration() (ret Config) {
	ret.parameters = make(map[string]string)
	return
}

/*GetConnectionID *
 * Returns the ID of the connection being joined, if any. If no connection
 * is being joined, this returns null, and the protocol must be set.
 *
 * @return The ID of the connection being joined, or null if no connection
 *         is being joined.
 */
func (opt *Config) GetConnectionID() string {
	return opt.connectionID
}

/*SetConnectionID *
 * Sets the ID of the connection being joined, if any. If no connection
 * is being joined, this value must be omitted, and the protocol must be
 * set instead.
 *
 * @param connectionID The ID of the connection being joined.
 */
func (opt *Config) SetConnectionID(connectionID string) {
	opt.connectionID = connectionID
}

/*GetProtocol *
 * Returns the name of the protocol to be used.
 * @return The name of the protocol to be used.
 */
func (opt *Config) GetProtocol() string {
	return opt.protocol
}

/*SetProtocol *
 * Sets the name of the protocol to be used.
 * @param protocol The name of the protocol to be used.
 */
func (opt *Config) SetProtocol(protocol string) {
	opt.protocol = protocol
}

/*GetParameter *
 * Returns the value set for the parameter with the given name, if any.
 * @param name The name of the parameter to return the value for.
 * @return The value of the parameter with the given name, or null if
 *         that parameter has not been set.
 */
func (opt *Config) GetParameter(name string) string {
	return opt.parameters[name]
}

/*SetParameter *
 * Sets the value for the parameter with the given name.
 *
 * @param name The name of the parameter to set the value for.
 * @param value The value to set for the parameter with the given name.
 */
func (opt *Config) SetParameter(name string, value string) {
	opt.parameters[name] = value
}

/*UnsetParameter *
 * Removes the value set for the parameter with the given name.
 *
 * @param name The name of the parameter to remove the value of.
 */
func (opt *Config) UnsetParameter(name string) {
	delete(opt.parameters, name)
}

/*GetParameterNames *
 * Returns a set of all currently defined parameter names. Each name
 * corresponds to a parameter that has a value set on this
 * Config via setParameter().
 *
 * @return A set of all currently defined parameter names.
 */
func (opt *Config) GetParameterNames() (ret []string) {
	ret = make([]string, 0, len(opt.parameters))
	for k := range opt.parameters {
		ret = append(ret, k)
	}
	return
}

/*GetParameters *
 * Returns a map which contains parameter name/value pairs as key/value
 * pairs. Changes to this map will affect the parameters stored within
 * this configuration.
 *
 * @return
 *     A map which contains all parameter name/value pairs as key/value
 *     pairs.
 */
func (opt *Config) GetParameters() map[string]string {
	return opt.parameters
}

/*SetParameters *
 * Replaces all current parameters with the parameters defined within the
 * given map. Key/value pairs within the map represent parameter name/value
 * pairs.
 *
 * @param parameters
 *     A map which contains all parameter name/value pairs as key/value
 *     pairs.
 */
func (opt *Config) SetParameters(parameters map[string]string) {
	opt.parameters = make(map[string]string)
	for k, v := range parameters {
		opt.SetParameter(k, v)
	}
}
