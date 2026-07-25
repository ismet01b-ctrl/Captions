# -*- coding: utf-8 -*-
"""Blender-Engine fuer DouchkoVE Captions: rendert Text als echtes 3D-Wasser-Glas
(IOR 1.33, Fluessigkeits-Bump, Absorption in der Szenen-Farbe). Der Video-Frame des
Moments dient als Refraktions-Quelle - die Szene bricht sich durch die Buchstaben.
Ein Render pro Moment; Bewegung/Okklusion uebernimmt die render.py-Pipeline."""
import os
import json
import shutil
import hashlib
import subprocess
import tempfile

import numpy as np
import cv2

HERE = os.path.dirname(os.path.abspath(__file__))

WINDOWS_PATHS = [
    r'C:\Program Files\Blender Foundation',
    r'C:\Program Files (x86)\Blender Foundation',
]


def find_blender(cfg_path=None):
    """Findet Blender: Config-Pfad > PATH > uebliche Windows-Installationen."""
    if cfg_path and os.path.exists(cfg_path):
        return cfg_path
    p = shutil.which('blender')
    if p:
        return p
    for base in WINDOWS_PATHS:
        if os.path.isdir(base):
            for d in sorted(os.listdir(base), reverse=True):
                exe = os.path.join(base, d, 'blender.exe')
                if os.path.exists(exe):
                    return exe
    return None


