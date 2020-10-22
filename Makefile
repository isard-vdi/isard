VERSION := 3.0.0-rc0
export VERSION

MICROSERVICES = common hyper desktopbuilder orchestrator controller backend

all: tidy gen test build docker
.PHONY: all

tidy:
	go mod tidy

gen: tidy
	$(foreach microservice,$(MICROSERVICES),$(MAKE) -C $(microservice) gen;)

test: gen
	$(foreach microservice,$(MICROSERVICES),$(MAKE) -C $(microservice) test;)

build: test
	$(foreach microservice,$(MICROSERVICES),$(MAKE) -C $(microservice) build;)

docker:
	$(foreach microservice,$(MICROSERVICES),$(MAKE) -C $(microservice) docker;)

docker-compose-up:
	docker-compose -f ./deployments/docker-compose/docker-compose.yml --project-directory . up -d

docker-compose-down:
	docker-compose -f ./deployments/docker-compose/docker-compose.yml --project-directory . down

dev:
	tmux new -s isardvdi-dev -n workspace -d
	$(foreach microservice,$(MICROSERVICES), if [ "$(microservice)" != "common" ]; then tmux neww -e $(shell echo $(microservice) | tr '[:lower:]' '[:upper:]')_DB_USR=dev -e $(shell echo $(microservice) | tr '[:lower:]' '[:upper:]')_DB_PWD=dev -n $(microservice); fi ;)
	$(foreach microservice,$(MICROSERVICES), if [ "$(microservice)" != "common" ]; then tmux send-keys -t "isardvdi-dev:$(microservice)" C-z 'cd isardvdi && $(MAKE) -C $(microservice) run' Enter; fi ;)
	tmux a -t isardvdi-dev:workspace
