#!/usr/bin/env python3
"""Tests for scripts/secret_sweep.py, the hard rule that no secret enters the repository.

Every fixture that looks like a secret is assembled from parts at run time, so that this file does not trip the
sweep it tests. Run with: python3 scripts/test_secret_sweep.py
"""
import contextlib
import io
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import secret_sweep  # noqa: E402

PEM_HEADER = "-----BEGIN " + "RSA PRIVATE KEY-----"
GH_CREDENTIAL = "gh" + "p_" + "a" * 36
ASSIGNED = "pass" + "word = hunter2hunter2"
PLACEHOLDER = "API" + '_KEY="REDACTED"'
HEX = "a1" * 20


def sh(*args, cwd):
    subprocess.run(args, cwd=cwd, check=True, capture_output=True)


class Repo:
    """A throwaway git repository that the sweep runs in."""

    def __enter__(self):
        self.dir = tempfile.TemporaryDirectory()
        self.old = os.getcwd()
        os.chdir(self.dir.name)
        sh("git", "init", "-q", cwd=self.dir.name)
        sh("git", "config", "user.email", "t@example.com", cwd=self.dir.name)
        sh("git", "config", "user.name", "t", cwd=self.dir.name)
        return self

    def __exit__(self, *exc):
        os.chdir(self.old)
        self.dir.cleanup()

    def stage(self, name, text):
        p = Path(self.dir.name) / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
        sh("git", "add", name, cwd=self.dir.name)

    def commit(self, msg="c"):
        sh("git", "commit", "-q", "-m", msg, cwd=self.dir.name)


def reasons(found):
    return sorted(why for _, why in found)


class StagedTests(unittest.TestCase):
    def test_private_key_block_is_found(self):
        with Repo() as r:
            r.stage("notes.md", f"text\n{PEM_HEADER}\nmore\n")
            self.assertEqual(reasons(secret_sweep.scan_staged()), ["private key block"])

    def test_a_credential_shape_is_found_without_a_name_around_it(self):
        with Repo() as r:
            r.stage("a.txt", f"value {GH_CREDENTIAL}\n")
            self.assertEqual(reasons(secret_sweep.scan_staged()), ["GitHub credential"])

    def test_assignment_of_a_credential_is_found(self):
        with Repo() as r:
            r.stage("a.yaml", ASSIGNED + "\n")
            self.assertEqual(reasons(secret_sweep.scan_staged()), ["a credential assigned a value"])

    def test_placeholders_and_references_are_allowed(self):
        with Repo() as r:
            r.stage("a.sh", PLACEHOLDER + "\nexport T=${TOKEN_FROM_SECRET_MANAGER}\n")
            self.assertEqual(secret_sweep.scan_staged(), [])

    def test_a_switch_with_a_credential_sounding_name_is_not_a_finding(self):
        with Repo() as r:
            r.stage("a.yaml", "automountServiceAccount" + "Token: false\n" + "allow_" + "token = true\n" + '"pass' + 'word": FALSE,\n')
            self.assertEqual(secret_sweep.scan_staged(), [])

    def test_a_value_that_only_starts_like_a_boolean_or_is_quoted_is_still_found(self):
        with Repo() as r:
            r.stage("a.yaml", "pass" + "word = truebluepassphrase\n")
            self.assertEqual(reasons(secret_sweep.scan_staged()), ["a credential assigned a value"])
        with Repo() as r:
            r.stage("a.yaml", "to" + 'ken: "true"\n')
            self.assertEqual(reasons(secret_sweep.scan_staged()), ["a credential assigned a value"])

    def test_prose_that_ends_with_the_word_is_not_a_finding(self):
        with Repo() as r:
            r.stage("a.md", "Never write a " + "sec" + "ret:\nand do not paste a " + "tok" + "en:\n")
            self.assertEqual(secret_sweep.scan_staged(), [])

    def test_long_hexadecimal_literal_is_found_but_a_digest_is_not(self):
        with Repo() as r:
            r.stage("a.yaml", f'value: "{HEX}"\n')
            self.assertEqual(reasons(secret_sweep.scan_staged()), ["a long hexadecimal literal"])
        with Repo() as r:
            r.stage("a.yaml", f'image_digest: "{HEX}"\n')
            self.assertEqual(secret_sweep.scan_staged(), [])

    def test_provider_lock_file_hashes_are_exempt(self):
        with Repo() as r:
            r.stage("env/.terraform.lock.hcl", f'  hashes = [\n    "zh:{HEX}",\n  ]\n')
            self.assertEqual(secret_sweep.scan_staged(), [])

    def test_forbidden_file_names_are_found_whatever_they_hold(self):
        with Repo() as r:
            for name in ("cert.pem", "server.key", "env/prod.tfvars", "terraform.tfstate", "x/foo.tfplan", "kubeconfig", "sa-credentials.json"):
                r.stage(name, "nothing secret inside\n")
            found = secret_sweep.scan_staged()
            self.assertEqual(len(found), 7)
            self.assertTrue(all(why == "a file type that must never be committed" for _, why in found))

    def test_an_ordinary_file_is_clean(self):
        with Repo() as r:
            r.stage("README.md", "# Title\nSome prose about Secret Manager and how it is used.\n")
            self.assertEqual(secret_sweep.scan_staged(), [])


class OutputAndHistoryTests(unittest.TestCase):
    def test_the_output_never_contains_the_value(self):
        with Repo() as r:
            r.stage("a.txt", f"value {GH_CREDENTIAL}\n")
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                code = secret_sweep.main(["x", "--staged"])
            self.assertEqual(code, 1)
            self.assertNotIn(GH_CREDENTIAL, buf.getvalue())
            self.assertIn("a.txt:1", buf.getvalue())

    def test_history_finds_a_secret_that_was_later_removed(self):
        with Repo() as r:
            r.stage("a.txt", f"value {GH_CREDENTIAL}\n")
            r.commit("add")
            r.stage("a.txt", "clean now\n")
            r.commit("remove")
            self.assertEqual(secret_sweep.scan_tree(), [])
            self.assertEqual(reasons(secret_sweep.scan_history()), ["GitHub credential"])

    def test_history_honours_the_reviewed_register_but_the_tree_does_not(self):
        with Repo() as r:
            r.stage("a.txt", f"value {GH_CREDENTIAL}\n")
            r.commit("add")
            commit8 = subprocess.run(["git", "rev-parse", "--short=8", "HEAD"], capture_output=True, text=True).stdout.strip()
            r.stage("scripts/secret_sweep_reviewed.txt", f"{commit8} a.txt:1  # reviewed in a test\n")
            self.assertEqual(secret_sweep.scan_history(), [])
            self.assertEqual(reasons(secret_sweep.scan_tree()), ["GitHub credential"])


if __name__ == "__main__":
    unittest.main()
