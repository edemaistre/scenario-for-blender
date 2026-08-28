BLENDER ?= /Applications/Blender.app/Contents/MacOS/Blender

.PHONY: test test-blender build install
test:
	python3 -m pytest
test-blender:
	$(BLENDER) --background --python-exit-code 1 --python tests/blender/run_all.py
build:
	./tools/build.sh
install:
	./tools/install_dev.sh
