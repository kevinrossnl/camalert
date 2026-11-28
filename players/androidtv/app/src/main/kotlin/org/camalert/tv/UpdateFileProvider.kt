// CamAlert for Android TV / Fire TV. Copyright (C) 2026 CamAlert developers. GPL v2.
package org.camalert.tv

import android.content.ContentProvider
import android.content.ContentValues
import android.database.Cursor
import android.database.MatrixCursor
import android.net.Uri
import android.os.ParcelFileDescriptor
import android.provider.OpenableColumns
import java.io.File
import java.io.FileNotFoundException

/**
 * Hands the downloaded release APK to the system package installer (#126). Only files in cache/updates, read
 * only, and only for the installer the app grants the URI to (not exported). A tiny stand-in for FileProvider.
 */
class UpdateFileProvider : ContentProvider() {
    companion object {
        const val AUTHORITY = "org.camalert.tv.updates"
        const val APK_TYPE = "application/vnd.android.package-archive"
        fun dir(cacheDir: File) = File(cacheDir, "updates")
        fun uri(file: File): Uri = Uri.Builder().scheme("content").authority(AUTHORITY).appendPath(file.name).build()
    }

    private fun file(uri: Uri): File {
        val name = uri.lastPathSegment ?: throw FileNotFoundException()
        if (name.contains('/') || name.startsWith(".") || !name.endsWith(".apk")) throw FileNotFoundException(name)
        val f = File(dir(context!!.cacheDir), name)
        if (!f.isFile) throw FileNotFoundException(name)
        return f
    }

    override fun onCreate() = true
    override fun getType(uri: Uri) = APK_TYPE
    override fun openFile(uri: Uri, mode: String): ParcelFileDescriptor =
        ParcelFileDescriptor.open(file(uri), ParcelFileDescriptor.MODE_READ_ONLY)

    override fun query(uri: Uri, projection: Array<out String>?, selection: String?, selectionArgs: Array<out String>?, sortOrder: String?): Cursor {
        val f = file(uri)
        return MatrixCursor(arrayOf(OpenableColumns.DISPLAY_NAME, OpenableColumns.SIZE)).apply { addRow(arrayOf<Any>(f.name, f.length())) }
    }

    override fun insert(uri: Uri, values: ContentValues?): Uri? = null
    override fun delete(uri: Uri, selection: String?, selectionArgs: Array<out String>?) = 0
    override fun update(uri: Uri, values: ContentValues?, selection: String?, selectionArgs: Array<out String>?) = 0
}
