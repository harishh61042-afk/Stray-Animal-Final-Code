"""Flask-WTF forms. ``form_data`` converts a validated form into a plain dict for the services."""


def int_or_none(value):
    """``coerce`` for optional ``SelectField`` values: ``""`` / ``None`` -> ``None``, otherwise an ``int``."""
    if value is None or str(value).strip() == "":
        return None
    return int(value)


def first_error(form):
    """One short, readable message for the first validation problem of ``form``.

    Small inline forms (assign, note, status ...) redirect back to the page and flash this message
    instead of re-rendering themselves.
    """
    for name, errors in form.errors.items():
        if not errors:
            continue
        if name == "csrf_token":
            return "Your session expired. Please reload the page and try again."
        field = form._fields.get(name)
        label = field.label.text.rstrip(":?* ") if field is not None else name.replace("_", " ").capitalize()
        message = errors[0] if isinstance(errors[0], str) else "is not valid."
        return f"{label}: {message}"
    return "Please check the form and try again."


def form_data(form, *exclude):
    """``{field_name: value}`` for every non-file, non-CSRF field of ``form``."""
    skip = {"csrf_token", "submit"} | set(exclude)
    data = {}
    for name, field in form._fields.items():
        if name in skip or field.type in ("FileField", "MultipleFileField", "SubmitField"):
            continue
        data[name] = field.data
    return data
