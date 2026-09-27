# -*- coding: utf-8 -*-
"""Exceptions carrying an i18n key, so the message reaches the user translated."""


class UserError(ValueError):
    """An expected problem the user can fix (bad file, nothing selected...)."""

    def __init__(self, key, **params):
        super().__init__(key)
        self.key = key
        self.params = params


class SvgError(UserError):
    pass


class ProjectError(UserError):
    pass


class EngineError(UserError):
    pass


class Cancelled(Exception):
    """Raised by progress callbacks to abort a long operation."""
