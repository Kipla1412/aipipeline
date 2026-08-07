"""Interface definitions for the transformer pipeline.

Small, focused interfaces following Interface Segregation Principle.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class IObservationBuilder(ABC):
    @abstractmethod
    def build(self, raw_data: dict[str, Any]) -> list[dict[str, Any]]: ...


class IDiagnosisBuilder(ABC):
    @abstractmethod
    def build(self, raw_data: dict[str, Any]) -> list[dict[str, Any]]: ...


class IMedicationBuilder(ABC):
    @abstractmethod
    def build(self, raw_data: dict[str, Any]) -> list[dict[str, Any]]: ...


class IObservationNormalizer(ABC):
    @abstractmethod
    def normalize(self, observations: list[dict[str, Any]]) -> list[dict[str, Any]]: ...


class IObservationValidator(ABC):
    @abstractmethod
    def validate(self, observations: list[dict[str, Any]]) -> list[dict[str, Any]]: ...


class IPatientBuilder(ABC):
    @abstractmethod
    def build(self, raw_data: dict[str, Any]) -> dict[str, Any]: ...
