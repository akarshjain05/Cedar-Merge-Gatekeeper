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
	@echo "After 'make deploy', note the PolicyStoreId output, then:"
	@echo "  aws verifiedpermissions put-schema --policy-store-id <id> --definition '{\"cedarJson\":\"...\"}'"
	@echo "  aws verifiedpermissions create-policy --policy-store-id <id> --definition '{\"static\":{\"statement\":\"...\"}}'"
	@echo "Exact JSON shapes: check current AWS CLI docs -- this is the one area worth double-checking against the live docs before typing it in front of a judge."
