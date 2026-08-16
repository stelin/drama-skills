import ast
import re
import subprocess
import unittest
from pathlib import Path

from tests.private_release_gate import load_private_terms


SUITE = Path(__file__).resolve().parents[1]
SHIPPED_SKILLS = SUITE / "skills"
DASHBOARD_SERVER = SHIPPED_SKILLS / "short-drama/scripts/dashboard_server.py"
RELEASE_TEXT_SUFFIXES = {
    ".ass",
    ".css",
    ".html",
    ".js",
    ".json",
    ".jsonl",
    ".md",
    ".py",
    ".srt",
    ".txt",
    ".yaml",
    ".yml",
}


def shipped_text_files() -> list[Path]:
    return [
        path
        for path in SHIPPED_SKILLS.rglob("*")
        if path.is_file()
        and path.suffix.lower() in RELEASE_TEXT_SUFFIXES
        and "__pycache__" not in path.parts
    ]


def release_facing_text_files() -> list[Path]:
    roots = [SUITE / "skills", SUITE / "maintainers", SUITE / "demo"]
    top_level = [SUITE / "README.md", SUITE / "README_EN.md", SUITE / "CONTRIBUTING.md"]
    nested = [
        path
        for root in roots
        if root.is_dir()
        for path in root.rglob("*")
        if path.is_file()
        and path.suffix.lower() in RELEASE_TEXT_SUFFIXES
        and "__pycache__" not in path.parts
    ]
    return [path for path in top_level if path.is_file()] + nested


def local_forbidden_terms() -> frozenset[str]:
    # Maintainer-specific source vocabulary lives outside the repository so the
    # shipped tree never carries the terms it screens for. One term per line.
    return load_private_terms(Path(__file__).resolve().parent / "local-terms.txt")


