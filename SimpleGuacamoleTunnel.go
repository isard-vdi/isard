package guac

import (
	guid "github.com/satori/go.uuid"
)

// SimpleGuacamoleTunnel ==> AbstractGuacamoleTunnel
// * GuacamoleTunnel implementation which uses a provided socket. The UUID of
// * the tunnel will be randomly generated.
type SimpleGuacamoleTunnel struct {
	AbstractGuacamoleTunnel

	/**
	 * The UUID associated with this tunnel. Every tunnel must have a
	 * corresponding UUID such that tunnel read/write requests can be
	 * directed to the proper tunnel.
	 */
	uuid guid.UUID

	/**
	 * The GuacamoleSocket that tunnel should use for communication on
	 * behalf of the connecting user.
	 */
	socket GuacamoleSocket
}

// NewSimpleGuacamoleTunnel Construct function
func NewSimpleGuacamoleTunnel(socket GuacamoleSocket) (ret GuacamoleTunnel) {
	one := SimpleGuacamoleTunnel{
		uuid:   guid.NewV4(),
		socket: socket,
	}
	one.AbstractGuacamoleTunnel = NewAbstractGuacamoleTunnel(&one)
	ret = &one
	return
}

// GetUUID override GuacamoleTunnel.GetUUID
func (opt *SimpleGuacamoleTunnel) GetUUID() guid.UUID {
	return opt.uuid
}

// GetSocket override GuacamoleTunnel.GetSocket
func (opt *SimpleGuacamoleTunnel) GetSocket() GuacamoleSocket {
	return opt.socket
}
