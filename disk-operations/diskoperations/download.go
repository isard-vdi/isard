package desktopbuilder

import (
	"bytes"
	"context"
	"fmt"

	"github.com/isard-vdi/isard/disk-operations/pkg/proto"

	"io"
	"net/http"
	"os"
	"strings"

	"github.com/dustin/go-humanize"
)

func (d *DiskOperations) Donwload(ctx context.Context, DownloadFile(filepath string, url string) error {
	// Create the file, but give it a tmp file extension, this means we won't overwrite a
	// file until it's downloaded, but we'll remove the tmp extension once downloaded.

	//_, err = os.Stat(req.Source)
	//if os.IsNotExist(err) {
	//	return &proto.MoveDiskResponse{Result: false}, status.Error(codes.Unimplemented, err.Error())
	//}

	dir, _ := path.Split(filepath)
	if _, err := os.Stat(dir); os.IsNotExist(err) {
		os.Mkdir(dir, os.ModePerm)
	}

	out, err := os.Create(filepath + ".tmp")
	if err != nil {
		return err
	}

	// Get the data
	resp, err := http.Get(url)
	if err != nil {
		out.Close()
		return err
	}
	defer resp.Body.Close()

	// Create our progress reporter and pass it to be used alongside our writer
	counter := &WriteCounter{}
	if _, err = io.Copy(out, io.TeeReader(resp.Body, counter)); err != nil {
		out.Close()
		return err
	}

	// The progress use the same line so print a new line once it's finished downloading
	fmt.Print("\n")

	// Close the file without defer so it can happen before Rename()
	out.Close()

	if err = os.Rename(filepath+".tmp", filepath); err != nil {
		return err
	}
	return nil
}

