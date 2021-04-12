all: deps gen test build docker

deps:
	npm install --save

gen:
	

test:
	npm run test:unit
	npm run test:e2e

.PHONY: build
build:
	npm run build

docker:


run:
	npm run serve
