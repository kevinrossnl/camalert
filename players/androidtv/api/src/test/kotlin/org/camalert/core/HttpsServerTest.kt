// CamAlert - show IP cameras on your TV.
// Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
package org.camalert.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File
import java.net.URL
import java.security.KeyStore
import java.security.cert.X509Certificate
import javax.net.ssl.HttpsURLConnection
import javax.net.ssl.KeyManagerFactory
import javax.net.ssl.SSLContext
import javax.net.ssl.TrustManager
import javax.net.ssl.X509TrustManager

/** api_https (#66): the HTTP API on a TLS socket with a self-signed certificate, like Enigma2 and Kodi. */
class HttpsServerTest {
    private fun serverContext(): SSLContext {
        val dir = File(System.getProperty("java.io.tmpdir"), "camalert-https-test-${System.nanoTime()}").apply { mkdirs() }
        val ks = File(dir, "test.p12")
        val keytool = File(System.getProperty("java.home"), "bin/keytool").path
        val p = ProcessBuilder(keytool, "-genkeypair", "-alias", "camalert", "-keyalg", "RSA", "-keysize", "2048",
            "-validity", "2", "-dname", "CN=CamAlert", "-storetype", "PKCS12", "-keystore", ks.path,
            "-storepass", "testpass", "-keypass", "testpass").redirectErrorStream(true).start()
        p.inputStream.readBytes()
        assertEquals(0, p.waitFor())
        val store = KeyStore.getInstance("PKCS12").apply { ks.inputStream().use { load(it, "testpass".toCharArray()) } }
        val kmf = KeyManagerFactory.getInstance(KeyManagerFactory.getDefaultAlgorithm()).apply { init(store, "testpass".toCharArray()) }
        dir.deleteRecursively()
        return SSLContext.getInstance("TLS").apply { init(kmf.keyManagers, null, null) }
    }

    private val trustAll = SSLContext.getInstance("TLS").apply {
        init(null, arrayOf<TrustManager>(object : X509TrustManager {
            override fun checkClientTrusted(chain: Array<out X509Certificate>?, authType: String?) {}
            override fun checkServerTrusted(chain: Array<out X509Certificate>?, authType: String?) {}
            override fun getAcceptedIssuers(): Array<X509Certificate> = arrayOf()
        }), null)
    }

    @Test
    fun statusOverHttpsAndNotOverHttp() {
        val backend = HttpContractTest.TestBackend(Schema.validate(emptyMap()).first, RecordingController(), listOf("front_door"))
        val server = HttpServer(Api(), backend, 0, java.net.InetAddress.getLoopbackAddress(), serverContext())
        server.start()
        try {
            assertTrue(server.https)
            val c = URL("https://127.0.0.1:${server.localPort}/camalert/status").openConnection() as HttpsURLConnection
            c.sslSocketFactory = trustAll.socketFactory
            c.setHostnameVerifier { _, _ -> true }
            assertEquals(200, c.responseCode)
            val body = Json.parse(c.inputStream.readBytes().toString(Charsets.UTF_8)) as Map<*, *>
            assertEquals("0.0.0-test", body["version"])
            assertEquals("CN=CamAlert", (c.serverCertificates[0] as X509Certificate).subjectX500Principal.name)
            val plain = try {
                (URL("http://127.0.0.1:${server.localPort}/camalert/status").openConnection() as java.net.HttpURLConnection).apply {
                    readTimeout = 3000
                }.responseCode
            } catch (e: Exception) { -1 }
            assertFalse("plain HTTP must not be answered on the HTTPS port", plain == 200)
        } finally {
            server.stop()
        }
        assertFalse(HttpServer(Api(), backend, 0).https)
    }
}
