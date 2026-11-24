# -*- coding: utf-8 -*-
# CamAlert - show IP cameras on your TV.
# Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
"""ONVIF (SOAP 1.2) PTZ: envelopes, WS-Security digest and answer parsers."""

import re


# ONVIF (SOAP 1.2) -------------------------------------------------------------------------------------------------
ONVIF_NS = ('xmlns:s="http://www.w3.org/2003/05/soap-envelope" xmlns:tds="http://www.onvif.org/ver10/device/wsdl" '
            'xmlns:trt="http://www.onvif.org/ver10/media/wsdl" xmlns:tptz="http://www.onvif.org/ver20/ptz/wsdl" '
            'xmlns:tt="http://www.onvif.org/ver10/schema"')


def wsse_digest(password, nonce, created):
    """WS-Security UsernameToken PasswordDigest: Base64(SHA1(nonce + created + password)); nonce = raw bytes."""
    import base64
    import hashlib
    return base64.b64encode(hashlib.sha1(nonce + created.encode("utf-8") + password.encode("utf-8")).digest()).decode("ascii")


def onvif_created(timestamp):
    """Unix time -> '2026-11-23T20:15:00Z' (UTC, as ONVIF wants it)."""
    import time as _t
    return _t.strftime("%Y-%m-%dT%H:%M:%SZ", _t.gmtime(int(timestamp)))


def _xml(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def onvif_envelope(body, user=None, password="", nonce=None, created=None):
    """SOAP envelope; with a user a WS-Security UsernameToken (digest) header is added."""
    header = ""
    if user:
        import base64
        header = ('<s:Header><Security s:mustUnderstand="1" xmlns="http://docs.oasis-open.org/wss/2004/01/'
                  'oasis-200401-wss-wssecurity-secext-1.0.xsd"><UsernameToken><Username>%s</Username>'
                  '<Password Type="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-username-token-profile-1.0'
                  '#PasswordDigest">%s</Password><Nonce EncodingType="http://docs.oasis-open.org/wss/2004/01/'
                  'oasis-200401-wss-soap-message-security-1.0#Base64Binary">%s</Nonce><Created xmlns="http://docs.'
                  'oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd">%s</Created>'
                  '</UsernameToken></Security></s:Header>'
                  % (_xml(user), wsse_digest(password, nonce, created), base64.b64encode(nonce).decode("ascii"), created))
    return '<?xml version="1.0" encoding="UTF-8"?><s:Envelope %s>%s<s:Body>%s</s:Body></s:Envelope>' % (ONVIF_NS, header, body)


def onvif_body(action, token=None, vector=None):
    """SOAP body for: GetSystemDateAndTime, GetCapabilities, GetProfiles, ContinuousMove, Stop, GotoHomePosition."""
    if action == "GetSystemDateAndTime":
        return "<tds:GetSystemDateAndTime/>"
    if action == "GetCapabilities":
        return "<tds:GetCapabilities><tds:Category>All</tds:Category></tds:GetCapabilities>"
    if action == "GetProfiles":
        return "<trt:GetProfiles/>"
    tok = "<tptz:ProfileToken>%s</tptz:ProfileToken>" % _xml(token)
    if action == "ContinuousMove":
        x, y, z = vector
        return ('<tptz:ContinuousMove>%s<tptz:Velocity><tt:PanTilt x="%g" y="%g"/><tt:Zoom x="%g"/></tptz:Velocity>'
                '</tptz:ContinuousMove>' % (tok, x, y, z))
    if action == "Stop":
        return "<tptz:Stop>%s<tptz:PanTilt>true</tptz:PanTilt><tptz:Zoom>true</tptz:Zoom></tptz:Stop>" % tok
    if action == "GotoHomePosition":
        return "<tptz:GotoHomePosition>%s</tptz:GotoHomePosition>" % tok
    raise ValueError(action)


def _local(tag):
    return tag.rsplit("}", 1)[-1]


def onvif_xaddrs(xml):
    """GetCapabilities answer -> {"media": url, "ptz": url} (only what the camera offers)."""
    import xml.etree.ElementTree as ET
    out = {}
    for el in ET.fromstring(xml).iter():
        name = _local(el.tag).lower()
        if name in ("media", "ptz") and name not in out:
            for child in el:
                if _local(child.tag) == "XAddr" and child.text:
                    out[name] = child.text.strip()
    return out


def onvif_profile_token(xml):
    """First media profile token from GetProfiles (preferably one with a PTZ configuration)."""
    import xml.etree.ElementTree as ET
    first = None
    for el in ET.fromstring(xml).iter():
        if _local(el.tag) == "Profiles" and el.get("token"):
            first = first or el.get("token")
            if any(_local(c.tag) == "PTZConfiguration" for c in el):
                return el.get("token")
    return first


def onvif_time(xml):
    """GetSystemDateAndTime answer -> UTC unix time of the camera (None if missing); used to correct the clock."""
    import calendar
    import xml.etree.ElementTree as ET
    root = ET.fromstring(xml)
    for el in root.iter():
        if _local(el.tag) == "UTCDateTime":
            v = {}
            for part in el.iter():
                if _local(part.tag) in ("Year", "Month", "Day", "Hour", "Minute", "Second") and part.text:
                    v[_local(part.tag)] = int(part.text)
            if len(v) == 6:
                return calendar.timegm((v["Year"], v["Month"], v["Day"], v["Hour"], v["Minute"], v["Second"], 0, 0, 0))
    return None


def onvif_fault(xml):
    """Fault reason text of a SOAP answer, or None."""
    m = re.search(r"<(?:\w+:)?Text[^>]*>([^<]*)</(?:\w+:)?Text>", xml or "") if "Fault" in (xml or "") else None
    return (m.group(1) if m else "SOAP fault") if xml and "Fault>" in xml else None
