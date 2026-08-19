SHELL := /bin/bash
.DEFAULT_GOAL := help
TF_MODULE ?= terraform
COMPOSE   ?= docker compose

help: ## show targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-18s\033[0m %s\n",$$1,$$2}'

up: ## start the full stack against a real tenant (needs .env)
	@test -f .env || { echo ".env missing - cp .env.example .env and fill in PRISMACLOUD_*"; exit 1; }
	$(COMPOSE) up -d --build

demo: ## start the stack with synthetic data (no Prisma tenant needed)
	TF_MODULE=terraform-mock TENANT_LABEL=demo-tenant $(COMPOSE) up -d --build

alloy: ## same as up, but ship logs with Grafana Alloy instead of Promtail
	$(COMPOSE) --profile alloy up -d --build alloy
	$(COMPOSE) stop promtail

down: ## stop everything (keeps volumes)
	$(COMPOSE) --profile alloy down

clean: down ## stop and delete volumes + generated reports
	$(COMPOSE) --profile alloy down -v
	rm -rf reports/*.json reports/*.jsonl reports/derived reports/.runner

logs: ## tail the runner + scraper
	$(COMPOSE) logs -f --tail=100 terraform-runner metrics-scraper

run-once: ## one Terraform apply of $(TF_MODULE) on the host, files land in ./reports
	cd $(TF_MODULE) && terraform init -input=false >/dev/null && terraform apply -auto-approve -input=false -parallelism=3

scrape: ## run the metrics scraper once on the host and print the metrics
	python3 scraper/metrics_scraper.py --reports-dir reports --once

fixtures: ## seed ./reports with fixture data (run=1|2) without Terraform:  make fixtures RUN=2
	python3 scraper/tests/fixtures.py --out reports --run $(or $(RUN),1)

dashboards: ## regenerate grafana/dashboards/*.json from grafana/build_dashboards.py
	python3 grafana/build_dashboards.py

validate: ## static checks: terraform validate (both modules), promtool, compose config, scraper tests, dashboards in sync
	@set -e; for m in terraform terraform-mock; do \
	  echo "== terraform validate ($$m)"; \
	  (cd $$m && terraform init -backend=false -input=false >/dev/null && terraform fmt -recursive >/dev/null && terraform validate); \
	done
	@echo "== promtool"; promtool check config prometheus/prometheus.yml && promtool check rules prometheus/rules/prisma_rules.yml
	@echo "== compose"; $(COMPOSE) config -q
	@echo "== scraper tests"; python3 -m unittest discover -s scraper/tests -q
	@echo "== dashboards"; python3 grafana/build_dashboards.py --check
	@echo "== promtail"; docker run --rm -v $(PWD)/promtail:/cfg:ro grafana/promtail:3.6.11 -config.file=/cfg/promtail-config.yml -check-syntax
	@echo "== loki"; docker run --rm -v $(PWD)/loki:/cfg:ro grafana/loki:3.7.6 -config.file=/cfg/loki-config.yml -verify-config=true
	@echo "== alloy"; docker run --rm -v $(PWD)/alloy:/cfg:ro grafana/alloy:v1.18.1 fmt /cfg/config.alloy >/dev/null

test: ## scraper unit tests
	python3 -m unittest discover -s scraper/tests -v

.PHONY: help up demo alloy down clean logs run-once scrape fixtures dashboards validate test
