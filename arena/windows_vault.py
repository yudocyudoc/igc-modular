"""Native Windows Credential Manager adapter. No service, master key or crypto file.

Uses documented CredReadW/CredWriteW/CredFree for this user's credential set.
Only igc-arena/<name> generic credentials are addressed; no enumeration.
"""
import ctypes
import re

from .common import ArenaError

DWORD = ctypes.c_uint32


class FileTime(ctypes.Structure):
    _fields_ = [("low", DWORD), ("high", DWORD)]


class Credential(ctypes.Structure):
    _fields_ = [("Flags", DWORD), ("Type", DWORD), ("TargetName", ctypes.c_wchar_p),
                ("Comment", ctypes.c_wchar_p), ("LastWritten", FileTime),
                ("CredentialBlobSize", DWORD), ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
                ("Persist", DWORD), ("AttributeCount", DWORD), ("Attributes", ctypes.c_void_p),
                ("TargetAlias", ctypes.c_wchar_p), ("UserName", ctypes.c_wchar_p)]


class WindowsVault:
    priority = 1

    def __init__(self, *, dll=None, last_error=None):
        self.api = dll if dll is not None else ctypes.WinDLL("Advapi32.dll", use_last_error=True)
        self.last_error = last_error or ctypes.get_last_error
        self.api.CredReadW.argtypes = [ctypes.c_wchar_p, DWORD, DWORD, ctypes.POINTER(ctypes.POINTER(Credential))]
        self.api.CredReadW.restype = ctypes.c_int
        self.api.CredWriteW.argtypes = [ctypes.POINTER(Credential), DWORD]
        self.api.CredWriteW.restype = ctypes.c_int
        self.api.CredFree.argtypes = [ctypes.c_void_p]
        self.api.CredFree.restype = None

    def _target(self, service, name):
        if service != "igc-arena" or not re.fullmatch(r"[A-Za-z0-9_./-]{1,180}", name):
            raise ArenaError("Invalid Arena vault reference.")
        return service + "/" + name

    def get_password(self, service, name):
        pointer = ctypes.POINTER(Credential)()
        if not self.api.CredReadW(self._target(service, name), 1, 0, ctypes.byref(pointer)):
            if self.last_error() == 1168:  # ERROR_NOT_FOUND
                return None
            raise ArenaError("Windows vault is unavailable in this logon session.")
        try:
            item = pointer.contents
            if item.Type != 1 or item.CredentialBlobSize > 2560 or item.CredentialBlobSize % 2:
                raise ArenaError("Invalid Arena credential in Windows vault.")
            return ctypes.string_at(item.CredentialBlob, item.CredentialBlobSize).decode("utf-16-le")
        finally:
            self.api.CredFree(pointer)

    def set_password(self, service, name, value):
        raw = value.encode("utf-16-le")
        if not raw or len(raw) > 2560:
            raise ArenaError("Credential is empty or exceeds Windows vault capacity.")
        blob = (ctypes.c_ubyte * len(raw)).from_buffer_copy(raw)
        item = Credential(Type=1, TargetName=self._target(service, name),
                          CredentialBlobSize=len(raw), CredentialBlob=blob, Persist=2, UserName="igc-arena")
        try:
            if not self.api.CredWriteW(ctypes.byref(item), 0):
                raise ArenaError("Windows vault could not store the credential in this logon session.")
        finally:
            ctypes.memset(blob, 0, len(raw))

