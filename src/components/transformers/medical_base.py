"""BaseTransformer — shared data type normalization for medical transformers."""

import logging
from datetime import datetime, date
from decimal import Decimal
from typing import Dict, Any

logger = logging.getLogger(__name__)


class BaseTransformer:
    def clean(self, data: Dict[str, Any]) -> Dict[str, Any]:
        clean_row = {}
        for key, value in data.items():
            if isinstance(value, (datetime, date)):
                clean_row[key] = value.isoformat()
            elif isinstance(value, Decimal):
                clean_row[key] = float(value)
            elif value is not None and not isinstance(value, (str, int, float, bool, list, dict)):
                clean_row[key] = str(value)
            else:
                clean_row[key] = value
        return clean_row
