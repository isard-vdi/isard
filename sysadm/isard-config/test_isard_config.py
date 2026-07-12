"""Unit tests for the pure units of isard_config.

Stdlib unittest only (no pytest on the box). Run with:
    python3 -m unittest -v test_isard_config
These cover the *pure* logic — arg parsing, key map, value coercion, request
building, JWT decode, URL building. Live API behaviour is verified separately
against the running stack.
"""

import base64
import json
import unittest

import isard_config as ic


class TestNormalizeBaseUrl(unittest.TestCase):
    def test_strips_trailing_slash(self):
        self.assertEqual(ic.normalize_base_url("https://a.b/"), "https://a.b")

    def test_adds_https_when_scheme_missing(self):
        self.assertEqual(ic.normalize_base_url("a.b"), "https://a.b")

    def test_keeps_http_scheme(self):
        self.assertEqual(ic.normalize_base_url("http://a.b"), "http://a.b")

    def test_strips_path(self):
        # A bare host[:port] is what we want; drop any trailing path a user pastes.
        self.assertEqual(
            ic.normalize_base_url("https://a.b/isard-admin/"), "https://a.b"
        )


class TestBuildLoginUrl(unittest.TestCase):
    def test_form_provider(self):
        self.assertEqual(
            ic.build_login_url("https://a.b", "default"),
            "https://a.b/authentication/login?provider=form&category_id=default",
        )

    def test_category_is_url_encoded(self):
        url = ic.build_login_url("https://a.b", "my cat/x")
        self.assertIn("category_id=my+cat%2Fx", url)


