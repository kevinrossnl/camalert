// CamAlert - show IP cameras on your TV.
// Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
package org.camalert.core

import java.net.Inet6Address
import java.net.InetAddress
import java.security.MessageDigest

/** Who may call the API: address allowlist, token check, rate limit (port of core/camalert_core/access.py). */
object Access {
    private class Net(val bytes: ByteArray, val prefix: Int)
    private val IPV4 = Regex("^\\d{1,3}(\\.\\d{1,3}){3}$")
    private val IPV6 = Regex("^[0-9A-Fa-f:.]+$")

    // the local network (#52): RFC 1918, CGNAT/Tailscale, loopback, link-local, IPv6 loopback/link-local/ULA
    private val LAN = listOf(
        "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "100.64.0.0/10", "127.0.0.0/8", "169.254.0.0/16",
        "::1/128", "fe80::/10", "fc00::/7",
    ).map { n -> val (a, p) = n.split("/"); Net(literal(a)!!.address, p.toInt()) }
    val LOCAL_SUFFIXES = listOf(".local", ".lan", ".home", ".home.arpa", ".internal")


    /** An IP literal (never a DNS lookup); IPv4-mapped IPv6 becomes IPv4; null for anything else. */
    fun literal(text: String?): InetAddress? {
        var t = (text ?: "").trim().trim('[', ']')
        t = t.substringBefore('%')
        if (t.isEmpty()) return null
        val ok = if (t.contains(':')) IPV6.matches(t) && t.count { it == ':' } >= 2 else
            IPV4.matches(t) && t.split('.').all { it.toInt() <= 255 && (it.length == 1 || !it.startsWith("0")) }
        if (!ok) return null
        val a = try { InetAddress.getByName(t) } catch (e: Exception) { return null }
        if (a is Inet6Address) {
            val b = a.address
            val mapped = (0 until 10).all { b[it] == 0.toByte() } && b[10] == 0xff.toByte() && b[11] == 0xff.toByte()
            if (mapped) return InetAddress.getByAddress(b.copyOfRange(12, 16))
        }
        return a
    }

    private fun inNet(a: InetAddress, n: Net): Boolean {
        val b = a.address
        if (b.size != n.bytes.size) return false
        var bits = n.prefix
        var k = 0
        while (bits > 0) {
            val mask = if (bits >= 8) 0xff else (0xff shl (8 - bits)) and 0xff
            if ((b[k].toInt() and mask) != (n.bytes[k].toInt() and mask)) return false
            bits -= 8
            k++
        }
        return true
    }

    fun lanAddress(ip: String?): Boolean {
        val a = literal(ip) ?: return false
        return LAN.any { inNet(a, it) }
    }

    fun clientAllowed(ip: String?, allow: String = "lan"): Boolean = allow == "any" || lanAddress(ip)

    fun localName(host: String?): Boolean {
        val h = (host ?: "").lowercase().trimEnd('.')
        return h.isNotEmpty() && (!h.contains('.') || LOCAL_SUFFIXES.any { h.endsWith(it) })
    }

    /** Every address a host name resolves to ([] if it does not). Blocking. */
    fun resolve(host: String): List<String> = try {
        InetAddress.getAllByName(host).map { it.hostAddress ?: "" }.filter { it.isNotEmpty() }.distinct().sorted()
    } catch (e: Exception) {
        emptyList()
    }

    private fun hostOf(url: String): String? {
        // like urllib.parse.urlsplit(url).hostname: lower case, without brackets
        val rest = url.substringAfter("://")
        val auth = rest.substringBefore('/').substringBefore('?').substringBefore('#').substringAfterLast('@')
        if (auth.startsWith("[")) {
            val end = auth.indexOf(']')
            return if (end > 0) auth.substring(1, end).lowercase() else null
        }
        val h = auth.substringBefore(':').lowercase()
        return h.ifEmpty { null }
    }

    /** Why a server-side request to url (the Home Assistant webhook) is refused, or null when it may go (#53). */
    fun urlTarget(url: String?, callerIp: String? = null, resolver: (String) -> List<String> = ::resolve): String? {
        val text = url ?: ""
        if (!(text.startsWith("http://") || text.startsWith("https://"))) return "url must start with http:// or https://"
        val host = try { hostOf(text) } catch (e: Exception) { return "invalid url" } ?: return "invalid url"
        val lit = literal(host)
        if (!callerIp.isNullOrEmpty() && lit != null && lit == literal(callerIp)) return null
        if (lit != null) return if (lanAddress(host)) null else "url must point to the local network"
        if (localName(host)) return null
        val addresses = resolver(host)
        if (addresses.isEmpty()) return "url host name does not resolve"
        if (!addresses.all { lanAddress(it) }) return "url must point to the local network"
        return null
    }

    fun tokenOk(expected: String?, given: String?): Boolean {
        if (expected.isNullOrEmpty()) return true
        if (given.isNullOrEmpty()) return false
        return MessageDigest.isEqual(expected.toByteArray(Charsets.UTF_8), given.toByteArray(Charsets.UTF_8))
    }

    fun exposedWithoutToken(allow: String, token: String, ip: String): Boolean =
        allow == "any" && token.isEmpty() && !clientAllowed(ip, "lan")
}

/** At most [limit] requests per [window] seconds per caller address. */
class RateLimiter(val limit: Int = 30, val window: Double = 10.0) {
    val seen = HashMap<String, MutableList<Double>>()

    @Synchronized
    fun allow(who: String, now: Double): Boolean {
        val times = (seen[who] ?: mutableListOf()).filter { now - it < window }.toMutableList()
        val ok = times.size < limit
        if (ok) times.add(now)
        seen[who] = times
        if (seen.size > 256) {
            val keep = seen.filter { it.value.isNotEmpty() && now - it.value.last() < window }
            seen.clear()
            seen.putAll(keep)
        }
        return ok
    }

    @Synchronized
    fun clear() = seen.clear()
}
