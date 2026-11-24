"""Golden file listings of the packages (#28): what is inside the ipk, the Kodi add-on zip and the Kodi repository.

Path + mode per file (no sizes, no timestamps), plus the package metadata that matters (control fields,
addon.xml). The version is replaced by @VERSION@ so a release does not touch the listings.
"""
import io
import os
import stat
import tarfile
import xml.etree.ElementTree as ET
import zipfile

CONTROL_FIELDS = ("Package", "Version", "Section", "Architecture", "Depends", "Recommends", "License")


def _ver(text, version):
    return text.replace(version, "@VERSION@") if version else text


def ar_members(path):
    with open(path, "rb") as f:
        data = f.read()
    assert data[:8] == b"!<arch>\n", "not an ar archive"
    i, out = 8, []
    while i < len(data):
        name = data[i:i + 16].decode().strip()
        size = int(data[i + 48:i + 58].decode().strip())
        out.append((name, data[i + 60:i + 60 + size]))
        i += 60 + size + (size % 2)
    return out


def _tar_lines(prefix, blob):
    lines = []
    with tarfile.open(fileobj=io.BytesIO(blob)) as tar:
        for m in tar.getmembers():
            kind = "d" if m.isdir() else "-"
            lines.append("%s %s%s %s" % (prefix, kind, stat.filemode(m.mode)[1:], m.name))
    return sorted(lines)


def ipk_listing(path, version):
    members = ar_members(path)
    lines = ["ar " + " ".join(n for n, _d in members)]
    blobs = dict(members)
    lines += _tar_lines("control", blobs["control.tar.gz"])
    with tarfile.open(fileobj=io.BytesIO(blobs["control.tar.gz"])) as tar:
        control = tar.extractfile("./control").read().decode()
    for line in control.splitlines():
        if line.split(":", 1)[0] in CONTROL_FIELDS:
            lines.append("field " + _ver(line, version))
    lines += _tar_lines("data", blobs["data.tar.gz"])
    return "\n".join(lines) + "\n"


def addon_xml_lines(text, version):
    root = ET.fromstring(text)
    lines = ["addon id=%s version=%s provider=%s" % (root.get("id"), _ver(root.get("version"), version),
                                                     root.get("provider-name"))]
    for imp in root.iter("import"):
        lines.append("requires %s %s" % (imp.get("addon"), imp.get("version")))
    for ext in root.findall("extension"):
        attrs = " ".join("%s=%s" % (k, v) for k, v in sorted(ext.attrib.items()) if k != "point")
        lines.append(("extension %s %s" % (ext.get("point"), attrs)).rstrip())
        for el in ext.iter():
            if el.tag in ("info", "checksum", "datadir", "platform", "license", "source", "icon", "fanart"):
                lines.append("  %s %s" % (el.tag, (el.text or "").strip()))
    return lines


def zip_listing(path, version):
    lines = []
    with zipfile.ZipFile(path) as z:
        for info in z.infolist():
            mode = (info.external_attr >> 16) & 0o777
            lines.append("file %s %s" % (stat.filemode(stat.S_IFREG | mode)[1:], _ver(info.filename, version)))
        lines.sort()
        xml = [n for n in z.namelist() if n.count("/") == 1 and n.endswith("/addon.xml")]
        for n in xml:
            lines += addon_xml_lines(z.read(n), version)
    return "\n".join(lines) + "\n"


def repo_tree_listing(tree, version):
    lines = []
    for d, dirs, files in os.walk(tree):
        dirs.sort()
        for f in sorted(files):
            rel = os.path.relpath(os.path.join(d, f), tree).replace(os.sep, "/")
            lines.append("file " + (_ver(rel, version) if rel.startswith("service.camalert") else rel))
    lines.sort()
    root = ET.parse(os.path.join(tree, "addons.xml")).getroot()
    for a in root:  # only the add-on follows the release version; the repository add-on has its own
        v = _ver(a.get("version"), version) if a.get("id") == "service.camalert" else a.get("version")
        lines.append("addons.xml %s %s" % (a.get("id"), v))
    return "\n".join(lines) + "\n"


def build_all(outdir, repo_url="https://example.invalid/kodi"):
    """{golden name: listing} of freshly built packages."""
    import build_ipk
    import build_kodi
    ver = build_kodi.version()
    ipk = build_ipk.build(outdir, "someone")
    addon_zip, repo_zip, tree = build_kodi.build(outdir, repo_url)
    return {
        "ipk.txt": ipk_listing(ipk, ver),
        "kodi_addon.txt": zip_listing(addon_zip, ver),
        "kodi_repo.txt": zip_listing(repo_zip, None) + repo_tree_listing(tree, ver),
    }
