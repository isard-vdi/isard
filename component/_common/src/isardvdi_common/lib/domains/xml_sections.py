#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Layer 2 queries for the apiv4 XML-sections editor service.

Mirrors the table-level reads/writes that previously lived inline in
``component/apiv4/src/api/services/xml_sections.py``. The pure-XML
splitting/merging helpers stay in apiv4 — only the rdb-shaped operations
move here.

Tables touched:
* ``domains`` — read xml + create_dict; write xml + xml_protected_sections.
* ``hypervisors`` — read cached domain_capabilities from any online hyp.
* ``virt_install`` — read xml; insert / update template rows.
"""

from isardvdi_common.connections.rethink_connection_factory import (
    RethinkSharedConnection,
)
from isardvdi_common.helpers.xml_compression import compress_xml, decompress_xml
from rethinkdb import r


class XmlSectionsProcessed(RethinkSharedConnection):
    """Table-level queries for the XML-sections editor.

    Methods are split by table noun (``..._domain``, ``..._virt_install``,
    ``..._hypervisor_caps``) so each is unambiguous about which table
    it touches.
    """

    @classmethod
    def update_domain_xml_and_protected(
        cls, domain_id: str, xml: str, protected_sections: list[str]
    ) -> None:
        """Persist the merged XML and ``xml_protected_sections`` list.

        ``protected_sections`` is wrapped in ``r.literal(...)`` so the
        list replaces (rather than recursively merges with) the existing
        nested array — otherwise removed sections would never disappear.
        """
        with cls._rdb_context():
            r.table("domains").get(domain_id).update(
                {
                    "xml": compress_xml(xml),
                    "create_dict": {
                        "xml_protected_sections": r.literal(protected_sections)
                    },
                }
            ).run(cls._rdb_connection)

    @classmethod
    def get_domain_capabilities(cls) -> dict:
        """Fetch ``info.domain_capabilities`` from any hypervisor that
        has populated it.

        Returns the first non-empty ``domain_capabilities`` dict, or
        ``{}`` if no hypervisor has reported capabilities yet.
        """
        with cls._rdb_context():
            hyps = list(
                r.table("hypervisors")
                .has_fields({"info": {"domain_capabilities": True}})
                .filter(
                    lambda hyp: hyp["info"]["domain_capabilities"].keys().count() > 0
                )
                .pluck({"info": {"domain_capabilities": True}})
                .limit(1)
                .run(cls._rdb_connection)
            )
        if hyps:
            return hyps[0].get("info", {}).get("domain_capabilities", {})
        return {}

    @classmethod
    def get_domain(cls, domain_id: str) -> dict | None:
        """Read a single domain row.

        Returns the row dict or ``None`` when the id doesn't exist.
        Used by the save-as-virt_install path which needs the live
        domain's xml as the merge base.
        """
        with cls._rdb_context():
            row = (
                r.table("domains").get(domain_id).default(None).run(cls._rdb_connection)
            )
        if row is not None and "xml" in row:
            row["xml"] = decompress_xml(row.get("xml"))
        return row

    @classmethod
    def get_virt_install(cls, virt_id: str) -> dict | None:
        """Read a single virt_install row.

        Returns the row dict or ``None`` when the id doesn't exist.
        """
        with cls._rdb_context():
            return (
                r.table("virt_install")
                .get(virt_id)
                .default(None)
                .run(cls._rdb_connection)
            )

    @classmethod
    def update_virt_install_xml(cls, virt_id: str, xml: str) -> None:
        """Persist a rebuilt XML on a virt_install row."""
        with cls._rdb_context():
            r.table("virt_install").get(virt_id).update({"xml": xml}).run(
                cls._rdb_connection
            )

    @classmethod
    def insert_virt_install(cls, record: dict) -> None:
        """Insert a new virt_install row.

        Caller is responsible for shaping ``record`` and for the
        prior duplicate check (see ``get_virt_install``).
        """
        with cls._rdb_context():
            r.table("virt_install").insert(record).run(cls._rdb_connection)

    @classmethod
    def list_virt_installs(cls) -> list[dict]:
        """Return all virt_install rows ordered by name, plucking only the
        fields needed for the media-install selector."""
        with cls._rdb_context():
            return list(
                r.table("virt_install")
                .pluck("id", "name", "description", "vers")
                .order_by("name")
                .run(cls._rdb_connection)
            )
