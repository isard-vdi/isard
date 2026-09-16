# SPDX-License-Identifier: AGPL-3.0-or-later

"""Replacing a domain's whole XML must refuse what the engine could not
define. The body is a string since the schema stopped declaring it as an
object, so malformed XML now reaches the service instead of failing in
``compress_xml`` with a 500; it has to be turned away as a 400 before the
row is flipped to ``Updating``.
"""

import pytest
from api.services.error import Error


@pytest.fixture
def service(monkeypatch):
    from api.services.admin import domains as svc

    writes = []

    def _update_xml(cls, domain_id, data):
        writes.append((domain_id, data))
        return data.get("xml")

    monkeypatch.setattr(svc.DomainsProcessed, "update_xml", classmethod(_update_xml))
    monkeypatch.setattr(svc, "clear_domains_field_cache", lambda: None)
    yield svc.AdminDomainsService, writes


def test_a_well_formed_domain_xml_is_stored(service):
    admin_domains, writes = service
    xml = "<domain type='kvm'><name>d1</name></domain>"

    assert admin_domains.update_domain_xml("d-1", {"xml": xml}) == xml
    assert writes == [("d-1", {"xml": xml})]


@pytest.mark.parametrize(
    "xml",
    [
        "<domain><name>d1</name>",
        "not xml at all",
        "<!DOCTYPE d [<!ENTITY a 'b'>]><domain><name>&a;</name></domain>",
        "<network><name>n1</name></network>",
    ],
    ids=["unclosed", "plain-text", "entity-declaration", "wrong-root"],
)
def test_xml_the_engine_could_not_define_is_refused_before_any_write(service, xml):
    admin_domains, writes = service

    with pytest.raises(Error) as exc:
        admin_domains.update_domain_xml("d-1", {"xml": xml})

    assert exc.value.status_code == 400
    assert writes == []
