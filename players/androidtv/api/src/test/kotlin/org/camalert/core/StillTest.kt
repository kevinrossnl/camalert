package org.camalert.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/** #91: same scenarios as tests/core/test_frames.py TestLiveStill. */
class StillTest {
    private var now = 100.0
    private val still = LiveStill({ now }, 15.0)

    @Test fun maximumFromTheCore() = assertEquals(15.0, CoreData.load().stillMaxSeconds, 0.0)

    @Test fun pictureBeforeFirstFrameIsShownThenHidden() {
        val t = still.start("front_door")
        assertTrue(still.picture(t))
        assertTrue(still.showing)
        assertTrue(still.playing(t))
        assertFalse(still.showing)
        assertFalse(still.playing(t))
    }

    @Test fun pictureAfterFirstFrameIsNotShown() {
        val t = still.start("front_door")
        assertFalse(still.playing(t))
        assertFalse(still.picture(t))
    }

    @Test fun pictureOfAnEarlierCameraIsIgnored() {
        val old = still.start("front_door")
        val new = still.start("garden")
        assertFalse(still.picture(old))
        assertFalse(still.playing(old))
        assertTrue(still.picture(new))
    }

    @Test fun neverLongerThanTheMaximum() {
        val t = still.start("front_door")
        assertTrue(still.picture(t))
        now += 14.0
        assertFalse(still.expired())
        now += 2.0
        assertTrue(still.expired())
        assertFalse(still.expired())
        val t2 = still.start("garden")
        now += 16.0
        assertFalse(still.picture(t2))
    }

    @Test fun stopHidesAndDropsLatePictures() {
        val t = still.start("front_door")
        assertTrue(still.picture(t))
        assertTrue(still.stop())
        assertFalse(still.picture(t))
        assertFalse(still.stop())
    }
}
