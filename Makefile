.PHONY: lint typecheck test check-handler-purity ci

lint:
	ruff check src/

typecheck:
	mypy src/sdd/

test:
	pytest tests/ -q

# I-CI-PURITY-1: exits 0 when no violations found in handle() bodies.
# I-CI-PURITY-2: whitelist is exactly validate_invariants.py and report_error.py.
# I-CI-PURITY-3: enforces I-KERNEL-WRITE-1, I-KERNEL-PROJECT-1, I-HANDLER-PURE-1.
#
# Uses Python AST to scope checks to handle() method bodies only, so calls to
# EventStore / rebuild_state / .handle() in CLI main() or kernel code are not flagged.
define PURITY_CHECK_SCRIPT
import ast, pathlib, re, sys

WHITELIST = {
    "src/sdd/commands/validate_invariants.py",
    "src/sdd/commands/report_error.py",
}

PATTERNS = [
    (re.compile(r"EventStore.*\.append"), "I-KERNEL-WRITE-1"),
    (re.compile(r"\brebuild_state\("), "I-KERNEL-PROJECT-1"),
    (re.compile(r"\.handle\("), "I-HANDLER-PURE-1"),
]


def violations(text):
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    lines = text.splitlines()
    found = []

    class V(ast.NodeVisitor):
        def visit_FunctionDef(self, node):
            if node.name == "handle":
                for stmt in node.body:
                    for ln in range(stmt.lineno - 1,
                                   getattr(stmt, "end_lineno", stmt.lineno)):
                        if ln >= len(lines):
                            continue
                        for pat, inv in PATTERNS:
                            if pat.search(lines[ln]):
                                found.append((ln + 1, inv, lines[ln].rstrip()))
            self.generic_visit(node)

    V().visit(tree)
    return found


fail = 0
for path in sorted(pathlib.Path("src/sdd/commands").glob("*.py")):
    rel = str(path)
    if rel in WHITELIST:
        continue
    viols = violations(path.read_text(encoding="utf-8"))
    for lineno, inv, line in viols:
        print(f"FAIL [{rel}:{lineno}] {inv}: {line}", file=sys.stderr)
        fail = 1

if not fail:
    print("OK: handler purity check passed")
sys.exit(fail)
endef

check-handler-purity:
	$(file > /tmp/._sdd_purity.py,$(PURITY_CHECK_SCRIPT))
	@python3 /tmp/._sdd_purity.py; rc=$$?; rm -f /tmp/._sdd_purity.py; exit $$rc

ci: lint typecheck test check-handler-purity
