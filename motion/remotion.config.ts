// remotion.config.ts — render/studio defaults. CLI flags still override these.
import { Config } from '@remotion/cli/config';

Config.setVideoImageFormat('jpeg');
Config.setJpegQuality(95);
Config.setCodec('h264');
Config.setCrf(17); // near-visually-lossless for the MP4 preview path
Config.setOverwriteOutput(true);
// Variable fonts + any remote CSS are fetched during render; give them headroom
// so a slow font load never surfaces as a blank first frame.
Config.setDelayRenderTimeoutInMilliseconds(30000);
// Chromium hardening for headless render farms (no GPU assumed).
Config.setChromiumDisableWebSecurity(false);
