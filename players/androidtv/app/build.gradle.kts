// The Android TV / Fire TV app (#64). AGP 9 compiles Kotlin itself (built-in Kotlin, no kotlin-android plugin).
plugins {
    alias(libs.plugins.android.application)
}

android {
    namespace = "org.camalert.tv"
    compileSdk = 37

    defaultConfig {
        applicationId = "org.camalert.tv"
        minSdk = 25          // Android 7.1 = Fire OS 6 (Fire TV Stick 4K, 1st generation)
        targetSdk = 37
        versionCode = providers.gradleProperty("camalertVersionCode").map { it.toInt() }.getOrElse(1)  // #65
        versionName = providers.gradleProperty("camalertVersion").getOrElse("0.0.0-dev")
    }

    // Release signing (#65): only from the environment (CI secrets on GitHub at tag time), never from git.
    val releaseKeystore = System.getenv("CAMALERT_KEYSTORE")
    signingConfigs {
        if (releaseKeystore != null) {
            create("release") {
                storeFile = file(releaseKeystore)
                storePassword = System.getenv("CAMALERT_KEYSTORE_PASSWORD")
                keyAlias = System.getenv("CAMALERT_KEY_ALIAS")
                keyPassword = System.getenv("CAMALERT_KEY_PASSWORD")
            }
        }
    }

    buildTypes {
        debug {
            isMinifyEnabled = false
        }
        release {
            // signed only when CAMALERT_KEYSTORE is set (see docs/players/androidtv.md); otherwise unsigned
            if (releaseKeystore != null) signingConfig = signingConfigs.getByName("release")
            isMinifyEnabled = false
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    lint {
        abortOnError = true
        warningsAsErrors = false
        checkReleaseBuilds = false
        // the build uses pinned versions on purpose (players/androidtv/DEVELOPMENT.md); updates are a reviewed change
        disable += setOf("GradleDependency", "NewerVersionAvailable", "AndroidGradlePluginVersion", "OldTargetApi")
        // generated translations come from the master catalogue; a missing one is caught by tools/i18n/i18n.py check
        disable += setOf("MissingTranslation", "ExtraTranslation", "Typos", "TypographyDashes", "TypographyEllipsis")
        // core texts and settings labels are looked up by msgid at run time (resource t_<crc32>, Tr in Support.kt)
        disable += setOf("UnusedResources")
    }

    packaging {
        resources.excludes += setOf("META-INF/*.version", "META-INF/*.kotlin_module", "kotlin/**", "DebugProbesKt.bin")
    }
}

dependencies {
    implementation(project(":api"))
    implementation(libs.media3.exoplayer)
    implementation(libs.media3.rtsp)
    implementation(libs.media3.hls)
    implementation(libs.media3.ui)
    implementation(libs.leanback.preference)
    implementation(libs.preference)
}