# Das bpy-Skript wird als Datei geschrieben und headless ausgefuehrt.
# Parameter kommen per JSON (Pfad als argv nach '--').
BPY_SCRIPT = r'''
import bpy, math, json, sys
args = json.load(open(sys.argv[sys.argv.index('--') + 1], encoding='utf-8'))

scn = bpy.context.scene
bpy.ops.object.select_all(action='SELECT'); bpy.ops.object.delete()

cam_data = bpy.data.cameras.new('cam'); cam = bpy.data.objects.new('cam', cam_data)
scn.collection.objects.link(cam); scn.camera = cam
cam.location = (0, -4.2, 0.0); cam.rotation_euler = (math.radians(90), 0, 0)

# Hintergrund-Ebene: NUR fuer Transmission sichtbar - die Buchstaben brechen den
# echten Video-Frame, der Rest des Bildes bleibt transparent (Alpha-Sprite)
img = bpy.data.images.load(args['bg'])
bpy.ops.mesh.primitive_plane_add(size=1, location=(0, 3.2, 0.0))
bg = bpy.context.object
dist = 3.2 - cam.location.y
fov = cam_data.angle
w = 2 * dist * math.tan(fov / 2)
bg.scale = (w, w * args['bg_aspect'], 1)
bg.rotation_euler = (math.radians(90), 0, 0)
bg.visible_camera = False
m = bpy.data.materials.new('bg'); m.use_nodes = True
nt = m.node_tree; nt.nodes.clear()
tex = nt.nodes.new('ShaderNodeTexImage'); tex.image = img
em = nt.nodes.new('ShaderNodeEmission'); em.inputs['Strength'].default_value = 1.0
out = nt.nodes.new('ShaderNodeOutputMaterial')
nt.links.new(tex.outputs['Color'], em.inputs['Color'])
nt.links.new(em.outputs['Emission'], out.inputs['Surface'])
bg.data.materials.append(m)

bpy.ops.object.text_add(location=(0, 0, 0))
txt = bpy.context.object
txt.data.body = args['text']
txt.data.extrude = 0.06
txt.data.bevel_depth = 0.016
txt.data.bevel_resolution = 4
txt.data.align_x = 'CENTER'
txt.data.align_y = 'CENTER'
txt.data.size = 0.8
txt.data.space_character = 1.05
txt.rotation_euler = (math.radians(90), 0, 0)
try:
    txt.data.font = bpy.data.fonts.load(args['font'])
except Exception:
    pass
bpy.ops.object.convert(target='MESH')
# Bevel-Selbstschnitte an Innenecken heilen: Doppel-Vertices verschmelzen,
# Normalen konsistent nach aussen - sonst rendert Glas dort schwarz
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.mesh.select_all(action='SELECT')
bpy.ops.mesh.remove_doubles(threshold=0.0012)
bpy.ops.mesh.normals_make_consistent(inside=False)
bpy.ops.object.mode_set(mode='OBJECT')
bpy.ops.object.shade_smooth()

wm = bpy.data.materials.new('mat'); wm.use_nodes = True
nt = wm.node_tree; nt.nodes.clear()
noise = nt.nodes.new('ShaderNodeTexNoise')
noise.noise_dimensions = '4D'
bump = nt.nodes.new('ShaderNodeBump')
outm = nt.nodes.new('ShaderNodeOutputMaterial')
t = args['tint']
if args.get('material', 'wasser') == 'wasser':
    # Fluessiges Wasser-Glas: bricht die Szene, Wellen-Bump
    noise.inputs['Scale'].default_value = 5.0
    noise.inputs['Detail'].default_value = 6.0
    bump.inputs['Strength'].default_value = 0.28
    shader = nt.nodes.new('ShaderNodeBsdfGlass')
    shader.inputs['IOR'].default_value = 1.33
    shader.inputs['Roughness'].default_value = 0.015
    shader.inputs['Color'].default_value = (0.90 + t[0]*0.08, 0.92 + t[1]*0.08,
                                            0.92 + t[2]*0.08, 1.0)
    out_sock = shader.outputs['BSDF']
else:
    # Massives, mattes 3D fuer Boden/Wand: Szenen-Farbe, Material-Struktur,
    # leichter Metall-Schimmer an den Kanten - kein Glas auf Asphalt
    noise.inputs['Scale'].default_value = 2.2
    noise.inputs['Detail'].default_value = 4.0
    bump.inputs['Strength'].default_value = 0.10
    shader = nt.nodes.new('ShaderNodeBsdfPrincipled')
    shader.inputs['Base Color'].default_value = (min(t[0]*1.35+0.18, 1.0),
                                                 min(t[1]*1.35+0.18, 1.0),
                                                 min(t[2]*1.35+0.18, 1.0), 1.0)
    shader.inputs['Roughness'].default_value = 0.55
    shader.inputs['Metallic'].default_value = 0.12
    out_sock = shader.outputs['BSDF']
nt.links.new(noise.outputs['Fac'], bump.inputs['Height'])
nt.links.new(bump.outputs['Normal'], shader.inputs['Normal'])
nt.links.new(out_sock, outm.inputs['Surface'])
txt.data.materials.append(wm)

# Kamera: explizit auf die Text-Bounding-Box zentrieren (robust gegen
# Ursprungs-Verschiebung durch die Mesh-Reparatur), Text fuellt ~80% der Breite
from mathutils import Vector
bb = [txt.matrix_world @ Vector(c) for c in txt.bound_box]
cx_t = sum(v.x for v in bb) / 8.0
cz_t = sum(v.z for v in bb) / 8.0
tw = max(txt.dimensions.x, 0.2)
cam.location.x = cx_t
cam.location.z = cz_t
cam.location.y = -(tw / 0.80) / (2 * math.tan(fov / 2))
bg.scale = (w * 2, w * args['bg_aspect'] * 2, 1)   # Backdrop grosszuegig

sun = bpy.data.objects.new('sun', bpy.data.lights.new('sun', 'SUN'))
sun.data.energy = 3.0; sun.rotation_euler = (math.radians(50), math.radians(-20), 0)
scn.collection.objects.link(sun)
area = bpy.data.objects.new('area', bpy.data.lights.new('area', 'AREA'))
area.data.energy = 340; area.data.size = 4.0
area.location = (1.5, -2.5, 2.6); area.rotation_euler = (math.radians(45), 0, math.radians(20))
scn.collection.objects.link(area)

world = bpy.data.worlds.new('w'); scn.world = world
world.use_nodes = True
bgn = world.node_tree.nodes['Background']
sky = args['sky']
bgn.inputs['Color'].default_value = (sky[0], sky[1], sky[2], 1.0)
bgn.inputs['Strength'].default_value = 1.3

scn.render.engine = 'CYCLES'
scn.cycles.device = 'GPU' if args.get('gpu') else 'CPU'
if args.get('gpu'):
    try:
        prefs = bpy.context.preferences.addons['cycles'].preferences
        for ctype in ('OPTIX', 'CUDA', 'HIP', 'ONEAPI'):
            try:
                prefs.compute_device_type = ctype
                prefs.get_devices()
                if any(d.type != 'CPU' for d in prefs.devices):
                    for d in prefs.devices:
                        d.use = True
                    break
            except Exception:
                continue
        else:
            scn.cycles.device = 'CPU'
    except Exception:
        scn.cycles.device = 'CPU'
scn.cycles.samples = int(args.get('samples', 128))
try:
    scn.cycles.use_denoising = True
    bpy.ops.render.render(write_still=False)   # Probe: faellt frueh, wenn kein OIDN
except Exception:
    scn.cycles.use_denoising = False
scn.cycles.sample_clamp_indirect = 4.0
scn.cycles.max_bounces = 24
scn.cycles.transmission_bounces = 24
scn.cycles.glossy_bounces = 8
scn.cycles.transparent_max_bounces = 32
scn.render.film_transparent = True
h_ratio = max(txt.dimensions.z / max(txt.dimensions.x, 0.2), 0.12)
scn.render.resolution_x = int(args.get('width', 1600))
scn.render.resolution_y = max(int(scn.render.resolution_x * h_ratio * 2.0), 260)
scn.render.image_settings.file_format = 'PNG'
scn.render.image_settings.color_mode = 'RGBA'
N = max(int(args.get('frames', 1)), 1)
for fi in range(N):
    # Wasser lebt: die 4. Noise-Dimension laeuft - Wellen wandern ueber die Buchstaben
    noise.inputs['W'].default_value = fi / float(N) * 1.7
    scn.render.filepath = args['out'].replace('IDX', f'{fi:03d}')
    bpy.ops.render.render(write_still=True)
'''


