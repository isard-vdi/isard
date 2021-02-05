package model

type Desktop struct {
	ID   string `json:"id,omitempty"`
	Name string `json:"name,omitempty"`
	Description string `json:"description,omitempty"`
	State string `json:"state,omitempty"`
	Type string `json:"type,omitempty"`
	Template string `json:"template,omitempty"`
	Viewers []string `json:"viewers,omitempty"`
	Icon string `json:"icon,omitempty"`
	Image string `json:"image,omitempty"`
}
