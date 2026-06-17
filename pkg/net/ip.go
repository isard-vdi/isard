package net

import (
	"fmt"
	"net"
)

// IsLocalIP returns true if the IP belongs to this server.
func IsLocalIP(ip net.IP) bool {
	if ip.IsLoopback() || ip.IsUnspecified() || ip.IsLinkLocalUnicast() || ip.IsLinkLocalMulticast() {
		return true
	}

	addrs, err := net.InterfaceAddrs()
	if err != nil {
		return false
	}

	for _, addr := range addrs {
		if ipNet, ok := addr.(*net.IPNet); ok && ipNet.IP.Equal(ip) {
			return true
		}
	}

	return false
}

// IsLocalHostname returns true if the hostname belongs to this server.
func IsLocalHostname(hostname string) (bool, error) {
	if ip := net.ParseIP(hostname); ip != nil {
		return IsLocalIP(ip), nil
	}

	// Resolve the hostname and check all resulting IPs
	ips, err := net.LookupIP(hostname)
	if err != nil {
		return false, fmt.Errorf("resolve host %q: %w", hostname, err)
	}

	for _, ip := range ips {
		if IsLocalIP(ip) {
			return true, nil
		}
	}

	return false, nil
}
