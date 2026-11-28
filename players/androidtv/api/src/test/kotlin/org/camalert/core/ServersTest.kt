package org.camalert.core

import org.junit.Assert.assertEquals
import org.junit.Test

/** #15: the same cases as tests/core/test_servers.py. */
class ServersTest {
    private val a = "http://192.168.1.10:1984"
    private val b = "http://192.168.1.20:1984"
    private val c = "http://192.168.1.30:1984"

    @Test
    fun parseMore() {
        val (entries, problems) = Servers.parseMore("garden=192.168.1.20, 192.168.1.30:1984\nBad Prefix=192.168.1.40;s3=192.168.1.50, ftp://x, ")
        assertEquals(listOf(Pair("garden", b), Pair(null, c)), entries)
        assertEquals(listOf("bad prefix=192.168.1.40", "s3=192.168.1.50", "ftp://x"), problems)
    }

    @Test
    fun serverListAndCombine() {
        val servers = Servers.serverList("192.168.1.10", "garden=192.168.1.20, 192.168.1.30, 192.168.1.10, garden=192.168.1.60")
        assertEquals(listOf(GoServer("s1", a), GoServer("s2", b, "garden"), GoServer("s3", c)), servers)
        val r = Servers.combine(listOf(
            Triple(servers[0], listOf("front_door", "garage", "all"), setOf("all")),
            Triple(servers[1], listOf("front_door", "shed"), emptySet()),
            Triple(servers[2], listOf("garage", "drive"), emptySet())))
        assertEquals(listOf("all", "drive", "front_door", "garage", "garden.front_door", "garden.shed", "s3.garage"), r.names)
        assertEquals(setOf("all"), r.composites)
        assertEquals(Pair(c, "garage"), r.mapping["s3.garage"])
    }

    @Test
    fun resolve() {
        val servers = Servers.serverList("192.168.1.10", "garden=192.168.1.20, 192.168.1.30")
        assertEquals(Pair(a, "front_door"), Servers.resolve("front_door", servers))
        assertEquals(Pair(b, "shed"), Servers.resolve("garden.shed", servers))
        assertEquals(Pair(c, "garage"), Servers.resolve("s3.garage", servers))
        assertEquals(Pair(a, "s1.x"), Servers.resolve("s1.x", servers))
        assertEquals(Pair(a, "cam.1"), Servers.resolve("cam.1", servers))
        assertEquals(Pair(a, "drive"), Servers.resolve("drive", servers, mapOf("drive" to Pair("http://192.168.1.99:1984", "drive"))))
        assertEquals(Pair<String?, String>(null, "x"), Servers.resolve("x", emptyList()))
    }
}
