# linguexx: the things that are done to the package as a whole.
#
# The test suite has its own Makefile in tests/ (the smoke-test battery);
# this one is about the package: check it, test it, build the manual, and
# assemble the CTAN upload.
#
#   make check     the version strings agree everywhere they are stated
#   make test      the regression suite, all three engines, documents too
#   make manual    rebuild linguexx-doc.pdf in place (lualatex only)
#   make ctan      build dist/linguexx.zip, and prove it installs
#   make ctan-tds  ... and linguexx.tds.zip beside it
#   make clean     remove dist/ and the manual's auxiliary files
#
# `make ctan` runs `make check` and `make test` itself -- the release does
# not depend on anyone having remembered to.  It never bumps a version,
# writes a tag or uploads anything; see tools/ctan.py.

PYTHON ?= python3

.PHONY: all check test manual ctan ctan-tds clean

all: check test

check:
	@$(PYTHON) tools/ctan.py --check

test:
	@$(PYTHON) tests/runtests.py --documents

# In place, and lualatex only: the manual documents (and contains) the
# dot-below transliterations that pdflatex gives a broken text layer, and
# refuses to build under it for that reason.  Three passes for the
# cross-references and the table of contents.  The copy that goes INTO the
# archive is not this one -- tools/ctan.py rebuilds it in a directory of
# its own, so that a committed PDF older than the .sty cannot be shipped.
manual:
	@lualatex -interaction=nonstopmode -halt-on-error linguexx-doc.tex >/dev/null
	@lualatex -interaction=nonstopmode -halt-on-error linguexx-doc.tex >/dev/null
	@lualatex -interaction=nonstopmode -halt-on-error linguexx-doc.tex >/dev/null
	@echo "OK  linguexx-doc.pdf"

ctan:
	@$(PYTHON) tools/ctan.py

ctan-tds:
	@$(PYTHON) tools/ctan.py --tds

clean:
	@rm -rf dist
	@rm -f linguexx-doc.aux linguexx-doc.log linguexx-doc.out linguexx-doc.toc
	@echo "dist/ and the manual's auxiliary files removed"
