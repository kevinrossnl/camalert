"""tools/check_images.py: no metadata (EXIF, text, ICC, comments) in the repository's images (#8)."""
import os
import struct
import tempfile
import unittest
import zlib

import _paths  # noqa: E402

_paths.tools()
import check_images as C  # noqa: E402


def png(*extra):
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    ihdr = chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 0, 0, 0, 0))
    idat = chunk(b"IDAT", zlib.compress(b"\x00\x80"))
    return C.PNG_SIG + ihdr + b"".join(chunk(k, v) for k, v in extra) + idat + chunk(b"IEND", b"")


def jpeg(*segments):
    def seg(marker, data):
        return bytes((0xFF, marker)) + struct.pack(">H", len(data) + 2) + data
    body = b"".join(seg(m, d) for m, d in segments)
    return b"\xff\xd8" + seg(0xE0, b"JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00") + body + \
        seg(0xDB, b"\x00" + bytes(64)) + b"\xff\xda\x00\x08\x01\x01\x00\x00\x3f\x00\x12\x34\xff\xd9"


class TestImageCheck(unittest.TestCase):
    def test_clean_images(self):
        self.assertEqual(C.metadata(png()), [])
        self.assertEqual(C.metadata(png((b"pHYs", bytes(9)), (b"gAMA", bytes(4)))), [])
        self.assertEqual(C.metadata(jpeg()), [])

    def test_png_metadata_found_and_stripped(self):
        dirty = png((b"tEXt", b"Author\x00someone"), (b"eXIf", b"MM\x00*"), (b"tIME", bytes(7)), (b"iCCP", b"x\x00\x00"))
        self.assertEqual(C.metadata(dirty), ["PNG chunk eXIf", "PNG chunk iCCP", "PNG chunk tEXt", "PNG chunk tIME"])
        clean = C.strip(dirty)
        self.assertEqual(C.metadata(clean), [])
        self.assertEqual(clean, png())  # pixels untouched
        self.assertNotIn(b"someone", clean)

    def test_jpeg_metadata_found_and_stripped(self):
        dirty = jpeg((0xE1, b"Exif\x00\x00GPS 52.1 5.1"), (0xE2, b"ICC_PROFILE\x00"), (0xED, b"Photoshop 3.0"),
                     (0xFE, b"made on my phone"))
        self.assertEqual(C.metadata(dirty), ["JPEG EXIF/XMP (APP1)", "JPEG ICC profile (APP2)", "JPEG IPTC (APP13)",
                                             "JPEG comment (COM)"])
        clean = C.strip(dirty)
        self.assertEqual(C.metadata(clean), [])
        self.assertEqual(clean, jpeg())
        self.assertNotIn(b"GPS", clean)

    def test_gif_webp_and_fakes(self):
        self.assertEqual(C.metadata(b"GIF89a" + bytes(10) + b"\x21\xfe\x03abc\x00;"), ["GIF comment extension"])
        # a well-formed GIF is read block by block: 0x21 0xFE inside the LZW image data is not a comment (#23)
        gif = (b"GIF89a" + bytes([1, 0, 1, 0, 0x80, 0, 0]) + bytes(6)                  # 1x1, 2-colour table
               + b"\x21\xff\x0bNETSCAPE2.0\x03\x01\x00\x00\x00"                       # loop count: allowed
               + b"\x2c" + bytes([0, 0, 0, 0, 1, 0, 1, 0, 0]) + b"\x02\x02\x21\xfe\x00;")  # image data with 21 fe
        self.assertEqual(C.metadata(gif), [])
        self.assertEqual(C.metadata(gif[:-1] + b"\x21\xfe\x01x\x00;"), ["GIF comment extension"])
        self.assertEqual(C.metadata(gif[:-1] + b"\x21\xff\x03XMP\x00;"), ["GIF application extension"])
        webp = b"RIFF" + struct.pack("<I", 20) + b"WEBP" + b"EXIF" + struct.pack("<I", 2) + b"MM"
        self.assertEqual(C.metadata(webp), ["WebP chunk EXIF"])
        with self.assertRaises(ValueError):
            C.metadata(b"<svg/>")
        with self.assertRaises(ValueError):
            C.strip(b"GIF89a")

    def test_problems_and_strip_command(self):
        with tempfile.TemporaryDirectory() as d:
            os.mkdir(os.path.join(d, "img"))
            p = os.path.join(d, "img", "a.png")
            open(p, "wb").write(png((b"tEXt", b"Comment\x00x")))
            open(os.path.join(d, "img", "b.jpg"), "wb").write(b"not an image")
            open(os.path.join(d, "notes.txt"), "w").write("text files are check_private.py's job")
            found = C.problems(d)
            self.assertEqual(len(found), 2, found)
            self.assertEqual(C.main(["--strip", p]), 0)
            self.assertEqual(C.metadata(open(p, "rb").read()), [])
            self.assertEqual(C.main([d]), 1)  # b.jpg is still not an image

    def test_repository_images_are_clean(self):
        root = os.path.join(os.path.dirname(__file__), "..")
        self.assertTrue(C.files(root))
        self.assertEqual(C.problems(root), [])


if __name__ == "__main__":
    unittest.main()
