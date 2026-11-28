// CamAlert - show IP cameras on your TV.
// Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
package org.camalert.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/** #132: QR codes and the problem report give the same answers as the Python core (contract/core.json). */
@Suppress("UNCHECKED_CAST")
class ReportTest {
    private val ref = Exported.core

    @Test
    fun qrMatchesPython() {
        for (c in ref["qr"] as List<Map<String, Any?>>) {
            val got = Qr.textRows(Qr.encode(c["text"] as String, c["level"] as String), 0)
            assertEquals("qr(${c["text"]}, ${c["level"]})", c["rows"], got)
        }
    }

    @Test
    fun qrTooLong() {
        try { Qr.encode("x".repeat(3000), "M"); error("no TooLong") } catch (e: Qr.TooLong) { }
    }

    @Test
    fun scrubMatchesPython() {
        val r = ref["report"] as Map<String, Any?>
        for (c in r["scrub"] as List<Map<String, Any?>>) assertEquals("scrub(${c["in"]})", c["out"], Report.scrub(c["in"] as String))
    }

    @Test
    fun buildSummaryAndIssueUrlMatchPython() {
        val rep = Report()
        val r = ref["report"] as Map<String, Any?>
        for (c in r["build"] as List<Map<String, Any?>>) {
            val out = rep.build(c["status"] as Map<String, Any?>, c["settings"] as Map<String, Any?>, c["log"] as List<String>,
                c["extra"] as Map<String, Any?>, (c["now"] as Number).toDouble())
            assertEquals(Json.write(c["out"], sortKeys = true), Json.write(out, sortKeys = true))
            assertEquals(c["summary"], rep.summary(out))
            val url = rep.issueUrl(out)
            assertEquals(c["issue_url"], url)
            assertTrue(url.toByteArray().size <= 600)
            assertTrue("token" !in (out["settings"] as Map<String, Any?>))
        }
    }
}
