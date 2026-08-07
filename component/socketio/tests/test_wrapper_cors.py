def _cors_allowed(wrapper_loader, value):
    return wrapper_loader(cors=value)["cors_allowed_origins"]


def test_cors_unset_is_empty_list(wrapper_loader):
    assert wrapper_loader(cors=None)["cors_allowed_origins"] == []


def test_cors_empty_string_is_empty_list(wrapper_loader):
    assert _cors_allowed(wrapper_loader, "") == []


def test_cors_whitespace_only_is_empty_list(wrapper_loader):
    assert _cors_allowed(wrapper_loader, "   ") == []


def test_cors_single_origin(wrapper_loader):
    assert _cors_allowed(wrapper_loader, "https://a.example") == ["https://a.example"]


def test_cors_multiple_origins(wrapper_loader):
    assert _cors_allowed(wrapper_loader, "https://a.example,https://b.example") == [
        "https://a.example",
        "https://b.example",
    ]


def test_cors_trims_whitespace_around_origins(wrapper_loader):
    # A space-prefixed origin never matches a browser's Origin header, so the
    # operator's second origin would be silently dropped.
    assert _cors_allowed(wrapper_loader, "https://a.example, https://b.example") == [
        "https://a.example",
        "https://b.example",
    ]


def test_cors_drops_empty_entries(wrapper_loader):
    # A trailing comma must not leak an empty-string origin into the allow list.
    assert _cors_allowed(wrapper_loader, "https://a.example,") == ["https://a.example"]
