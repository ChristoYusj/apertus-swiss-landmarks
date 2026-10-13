# Hack Apertus 2026 - Track 1B - Swiss heritage factuality benchmark
# Judges: `make run` (Docker). Offline verification always runs and sets the exit code;
# a live evaluation of LLM_NAME/LLM_BASE_URL/LLM_API_KEY runs on a seeded sample when they are set.
IMAGE  ?= apertus-swiss-landmarks
SAMPLE ?= 150
FULL   ?= 0
DOCKER ?= docker
HFVOL  := -v landmarks-hf-cache:/root/.cache/huggingface
ENVS   := -e LLM_NAME -e LLM_BASE_URL -e LLM_API_KEY -e LLM_CONCURRENCY \
          -e JUDGE_MODEL -e JUDGE_BASE_URL -e JUDGE_API_KEY -e LANDMARKS_DATASET
RESULTS := $(CURDIR)/results

.PHONY: run build verify live smoke test shell clean report

run: build verify live

build:
	$(DOCKER) build --target runtime -t $(IMAGE) .

verify: build
	$(DOCKER) run --rm $(HFVOL) -e LANDMARKS_DATASET $(IMAGE) verify

live: build
	@if [ -n "$$LLM_NAME" ] && [ -n "$$LLM_BASE_URL" ] && [ -n "$$LLM_API_KEY" ]; then \
	  mkdir -p "$(RESULTS)"; \
	  $(DOCKER) run --rm $(HFVOL) $(ENVS) -v "$(RESULTS):/app/results" $(IMAGE) live \
	    $$( [ "$(FULL)" = "1" ] || echo --sample $(SAMPLE) ) || [ "$(STRICT)" != "1" ]; \
	else echo "live run skipped: set LLM_NAME, LLM_BASE_URL and LLM_API_KEY to evaluate a model"; fi

smoke: build
	$(MAKE) live SAMPLE=20

test:
	$(DOCKER) build --target test -t $(IMAGE)-test .
	$(DOCKER) run --rm $(IMAGE)-test

shell: build
	$(DOCKER) run --rm -it $(HFVOL) $(ENVS) --entrypoint bash $(IMAGE)

clean:
	-$(DOCKER) rmi $(IMAGE) $(IMAGE)-test

# Team only (needs pandoc + xelatex locally): the submission PDF from technical_report.md
report:
	pandoc technical_report.md -o RedPandas_Report.pdf --pdf-engine=xelatex -H tools/report_header.tex \
	  -V geometry:margin=2cm -V fontsize=10pt -V mainfont=Calibri -V monofont=Consolas -V colorlinks=true
