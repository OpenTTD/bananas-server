def _safe_name(name):
    new_name = ""

    for letter in name:
        if (
            (letter >= "a" and letter <= "z")
            or (letter >= "A" and letter <= "Z")
            or (letter >= "0" and letter <= "9")
            or letter == "."
        ):
            new_name += letter
        elif new_name and new_name[-1] != "_":
            new_name += "_"

    return new_name.strip("._")


def safe_filename(content_entry):
    return (
        content_entry.unique_id.hex() + "-" + _safe_name(content_entry.name) + "-" + _safe_name(content_entry.version)
    )
