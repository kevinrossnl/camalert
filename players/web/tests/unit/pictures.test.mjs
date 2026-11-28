// Cameras and picture sources of the browser player (#92): ported from urls.py, cameras.py, warm.py.
import assert from "node:assert/strict";
import { test } from "node:test";
import { compositeStreams, derivedStreams, displayName, overviewCameras, parseReady, parseTitles, pictureSources,
         streamInfo, titleFor } from "../../core/pictures.js";
import { STREAMS } from "../fake/server.mjs";

test("names and titles", () => {
  assert.equal(displayName("front_door"), "Front door");
  assert.deepEqual(parseTitles("front_door=Main entrance|bad name=x|garden="), { front_door: "Main entrance" });
  assert.equal(titleFor("garden", { front_door: "x" }), "Garden");
  assert.deepEqual(parseReady("front_door=front_door_jpeg|garden, side"), { front_door: "front_door_jpeg", garden: "garden", side: "side" });
});

test("helper and composite streams (#117, #125)", () => {
  assert.deepEqual([...derivedStreams(STREAMS)], ["front_door_jpeg", "front_door_talk"]);
  assert.deepEqual([...compositeStreams(STREAMS)], ["all"]);
  const running = { cam: { producers: [{ url: "rtsp://192.168.1.10/x" }] },
                    cam_jpeg: { producers: [{ url: "rtsp://127.0.0.1:8554/cam?video&source=ffmpeg:cam%23video%3Dmjpeg" }] } };
  assert.deepEqual([...derivedStreams(running)], ["cam_jpeg"]);
  const info = streamInfo(STREAMS, "");
  assert.deepEqual(info.names, ["all", "front_door", "garden"]);
  assert.deepEqual(overviewCameras(info), ["front_door", "garden"]);
  assert.deepEqual(streamInfo(null).names, []);
  assert.deepEqual(streamInfo({ garden: {}, front_door: {} }, "front_door=garden").names, ["front_door"]);
});

test("picture order: warm feed, else cached frame then new frames", () => {
  const base = "http://ha:8123/api/camalert/go2rtc/web0123456789ab";
  assert.deepEqual(pictureSources(base, "front_door", "front_door=front_door_jpeg"),
                   { stream: `${base}/api/stream.mjpeg?src=front_door_jpeg`, first: null, next: null });
  const s = pictureSources(base, "garden", "front_door=front_door_jpeg");
  assert.equal(s.first, `${base}/api/frame.jpeg?src=garden&cache=10s`);
  assert.equal(s.next, `${base}/api/frame.jpeg?src=garden`);
});

test("talk-back streams (#98): <camera>_talk with only a backchannel, never a camera", async () => {
  const { talkStreams, isBackchannel } = await import("../../core/pictures.js");
  const talk = "exec:ffmpeg -f alaw -ar 8000 -ac 1 -i - -c:a aac -f adts udp://192.168.1.14:7004#backchannel=1#audio=alaw/8000";
  const data = { front_door: { producers: [{ url: "rtsp://192.168.1.10/x" }] },
                 front_door_talk: { producers: [{ url: talk }] },
                 garden_talk: { producers: [{ url: talk }] },
                 side: { producers: [{ url: "rtsp://192.168.1.12/y" }] },
                 side_talk: { producers: [{ url: "rtsp://192.168.1.12/z" }] } };
  assert.ok(isBackchannel(talk));
  assert.ok(!isBackchannel("rtsp://192.168.1.10/x") && !isBackchannel(undefined));
  assert.deepEqual(talkStreams(data), { front_door: "front_door_talk" });
  assert.ok(derivedStreams(data).has("front_door_talk") && derivedStreams(data).has("garden_talk"));
  const info = streamInfo(data, "");
  assert.deepEqual(info.names, ["front_door", "side", "side_talk"]);
  assert.deepEqual(info.talks, { front_door: "front_door_talk" });
  assert.deepEqual(talkStreams(null), {});
});
