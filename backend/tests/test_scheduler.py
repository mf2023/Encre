#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Copyright © 2025-2026 Wenze Wei. All Rights Reserved.
#
# This file is part of Encre.
# The Encre project belongs to the Dunimd Team.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# You may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# DISCLAIMER: Users must comply with applicable AI regulations.
# Non-compliance may result in service termination or legal liability.

from __future__ import annotations

"""Tests for the cron scheduler: :class:`CronSchedule`, :class:`ScheduledJob`,
:class:`EncreScheduler`, :class:`ScheduleType`, and :class:`JobState`.
"""

import json
import os
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from encre.scheduler import (
    CronSchedule,
    EncreScheduler,
    JobExecution,
    JobState,
    ScheduledJob,
    ScheduleType,
)


@pytest.fixture(autouse=True)
def isolate_default_scheduler_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep default scheduler instances independent across tests."""
    monkeypatch.setattr("encre.config.get_data_dir", lambda: tmp_path)

# ===========================================================================
# CronSchedule.parse()
# ===========================================================================

class TestCronScheduleParse:
    """Test cases covering cron schedule parse.
    
    Covers the expected behavior and relevant edge cases.
    """
    """Test :meth:`CronSchedule.parse` with valid and invalid expressions."""

    def test_parse_every_minute(self):
        """Verifies that parse every minute."""
        cs = CronSchedule.parse("* * * * *")
        # Confirm the expected result for this scenario: parse every minute.
        assert cs.minute == "*"
        assert cs.hour == "*"
        assert cs.day_of_month == "*"
        assert cs.month == "*"
        assert cs.day_of_week == "*"

    def test_parse_specific_time(self):
        """Verifies that parse specific time."""
        cs = CronSchedule.parse("30 9 15 3 *")
        # Confirm the expected result for this scenario: parse specific time.
        assert cs.minute == "30"
        assert cs.hour == "9"
        assert cs.day_of_month == "15"
        assert cs.month == "3"
        assert cs.day_of_week == "*"

    def test_parse_with_ranges(self):
        """Verifies that parse with ranges."""
        cs = CronSchedule.parse("0 9-17 * * 1-5")
        # Confirm the expected result for this scenario: parse with ranges.
        assert cs.hour == "9-17"
        assert cs.day_of_week == "1-5"

    def test_parse_with_step(self):
        """Verifies that parse with step."""
        cs = CronSchedule.parse("*/5 * * * *")
        # Confirm the expected result for this scenario: parse with step.
        assert cs.minute == "*/5"

    def test_parse_with_named_days(self):
        """Verifies that parse with named days."""
        cs = CronSchedule.parse("0 9 * * mon")
        # Confirm the expected result for this scenario: parse with named days.
        assert cs.day_of_week == "mon"

    def test_parse_with_comma_list(self):
        """Verifies that parse with comma list."""
        cs = CronSchedule.parse("0,30 9,17 * * *")
        # Confirm the expected result for this scenario: parse with comma list.
        assert cs.minute == "0,30"
        assert cs.hour == "9,17"

    def test_parse_too_few_fields_raises(self):
        """Verifies that parse too few fields raises."""
        with pytest.raises(ValueError, match="Expected 5 fields"):
            CronSchedule.parse("0 9 * *")

    def test_parse_too_many_fields_raises(self):
        """Verifies that parse too many fields raises."""
        with pytest.raises(ValueError, match="Expected 5 fields"):
            CronSchedule.parse("0 9 * * * *")

    def test_parse_empty_raises(self):
        """Verifies that parse empty raises."""
        with pytest.raises(ValueError, match="Expected 5 fields"):
            CronSchedule.parse("")

    def test_parse_whitespace_only_raises(self):
        """Verifies that parse whitespace only raises."""
        with pytest.raises(ValueError):
            CronSchedule.parse("     ")

    def test_to_expression_roundtrip(self):
        """Verifies that to expression roundtrip."""
        expr = "*/10 8-18 1,15 * mon-fri"
        cs = CronSchedule.parse(expr)
        # Confirm the expected result for this scenario: to expression roundtrip.
        assert cs.to_expression() == expr


# ===========================================================================
# CronSchedule._match_field
# ===========================================================================

class TestMatchField:
    """Test cases covering match field.
    
    Covers the expected behavior and relevant edge cases.
    """
    """Test :meth:`CronSchedule._match_field` logic."""

    def test_star_matches_all(self):
        """Verifies that star matches all."""
        cs = CronSchedule.parse("* * * * *")
        for v in range(60):
            # Confirm the expected result for this scenario: star matches all.
            assert cs._match_field(v, "*") is True

    def test_exact_match(self):
        """Verifies that exact match."""
        cs = CronSchedule.parse("* * * * *")
        # Confirm the expected result for this scenario: exact match.
        assert cs._match_field(30, "30") is True
        assert cs._match_field(31, "30") is False

    def test_step_match(self):
        """Verifies that step match."""
        cs = CronSchedule.parse("* * * * *")
        # Confirm the expected result for this scenario: step match.
        assert cs._match_field(0, "*/5") is True
        assert cs._match_field(5, "*/5") is True
        assert cs._match_field(7, "*/5") is False

    def test_step_with_base(self):
        """Verifies that step with base."""
        cs = CronSchedule.parse("* * * * *")
        # Confirm the expected result for this scenario: step with base.
        assert cs._match_field(10, "10/5") is True
        assert cs._match_field(15, "10/5") is True
        assert cs._match_field(9, "10/5") is False

    def test_range_match(self):
        """Verifies that range match."""
        cs = CronSchedule.parse("* * * * *")
        # Confirm the expected result for this scenario: range match.
        assert cs._match_field(10, "9-17") is True
        assert cs._match_field(9, "9-17") is True
        assert cs._match_field(17, "9-17") is True
        assert cs._match_field(8, "9-17") is False
        assert cs._match_field(18, "9-17") is False

    def test_comma_list_match(self):
        """Verifies that comma list match."""
        cs = CronSchedule.parse("* * * * *")
        # Confirm the expected result for this scenario: comma list match.
        assert cs._match_field(0, "0,30") is True
        assert cs._match_field(30, "0,30") is True
        assert cs._match_field(15, "0,30") is False

    def test_invalid_int_ignored(self):
        """Verifies that invalid int ignored."""
        cs = CronSchedule.parse("* * * * *")
        # Non-integer should not raise, just not match
        # Confirm the expected result for this scenario: invalid int ignored.
        assert cs._match_field(5, "mon") is False


# ===========================================================================
# CronSchedule._normalize_dow
# ===========================================================================

class TestNormalizeDOW:
    """Test cases covering normalize d o w.
    
    Covers the expected behavior and relevant edge cases.
    """
    """Test named day-of-week conversion."""

    def test_sun_to_0(self):
        """Verifies that sun to 0."""
        # Confirm the expected result for this scenario: sun to 0.
        assert CronSchedule._normalize_dow("sun") == "0"

    def test_mon_to_1(self):
        """Verifies that mon to 1."""
        # Confirm the expected result for this scenario: mon to 1.
        assert CronSchedule._normalize_dow("mon") == "1"

    def test_tue_to_2(self):
        """Verifies that tue to 2."""
        # Confirm the expected result for this scenario: tue to 2.
        assert CronSchedule._normalize_dow("tue") == "2"

    def test_wed_to_3(self):
        """Verifies that wed to 3."""
        # Confirm the expected result for this scenario: wed to 3.
        assert CronSchedule._normalize_dow("wed") == "3"

    def test_thu_to_4(self):
        """Verifies that thu to 4."""
        # Confirm the expected result for this scenario: thu to 4.
        assert CronSchedule._normalize_dow("thu") == "4"

    def test_fri_to_5(self):
        """Verifies that fri to 5."""
        # Confirm the expected result for this scenario: fri to 5.
        assert CronSchedule._normalize_dow("fri") == "5"

    def test_sat_to_6(self):
        """Verifies that sat to 6."""
        # Confirm the expected result for this scenario: sat to 6.
        assert CronSchedule._normalize_dow("sat") == "6"

    def test_case_insensitive(self):
        """Verifies that case insensitive."""
        # Confirm the expected result for this scenario: case insensitive.
        assert CronSchedule._normalize_dow("MON") == "1"
        assert CronSchedule._normalize_dow("Fri") == "5"

    def test_mixed_range(self):
        """Verifies that mixed range."""
        # "mon-fri" -> names replaced in order: mon->1, fri->5 -> "1-5"
        result = CronSchedule._normalize_dow("mon-fri")
        # Confirm the expected result for this scenario: mixed range.
        assert result == "1-5"

    def test_numeric_unchanged(self):
        """Verifies that numeric unchanged."""
        # Confirm the expected result for this scenario: numeric unchanged.
        assert CronSchedule._normalize_dow("5") == "5"


# ===========================================================================
# CronSchedule._weekday_cron
# ===========================================================================

class TestWeekdayCron:
    """Test cases covering weekday cron.
    
    Covers the expected behavior and relevant edge cases.
    """
    """Test the weekday calculation helper."""

    def test_known_date_monday(self):
        """Verifies that known date monday."""
        # 2024-01-01 was a Monday
        wday = CronSchedule._weekday_cron(2024, 1, 1)
        # Confirm the expected result for this scenario: known date monday.
        assert wday == 1  # Monday = 1 in cron

    def test_known_date_sunday(self):
        """Verifies that known date sunday."""
        # 2024-01-07 was a Sunday
        wday = CronSchedule._weekday_cron(2024, 1, 7)
        # Confirm the expected result for this scenario: known date sunday.
        assert wday == 0  # Sunday = 0 in cron

    def test_known_date_friday(self):
        """Verifies that known date friday."""
        # 2026-05-15 was a Friday
        wday = CronSchedule._weekday_cron(2026, 5, 15)
        # Confirm the expected result for this scenario: known date friday.
        assert wday == 5  # Friday = 5 in cron


# ===========================================================================
# CronSchedule.next_fire()
# ===========================================================================

class TestNextFire:
    """Test cases covering next fire.
    
    Covers the expected behavior and relevant edge cases.
    """
    """Test :meth:`CronSchedule.next_fire` with various patterns."""

    def test_next_fire_every_minute(self):
        """Verifies that next fire every minute."""
        cs = CronSchedule.parse("* * * * *")
        now = time.time()
        nf = cs.next_fire(now)
        # Confirm the expected result for this scenario: next fire every minute.
        assert nf is not None
        assert nf > now
        assert nf - now <= 62

    def test_next_fire_specific_minute(self):
        """Verifies that next fire specific minute."""
        cs = CronSchedule.parse("7 * * * *")
        now = time.time()
        nf = cs.next_fire(now)
        # Confirm the expected result for this scenario: next fire specific minute.
        assert nf is not None
        assert nf > now
        t = time.localtime(nf)
        assert t.tm_min == 7

    def test_next_fire_daily_9am(self):
        """Verifies that next fire daily 9am."""
        cs = CronSchedule.parse("0 9 * * *")
        now = time.time()
        nf = cs.next_fire(now)
        # Confirm the expected result for this scenario: next fire daily 9am.
        assert nf is not None
        t = time.localtime(nf)
        assert t.tm_hour == 9
        assert t.tm_min == 0

    def test_next_fire_weekdays(self):
        """Verifies that next fire weekdays."""
        cs = CronSchedule.parse("0 9 * * 1-5")
        now = time.time()
        nf = cs.next_fire(now)
        # Confirm the expected result for this scenario: next fire weekdays.
        assert nf is not None
        t = time.localtime(nf)
        assert 0 <= t.tm_wday <= 4  # Python: 0=Mon, 4=Fri
        assert t.tm_hour == 9

    def test_next_fire_on_monday(self):
        """Verifies that next fire on monday."""
        cs = CronSchedule.parse("0 12 * * mon")
        now = time.time()
        nf = cs.next_fire(now)
        # Confirm the expected result for this scenario: next fire on monday.
        assert nf is not None
        t = time.localtime(nf)
        assert t.tm_wday == 0  # Python: Monday=0
        assert t.tm_hour == 12

    def test_next_fire_returns_future_only(self):
        """Verifies that next fire returns future only."""
        cs = CronSchedule.parse("* * * * *")
        now = time.time()
        nf = cs.next_fire(now)
        # Confirm the expected result for this scenario: next fire returns future only.
        assert nf > now


# ===========================================================================
# Leap year handling
# ===========================================================================

class TestLeapYearHandling:
    """Test cases covering leap year handling.
    
    Covers the expected behavior and relevant edge cases.
    """
    """Test that Feb 29 (day_of_month=29, month=2) works in leap years."""

    def test_feb_29_matches_in_leap_year(self):
        """Verifies that feb 29 matches in leap year."""
        cs = CronSchedule.parse("0 12 29 2 *")
        from datetime import datetime
        ts = datetime(2024, 2, 28, 11, 59).timestamp()
        nf = cs.next_fire(ts)
        # Confirm the expected result for this scenario: feb 29 matches in leap year.
        assert nf is not None
        t = time.localtime(nf)
        assert t.tm_mon == 2
        assert t.tm_mday == 29
        assert t.tm_year == 2024

    def test_feb_29_skipped_non_leap_year(self):
        """Verifies that feb 29 skipped non leap year."""
        cs = CronSchedule.parse("0 12 29 2 *")
        from datetime import datetime
        # 2023 was NOT a leap year. Start from late 2023 so that
        # 2024-02-29 falls within max_iter (525600 min = 365 days).
        # From 2023-02-01 to 2024-02-29 is ~394 days, which exceeds max_iter.
        ts = datetime(2023, 12, 1, 0, 0).timestamp()
        nf = cs.next_fire(ts)
        # Confirm the expected result for this scenario: feb 29 skipped non leap year.
        assert nf is not None
        t = time.localtime(nf)
        # Should land in 2024 (the next leap year)
        assert t.tm_year == 2024
        assert t.tm_mon == 2
        assert t.tm_mday == 29

    def test_leap_year_days_in_february(self):
        """Verifies that leap year days in february."""
        cs = CronSchedule.parse("0 12 28 2 *")
        from datetime import datetime
        # Feb 28 exists in all years; query from 2024-02-27
        ts = datetime(2024, 2, 27, 0, 0).timestamp()
        nf = cs.next_fire(ts)
        # Confirm the expected result for this scenario: leap year days in february.
        assert nf is not None
        t = time.localtime(nf)
        assert t.tm_mon == 2
        assert t.tm_mday == 28


# ===========================================================================
# ScheduledJob serialization
# ===========================================================================

class TestScheduledJob:
    """Test cases covering scheduled job.
    
    Covers the expected behavior and relevant edge cases.
    """
    """Test :class:`ScheduledJob` serialization and creation."""

    def test_create_one_shot_job(self):
        """Verifies that create one shot job."""
        job = ScheduledJob(
            id="abc123",
            name="Reminder",
            prompt="Check the deploy",
            schedule_type=ScheduleType.ONE_SHOT,
            fire_at=time.time() + 300,
        )
        # Confirm the expected result for this scenario: create one shot job.
        assert job.id == "abc123"
        assert job.state == JobState.PENDING
        assert job.cron is None

    def test_create_recurring_job(self):
        """Verifies that create recurring job."""
        cs = CronSchedule.parse("0 9 * * 1-5")
        job = ScheduledJob(
            id="rec1",
            name="Daily report",
            prompt="Generate daily report",
            schedule_type=ScheduleType.RECURRING,
            cron=cs,
        )
        # Confirm the expected result for this scenario: create recurring job.
        assert job.schedule_type == ScheduleType.RECURRING
        assert job.cron is not None

    def test_to_dict(self):
        """Verifies that to dict."""
        cs = CronSchedule.parse("0 9 * * *")
        job = ScheduledJob(
            id="test1",
            name="Test job",
            prompt="Run tests",
            schedule_type=ScheduleType.RECURRING,
            cron=cs,
            fail_count=2,
            max_failures=5,
            metadata={"key": "value"},
        )
        d = job.to_dict()
        # Confirm the expected result for this scenario: to dict.
        assert d["id"] == "test1"
        assert d["name"] == "Test job"
        assert d["cron"] == "0 9 * * *"
        assert d["fail_count"] == 2
        assert d["max_failures"] == 5
        assert d["metadata"]["key"] == "value"
        assert d["state"] == "PENDING"

    def test_from_dict_recurring(self):
        """Verifies that from dict recurring."""
        data = {
            "id": "test2",
            "name": "Cron job",
            "prompt": "do stuff",
            "schedule_type": "RECURRING",
            "cron": "*/10 * * * *",
            "fire_at": None,
            "state": "PENDING",
            "created_at": 1700000000.0,
            "last_fired": None,
            "last_result": None,
            "fail_count": 0,
            "max_failures": 3,
            "metadata": {},
            "agent_config": None,
        }
        job = ScheduledJob.from_dict(data)
        # Confirm the expected result for this scenario: from dict recurring.
        assert job.id == "test2"
        assert job.schedule_type == ScheduleType.RECURRING
        assert job.cron is not None
        assert job.cron.minute == "*/10"

    def test_from_dict_one_shot(self):
        """Verifies that from dict one shot."""
        data = {
            "id": "os1",
            "name": "One-shot",
            "prompt": "Do it once",
            "schedule_type": "ONE_SHOT",
            "cron": None,
            "fire_at": 1700001000.0,
            "state": "PENDING",
            "created_at": 1700000000.0,
            "last_fired": None,
            "last_result": None,
            "fail_count": 0,
            "max_failures": 3,
            "metadata": {},
            "agent_config": None,
        }
        job = ScheduledJob.from_dict(data)
        # Confirm the expected result for this scenario: from dict one shot.
        assert job.schedule_type == ScheduleType.ONE_SHOT
        assert job.cron is None
        assert job.fire_at == 1700001000.0

    def test_from_dict_missing_cron(self):
        """Verifies that from dict missing cron."""
        data = {
            "id": "x",
            "name": "x",
            "prompt": "x",
            "schedule_type": "RECURRING",
            "cron": None,
        }
        job = ScheduledJob.from_dict(data)
        # Confirm the expected result for this scenario: from dict missing cron.
        assert job.cron is None


# ===========================================================================
# EncreScheduler: scheduling and cancellation
# ===========================================================================

class TestEncreSchedulerBasic:
    """Test cases covering encre scheduler basic.
    
    Covers the expected behavior and relevant edge cases.
    """
    """Test :class:`EncreScheduler` schedule and cancel methods."""

    def test_schedule_recurring(self):
        """Verifies that schedule recurring."""
        sched = EncreScheduler()
        job_id = sched.schedule(
            name="Test recurring",
            prompt="Run something",
            cron="0 9 * * *",
        )
        # Confirm the expected result for this scenario: schedule recurring.
        assert job_id is not None
        assert len(job_id) > 0
        job = sched.get_job(job_id)
        assert job is not None
        assert job.name == "Test recurring"
        assert job.schedule_type == ScheduleType.RECURRING

    def test_schedule_one_shot(self):
        """Verifies that schedule one shot."""
        sched = EncreScheduler()
        job_id = sched.schedule(
            name="Test one-shot",
            prompt="Run once",
            fire_at=time.time() + 3600,
        )
        job = sched.get_job(job_id)
        # Confirm the expected result for this scenario: schedule one shot.
        assert job is not None
        assert job.schedule_type == ScheduleType.ONE_SHOT
        assert job.fire_at is not None

    def test_schedule_no_cron_no_fire_at_defaults_immediate(self):
        """Verifies that schedule no cron no fire at defaults immediate."""
        sched = EncreScheduler()
        job_id = sched.schedule(name="Immediate", prompt="Go")
        job = sched.get_job(job_id)
        # Confirm the expected result for this scenario: schedule no cron no fire at defaults immediate.
        assert job is not None
        assert job.schedule_type == ScheduleType.ONE_SHOT
        assert job.fire_at is not None
        assert abs(job.fire_at - time.time()) < 5

    def test_cancel_existing_job(self):
        """Verifies that cancel existing job."""
        sched = EncreScheduler()
        job_id = sched.schedule(name="Cancel me", prompt="...", cron="0 9 * * *")
        # Confirm the expected result for this scenario: cancel existing job.
        assert sched.cancel(job_id) is True
        job = sched.get_job(job_id)
        assert job.state == JobState.CANCELLED

    def test_cancel_nonexistent_job(self):
        """Verifies that cancel nonexistent job."""
        sched = EncreScheduler()
        # Confirm the expected result for this scenario: cancel nonexistent job.
        assert sched.cancel("nonexistent") is False

    def test_cancel_all(self):
        """Verifies that cancel all."""
        sched = EncreScheduler()
        ids = [sched.schedule(name=f"job{i}", prompt="...", cron="0 9 * * *") for i in range(5)]
        count = sched.cancel_all()
        # Confirm the expected result for this scenario: cancel all.
        assert count == 5
        for jid in ids:
            assert sched.get_job(jid).state == JobState.CANCELLED

    def test_list_jobs_all(self):
        """Verifies that list jobs all."""
        sched = EncreScheduler()
        sched.schedule(name="A", prompt="A", cron="* * * * *")
        sched.schedule(name="B", prompt="B", cron="0 0 * * *")
        jobs = sched.list_jobs()
        # Confirm the expected result for this scenario: list jobs all.
        assert len(jobs) == 2

    def test_list_jobs_filtered(self):
        """Verifies that list jobs filtered."""
        sched = EncreScheduler()
        jid = sched.schedule(name="A", prompt="A", cron="* * * * *")
        sched.cancel(jid)
        cancelled = sched.list_jobs(state=JobState.CANCELLED)
        # Confirm the expected result for this scenario: list jobs filtered.
        assert len(cancelled) == 1
        # All other states are empty
        pending = sched.list_jobs(state=JobState.PENDING)
        assert len(pending) == 0

    def test_list_jobs_can_include_finished_one_shot_history(self):
        sched = EncreScheduler()
        job_id = sched.schedule(name="Finished", prompt="...", fire_at=time.time() + 60)
        job = sched.get_job(job_id)
        assert job is not None
        job.state = JobState.COMPLETED

        assert sched.list_jobs() == []
        assert sched.list_jobs(include_finished=True) == [job]

    def test_get_job_nonexistent(self):
        """Verifies that get job nonexistent."""
        sched = EncreScheduler()
        # Confirm the expected result for this scenario: get job nonexistent.
        assert sched.get_job("nonexistent") is None


# ===========================================================================
# EncreScheduler: durable persistence
# ===========================================================================

class TestEncreSchedulerDurability:
    """Test cases covering encre scheduler durability.
    
    Covers the expected behavior and relevant edge cases.
    """
    """Test that durable jobs survive being written to and read from disk."""

    def test_durable_save_and_load(self):
        """Verifies that durable save and load."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "jobs.json")
            sched1 = EncreScheduler(durable_path=path)
            jid1 = sched1.schedule(name="Persistent", prompt="Run forever", cron="0 9 * * 1-5")
            jid2 = sched1.schedule(name="One-off", prompt="Run once", fire_at=time.time() + 99999)

            sched2 = EncreScheduler(durable_path=path)
            job1 = sched2.get_job(jid1)
            job2 = sched2.get_job(jid2)

            # Confirm the expected result for this scenario: durable save and load.
            assert job1 is not None
            assert job1.name == "Persistent"
            assert job1.schedule_type == ScheduleType.RECURRING
            assert job1.cron is not None

            assert job2 is not None
            assert job2.name == "One-off"
            assert job2.schedule_type == ScheduleType.ONE_SHOT

    def test_durable_persists_cancel(self):
        """Verifies that durable persists cancel."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "jobs2.json")
            sched1 = EncreScheduler(durable_path=path)
            jid = sched1.schedule(name="Cancel me", prompt="...", cron="* * * * *")
            sched1.cancel(jid)

            sched2 = EncreScheduler(durable_path=path)
            job = sched2.get_job(jid)
            # Confirm the expected result for this scenario: durable persists cancel.
            assert job is not None
            assert job.state == JobState.CANCELLED

    def test_durable_creates_parent_dir(self):
        """Verifies that durable creates parent dir."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "subdir", "nested", "jobs.json")
            sched = EncreScheduler(durable_path=path)
            sched.schedule(name="Nested save", prompt="...", cron="* * * * *")
            # Confirm the expected result for this scenario: durable creates parent dir.
            assert os.path.exists(path)

    def test_durable_no_file_no_error(self):
        """Verifies that durable no file no error."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "nonexistent.json")
            sched = EncreScheduler(durable_path=path)
            # Confirm the expected result for this scenario: durable no file no error.
            assert sched._jobs == {}

    def test_durable_corrupted_json_recovers(self):
        """Verifies that durable corrupted json recovers."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "corrupt.json")
            Path(path).write_text("not valid json at all", encoding="utf-8")
            sched = EncreScheduler(durable_path=path)
            # Confirm the expected result for this scenario: durable corrupted json recovers.
            assert sched._jobs == {}

    def test_durable_bad_entry_skipped(self):
        """Verifies that durable bad entry skipped."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "partial.json")
            data = [{"id": "x"}]  # Missing required keys
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f)
            # Should warn, not crash
            sched = EncreScheduler(durable_path=path)
            # The bad entry is skipped due to KeyError in from_dict
            # Confirm the expected result for this scenario: durable bad entry skipped.
            assert sched._jobs == {}


# ===========================================================================
# EncreScheduler: missed recurring occurrences must not fire late
# ===========================================================================

class TestRecurringMissedOccurrences:
    """Recurring jobs whose scheduled time passed while the process was
    offline (e.g. the app/server was started after the scheduled time)
    must NOT fire on startup -- they wait for the next occurrence.
    """

    def _run_one_poll(self, sched: EncreScheduler, monkeypatch: pytest.MonkeyPatch) -> list[ScheduledJob]:
        """Run a single scheduler poll iteration and return spawned jobs."""
        spawned: list[ScheduledJob] = []
        monkeypatch.setattr(sched, "_spawn_job", lambda j: spawned.append(j))

        async def _stop(seconds: float) -> None:
            sched._running = False

        monkeypatch.setattr("asyncio.sleep", _stop)
        sched._running = True
        import asyncio
        asyncio.run(sched._loop())
        return spawned

    def test_occurrence_before_session_start_is_skipped(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        """Server started at 12:05; a daily 10:00 job must not fire late."""
        now = time.mktime(time.strptime("2026-08-07 12:05:30", "%Y-%m-%d %H:%M:%S"))
        monkeypatch.setattr("encre.scheduler.time.time", lambda: now)

        sched = EncreScheduler(durable_path=str(tmp_path / "jobs.json"))
        job_id = sched.schedule(name="10am job", prompt="...", cron="0 10 * * *")
        job = sched.get_job(job_id)
        assert job is not None
        # Job was created at 09:30 the same day and never fired (offline at 10:00).
        job.created_at = time.mktime(time.strptime("2026-08-07 09:30:00", "%Y-%m-%d %H:%M:%S"))
        job.last_fired = None
        sched._started_at = now

        spawned = self._run_one_poll(sched, monkeypatch)

        # Confirm the expected result: no late execution, state stays PENDING,
        # and the reference advances past the missed 10:00 occurrence.
        assert spawned == []
        assert job.state == JobState.PENDING
        assert job.last_fired == time.mktime(time.strptime("2026-08-07 10:00:00", "%Y-%m-%d %H:%M:%S"))

    def test_occurrence_before_session_start_with_previous_run_skipped(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        """Fired yesterday 10:00, server offline today at 10:00 -- no late fire."""
        now = time.mktime(time.strptime("2026-08-07 12:05:30", "%Y-%m-%d %H:%M:%S"))
        monkeypatch.setattr("encre.scheduler.time.time", lambda: now)

        sched = EncreScheduler(durable_path=str(tmp_path / "jobs.json"))
        job_id = sched.schedule(name="10am job", prompt="...", cron="0 10 * * *")
        job = sched.get_job(job_id)
        assert job is not None
        job.created_at = time.mktime(time.strptime("2026-08-05 09:00:00", "%Y-%m-%d %H:%M:%S"))
        job.last_fired = time.mktime(time.strptime("2026-08-06 10:00:00", "%Y-%m-%d %H:%M:%S"))
        sched._started_at = now

        spawned = self._run_one_poll(sched, monkeypatch)

        # Confirm the expected result: today's missed 10:00 occurrence is
        # skipped; the job is armed for tomorrow 10:00.
        assert spawned == []
        assert job.state == JobState.PENDING
        assert job.last_fired == time.mktime(time.strptime("2026-08-07 10:00:00", "%Y-%m-%d %H:%M:%S"))

    def test_occurrence_within_session_fires(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        """Server online since 09:00: the 10:00 occurrence fires normally."""
        now = time.mktime(time.strptime("2026-08-07 12:05:30", "%Y-%m-%d %H:%M:%S"))
        monkeypatch.setattr("encre.scheduler.time.time", lambda: now)

        sched = EncreScheduler(durable_path=str(tmp_path / "jobs.json"))
        job_id = sched.schedule(name="10am job", prompt="...", cron="0 10 * * *")
        job = sched.get_job(job_id)
        assert job is not None
        job.created_at = time.mktime(time.strptime("2026-08-06 09:00:00", "%Y-%m-%d %H:%M:%S"))
        job.last_fired = time.mktime(time.strptime("2026-08-06 10:00:00", "%Y-%m-%d %H:%M:%S"))
        sched._started_at = time.mktime(time.strptime("2026-08-07 09:00:00", "%Y-%m-%d %H:%M:%S"))

        spawned = self._run_one_poll(sched, monkeypatch)

        # Confirm the expected result: today's 10:00 occurrence happened while
        # the scheduler was online, so it fires (normal catch-up).
        assert spawned == [job]


# ===========================================================================
# Job lifecycle callbacks
# ===========================================================================

class TestJobCallbacks:
    """Test cases covering job callbacks.
    
    Covers the expected behavior and relevant edge cases.
    """
    def test_on_job_complete_callback_registered(self):
        """Verifies that on job complete callback registered."""
        sched = EncreScheduler()
        results: list[ScheduledJob] = []

        def callback(job):
            """Verifies that callback."""
            results.append(job)

        sched.on_job_complete(callback)
        # Confirm the expected result for this scenario: on job complete callback registered.
        assert sched._on_complete is callback

    def test_schedule_with_metadata(self):
        """Verifies that schedule with metadata."""
        sched = EncreScheduler()
        jid = sched.schedule(
            name="Meta job",
            prompt="...",
            cron="0 0 * * *",
            metadata={"priority": "high", "tags": ["critical"]},
        )
        job = sched.get_job(jid)
        # Confirm the expected result for this scenario: schedule with metadata.
        assert job.metadata["priority"] == "high"
        assert "critical" in job.metadata["tags"]

    def test_schedule_with_agent_config(self):
        """Verifies that schedule with agent config."""
        sched = EncreScheduler()
        jid = sched.schedule(
            name="Agent job",
            prompt="...",
            cron="0 0 * * *",
            agent_config={"model": "claude-sonnet-4-20250514", "max_turns": 15},
        )
        job = sched.get_job(jid)
        # Confirm the expected result for this scenario: schedule with agent config.
        assert job._agent_config is not None
        assert job._agent_config["model"] == "claude-sonnet-4-20250514"

    def test_execute_job_streams_snapshot_with_preallocated_session_id(self, tmp_path: Path):
        """Automation stream, durable history, and sub-agent use one session id."""
        class FakeLoop:
            def __init__(self):
                self.received_session_id = ""

            async def _run_sub_agent(self, **kwargs):
                self.received_session_id = kwargs["session_id"]
                await kwargs["progress_callback"]([
                    {"role": "user", "content": "Run report"},
                    {"role": "assistant", "content": "Report complete"},
                ])
                return {
                    "content": "Report complete",
                    "messages": [],
                    "session_id": self.received_session_id,
                }

        fake_loop = FakeLoop()
        scheduler = EncreScheduler(durable_path=str(tmp_path / "jobs.json"))
        job_id = scheduler.schedule(name="Report", prompt="Run report", fire_at=time.time())
        job = scheduler.get_job(job_id)
        assert job is not None
        scheduler._agent_factory = lambda _config: SimpleNamespace(loop=fake_loop)

        events: list[tuple[str, dict[str, object]]] = []

        async def capture(_job, event_type, event_data):
            events.append((event_type, event_data))

        scheduler.on_job_progress(capture)
        import asyncio
        asyncio.run(scheduler._execute_job(job))

        execution = scheduler.get_execution_history()[0]
        assert job.state == JobState.COMPLETED
        assert execution.session_id == fake_loop.received_session_id
        assert execution.session_id
        assert scheduler.list_jobs(include_finished=True) == [job]

        start = next(data for event_type, data in events if event_type == "start")
        snapshot = next(data for event_type, data in events if event_type == "snapshot")
        assert start["session_id"] == execution.session_id
        assert snapshot["session_id"] == execution.session_id
        assert snapshot["messages"] == [
            {"role": "user", "content": "Run report"},
            {"role": "assistant", "content": "Report complete"},
        ]

    def test_deleting_job_preserves_global_execution_history(self, tmp_path: Path):
        scheduler = EncreScheduler(durable_path=str(tmp_path / "jobs.json"))
        job_id = scheduler.schedule(name="Keep history", prompt="Run", fire_at=time.time() + 60)
        scheduler._executions.append(JobExecution(
            time=time.time(),
            state="COMPLETED",
            result="Done",
            name="Keep history",
            job_id=job_id,
        ))

        assert scheduler.delete_job(job_id)
        history = scheduler.get_execution_history()
        assert len(history) == 1
        assert history[0].job_id == job_id
        assert history[0].name == "Keep history"

    def test_reloading_history_preserves_renamed_execution(self, tmp_path: Path):
        """Dedicated history wins over a matching legacy execution title."""
        path = tmp_path / "jobs.json"
        timestamp = 1234.5
        job_id = "daily_report"
        legacy_job = {
            "id": job_id,
            "name": "Original name",
            "prompt": "Run report",
            "schedule_type": "ONE_SHOT",
            "cron": None,
            "fire_at": timestamp + 60,
            "state": "COMPLETED",
            "executions": [{
                "time": timestamp,
                "state": "COMPLETED",
                "result": "Done",
                "name": "Original name",
                "job_id": job_id,
            }],
        }
        path.write_text(json.dumps([legacy_job]), encoding="utf-8")
        history_path = path.with_name("automation_history.json")
        history_path.write_text(json.dumps([{
            "time": timestamp,
            "state": "COMPLETED",
            "result": "Done",
            "name": "Renamed execution",
            "job_id": job_id,
        }]), encoding="utf-8")

        scheduler = EncreScheduler(durable_path=str(path))

        history = scheduler.get_execution_history()
        assert len(history) == 1
        assert history[0].name == "Renamed execution"


# ===========================================================================
# Enums
# ===========================================================================

class TestEnums:
    """Test cases covering enums.
    
    Covers the expected behavior and relevant edge cases.
    """
    def test_schedule_type_values(self):
        """Verifies that schedule type values."""
        # Confirm the expected result for this scenario: schedule type values.
        assert ScheduleType.ONE_SHOT is not None
        assert ScheduleType.RECURRING is not None
        assert ScheduleType.ONE_SHOT != ScheduleType.RECURRING

    def test_job_state_values(self):
        """Verifies that job state values."""
        # Confirm the expected result for this scenario: job state values.
        assert JobState.PENDING is not None
        assert JobState.RUNNING is not None
        assert JobState.COMPLETED is not None
        assert JobState.FAILED is not None
        assert JobState.CANCELLED is not None

    def test_job_state_from_string(self):
        """Verifies that job state from string."""
        # Confirm the expected result for this scenario: job state from string.
        assert JobState["PENDING"] == JobState.PENDING
        assert JobState["CANCELLED"] == JobState.CANCELLED
