// demo-spec.ts — the sample props used by Studio defaultProps and the render scripts.
// Single source of truth is demo-spec.json (also passed via --props at render time), so
// the typed export and the CLI render can never drift apart.

import raw from './demo-spec.json';
import { isSceneSpec, type SceneSpec } from './spec';

if (!isSceneSpec((raw as { spec: unknown }).spec)) {
  throw new Error('demo-spec.json is not a valid SceneSpec');
}

export const demoProps = raw as unknown as { spec: SceneSpec };
