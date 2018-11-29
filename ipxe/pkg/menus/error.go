package menus

import "bytes"

// GenerateError generates a menu with an error
func GenerateError(msg string) (string, error) {
	buf := new(bytes.Buffer)

	t := parseTemplate("error.ipxe")
	err := t.Execute(buf, menuTemplateData{
		Err: msg,
	})

	return buf.String(), err
}