class TestParseSetArg(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(
            ic.parse_set_arg("recycle_bin_cutoff=720"), ("recycle_bin_cutoff", "720")
        )

    def test_dotted_key(self):
        self.assertEqual(
            ic.parse_set_arg("logs_desktops.max_time=365"),
            ("logs_desktops.max_time", "365"),
        )

    def test_value_may_contain_equals(self):
        self.assertEqual(ic.parse_set_arg("k=a=b"), ("k", "a=b"))

    def test_missing_equals_raises(self):
        with self.assertRaises(ValueError):
            ic.parse_set_arg("noequals")

    def test_empty_key_raises(self):
        with self.assertRaises(ValueError):
            ic.parse_set_arg("=5")


class TestKeyMap(unittest.TestCase):
    def test_all_expected_keys_present(self):
        expected = {
            "recycle_bin_cutoff",
            "logs_desktops.max_time",
            "logs_desktops.action",
            "logs_users.max_time",
            "logs_users.action",
            "old_tasks.older_than",
            "old_tasks.enabled",
            "usage.daily_months",
            "usage.weekly_months",
            "usage.total_months",
        }
        self.assertEqual(set(ic.SETTINGS), expected)

    def test_unknown_key_lookup_raises(self):
        with self.assertRaises(KeyError):
            ic.get_setting("nope.nope")


class TestCoerceValue(unittest.TestCase):
    def test_int(self):
        s = ic.get_setting("recycle_bin_cutoff")
        self.assertEqual(ic.coerce_value(s, "720"), 720)

    def test_int_rejects_non_numeric(self):
        s = ic.get_setting("recycle_bin_cutoff")
        with self.assertRaises(ValueError):
            ic.coerce_value(s, "abc")

    def test_int_minimum_enforced(self):
        # old_tasks.older_than has a 86400s minimum
        s = ic.get_setting("old_tasks.older_than")
        with self.assertRaises(ValueError):
            ic.coerce_value(s, "10")
        self.assertEqual(ic.coerce_value(s, "604800"), 604800)

    def test_logs_max_time_minimum(self):
        s = ic.get_setting("logs_desktops.max_time")
        with self.assertRaises(ValueError):
            ic.coerce_value(s, "23")
        self.assertEqual(ic.coerce_value(s, "24"), 24)

    def test_bool_true_variants(self):
        s = ic.get_setting("old_tasks.enabled")
        for raw in ("true", "True", "1", "yes", "on"):
            self.assertIs(ic.coerce_value(s, raw), True)

    def test_bool_false_variants(self):
        s = ic.get_setting("old_tasks.enabled")
        for raw in ("false", "False", "0", "no", "off"):
            self.assertIs(ic.coerce_value(s, raw), False)

    def test_bool_rejects_garbage(self):
        s = ic.get_setting("old_tasks.enabled")
        with self.assertRaises(ValueError):
            ic.coerce_value(s, "maybe")

    def test_action_choices(self):
        s = ic.get_setting("logs_desktops.action")
        self.assertEqual(ic.coerce_value(s, "delete"), "delete")
        self.assertEqual(ic.coerce_value(s, "none"), "none")
        with self.assertRaises(ValueError):
            ic.coerce_value(s, "archive")

    def test_total_months_accepts_null(self):
        s = ic.get_setting("usage.total_months")
        for raw in ("null", "none", "None", ""):
            self.assertIsNone(ic.coerce_value(s, raw))
        self.assertEqual(ic.coerce_value(s, "24"), 24)

    def test_usage_bounds_match_spec(self):
        # From OpenAPI UsageRetentionConfig: daily min1/max120,
        # weekly min2/max120, total min1/max240.
        daily = ic.get_setting("usage.daily_months")
        self.assertEqual(ic.coerce_value(daily, "1"), 1)
        with self.assertRaises(ValueError):
            ic.coerce_value(daily, "0")
        with self.assertRaises(ValueError):
            ic.coerce_value(daily, "121")

        weekly = ic.get_setting("usage.weekly_months")
        self.assertEqual(ic.coerce_value(weekly, "2"), 2)
        with self.assertRaises(ValueError):
            ic.coerce_value(weekly, "1")

        total = ic.get_setting("usage.total_months")
        with self.assertRaises(ValueError):
            ic.coerce_value(total, "0")
        with self.assertRaises(ValueError):
            ic.coerce_value(total, "241")
        self.assertEqual(ic.coerce_value(total, "240"), 240)


class TestBuildSetRequest(unittest.TestCase):
    def test_path_kind_int(self):
        s = ic.get_setting("old_tasks.older_than")
        method, path, body = ic.build_set_request(s, 604800)
        self.assertEqual(method, "PUT")
        self.assertEqual(
            path, "/api/v4/admin/item/queues/old_tasks/config/max_time/604800"
        )
        self.assertIsNone(body)

    def test_path_kind_string_action(self):
        s = ic.get_setting("logs_desktops.action")
        method, path, body = ic.build_set_request(s, "delete")
        self.assertEqual(
            path, "/api/v4/admin/item/logs_desktops/config/old_entries/action/delete"
        )
        self.assertIsNone(body)

    def test_body_field_kind(self):
        s = ic.get_setting("recycle_bin_cutoff")
        method, path, body = ic.build_set_request(s, 720)
        self.assertEqual(method, "PUT")
        self.assertEqual(path, "/api/v4/item/recycle-bin/system/cutoff-time")
        self.assertEqual(body, {"recycle_bin_cuttoff_time": 720})

    def test_body_field_bool(self):
        s = ic.get_setting("old_tasks.enabled")
        method, path, body = ic.build_set_request(s, True)
        self.assertEqual(path, "/api/v4/admin/item/queues/old_tasks/config/enabled")
        self.assertEqual(body, {"enabled": True})

    def test_whole_object_kind_merges_current(self):
        # usage.* PUTs the whole retention object; the changed field is merged
        # onto the current values.
        s = ic.get_setting("usage.weekly_months")
        current = {"daily_months": 3, "weekly_months": 6, "total_months": None}
        method, path, body = ic.build_set_request(s, 8, current=current)
        self.assertEqual(method, "PUT")
        self.assertEqual(path, "/api/v4/admin/item/usage/retention")
        self.assertEqual(
            body, {"daily_months": 3, "weekly_months": 8, "total_months": None}
        )


class TestJwt(unittest.TestCase):
    @staticmethod
    def _make_token(payload):
        def seg(d):
            raw = json.dumps(d).encode()
            return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

        return f"{seg({'alg':'HS256'})}.{seg(payload)}.sig"

    def test_decode_payload(self):
        tok = self._make_token({"data": {"role_id": "admin"}})
        self.assertEqual(ic.decode_jwt_payload(tok)["data"]["role_id"], "admin")

    def test_decode_padding_needed(self):
        # payloads whose base64 length isn't a multiple of 4 must still decode
        tok = self._make_token({"data": {"role_id": "manager", "x": "y"}})
        self.assertEqual(ic.token_role(ic.decode_jwt_payload(tok)), "manager")

    def test_is_admin_true(self):
        p = {"data": {"role_id": "admin"}}
        self.assertTrue(ic.is_admin_payload(p))

    def test_is_admin_false(self):
        self.assertFalse(ic.is_admin_payload({"data": {"role_id": "manager"}}))

    def test_malformed_token_raises(self):
        with self.assertRaises(ValueError):
            ic.decode_jwt_payload("not-a-jwt")


class _FakeClient:
    """A tiny stand-in for Client that serves scripted GET responses and
    records PUTs. GET responses for the recycle_bin group can lag (simulating
    the apiv4 read cache) for a configurable number of reads."""

    def __init__(self, cutoff_after_writes, lag_reads=0):
        self._cutoff = 1
        self._target = cutoff_after_writes
        self._lag = lag_reads  # how many post-write GETs still return the old value
        self._written = False
        self.puts = []

    def get_json(self, path):
        if path.endswith("/recycle-bin/system/cutoff-time"):
            val = self._cutoff
            if self._written:
                if self._lag > 0:
                    self._lag -= 1  # still cached -> old value
                else:
                    val = self._target
            return {"recycle_bin_cuttoff_time": val}
        # every other group returns empty/defaults
        return {}

    def put_json(self, path, body):
        self.puts.append((path, body))
        self._written = True
        return body


class TestDoSetPolling(unittest.TestCase):
    def test_confirms_after_cache_lag(self):
        # first 3 post-write reads are stale, then it refreshes
        client = _FakeClient(cutoff_after_writes=720, lag_reads=3)
        slept = []
        fake_clock = {"t": 0.0}

        def clock():
            return fake_clock["t"]

        def sleeper(s):
            slept.append(s)
            fake_clock["t"] += s

        import io

        buf = io.StringIO()
        rc = ic.do_set(
            client,
            ["recycle_bin_cutoff=720"],
            assume_yes=True,
            verify_timeout=20.0,
            sleeper=sleeper,
            clock=clock,
            out=buf,
        )
        self.assertEqual(rc, 0)
        self.assertIn("CONFIRMED", buf.getvalue())
        self.assertEqual(
            client.puts,
            [
                (
                    "/api/v4/item/recycle-bin/system/cutoff-time",
                    {"recycle_bin_cuttoff_time": 720},
                )
            ],
        )

    def test_unconfirmed_when_cache_never_clears_in_window(self):
        client = _FakeClient(cutoff_after_writes=720, lag_reads=999)
        fake_clock = {"t": 0.0}

        def clock():
            return fake_clock["t"]

        def sleeper(s):
            fake_clock["t"] += s

        import io

        buf = io.StringIO()
        rc = ic.do_set(
            client,
            ["recycle_bin_cutoff=720"],
            assume_yes=True,
            verify_timeout=6.0,
            sleeper=sleeper,
            clock=clock,
            out=buf,
        )
        self.assertEqual(rc, 2)
        self.assertIn("UNCONFIRMED", buf.getvalue())
        # the write still happened (PUT accepted)
        self.assertEqual(len(client.puts), 1)


if __name__ == "__main__":
    unittest.main()
