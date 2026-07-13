"""Tolerancja developer-fields (Connect IQ) dla fitparse w pipeline fitmodel.

Gdy dev-pole nie ma deklaracji, zwracamy placeholder 1-bajtowy zamiast
FitParseError("No such field N for dev_data_index M") -> parser konsumuje
wlasciwa liczbe bajtow i czyta dalej standardowe pola (moc/HR/pozycja).
Import ma efekt uboczny: naklada patch raz. Ta sama logika co w
qbot_activity_ingest (raport), ktorej pipeline fitmodel wczesniej nie mial."""
import fitparse.base as _fb
import fitparse.records as _fr

_BYTE_BT = next((bt for bt in _fr.BASE_TYPES.values() if getattr(bt, "size", None) == 1), None)
_ORIG_GET_DEV_TYPE = _fb.get_dev_type


def _safe_get_dev_type(dev_data_index, field_def_num):
    try:
        return _ORIG_GET_DEV_TYPE(dev_data_index, field_def_num)
    except Exception:
        return _fr.DevField(
            dev_data_index=dev_data_index, def_num=field_def_num, type=_BYTE_BT,
            name="unknown_dev_%s_%s" % (dev_data_index, field_def_num),
            units=None, native_field_num=None,
        )


_fb.get_dev_type = _safe_get_dev_type
