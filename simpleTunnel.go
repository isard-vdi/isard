package guac

import (
	guid "github.com/satori/go.uuid"
)

// SimpleTunnel ==> BaseTunnel
// * Tunnel implementation which uses a provided socket. The UUID of
// * the tunnel will be randomly generated.
type SimpleTunnel struct {
	BaseTunnel

	/**
	 * The UUID associated with this tunnel. Every tunnel must have a
	 * corresponding UUID such that tunnel read/write requests can be
	 * directed to the proper tunnel.
	 */
	uuid guid.UUID

	/**
	 * The Socket that tunnel should use for communication on
	 * behalf of the connecting user.
	 */
	socket Socket
}

// NewSimpleTunnel Construct function
func NewSimpleTunnel(socket Socket) (ret Tunnel) {
	one := SimpleTunnel{
		uuid:   guid.NewV4(),
		socket: socket,
	}
	one.BaseTunnel = NewAbstractTunnel(&one)
	ret = &one
	return
}

// GetUUID override Tunnel.GetUUID
func (opt *SimpleTunnel) GetUUID() guid.UUID {
	return opt.uuid
}

// GetSocket override Tunnel.GetSocket
func (opt *SimpleTunnel) GetSocket() Socket {
	return opt.socket
}
