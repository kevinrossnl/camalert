// CamAlert - show IP cameras on your TV.
// Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
package org.camalert.core

import java.io.BufferedInputStream
import java.io.ByteArrayOutputStream
import java.io.IOException
import java.io.InputStream
import java.net.InetAddress
import java.net.InetSocketAddress
import java.net.ServerSocket
import java.net.Socket
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors
import java.util.concurrent.RejectedExecutionException
import java.util.concurrent.ThreadPoolExecutor
import java.util.concurrent.TimeUnit
import java.util.concurrent.ArrayBlockingQueue

/**
 * A small HTTP/1.1 server for the CamAlert API (one request per connection, like Python's http.server): request
 * line, headers and at most [MAX_BODY] bytes of body go to [Api.handle]. Never logs requests (they can contain the
 * token). Plain JVM, so the JVM tests run it on a real socket. With an SSLContext it serves HTTPS (api_https, #66).
 */
class HttpServer(private val api: Api, private val backend: Backend, val port: Int, private val bind: InetAddress? = null,
                 private val ssl: javax.net.ssl.SSLContext? = null) {
    companion object {
        const val MAX_BODY = 65536
        const val MAX_HEAD = 16384
    }

    private var server: ServerSocket? = null
    private var pool: ExecutorService? = null
    private var acceptor: Thread? = null
    val localPort get() = server?.localPort ?: -1
    val https get() = ssl != null

    @Throws(IOException::class)
    fun start() {
        // api_https (#66): the same server on a TLS socket (self-signed certificate of the player)
        val ss = ssl?.serverSocketFactory?.createServerSocket() ?: ServerSocket()
        ss.reuseAddress = true
        ss.bind(InetSocketAddress(bind, port), 32)
        server = ss
        // bounded: a flood of connections cannot use up memory (the rate limit in the API does the rest)
        pool = ThreadPoolExecutor(2, 8, 30, TimeUnit.SECONDS, ArrayBlockingQueue(32)) { r -> Thread(r, "camalert-http").apply { isDaemon = true } }
        acceptor = Thread({
            while (!ss.isClosed) {
                val s = try { ss.accept() } catch (e: IOException) { break }
                try {
                    pool!!.execute { serve(s) }
                } catch (e: RejectedExecutionException) {
                    try { s.close() } catch (x: IOException) { }
                }
            }
        }, "camalert-http-accept").apply { isDaemon = true; start() }
    }

    fun stop() {
        try { server?.close() } catch (e: IOException) { }
        pool?.shutdownNow()
        server = null
    }

    private fun readLine(inp: InputStream, budget: IntArray): String? {
        val out = ByteArrayOutputStream()
        while (true) {
            val c = inp.read()
            if (c < 0) return if (out.size() == 0) null else out.toString("ISO-8859-1")
            if (--budget[0] < 0) throw IOException("header too large")
            if (c == '\n'.code) break
            if (c != '\r'.code) out.write(c)
        }
        return out.toString("ISO-8859-1")
    }

    private fun serve(s: Socket) {
        s.use { sock ->
            try {
                sock.soTimeout = 10_000
                val inp = BufferedInputStream(sock.getInputStream())
                val budget = intArrayOf(MAX_HEAD)
                val first = readLine(inp, budget) ?: return
                val parts = first.split(" ")
                if (parts.size < 2) return write(sock, Response(400, mapOf("result" to false, "error" to "bad request")))
                val headers = HashMap<String, String>()
                while (true) {
                    val line = readLine(inp, budget) ?: break
                    if (line.isEmpty()) break
                    val i = line.indexOf(':')
                    if (i > 0) headers[line.substring(0, i).trim().lowercase()] = line.substring(i + 1).trim()
                }
                val target = parts[1]
                val path = target.substringBefore('?')
                val query = if ('?' in target) Api.parseQuery(target.substringAfter('?')) else emptyMap()
                val n = (headers["content-length"]?.toIntOrNull() ?: 0).coerceIn(0, MAX_BODY)
                val body = ByteArray(n)
                var got = 0
                while (got < n) {
                    val r = inp.read(body, got, n - got)
                    if (r < 0) break
                    got += r
                }
                val ip = (sock.inetAddress?.hostAddress ?: "").substringBefore('%')
                val req = Request(parts[0], path, query, ip, headers["x-camalert-token"], headers["user-agent"] ?: "",
                    body.copyOf(got), headers["content-type"] ?: "")
                write(sock, api.handle(backend, req))
            } catch (e: IOException) {
            }
        }
    }

    private fun reason(code: Int) = when (code) {
        200 -> "OK"; 400 -> "Bad Request"; 403 -> "Forbidden"; 404 -> "Not Found"; 405 -> "Method Not Allowed"
        429 -> "Too Many Requests"; 500 -> "Internal Server Error"; else -> "Status"
    }

    private fun write(sock: Socket, resp: Response) {
        val payload = resp.payload()
        val sb = StringBuilder("HTTP/1.1 ${resp.code} ${reason(resp.code)}\r\n")
        sb.append("Server: CamAlert\r\nContent-Type: ${resp.contentType}\r\nContent-Length: ${payload.size}\r\nConnection: close\r\n")
        for ((k, v) in resp.headers) sb.append("$k: $v\r\n")
        sb.append("\r\n")
        val out = sock.getOutputStream()
        out.write(sb.toString().toByteArray(Charsets.ISO_8859_1))
        out.write(payload)
        out.flush()
    }
}
