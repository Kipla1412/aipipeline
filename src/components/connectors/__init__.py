import logging
import importlib

"""
Connectors Package
==================
Purpose:
    A unified interface for connecting to various data sources.
"""

from .factory import ConnectorFactory
from .base import BaseConnector
from .jina import JinaConnector

_OPTIONAL = {
    "RDBMSConnector": "rdbms",
    "GmailConnector": "gmail",
    "ArxivConnector": "arxiv",
    "ElasticsearchConnector": "elasticsearch",
    "OpensearchConnector": "opensearch",
    "S3Connector": "s3",
}
for _cls, _mod in _OPTIONAL.items():
    try:
        m = importlib.import_module(f".{_mod}", __package__)
        globals()[_cls] = getattr(m, _cls)
    except (ImportError, AttributeError):
        globals()[_cls] = None

__all__ = ["ConnectorFactory", "BaseConnector", "JinaConnector"] + list(_OPTIONAL.keys())

logging.getLogger(__name__).addHandler(logging.NullHandler())