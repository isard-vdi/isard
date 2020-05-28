VERSION=2.0.0

all: docker

docker:
	for microservice in hyper hyper-stats orchestrator disk-operations desktop-builder; do \
		cd $$microservice && make docker VERSION=$(VERSION) ; \
		cd - ; \
	done
