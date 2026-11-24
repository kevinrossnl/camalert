"""Exceptions of the runner."""


class SafetyError(Exception):
    """A safety step failed (mute, snapshot, restore): stop using this device."""


class Skip(Exception):
    """A precondition or a missing prerequisite: the device or scenario is skipped, never forced."""
