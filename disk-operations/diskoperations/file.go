package diskoperations

// import (
// 	"context"
// 	"fmt"
// 	"io"
// 	"net/http"

// 	"github.com/spf13/afero"
// )

// func (d *DiskOperations) FileUpload(src io.Reader, dst string) error {
// 	f, err := afero.TempFile(d.env.FS, "", "diskoperations")
// 	if err != nil {
// 		return fmt.Errorf("create file: %w", err)
// 	}

// 	if _, err := io.Copy(f, src); err != nil {
// 		d.env.FS.Remove(f.Name())

// 		f.Close()
// 		return fmt.Errorf("set file content: %w", err)
// 	}
// 	f.Close()

// 	if err := d.env.FS.Rename(f.Name(), dst); err != nil {
// 		d.env.FS.Remove(f.Name())

// 		return fmt.Errorf("move file: %w", err)
// 	}

// 	return nil
// }

// func (d *DiskOperations) FileDownload(ctx context.Context, url, dst string) error {
// 	req, err := http.NewRequest(http.MethodGet, url, nil)
// 	if err != nil {
// 		return fmt.Errorf("create http request: %w", err)
// 	}

// 	req = req.WithContext(ctx)
// 	rsp, err := http.DefaultClient.Do(req)
// 	if err != nil {
// 		return fmt.Errorf("get the file: %w", err)
// 	}
// 	defer rsp.Body.Close()

// 	if rsp.StatusCode != http.StatusOK || rsp.StatusCode != http.StatusMovedPermanently || rsp.StatusCode != http.StatusFound {
// 		return fmt.Errorf("get the file: http code: %d", rsp.StatusCode)
// 	}

// 	if err := d.FileUpload(rsp.Body, dst); err != nil {
// 		return fmt.Errorf("download the file: %w", err)
// 	}

// 	return nil
// }
