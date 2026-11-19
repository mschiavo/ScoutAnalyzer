from enum import Enum
from typing import Dict, Any

class Severity(Enum):
    WARNING = "WARNING"
    ERRORE = "ERRORE"
    ERRORE_CRITICO = "ERRORE_CRITICO"

    # Alias di compatibilità
    ERROR = "ERRORE"
    CRITICAL = "ERRORE_CRITICO"

class ValidationIssue:
    def __init__(self, code: str, message: str, severity: Severity, section: str = "", line_num: int = None):
        self.code = code
        self.message = message
        self.severity = severity
        self.section = section
        self.line_num = line_num

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "severity": self.severity.value,
            "section": self.section,
            "line_num": self.line_num
        }

    def __repr__(self):
        line_info = f" (linea {self.line_num})" if self.line_num else ""
        return f"[{self.severity.value}] [{self.section}{line_info}] {self.code}: {self.message}"
