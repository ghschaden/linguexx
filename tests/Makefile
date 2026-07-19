# Makefile for the linguexx test suite
#
# Runs the smoke-test files (linguexx-test.tex, linguexx-test-gb4e.tex)
# under pdflatex, xelatex and lualatex, producing one PDF per
# test/engine pair: linguexx-test-pdflatex.pdf, linguexx-test-xelatex.pdf,
# linguexx-test-lualatex.pdf, and the same for the gb4e test.
#
# Targets:
#   make            build everything (two passes per PDF, for the refs)
#   make pdflatex   only the two PDFs for one engine (same for the others)
#   make clean      remove auxiliary files
#   make distclean  remove auxiliary files and the PDFs
#
# Each run uses -jobname, so every test/engine pair has its own .aux and
# .log; engines never step on each other's auxiliary files.  Compilation
# output is discarded (-halt-on-error makes failures stop make); on
# failure, consult the corresponding <test>-<engine>.log.

ENGINES := pdflatex xelatex lualatex
TESTS   := linguexx-test linguexx-test-gb4e

export TEXINPUTS := ..:$(TEXINPUTS)
LATEXFLAGS := -interaction=nonstopmode -halt-on-error

PDFS := $(foreach e,$(ENGINES),$(foreach t,$(TESTS),$(t)-$(e).pdf))

all: $(PDFS)
	@echo "All $(words $(PDFS)) test PDFs built successfully."

# one engine only: make pdflatex / make xelatex / make lualatex
$(ENGINES): %: $(foreach t,$(TESTS),$(t)-%.pdf)
	@echo "$@: OK"

# --- build rules, one pattern rule per engine ------------------------------
# Two passes: the battery contains \label/\ref (and \sublabel writes to
# the .aux), so cross-references need a second run to resolve.

%-pdflatex.pdf: %.tex ../linguexx.sty
	@pdflatex $(LATEXFLAGS) -jobname=$*-pdflatex $< > /dev/null
	@pdflatex $(LATEXFLAGS) -jobname=$*-pdflatex $< > /dev/null
	@echo "OK  $@"

%-xelatex.pdf: %.tex ../linguexx.sty
	@xelatex $(LATEXFLAGS) -jobname=$*-xelatex $< > /dev/null
	@xelatex $(LATEXFLAGS) -jobname=$*-xelatex $< > /dev/null
	@echo "OK  $@"

%-lualatex.pdf: %.tex ../linguexx.sty
	@lualatex $(LATEXFLAGS) -jobname=$*-lualatex $< > /dev/null
	@lualatex $(LATEXFLAGS) -jobname=$*-lualatex $< > /dev/null
	@echo "OK  $@"

# --- housekeeping -----------------------------------------------------------
AUXEXTS := aux log out toc nav snm vrb

clean:
	@rm -f $(foreach p,$(basename $(PDFS)),$(foreach x,$(AUXEXTS),$(p).$(x)))
	@echo "auxiliary files removed"

distclean: clean
	@rm -f $(PDFS)
	@echo "PDFs removed"

.PHONY: all clean distclean $(ENGINES)
