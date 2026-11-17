from sampling.validation import normalize_import


def put_series(repository, series_id, source_version, unit, rows, correction_parent=None):
    payload = normalize_import(series_id, source_version, unit, rows, correction_parent)
    return repository.put(payload)
