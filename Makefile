VERSION := 3.0.0-rc0
export VERSION

MICROSERVICES = common hyper desktopbuilder orchestrator controller backend

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

docker:
	$(foreach micorservice,$(MICROSERVICES),$(MAKE) -C $(micorservice) docker;)

docker-compose-up:
	docker-compose -f ./deployments/docker-compose/docker-compose.yml --project-directory . up -d

docker-compose-down:
	docker-compose -f ./deployments/docker-compose/docker-compose.yml --project-directory . down
