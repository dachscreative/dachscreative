"""Offline tests. stdlib unittest, no network, no extra dependencies.

    .venv/bin/python -m unittest discover -s tests -v
"""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from jobscraper import cli, vpn
from jobscraper.config import Config, ScoringConfig, VpnConfig
from jobscraper.export import export_all
from jobscraper.models import Job
from jobscraper.scoring import Scorer
from jobscraper.store import Store

NOW = datetime.now(timezone.utc)


def job(**kw) -> Job:
    base = dict(
        source="fixture",
        title="Backend Engineer",
        company="Acme",
        url="https://example.invalid/1",
        location="Remote",
        description="We use Python and Postgres.",
        tags=["python"],
        posted_at=NOW,
        remote=True,
    )
    base.update(kw)
    return Job(**base)


class TestScoring(unittest.TestCase):
    def setUp(self):
        self.scorer = Scorer(
            ScoringConfig(
                include={"python": 3, "backend": 2},
                exclude={"unpaid": -10},
                title_multiplier=3.0,
                min_score=3.0,
                recency_days=7,
                recency_bonus=1.0,
            )
        )

    def test_title_match_counts_triple(self):
        in_title = self.scorer.score(job(title="Python Engineer", description=""))[0]
        in_body = self.scorer.score(job(title="Engineer", description="python", tags=[]))[0]
        # 3*3 + backend? no. + recency 1 = 10 vs 3 + 1 = 4
        self.assertEqual(in_title, 10.0)
        self.assertEqual(in_body, 4.0)

    def test_exclude_subtracts(self):
        score, matched = self.scorer.score(
            job(title="Engineer", description="python, unpaid role", tags=[])
        )
        self.assertEqual(score, 4.0 - 10.0)
        self.assertIn("-unpaid", matched)

    def test_word_boundary(self):
        # "python" must not fire inside "pythonic"... and must not miss "Python."
        self.assertEqual(self.scorer.score(job(title="X", description="pythonic", tags=[]))[0], 1.0)
        self.assertEqual(self.scorer.score(job(title="X", description="Python.", tags=[]))[0], 4.0)

    def test_recency_bonus_only_when_recent(self):
        old = job(title="X", description="python", tags=[], posted_at=NOW - timedelta(days=30))
        self.assertEqual(self.scorer.score(old)[0], 3.0)

    def test_min_score_gate(self):
        self.assertTrue(self.scorer.keeps(3.0))
        self.assertFalse(self.scorer.keeps(2.99))


class TestIdentity(unittest.TestCase):
    def test_uid_survives_a_url_change(self):
        a = job(url="https://example.invalid/jobs/111")
        b = job(url="https://example.invalid/jobs/999?utm=x")
        self.assertEqual(a.uid, b.uid, "a re-post at a new URL must not read as new")

    def test_uid_differs_by_company(self):
        self.assertNotEqual(job().uid, job(company="Other").uid)

    def test_html_is_stripped(self):
        j = job(description="<p>Python &amp; SQL</p><br>Great")
        self.assertNotIn("<", j.description)
        self.assertIn("Python & SQL", j.description)


class TestFilters(unittest.TestCase):
    def setUp(self):
        self.cfg = Config()

    def test_drops_stale_postings(self):
        self.cfg.filters.posted_within_days = 7
        jobs = [job(posted_at=NOW), job(posted_at=NOW - timedelta(days=40), company="Old")]
        self.assertEqual(len(cli.apply_filters(jobs, self.cfg)), 1)

    def test_undated_postings_are_kept(self):
        self.cfg.filters.posted_within_days = 7
        self.assertEqual(len(cli.apply_filters([job(posted_at=None)], self.cfg)), 1)

    def test_remote_only(self):
        self.cfg.filters.remote_only = True
        jobs = [job(), job(remote=False, company="OnSite")]
        self.assertEqual(len(cli.apply_filters(jobs, self.cfg)), 1)

    def test_location_substring(self):
        self.cfg.filters.locations = ["germany"]
        jobs = [job(location="Berlin, Germany", remote=False), job(location="Tokyo", remote=False)]
        kept = cli.apply_filters(jobs, self.cfg)
        self.assertEqual([j.location for j in kept], ["Berlin, Germany"])

    def test_rows_without_url_or_title_are_dropped(self):
        self.assertEqual(cli.apply_filters([job(url=""), job(title="")], self.cfg), [])


