package menus

import (
	"github.com/GeertJohan/go.rice/embedded"
	"time"
)

func init() {

	// define files
	file2 := &embedded.EmbeddedFile{
		Filename:    "VMList.ipxe",
		FileModTime: time.Unix(1542028311, 0),
		Content:     string("#!ipxe\nset tkn {{.Token}}\nmenu IsardVDI - {{.Username}}{{range .VMs}}\nitem {{.ID}} {{.Name}} -->{{end}}\nitem\nitem --gap -- ---- Actions ----\nitem bootFromDisk Boot from disk -->\nitem reboot Reboot -->\nitem poweroff Poweroff -->\nchoose target && goto ${target}\n{{range .VMs}}:{{.ID}}\nchain {{$.BaseURL}}/pxe/boot/start?tkn=${tkn:uristring}&id={{.ID}}\n{{end}}:bootFromDisk\nsanboot --no-describe --drive 0x80\n:reboot\nreboot\n:poweroff\npoweroff"),
	}
	file3 := &embedded.EmbeddedFile{
		Filename:    "auth.ipxe",
		FileModTime: time.Unix(1542110079, 0),
		Content:     string("#!ipxe\nchain {{.BaseURL}}/pxe/boot/list?tkn={{.Token}}&usr={{.Username}}"),
	}
	file4 := &embedded.EmbeddedFile{
		Filename:    "boot.ipxe",
		FileModTime: time.Unix(1542026171, 0),
		Content:     string("#!ipxe\nkernel {{.BaseURL}}/pxe/vmlinuz tkn={{.Token}} id={{.VMID}} initrd={{.BaseURL}}/pxe/initrd\ninitrd {{.BaseURL}}/pxe/initrd\nboot"),
	}
	file5 := &embedded.EmbeddedFile{
		Filename:    "error.ipxe",
		FileModTime: time.Unix(1542026839, 0),
		Content:     string("#!ipxe\necho There was an error {{.Err}}. If this error persists, contact your IsardVDI administrator.\nprompt Press any key to try again\nreboot"),
	}
	file6 := &embedded.EmbeddedFile{
		Filename:    "errorVM.ipxe",
		FileModTime: time.Unix(1542026844, 0),
		Content:     string("#!ipxe\necho The VM start has failed: {{.Err}}\nprompt Press any key to go back\nchain {{.BaseURL}}/pxe/boot/"),
	}
	file7 := &embedded.EmbeddedFile{
		Filename:    "login.ipxe",
		FileModTime: time.Unix(1542027405, 0),
		Content:     string("#!ipxe\nset username\nset password\nlogin\nchain {{.BaseURL}}/pxe/boot/auth?usr=${username:uristring}&pwd=${password:uristring}"),
	}

	// define dirs
	dir1 := &embedded.EmbeddedDir{
		Filename:   "",
		DirModTime: time.Unix(1542110021, 0),
		ChildFiles: []*embedded.EmbeddedFile{
			file2, // "VMList.ipxe"
			file3, // "auth.ipxe"
			file4, // "boot.ipxe"
			file5, // "error.ipxe"
			file6, // "errorVM.ipxe"
			file7, // "login.ipxe"

		},
	}

	// link ChildDirs
	dir1.ChildDirs = []*embedded.EmbeddedDir{}

	// register embeddedBox
	embedded.RegisterEmbeddedBox(`assets`, &embedded.EmbeddedBox{
		Name: `assets`,
		Time: time.Unix(1542110021, 0),
		Dirs: map[string]*embedded.EmbeddedDir{
			"": dir1,
		},
		Files: map[string]*embedded.EmbeddedFile{
			"VMList.ipxe":  file2,
			"auth.ipxe":    file3,
			"boot.ipxe":    file4,
			"error.ipxe":   file5,
			"errorVM.ipxe": file6,
			"login.ipxe":   file7,
		},
	})
}
