VERSION := 3.0.0-rc0
export VERSION

MICROSERVICES = common hyper desktopbuilder orchestrator controller

all: tidy gen test build docker
.PHONY: all

tidy:
	go mod tidy

gen: tidy
	$(foreach micorservice,$(MICROSERVICES),$(MAKE) -C $(micorservice) gen;)

test: gen
	$(foreach micorservice,$(MICROSERVICES),$(MAKE) -C $(micorservice) test;)

build: test
	$(foreach micorservice,$(MICROSERVICES),$(MAKE) -C $(micorservice) build;)

docker: build
	$(foreach micorservice,$(MICROSERVICES),$(MAKE) -C $(micorservice) docker;)
