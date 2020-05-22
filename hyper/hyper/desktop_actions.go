package hyper

import (
	"context"
	"fmt"

	"github.com/isard-vdi/isard/hyper/pkg/proto"

	libvirt "github.com/libvirt/libvirt-go"
)

func (d *Hyper) DesktopStart(ctx context.Context, xml string, password string) (string, error) {
	conn, err := libvirt.NewConnect("qemu:///system")
	if err != nil {
		return "", fmt.Errorf("libvirt connection failed")
	}
	defer conn.Close()

	domain, err := conn.DomainCreateXML(xml, libvirt.DOMAIN_NONE)
	if err != nil {
		return "", fmt.Errorf("libvirt DomainCreateXML failed")
	}
	defer domain.Free()

	xml, err = domain.GetXMLDesc(libvirt.DOMAIN_XML_SECURE)
	if err != nil {
		return "", fmt.Errorf("libvirt DomainCreateXML failed")
	}
	return xml, nil
}

func (d *Hyper) DesktopStartPaused(ctx context.Context, xml string, password string) (bool, error) {
	conn, err := libvirt.NewConnect("qemu:///system")
	if err != nil {
		return false, fmt.Errorf("libvirt connection failed")
	}
	defer conn.Close()

	domain, err := conn.DomainCreateXML(xml, libvirt.DOMAIN_START_PAUSED)
	if err != nil {
		return false, fmt.Errorf("libvirt DomainCreateXML paused failed")
	}
	defer domain.Free()
	if err != nil {
		return false, fmt.Errorf("libvirt DomainCreateXML paused failed")
	}
	err = domain.Destroy()

	return true, nil
}

func (d *Hyper) DesktopStop(ctx context.Context, id string) (bool, error) {
	conn, err := libvirt.NewConnect("qemu:///system")
	if err != nil {
		return false, fmt.Errorf("libvirt connection failed")
	}
	defer conn.Close()

	domain, err := conn.LookupDomainByName(id)
	if err != nil {
		return false, fmt.Errorf("domain not started")
	}
	defer domain.Free()
	return true, nil
}

func (d *Hyper) DesktopList(ctx context.Context) (proto.DesktopListResponse, error) {

	domainslist, err := conn.ListAllDomains(libvirt.CONNECT_LIST_DOMAINS_RUNNING)
	if err != nil {

		return nil, fmt.Errorf("libvirt connection failed")
	}

	return proto.DesktopListResponse{domains}, nil
	//defer domains.Free()
	var domains = []proto.DesktopListResponse{}
	//fmt.Printf("%d running domains:\n", len(doms))
	for _, dom := range domainslist {
		name, err := dom.GetName()
		if err == nil {
			append(domains, name)
		}
		dom.Free()
	}
	return domains, nil
}

func (d *Hyper) DesktopXMLGet(ctx context.Context, id string) (string, error) {
	conn, err := libvirt.NewConnect("qemu:///system")
	if err != nil {
		return "", fmt.Errorf("libvirt connection failed")
	}
	defer conn.Close()

	domain, err := conn.LookupDomainByName(id)
	if err != nil {
		return "", fmt.Errorf("domain not started")
	}
	defer domain.Free()
	xml, err := domain.GetXMLDesc(libvirt.DOMAIN_XML_SECURE)
	return xml, nil
}
