package menus

import "bytes"

// GenerateError generates a menu with an error
func GenerateError(err string) string {
	buf := new(bytes.Buffer)

	t := parseTemplate("error.ipxe")
	t.Execute(buf, menuTemplateData{
		Err: err,
	})

	return buf.String()
}