def render_water_text(text, bg_path, font_path, tint=(0.55, 0.9, 0.86),
                      sky=(0.75, 0.88, 0.92), width=1600, samples=128,
                      blender_path=None, gpu=True, cache_dir=None, timeout=900,
                      frames=1, material='wasser'):
    """Rendert einen Wasser-Glas-Text als RGBA-Sprite (numpy) oder None bei Fehler.
    frames>1: animierte Wasser-Oberflaeche als Loop -> Liste von Sprites.
    Cache ueber Text+Frame-Hash: identische Momente rendern nur einmal."""
    exe = find_blender(blender_path)
    if not exe or not os.path.exists(bg_path):
        return None
    cache_dir = cache_dir or os.path.join(tempfile.gettempdir(), 'douchko_blender')
    os.makedirs(cache_dir, exist_ok=True)
    key = hashlib.sha1((text + '|' + bg_path + '|' + str(tint) + '|'
                        + str(width) + '|' + str(samples) + '|' + str(frames)
                        + '|' + str(material))
                       .encode('utf-8')
                       + open(bg_path, 'rb').read(4096)).hexdigest()[:16]
    out_png = os.path.join(cache_dir, f'wt_{key}_IDX.png')
    frame_paths = [out_png.replace('IDX', f'{i:03d}') for i in range(max(frames, 1))]
    if not all(os.path.exists(p) for p in frame_paths):
        bgi = cv2.imread(bg_path)
        aspect = bgi.shape[0] / bgi.shape[1] if bgi is not None else 1.77
        if bgi is not None:
            # Refraktions-Platte: nur der untere Bild-Bereich (Wasser/Boden),
            # weichgezeichnet - keine Felsen/Boote als Geister in den Buchstaben
            h0 = int(bgi.shape[0] * 0.45)
            plate = bgi[h0:].astype(np.float32)
            # Ausreisser klemmen: dunkle Objekte (Boote) und helle Geister
            # (einbelegter Text) werden zur Wasser-Mitte gezogen - die Platte
            # wird ein sauberes Farbfeld, wie die Plate eines Compositors
            med = np.median(plate.reshape(-1, 3), axis=0)
            plate = np.clip(plate, med * 0.62, med * 1.55)
            plate = cv2.GaussianBlur(plate, (0, 0), 7).astype(np.uint8)
            aspect = plate.shape[0] / plate.shape[1]
            bg_path = os.path.join(cache_dir, f'bg_{key}.png')
            cv2.imwrite(bg_path, plate)
        args = {'text': text, 'bg': bg_path, 'out': out_png, 'font': font_path,
                'tint': list(tint), 'sky': list(sky), 'width': width,
                'samples': samples, 'gpu': bool(gpu), 'bg_aspect': aspect,
                'frames': max(frames, 1), 'material': material}
        with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False,
                                         encoding='utf-8') as fa:
            json.dump(args, fa); args_path = fa.name
        with tempfile.NamedTemporaryFile('w', suffix='.py', delete=False,
                                         encoding='utf-8') as fs:
            fs.write(BPY_SCRIPT); script_path = fs.name
        try:
            r = subprocess.run([exe, '-b', '--factory-startup', '-P', script_path,
                                '--', args_path],
                               capture_output=True, timeout=timeout * max(frames, 1))
            if not all(os.path.exists(p) for p in frame_paths):
                tail = (r.stdout or b'')[-500:].decode('utf-8', 'ignore')
                print(f"Blender render failed: {tail}")
                return None
        except subprocess.TimeoutExpired:
            print("Blender render: timed out")
            return None
        finally:
            for p in (args_path, script_path):
                try:
                    os.unlink(p)
                except OSError:
                    pass
    out = []
    for p in frame_paths:
        arr = cv2.imread(p, cv2.IMREAD_UNCHANGED)
        if arr is None or arr.shape[2] != 4:
            return None
        # Nachentrauschen (Builds ohne Denoiser) - nur RGB, Alpha bleibt scharf
        rgb = cv2.fastNlMeansDenoisingColored(arr[..., :3], None, 3, 3, 7, 21)
        arr = np.dstack([rgb, arr[..., 3]])
        out.append(np.ascontiguousarray(arr[..., [2, 1, 0, 3]]))
    return out[0] if frames <= 1 else out


def anim_loop_idx(dt, n, fps=10.0):
    """Ping-Pong-Index fuer nahtlose Sprite-Loops: 0..n-1..0..n-1..."""
    if n <= 1:
        return 0
    k = int(max(dt, 0.0) * fps) % (2 * n - 2)
    return k if k < n else 2 * n - 2 - k
