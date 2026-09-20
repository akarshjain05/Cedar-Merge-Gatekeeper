.PHONY: build deploy local test load-policies

build:
	sam build

deploy:
	sam deploy --guided

local:
	sam local start-api

test:
	PYTHONPATH=. pytest tests/ -v

load-policies:
	python3 upload_avp.py
