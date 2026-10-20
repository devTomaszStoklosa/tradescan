"""Wiring for the commands: the data provider and the use cases built from the settings and flags."""

from __future__ import annotations

import argparse

from tradescan.config import Settings
from tradescan.data.provider import DataProvider
from tradescan.parallel import ProcessRunner
from tradescan.services.composition import UseCases, build_use_cases, default_provider


def provider(settings: Settings, args: argparse.Namespace) -> DataProvider:
    return default_provider(settings, use_cache=not getattr(args, "no_cache", False))


def use_cases(settings: Settings, args: argparse.Namespace) -> UseCases:
    return build_use_cases(settings, provider(settings, args), runner=ProcessRunner())
