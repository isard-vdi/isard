"""Guard against the GPU-port regression where ``ui_actions`` called a
``domain_xml`` helper it never imported.

``controllers/ui_actions`` cannot be imported bare (it pulls the engine's DB,
libvirt and rethink stack), so we ast-parse it: collect the names imported from
``engine.models.domain_xml`` and the bare function calls, and assert every
``domain_xml`` helper that is *called* is also *imported*. This is exactly the
failure that broke every GPU desktop start with
``NameError: name 'add_iothread_pinning' is not defined`` -- the optimization
block called it under ``if _allow["iothreads"]`` but the import was dropped in
the port, so the surrounding try/except discarded all NUMA/hugepage tuning.
"""

import ast
import os

_SRC = os.path.join(os.path.dirname(__file__), "ui_actions.py")
_DOMAIN_XML_SRC = os.path.join(
    os.path.dirname(__file__), "..", "models", "domain_xml.py"
)


def _tree():
    return ast.parse(open(_SRC).read())


def _domain_xml_imported_names(tree):
    names = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.ImportFrom)
            and node.module
            and node.module.endswith("domain_xml")
        ):
            names.update(a.name for a in node.names)
    return names


def _domain_xml_exported_names():
    names = set()
    for node in ast.parse(open(_DOMAIN_XML_SRC).read()).body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            names.add(node.name)
    return names


def test_iothread_pinning_is_imported():
    assert "add_iothread_pinning" in _domain_xml_imported_names(_tree())


def test_every_called_domain_xml_helper_is_imported():
    tree = _tree()
    imported = _domain_xml_imported_names(tree)
    exported = _domain_xml_exported_names()
    called = {
        n.func.id
        for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
    }
    # Any name that is a real domain_xml helper AND is called must be imported.
    missing = {n for n in called if n in exported and n not in imported}
    assert not missing, f"called but not imported from domain_xml: {sorted(missing)}"
