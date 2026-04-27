# Safe string formatting that prevents SSTI via str.format()
# Rejects attribute access ({key.attr}) and item access ({key[0]})
import string


class _SafeFormatter(string.Formatter):
    def get_field(self, field_name, args, kwargs):
        if not field_name.isidentifier():
            raise ValueError(f"Invalid format field: {field_name!r}")
        return super().get_field(field_name, args, kwargs)


_safe_formatter = _SafeFormatter()


def safe_format(template, **kwargs):
    """Format a string template safely, blocking attribute/item access."""
    try:
        return _safe_formatter.format(template, **kwargs)
    except (ValueError, KeyError, IndexError):
        return template
