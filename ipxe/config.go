package isardipxe

import (
	"io/ioutil"
	"os"

	"gopkg.in/yaml.v2"
)

// config is the struct that contains all the configuration parameters
type config struct {
	BaseURL string `yaml:"base_url"`
}

// createInitialConfig creates the configuration file and populates it with the default values
func createInitialConfig() error {
	c := &config{
		BaseURL: "https://isard.domain.com",
	}

	d, err := yaml.Marshal(c)
	if err != nil {
		return err
	}

	err = ioutil.WriteFile("config.yml", d, 0644)
	if err != nil {
		return err
	}

	return nil
}

// ReadConfig reads the configuration
func (c *config) ReadConfig() error {
	if _, err := os.Stat("config.yml"); os.IsNotExist(err) {
		if err = createInitialConfig(); err != nil {
			return err
		}
	}

	yamlFile, err := ioutil.ReadFile("config.yml")
	if err != nil {
		return err
	}

	err = yaml.Unmarshal(yamlFile, c)
	if err != nil {
		return err
	}

	return nil
}
