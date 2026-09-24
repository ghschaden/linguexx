# linguexx: the things that are done to the package as a whole.
#
# The test suite has its own Makefile in tests/ (the smoke-test battery);
# this one is about the package: check it, test it, build the manual, and
# assemble the CTAN upload.
#
#   make check     the version strings agree everywhere they are stated
#   make lint      ruff over the Python that checks the package
#   make test      the regression suite, all three engines, documents too
#   make manual    rebuild linguexx-doc.pdf in place (lualatex only)
#   make ctan      build dist/linguexx.zip, and prove it installs
#   make ctan-tds  ... and linguexx.tds.zip beside it
#   make clean     remove dist/ and the manual's auxiliary files
#   make hooks     use the repository's git hooks (the revert check)
#
# `make ctan` runs `make check` and `make test` itself -- the release does
# not depend on anyone having remembered to.  It never bumps a version,
# writes a tag or uploads anything; see tools/ctan.py.

PYTHON ?= python3

.PHONY: all check lint test manual ctan ctan-tds clean hooks

all: check test

check:
	@$(PYTHON) tools/ctan.py --check

# The Python that checks the package -- the suite, tools/, the harness in
# .claude/.  Configured in ruff.toml, which says what is selected and why.
# Deliberately NOT part of `all` or of `make ctan`: ruff is not needed to
# build or release linguexx, and a release that cannot be cut on a machine
# without it would be a worse trade than an unlinted afternoon.  It is also
# why this target says so when ruff is missing instead of failing.
#
# One shell, not two lines: make gives each recipe line its own, so an
# `exit 0` on the first does not stop the second and the absent-ruff path
# fell through to a 127 from the real invocation.
lint:
	@if command -v ruff >/dev/null 2>&1; then \
	  ruff check . && echo "OK  ruff"; \
	else \
	  echo "ruff is not installed; skipping (see ruff.toml)"; \
	fi

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

# Point git at the hooks the repository keeps, in tools/hooks, rather than
# the unversioned .git/hooks.  Local to this clone; `git config --unset
# core.hooksPath` undoes it.
hooks:
	@git config core.hooksPath tools/hooks
	@echo "OK  git hooks from tools/hooks (the revert check: tools/revert_check.py)"

clean:
	@rm -rf dist
	@rm -f linguexx-doc.aux linguexx-doc.log linguexx-doc.out linguexx-doc.toc
	@echo "dist/ and the manual's auxiliary files removed"
