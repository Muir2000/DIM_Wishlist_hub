"""ingest 모듈이 backend/app 패키지를 import 할 수 있도록 sys.path 를 보정."""
import pathlib
import sys

_BACKEND = pathlib.Path(__file__).resolve().parents[1] / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))
