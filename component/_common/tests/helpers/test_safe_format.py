# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for ``safe_format``: an str.format() wrapper that blocks the
attribute / item access escape hatches that turn ``str.format`` into
a server-side template injection vector when a user-controlled
template is rendered against a sensitive context.

Background: ``"{user.password}".format(user=...)`` resolves the
attribute on whatever ``user`` is passed in, which can be a Flask
session, an SQLAlchemy model, anything; the same applies to
``"{x[0]}".format(x=...)``. Production callers that interpolate
user-provided strings into messages MUST go through ``safe_format``
so that ``{x.y}`` and ``{x[i]}`` are rejected.

Contract being pinned:

1. Plain field substitution still works.
2. Attribute access (``{x.attr}``) is rejected — fall back to the
   raw template, don't render the attribute.
3. Item access (``{x[0]}``) is rejected — same fallback.
4. Missing kwargs / empty kwargs don't blow up.
5. Templates without substitutions pass through unchanged.
"""

from isardvdi_common.helpers.safe_format import safe_format


def test_safe_format_basic_substitution():
    """Happy path: a single named field is substituted from kwargs."""
    assert safe_format("Hello {name}", name="world") == "Hello world"


def test_safe_format_multiple_fields():
    """Multiple named fields each get substituted in order."""
    assert (
        safe_format("{greeting}, {name}!", greeting="Hi", name="Alice") == "Hi, Alice!"
    )


def test_safe_format_no_substitutions_passes_through():
    """A template with no ``{...}`` returns unchanged. Pin this so a
    refactor that always-runs-formatter (and silently strips literal
    braces or similar) breaks loud.
    """
    assert safe_format("Hello world") == "Hello world"


def test_safe_format_blocks_attribute_access():
    """``{name.upper}`` would resolve the ``upper`` attribute on the
    str ``name`` value (a callable). Template injection vector.
    The custom ``_SafeFormatter.get_field`` rejects any field name
    that isn't a plain identifier; the outer try/except returns the
    raw template.
    """
    template = "{name.upper}"
    result = safe_format(template, name="alice")
    # Falls back to the raw template — the attribute was NOT
    # resolved, NOT rendered.
    assert result == template
    # Sanity: the value ``alice`` did not bleed into the output.
    assert "alice" not in result


def test_safe_format_blocks_dotted_path():
    """Multi-level attribute access (``{a.b.c}``) — same vector,
    same rejection.
    """

    class Outer:
        class Inner:
            secret = "do-not-render"

    template = "{obj.Inner.secret}"
    assert safe_format(template, obj=Outer) == template


def test_safe_format_blocks_item_access_by_index():
    """``{x[0]}`` would index into the value of ``x``. If ``x`` is
    a sensitive list (session token bytes, etc.), this leaks.
    Reject via the ``isidentifier`` guard which fails on the
    bracket char.
    """
    template = "{items[0]}"
    assert safe_format(template, items=["secret-0", "secret-1"]) == template


def test_safe_format_blocks_item_access_by_key():
    """``{x[key]}`` against a dict value — same item-access vector,
    different syntax. Both must fall back.
    """
    template = "{config[password]}"
    assert safe_format(template, config={"password": "do-not-render"}) == template


def test_safe_format_missing_kwarg_returns_template():
    """A template references a kwarg that wasn't supplied -> KeyError
    in the formatter -> the outer except catches it -> raw template
    returned. Locks in the fail-safe contract: bad templates don't
    raise into the request handler.
    """
    template = "Hello {missing}"
    assert safe_format(template) == template
    # The literal ``{missing}`` must remain — neither stripped nor
    # rendered as None.
    assert "{missing}" in safe_format(template)


def test_safe_format_empty_kwargs_with_no_fields():
    """Empty kwargs + no fields -> still valid pass-through."""
    assert safe_format("static text") == "static text"


def test_safe_format_positional_args_via_index_blocked():
    """``{0}`` (positional) — the ``isidentifier`` guard rejects
    digit-only field names, so positional substitution is also
    not allowed. This is intentional: callers should always use
    named kwargs to make the template's bindings explicit and
    grep-able.
    """
    template = "{0}"
    assert safe_format(template, name="ignored") == template


def test_safe_format_does_not_mutate_template():
    """Same input twice -> same output twice. Pin to catch a
    refactor that introduces mutable shared state in the formatter.
    """
    template = "Hello {name}"
    a = safe_format(template, name="world")
    b = safe_format(template, name="world")
    assert a == b == "Hello world"