class TestDeduplicate(unittest.TestCase):
    def test_keeps_the_higher_score(self):
        a, b = job(), job(source="other")
        a.score, b.score = 4.0, 9.0
        result = cli.deduplicate([a, b])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].score, 9.0)


class TestStore(unittest.TestCase):
    def test_new_marking_is_true_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / "jobs.db")
            jobs = [job(), job(company="Beta")]

            self.assertEqual(len(store.mark_new(jobs)), 2)
            store.upsert(jobs)

            again = [job(), job(company="Beta")]
            self.assertEqual(len(store.mark_new(again)), 0, "second run must report nothing new")

            plus_one = [job(), job(company="Beta"), job(company="Gamma")]
            self.assertEqual(len(store.mark_new(plus_one)), 1)
            store.close()

    def test_run_bookkeeping(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / "jobs.db")
            self.assertIsNone(store.last_successful_run())
            rid = store.start_run()
            store.finish_run(rid, found=10, kept=5, new=2, status="ok")
            self.assertIsNotNone(store.last_successful_run())
            store.close()


class TestExport(unittest.TestCase):
    def test_writes_all_four_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "exports"
            j = job()
            j.score, j.is_new, j.matched = 7.5, True, ["python(title)"]
            written = export_all(out, [j], [j])

            self.assertEqual(len(written), 4)
            for path in written:
                self.assertTrue(path.exists(), f"{path} was not written")

            csv_text = (out / "latest.csv").read_text()
            self.assertIn("Backend Engineer", csv_text)
            self.assertIn("7.50", csv_text)

            md_text = (out / "latest.md").read_text()
            self.assertIn("Backend Engineer", md_text)
            self.assertIn("https://example.invalid/1", md_text)

    def test_empty_new_list_says_so(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "exports"
            export_all(out, [], [])
            self.assertIn("Nothing new", (out / "latest.md").read_text())


class TestVpn(unittest.TestCase):
    def test_missing_interface_fails_closed(self):
        cfg = VpnConfig(interface_prefixes=["definitely-not-an-interface"], require_interface=True)
        status = vpn.check(cfg, "test-agent")
        self.assertFalse(status.ok)
        self.assertIn("No VPN interface", status.reason)

    def test_blocked_ip_is_refused(self):
        cfg = VpnConfig(require_interface=False, blocked_ips=["203.0.113.9"])
        original = vpn.public_ip
        vpn.public_ip = lambda *a, **k: "203.0.113.9"
        try:
            status = vpn.check(cfg, "test-agent")
        finally:
            vpn.public_ip = original
        self.assertFalse(status.ok)
        self.assertIn("bare connection", status.reason)

    def test_unreachable_check_url_fails_closed_when_blocklist_set(self):
        cfg = VpnConfig(require_interface=False, blocked_ips=["203.0.113.9"])
        original = vpn.public_ip
        vpn.public_ip = lambda *a, **k: None
        try:
            status = vpn.check(cfg, "test-agent")
        finally:
            vpn.public_ip = original
        self.assertFalse(status.ok, "must not assume safety when it cannot verify")

    def test_good_ip_passes(self):
        cfg = VpnConfig(require_interface=False, blocked_ips=["203.0.113.9"])
        original = vpn.public_ip
        vpn.public_ip = lambda *a, **k: "198.51.100.7"
        try:
            status = vpn.check(cfg, "test-agent")
        finally:
            vpn.public_ip = original
        self.assertTrue(status.ok)


class TestExitCodes(unittest.TestCase):
    """run.sh reads these. They are part of the interface."""

    def test_vpn_failure_is_2(self):
        original = vpn.check
        vpn.check = lambda *a, **k: vpn.VpnStatus(ok=False, reason="no tunnel")
        try:
            code = cli.main(["run"])
        finally:
            vpn.check = original
        self.assertEqual(code, cli.EXIT_VPN)
        self.assertEqual(code, 2)

    def test_keyboard_interrupt_is_130(self):
        original = cli.cmd_run
        def boom(*a, **k):
            raise KeyboardInterrupt
        cli.cmd_run = boom
        try:
            # rebuild the parser binding so the patched function is the one used
            code = cli.main(["run"]) if cli.build_parser else None
        finally:
            cli.cmd_run = original
        self.assertEqual(code, 130)

    def test_no_subcommand_is_error(self):
        self.assertEqual(cli.main([]), cli.EXIT_ERROR)


if __name__ == "__main__":
    unittest.main()
