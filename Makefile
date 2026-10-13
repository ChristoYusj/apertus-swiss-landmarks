# Forwarder: the project lives in track_1b/ (Hack Apertus template). `make run` works from here too.
.PHONY: run build verify live smoke test shell clean
run build verify live smoke test shell clean:
	$(MAKE) -C track_1b $@
