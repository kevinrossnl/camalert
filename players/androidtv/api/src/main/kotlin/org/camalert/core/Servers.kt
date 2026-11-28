// CamAlert - show IP cameras on your TV.
// Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
package org.camalert.core

/** One go2rtc server (#15): s1 is the setting `server`, the others come from `more_servers`. */
data class GoServer(val id: String, val url: String, val prefix: String? = null)

/**
 * Several go2rtc servers (#15), the same as camalert_core.servers: the main server keeps its camera names, a server
 * with a prefix shows its cameras as `<prefix>.<stream>`, a server without one keeps the stream names unless an
 * earlier server has that name (then `s<n>.<stream>`).
 */
object Servers {
    const val SEP = "."
    private val PREFIX = Regex("^[a-z0-9_-]{1,16}$")
    private val SID = Regex("^s\\d+$")
    private val SPLIT = Regex("[,\\n;]+")

    /** (entries, problems): entries are (prefix or null, normalized url). */
    fun parseMore(text: String?): Pair<List<Pair<String?, String>>, List<String>> {
        val entries = ArrayList<Pair<String?, String>>()
        val problems = ArrayList<String>()
        for (raw in SPLIT.split(text ?: "")) {
            var part = raw.trim()
            if (part.isEmpty()) continue
            var prefix: String? = null
            if ("=" in part && "://" !in part.substringBefore("=")) {
                prefix = part.substringBefore("=").trim().lowercase()
                part = part.substringAfter("=")
                if (!PREFIX.matches(prefix) || SID.matches(prefix)) {
                    problems.add(prefix + "=" + part.trim())
                    continue
                }
            }
            val url = Urls.normalizeServer(part)
            if (url == null) { problems.add(part); continue }
            entries.add(Pair(prefix, url))
        }
        return Pair(entries, problems)
    }

    fun serverList(main: String?, moreText: String? = ""): List<GoServer> {
        val out = ArrayList<GoServer>()
        val seen = HashSet<String>()
        val prefixes = HashSet<String>()
        Urls.normalizeServer(main)?.let { out.add(GoServer("s1", it)); seen.add(it) }
        for ((prefix, url) in parseMore(moreText).first) {
            if (url in seen || (prefix != null && prefix in prefixes)) continue
            seen.add(url)
            if (prefix != null) prefixes.add(prefix)
            out.add(GoServer("s${out.size + 1}", url, prefix))
        }
        return out
    }

    data class Combined(val names: List<String>, val composites: Set<String>, val mapping: Map<String, Pair<String, String>>)

    /** perServer: (server, stream names, composite streams) in server order. */
    fun combine(perServer: List<Triple<GoServer, List<String>, Set<String>>>): Combined {
        val names = ArrayList<String>()
        val composites = HashSet<String>()
        val mapping = LinkedHashMap<String, Pair<String, String>>()
        for ((srv, streams, comp) in perServer) {
            for (stream in streams) {
                val name = when {
                    srv.prefix != null -> srv.prefix + SEP + stream
                    stream in mapping -> srv.id + SEP + stream
                    else -> stream
                }
                if (name in mapping) continue
                mapping[name] = Pair(srv.url, stream)
                names.add(name)
                if (stream in comp) composites.add(name)
            }
        }
        return Combined(names.sorted(), composites, mapping)
    }

    /** (server url, stream) for a camera name; (null, name) without servers. */
    fun resolve(name: String, servers: List<GoServer>, mapping: Map<String, Pair<String, String>>? = null): Pair<String?, String> {
        if (servers.isEmpty()) return Pair(null, name)
        val hit = mapping?.get(name)
        if (hit != null && servers.any { it.url == hit.first }) return hit
        if (SEP in name) {
            val head = name.substringBefore(SEP)
            val rest = name.substringAfter(SEP)
            for (srv in servers) {
                if (rest.isNotEmpty() && srv.id != "s1" && (head == srv.prefix || head == srv.id)) return Pair(srv.url, rest)
            }
        }
        return Pair(servers[0].url, name)
    }
}
