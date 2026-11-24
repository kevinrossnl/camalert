"""Adapters per device type (enigma2: OpenWebif + ssh; kodi: JSON-RPC), the CamAlert API and Home Assistant.

Every device adapter has the same interface (see Enigma2 and Kodi): info, snapshot, mute, prepare, restore,
screenshot, geometry_settings. Every change is written to the state (write-ahead) before it is made, so that
`run.py --restore last` can undo it after a crash.
"""
