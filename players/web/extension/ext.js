// CamAlert - show IP cameras on your TV.
// Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
//
// The extension API of this browser (#131): Firefox's promise-based `browser`, else Chrome's and Edge's `chrome`
// (Manifest V3, promises as well). Every extension page imports this instead of using `chrome` directly.
export const ext = globalThis.browser && globalThis.browser.runtime ? globalThis.browser : globalThis.chrome;
