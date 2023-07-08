package director

import (
	_ "embed"
	"encoding/json"
)

var chamaleonGPUProfiles []*chamaleonEngineGPU

type chamaleonEngineGPU struct {
	Brand    string
	Model    string
	Profiles []*chamaleonEngineGPUProfile
}

type chamaleonEngineGPUProfile struct {
	Profile string
	Units   int
	Memory  int
}

//go:embed chamaleon_gpu_profiles.json
var chamaleonGPUProfilesB []byte

func init() {
	if err := json.Unmarshal(chamaleonGPUProfilesB, &chamaleonGPUProfiles); err != nil {
		panic(err)
	}
}