class ShippingBoundaryTests(unittest.TestCase):
    def test_maintainer_private_artifacts_are_local_only(self) -> None:
        ignored = (SUITE / ".gitignore").read_text(encoding="utf-8").splitlines()
        self.assertIn("maintainers/evals/", ignored)
        self.assertIn("tests/local-terms.txt", ignored)
        if not (SUITE / ".git").exists():
            return
        tracked = subprocess.run(
            [
                "git",
                "ls-files",
                "--",
                "maintainers/evals",
                "tests/local-terms.txt",
            ],
            cwd=SUITE,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.splitlines()
        self.assertEqual(tracked, [])

    def test_shipped_tree_contains_no_cache_or_binary_artifact(self) -> None:
        forbidden = {".pyc", ".pyo", ".so", ".dylib", ".dll", ".exe"}
        tracked = subprocess.run(
            ["git", "ls-files", "skills"],
            cwd=SUITE,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.splitlines()
        findings = [
            relative
            for relative in tracked
            if "__pycache__" in Path(relative).parts
            or Path(relative).suffix.lower() in forbidden
        ]
        self.assertEqual(findings, [])

    def test_shipped_tree_contains_no_urls(self) -> None:
        url = re.compile(r"https?://[^\s)>\]}`\"']+", re.IGNORECASE)
        leaks: list[str] = []
        for path in shipped_text_files():
            for found in url.findall(path.read_text(encoding="utf-8")):
                leaks.append(f"{path.relative_to(SUITE)}: {found}")
        self.assertEqual(leaks, [], "URLs shipped in skills tree:\n" + "\n".join(leaks))

    def test_shipping_tree_has_no_private_source_or_provider_task_vocabulary(
        self,
    ) -> None:
        # Assemble source-specific terms so the privacy test itself cannot become
        # a fingerprint hit if the maintainer tree is scanned separately.
        forbidden = {
            "mongo" + "db",
            "private" + " corpus",
            "provider" + "task",
            "provider" + "_task",
            "project" + "token",
            "backup" + "_project",
            "entity" + "_collections",
        }
        private_terms = local_forbidden_terms()
        findings: list[str] = []
        for path in shipped_text_files():
            text = path.read_text(encoding="utf-8").casefold()
            for term in sorted(forbidden):
                if term.casefold() in text:
                    findings.append(f"{path.relative_to(SUITE)}: {term}")
            if any(term.casefold() in text for term in private_terms):
                findings.append(
                    f"{path.relative_to(SUITE)}: maintainer-local exact term"
                )
        self.assertEqual(
            findings,
            [],
            "private schema/source or provider task vocabulary shipped:\n"
            + "\n".join(findings),
        )

    def test_private_release_terms_are_absent_from_release_facing_text(self) -> None:
        private_terms = local_forbidden_terms()
        findings = [
            str(path.relative_to(SUITE))
            for path in release_facing_text_files()
            if any(
                term.casefold() in path.read_text(encoding="utf-8").casefold()
                for term in private_terms
            )
        ]
        self.assertEqual(
            findings,
            [],
            "maintainer-local release vocabulary found in: " + ", ".join(findings),
        )

    def test_maintainer_tree_has_no_credentials_or_private_locators(self) -> None:
        patterns = {
            "IPv4 address": re.compile(
                r"(?<!\d)(?:\d{1,3}\.){3}\d{1,3}(?::\d+)?(?!\d)"
            ),
            "network URI": re.compile(
                r"\b(?:https?|mongodb(?:\+srv)?|postgres(?:ql)?|mysql|redis)://",
                re.IGNORECASE,
            ),
            "machine path": re.compile(
                r"(?<![\w.])/(?:Users|home|private|var|tmp)/|\b[A-Za-z]:[\\/]"
            ),
            "credential assignment": re.compile(
                r"\b(?:password|passwd|secret|api[_-]?key|access[_-]?token)"
                r"\s*[:=]\s*[^\s<]+",
                re.IGNORECASE,
            ),
            "private key": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
        }
        maintainer_root = SUITE / "maintainers"
        findings: list[str] = []
        for path in release_facing_text_files():
            if maintainer_root not in path.parents:
                continue
            text = path.read_text(encoding="utf-8")
            for label, pattern in patterns.items():
                if pattern.search(text):
                    findings.append(f"{path.relative_to(SUITE)}: {label}")
        self.assertEqual(
            findings,
            [],
            "private locator or credential material found:\n" + "\n".join(findings),
        )

    def test_shipping_tree_has_no_machine_absolute_paths(self) -> None:
        patterns = {
            "unix": re.compile(r"(?<![\w.])/(?:Users|home|private|var|tmp)/"),
            "windows": re.compile(r"\b[A-Za-z]:[\\/]"),
            "file_url": re.compile(r"\bfile://", re.IGNORECASE),
        }
        findings: list[str] = []
        for path in shipped_text_files():
            text = path.read_text(encoding="utf-8")
            for name, pattern in patterns.items():
                if pattern.search(text):
                    findings.append(f"{path.relative_to(SUITE)}: {name}")
        self.assertEqual(findings, [], "machine paths shipped:\n" + "\n".join(findings))

    def test_deterministic_scripts_do_not_import_network_or_private_runtime_clients(
        self,
    ) -> None:
        forbidden_imports = re.compile(
            r"^\s*(?:from|import)\s+(?:socket|urllib|httpx?|requests|aiohttp|pymongo)\b",
            re.MULTILINE,
        )
        runtime_lookup = re.compile(
            r"(?:connect|query|lookup|fetch|download).{0,32}(?:database|corpus|backup|provider)",
            re.IGNORECASE,
        )
        findings: list[str] = []
        for path in SHIPPED_SKILLS.rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            # The dashboard is an explicit loopback HTTP service, not a
            # deterministic production script. Its separate boundary test below
            # permits server/parser modules but still forbids outbound clients.
            if path == DASHBOARD_SERVER:
                continue
            text = path.read_text(encoding="utf-8")
            if forbidden_imports.search(text):
                findings.append(f"{path.relative_to(SUITE)}: outbound/private import")
            if runtime_lookup.search(text):
                findings.append(f"{path.relative_to(SUITE)}: runtime source lookup")
        self.assertEqual(
            findings, [], "runtime boundary violations:\n" + "\n".join(findings)
        )

    def test_dashboard_server_imports_no_outbound_or_private_runtime_client(
        self,
    ) -> None:
        text = DASHBOARD_SERVER.read_text(encoding="utf-8")
        imported: set[str] = set()
        for node in ast.walk(ast.parse(text)):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.update(f"{node.module}.{alias.name}" for alias in node.names)
        forbidden = {
            "socket",
            "urllib.request",
            "http.client",
            "httpx",
            "requests",
            "aiohttp",
            "pymongo",
        }
        findings = sorted(
            name
            for name in imported
            if any(name == item or name.startswith(f"{item}.") for item in forbidden)
        )
        self.assertEqual(
            findings,
            [],
            "dashboard must remain a local server without outbound clients",
        )

    def test_every_shipped_script_declares_the_documented_python_floor(self) -> None:
        """A creator-invoked script must state its own floor, and both READMEs
        must quote the same one. Otherwise the floor drifts silently upward the
        first time someone reaches for a newer standard-library API."""

        declaration = re.compile(r"^MINIMUM_PYTHON = \((\d+), (\d+)\)$", re.MULTILINE)
        declared: dict[str, tuple[int, int]] = {}
        for path in sorted(SHIPPED_SKILLS.rglob("scripts/*.py")):
            if "__pycache__" in path.parts:
                continue
            found = declaration.search(path.read_text(encoding="utf-8"))
            self.assertIsNotNone(
                found, f"{path.relative_to(SUITE)} declares no MINIMUM_PYTHON"
            )
            assert found is not None
            declared[str(path.relative_to(SUITE))] = (
                int(found.group(1)),
                int(found.group(2)),
            )
        self.assertTrue(declared, "no shipped scripts were scanned")
        self.assertEqual(
            len(set(declared.values())),
            1,
            f"shipped scripts disagree on the Python floor: {declared}",
        )
        major, minor = next(iter(declared.values()))
        for readme in ("README.md", "README_EN.md"):
            self.assertIn(
                f"Python {major}.{minor}",
                (SUITE / readme).read_text(encoding="utf-8"),
                f"{readme} does not document the Python {major}.{minor} floor",
            )


if __name__ == "__main__":
    unittest.main()
