"""Local unit tests for the isard OVMF varstore checker (docker/hypervisor/firmware)."""

import importlib.util
from pathlib import Path

_MODULE_PATH = Path(__file__).resolve().parents[1] / "firmware" / "firmware_vars.py"
_spec = importlib.util.spec_from_file_location("firmware_vars", _MODULE_PATH)
firmware_vars = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(firmware_vars)


def _good_print():
    return "\n".join(
        [
            "name=CustomMode guid=guid:EfiCustomModeEnable size=1",
            "  bool: off",
            "",
            "name=KEK guid=guid:EfiGlobalVariable size=4042",
            "  siglist type=guid:EfiCertX509 count=1",
            "    subject CN=Red Hat Secure Boot (PK/KEK key 1)",
            "    issuer CN=Red Hat Secure Boot (PK/KEK key 1)",
            "  siglist type=guid:EfiCertX509 count=1",
            "    subject CN=Microsoft Corporation KEK CA 2011",
            "    issuer CN=Microsoft Corporation Third Party Marketplace Root",
            "  siglist type=guid:EfiCertX509 count=1",
            "    subject CN=Microsoft Corporation KEK 2K CA 2023",
            "    issuer CN=Microsoft RSA Devices Root CA 2021",
            "",
            "name=PK guid=guid:EfiGlobalVariable size=976",
            "  siglist type=guid:EfiCertX509 count=1",
            "    subject CN=Red Hat Secure Boot (PK/KEK key 1)",
            "",
            "name=SecureBootEnable guid=guid:EfiSecureBootEnableDisable size=1",
            "  bool: ON",
            "",
            "name=db guid=guid:EfiImageSecurityDatabase size=7636",
            "  siglist type=guid:EfiCertX509 count=1",
            "    subject CN=Microsoft Windows Production PCA 2011",
            "  siglist type=guid:EfiCertX509 count=1",
            "    subject CN=Windows UEFI CA 2023",
            "  siglist type=guid:EfiCertX509 count=1",
            "    subject CN=Microsoft Corporation UEFI CA 2011",
            "  siglist type=guid:EfiCertX509 count=1",
            "    subject CN=Microsoft UEFI CA 2023",
            "  siglist type=guid:EfiCertX509 count=1",
            "    subject CN=Microsoft Option ROM UEFI CA 2023",
            "",
            "name=dbx guid=guid:EfiImageSecurityDatabase size=21292",
            f"  siglist type=guid:EfiCertSha256 count={firmware_vars.EXPECTED_DBX_SHA256_COUNT}",
        ]
    )


def test_good_varstore_passes():
    assert firmware_vars.check(firmware_vars.parse_print_output(_good_print())) == []


def test_parse_collects_subjects_and_dbx_count():
    variables = firmware_vars.parse_print_output(_good_print())
    assert variables["PK"]["x509"] == ["Red Hat Secure Boot (PK/KEK key 1)"]
    assert len(variables["KEK"]["x509"]) == 3
    assert len(variables["db"]["x509"]) == 5
    assert variables["dbx"]["sha256_count"] == firmware_vars.EXPECTED_DBX_SHA256_COUNT
    assert variables["dbx"]["x509"] == []


def test_missing_db_certificate_fails():
    text = _good_print().replace("    subject CN=Microsoft UEFI CA 2023\n", "")
    errors = firmware_vars.check(firmware_vars.parse_print_output(text))
    assert any("Microsoft UEFI CA 2023" in e for e in errors)


def test_missing_kek_certificate_fails():
    text = _good_print().replace(
        "    subject CN=Microsoft Corporation KEK 2K CA 2023\n", ""
    )
    errors = firmware_vars.check(firmware_vars.parse_print_output(text))
    assert any("KEK" in e and "KEK 2K CA 2023" in e for e in errors)


def test_pca_2011_revoked_in_dbx_fails():
    # A db cert appearing as an x509 entry in dbx means it has been revoked.
    text = (
        _good_print()
        + "\n"
        + "\n".join(
            [
                "  siglist type=guid:EfiCertX509 count=1",
                "    subject CN=Microsoft Windows Production PCA 2011",
                "    issuer CN=Microsoft Root Certificate Authority 2010",
            ]
        )
    )
    errors = firmware_vars.check(firmware_vars.parse_print_output(text))
    assert any(
        "dbx" in e and "Microsoft Windows Production PCA 2011" in e for e in errors
    )


def test_empty_dbx_fails():
    text = _good_print().replace(
        f"count={firmware_vars.EXPECTED_DBX_SHA256_COUNT}", "count=1"
    )
    errors = firmware_vars.check(firmware_vars.parse_print_output(text))
    assert any("dbx" in e and "revocation" in e for e in errors)
