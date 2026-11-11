import * as THREE from 'three';
import { OrbitControls } from './vendor/OrbitControls.js';

const COLORS = {
  tof: 0x50dcff,
  hc: 0xffaa3c,
  wall: 0x5096e6,
  wall_edge: 0x82c8ff,
  prior: 0x9ad6a0,
  selected: 0xffffff,
  presence: 0x5affb0,
};

const state = {
  ready: false,
  container: null,
  renderer: null,
  scene: null,
  camera: null,
  controls: null,
  groups: {},
  layers: {
    points: true,
    walls: true,
    priors: true,
    objects: true,
    labels: true,
    grid: true,
  },
  bounds: new THREE.Box3(),
  payload: null,
  hasPayload: false,
  autoRotate: false,
};

function color(value) {
  if (Array.isArray(value)) {
    return new THREE.Color(value[0] / 255, value[1] / 255, value[2] / 255);
  }
  return new THREE.Color(value || COLORS.wall);
}

function makeGroup(name) {
  const group = new THREE.Group();
  group.name = name;
  state.scene.add(group);
  state.groups[name] = group;
  return group;
}

function disposeObject(object) {
  object.traverse((child) => {
    if (child.geometry) child.geometry.dispose();
    if (child.material) {
      const materials = Array.isArray(child.material) ? child.material : [child.material];
      for (const material of materials) {
        if (material.map) material.map.dispose();
        material.dispose();
      }
    }
  });
}

function clearGroup(name) {
  const group = state.groups[name];
  if (!group) return;
  for (const child of [...group.children]) {
    group.remove(child);
    disposeObject(child);
  }
}

function labelSprite(text, textColor = '#ffffff', scale = 1) {
  const canvas = document.createElement('canvas');
  canvas.width = 512;
  canvas.height = 96;
  const context = canvas.getContext('2d');
  context.clearRect(0, 0, canvas.width, canvas.height);
  context.fillStyle = 'rgba(8, 15, 25, 0.84)';
  context.strokeStyle = 'rgba(120, 160, 205, 0.65)';
  context.lineWidth = 3;
  const radius = 18;
  context.beginPath();
  context.roundRect(4, 8, canvas.width - 8, canvas.height - 16, radius);
  context.fill();
  context.stroke();
  context.font = 'bold 30px system-ui, sans-serif';
  context.textAlign = 'center';
  context.textBaseline = 'middle';
  context.fillStyle = textColor;
  context.fillText(String(text).slice(0, 36), canvas.width / 2, canvas.height / 2 + 1);
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  const sprite = new THREE.Sprite(new THREE.SpriteMaterial({
    map: texture, transparent: true, depthTest: false, depthWrite: false,
    toneMapped: false,
  }));
  sprite.center.set(0.5, 0.5);
  sprite.scale.set(1.55 * scale, 0.29 * scale, 1);
  sprite.renderOrder = 1000;
  return sprite;
}

function addBox(box) {
  const length = Math.max(0.05, Number(box.length_m) || 0.05);
  const width = Math.max(0.05, Number(box.width_m) || 0.05);
  const z0 = Math.max(0, Number(box.z_bottom_m) || 0);
  const z1 = Math.max(z0 + 0.03, Number(box.z_top_m) || z0 + 0.1);
  const geometry = new THREE.BoxGeometry(length, width, z1 - z0);
  const base = color(box.color || COLORS[box.label] || COLORS.wall);
  const prior = box.source === 'prior';
  const wall = box.label === 'wall' || box.label === 'wall_edge';
  const material = new THREE.MeshStandardMaterial({
    color: base,
    emissive: base,
    emissiveIntensity: prior ? 0.05 : (wall ? 0.07 : 0.20),
    transparent: true,
    opacity: prior ? 0.15 : (wall ? 0.20 : 0.46),
    depthWrite: false,
    roughness: 0.62,
    metalness: 0.0,
    side: THREE.DoubleSide,
    toneMapped: false,
  });
  const mesh = new THREE.Mesh(geometry, material);
  mesh.position.set(Number(box.cx_m) || 0, Number(box.cy_m) || 0, (z0 + z1) / 2);
  mesh.rotation.z = THREE.MathUtils.degToRad(Number(box.angle_deg) || 0);
  mesh.userData.boxId = box.id;
  mesh.userData.box = box;
  const edge = new THREE.LineSegments(
    new THREE.EdgesGeometry(geometry),
    new THREE.LineBasicMaterial({
      color: base,
      transparent: true,
      opacity: prior ? 0.72 : 0.96,
      toneMapped: false,
    }),
  );
  mesh.add(edge);
  const groupName = wall ? 'walls' : (prior ? 'priors' : 'objects');
  state.groups[groupName].add(mesh);
  if (box.id === state.payload?.selectedId) {
    const helper = new THREE.BoxHelper(mesh, COLORS.selected);
    helper.material.depthTest = false;
    helper.material.transparent = true;
    helper.material.opacity = 0.98;
    helper.renderOrder = 1002;
    state.groups.labels.add(helper);
  }
  return mesh;
}

function addLabel(text, position, textColor = '#ffffff', scale = 1) {
  const sprite = labelSprite(text, textColor, scale);
  sprite.position.copy(position);
  state.groups.labels.add(sprite);
  return sprite;
}

function addDistanceLine(box, index) {
  const origin = new THREE.Vector3(0, 0, 0.025);
  const end = new THREE.Vector3(Number(box.cx_m) || 0, Number(box.cy_m) || 0, 0.025);
  if (origin.distanceTo(end) < 0.08) return;
  const geometry = new THREE.BufferGeometry().setFromPoints([origin, end]);
  const material = new THREE.LineBasicMaterial({
    color: color(box.color), transparent: true, opacity: 0.46,
  });
  state.groups.distances.add(new THREE.Line(geometry, material));
  // The distance is appended to the box label above the object, so the floor
  // stays clear and labels never stack at the sensor origin.
}

function addPresenceTrack(track, index, yawDeg) {
  const distance = Number(track.distance_cm) / 100;
  if (!Number.isFinite(distance) || distance <= 0) return;
  const yaw = THREE.MathUtils.degToRad(Number(yawDeg) || 0);
  const x = distance * Math.cos(yaw);
  const y = distance * Math.sin(yaw);
  const trackColor = index === 0 ? COLORS.presence : 0x66d9ff;
  const geometry = new THREE.CapsuleGeometry(0.23, 1.05, 5, 10);
  const material = new THREE.MeshStandardMaterial({
    color: trackColor,
    transparent: true,
    opacity: 0.40,
    depthWrite: false,
    emissive: trackColor,
    emissiveIntensity: 0.34,
    toneMapped: false,
  });
  const capsule = new THREE.Mesh(geometry, material);
  capsule.rotation.x = Math.PI / 2;
  capsule.position.set(x, y, 0.85);
  capsule.userData.track = track;
  state.groups.presence.add(capsule);
  const ring = new THREE.Mesh(
    new THREE.RingGeometry(0.22, 0.30, 24),
    new THREE.MeshBasicMaterial({
      color: trackColor, transparent: true, opacity: 0.75, side: THREE.DoubleSide,
    }),
  );
  ring.position.set(x, y, 0.025);
  state.groups.presence.add(ring);
  const lineGeometry = new THREE.BufferGeometry().setFromPoints([
    new THREE.Vector3(0, 0, 0.03), new THREE.Vector3(x, y, 0.03),
  ]);
  state.groups.presence.add(new THREE.Line(
    lineGeometry,
    new THREE.LineDashedMaterial({
      color: trackColor, dashSize: 0.10, gapSize: 0.06,
      transparent: true, opacity: 0.82,
    }),
  ).computeLineDistances());
  // The radar has no angle: draw the radial uncertainty arc so the marker is
  // not mistaken for an exact 2D position.
  const half = THREE.MathUtils.degToRad(
    Number(state.payload?.presenceUncertaintyDeg) || 60);
  const arcPoints = [];
  for (let step = 0; step <= 24; step += 1) {
    const angle = yaw - half + (2 * half * step) / 24;
    arcPoints.push(new THREE.Vector3(
      distance * Math.cos(angle), distance * Math.sin(angle), 0.035));
  }
  const arc = new THREE.Line(
    new THREE.BufferGeometry().setFromPoints(arcPoints),
    new THREE.LineDashedMaterial({
      color: trackColor, dashSize: 0.09, gapSize: 0.07,
      transparent: true, opacity: 0.38,
    }),
  );
  arc.computeLineDistances();
  state.groups.presence.add(arc);
  const label = addLabel(
    `${track.id || (index === 0 ? 'H1' : 'H2')} ${distance.toFixed(2)} m`,
    new THREE.Vector3(x, y, 2.05),
    index === 0 ? '#8dffc6' : '#9fe8ff',
    0.64,
  );
  label.renderOrder = 1003;
}

function updateBounds() {
  const box = new THREE.Box3();
  let has = false;
  let minZ = Infinity;
  let maxZ = -Infinity;
  for (const point of state.payload?.points || []) {
    minZ = Math.min(minZ, Number(point.z) || 0);
    maxZ = Math.max(maxZ, Number(point.z) || 0);
  }
  for (const item of state.payload?.boxes || []) {
    minZ = Math.min(minZ, Number(item.z_bottom_m) || 0);
    maxZ = Math.max(maxZ, Number(item.z_top_m) || 0.1);
  }
  const outline = (state.payload?.roomOutline || [])
    .filter(point => Array.isArray(point) && point.length >= 2);
  if (outline.length >= 3) {
    // Frame the measured room, not the desk/wardrobe priors outside it.
    for (const point of outline) {
      box.expandByPoint(new THREE.Vector3(point[0], point[1], 0));
    }
    has = true;
  } else {
    for (const point of state.payload?.points || []) {
      box.expandByPoint(new THREE.Vector3(point.x, point.y, point.z));
      has = true;
    }
    for (const item of state.payload?.boxes || []) {
      box.expandByPoint(new THREE.Vector3(
        item.cx_m, item.cy_m, Number(item.z_bottom_m) || 0));
      box.expandByPoint(new THREE.Vector3(
        item.cx_m, item.cy_m, Number(item.z_top_m) || 0.1));
      has = true;
    }
  }
  if (!has) box.set(new THREE.Vector3(-1, -1, 0), new THREE.Vector3(1, 1, 1));
  if (Number.isFinite(minZ) && Number.isFinite(maxZ)) {
    box.min.z = Math.min(box.min.z, minZ);
    box.max.z = Math.max(box.max.z, maxZ);
  }
  state.bounds.copy(box);
}

function centerAndRadius() {
  const center = state.bounds.getCenter(new THREE.Vector3());
  const size = state.bounds.getSize(new THREE.Vector3());
  const radius = Math.max(0.8, size.length() * 0.55);
  return { center, radius };
}

function setCamera(mode = 'iso') {
  if (!state.ready) return;
  const { center, radius } = centerAndRadius();
  const fov = THREE.MathUtils.degToRad(state.camera.fov);
  const margin = mode === 'top' ? 1.00 : 0.74;
  const distance = Math.max(2.4, radius / Math.sin(fov / 2) * margin);
  state.camera.up.set(0, 0, 1);
  if (mode === 'top') {
    state.camera.up.set(0, 1, 0);
    state.camera.position.copy(center).add(new THREE.Vector3(0, 0, distance));
  } else if (mode === 'front') {
    state.camera.position.copy(center).add(
      new THREE.Vector3(0, -distance, radius * 0.35));
  } else {
    state.camera.position.copy(center).add(
      new THREE.Vector3(0.72, -0.82, 0.72).normalize().multiplyScalar(distance));
  }
  state.controls.target.copy(center);
  state.controls.minPolarAngle = 0.02;
  state.controls.maxPolarAngle = Math.PI * 0.49;
  state.camera.near = Math.max(0.03, radius / 100);
  state.camera.far = Math.max(40, radius * 40);
  state.camera.updateProjectionMatrix();
  state.camera.lookAt(center);
  state.controls.update();
}

function applyLayers() {
  const layers = state.layers;
  const view = state.payload?.viewMode || 'both';
  if (state.groups.points) {
    state.groups.points.visible = layers.points && view !== 'blocks';
  }
  if (state.groups.walls) state.groups.walls.visible = layers.walls && view !== 'points';
  if (state.groups.priors) state.groups.priors.visible = layers.priors && view !== 'points'
    && (state.payload?.priorVisible !== false);
  if (state.groups.objects) state.groups.objects.visible = layers.objects && view !== 'points';
  if (state.groups.labels) state.groups.labels.visible = layers.labels;
  if (state.groups.grid) state.groups.grid.visible = layers.grid;
  if (state.groups.outline) state.groups.outline.visible = layers.grid
    && (state.payload?.priorVisible !== false);
  if (state.groups.axes) state.groups.axes.visible = layers.grid
    && (state.payload?.showAxis !== false);
  if (state.groups.presence) state.groups.presence.visible = layers.labels;
  if (state.groups.distances) state.groups.distances.visible = layers.labels
    && (state.payload?.showDistances !== false);
}

function update(payload) {
  if (!state.ready) return;
  state.payload = payload || {};
  for (const name of ['points', 'walls', 'priors', 'objects', 'labels',
    'presence', 'outline', 'distances']) clearGroup(name);

  const points = state.payload.points || [];
  if (points.length) {
    const positions = new Float32Array(points.length * 3);
    const colors = new Float32Array(points.length * 3);
    points.forEach((point, index) => {
      positions[index * 3] = point.x;
      positions[index * 3 + 1] = point.y;
      positions[index * 3 + 2] = point.z;
      const rgb = point.color || (point.source === 'tof' ? [80, 220, 255] : [255, 170, 60]);
      colors[index * 3] = rgb[0] / 255;
      colors[index * 3 + 1] = rgb[1] / 255;
      colors[index * 3 + 2] = rgb[2] / 255;
    });
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));
    const material = new THREE.PointsMaterial({
      size: 0.065,
      sizeAttenuation: true,
      vertexColors: true,
      transparent: true,
      opacity: 1.0,
      depthWrite: false,
      toneMapped: false,
    });
    state.groups.points.add(new THREE.Points(geometry, material));
  }

  const boxes = state.payload.boxes || [];
  boxes.forEach((box, index) => {
    addBox(box);
    const prior = box.source === 'prior';
    const wall = box.label === 'wall' || box.label === 'wall_edge';
    // Keep the 3D view readable: objects carry a permanent label; walls,
    // priors and the selected box are labelled only when selected/hovered.
    if (state.layers.labels && ((!prior && !wall) || box.id === state.payload?.selectedId)) {
      const distance = Number(wall ? box.nearest_m : box.distance_m);
      const suffix = !prior && Number.isFinite(distance)
        ? ` · ${distance.toFixed(2)} m` : '';
      const text = `#${index + 1} ${box.label}${prior ? ' prior' : ''}${suffix}`;
      addLabel(text, new THREE.Vector3(
        Number(box.cx_m) || 0,
        Number(box.cy_m) || 0,
        (Number(box.z_top_m) || 0) + 0.10,
      ), prior ? '#b9ffd0' : '#ffffff', prior ? 0.55 : 0.72);
    }
    if (state.payload.showDistances !== false) addDistanceLine(box, index + 1);
  });

  const outline = state.payload.roomOutline || [];
  if (outline.length >= 3) {
    const points3 = outline.map(([x, y]) => new THREE.Vector3(x, y, 0.01));
    const geometry = new THREE.BufferGeometry().setFromPoints([...points3, points3[0]]);
    const line = new THREE.Line(geometry, new THREE.LineDashedMaterial({
      color: 0x78ffc8, dashSize: 0.12, gapSize: 0.08,
      transparent: true, opacity: 0.55,
    }));
    line.computeLineDistances();
    state.groups.outline.add(line);
  }

  const tracks = state.payload.tracks || [];
  tracks.forEach((track, index) => addPresenceTrack(
    track, index, state.payload.presenceYawDeg || 0));

  const previousBounds = state.bounds.clone();
  updateBounds();
  const previousSize = previousBounds.getSize(new THREE.Vector3());
  const nextSize = state.bounds.getSize(new THREE.Vector3());
  const boundsChanged = !state.hasPayload
    || previousBounds.isEmpty()
    || previousSize.distanceTo(nextSize) > 0.35;
  if (boundsChanged) {
    state.hasPayload = true;
    setCamera('iso');
  }
  applyLayers();
  updateStatus(points.length, boxes.length, tracks.length,
    state.payload.occupancyLabel);
}

function updateStatus(points, boxes, tracks, occupancyLabel) {
  const element = document.getElementById('scene3d-status');
  if (!element) return;
  const occupancy = occupancyLabel ? ` · ${occupancyLabel}` : '';
  element.textContent = `WebGL · ${points} titik · ${boxes} blok · ${tracks} track${occupancy}`;
}

function setLayer(name, active) {
  if (!(name in state.layers)) return;
  state.layers[name] = Boolean(active);
  applyLayers();
}

function orbit(delta) {
  if (!state.ready) return;
  const offset = state.camera.position.clone().sub(state.controls.target);
  offset.applyAxisAngle(new THREE.Vector3(0, 0, 1), delta);
  state.camera.position.copy(state.controls.target).add(offset);
  state.controls.update();
}

function pitch(delta) {
  if (!state.ready) return;
  const offset = state.camera.position.clone().sub(state.controls.target);
  offset.applyAxisAngle(new THREE.Vector3(1, 0, 0), delta);
  state.camera.position.copy(state.controls.target).add(offset);
  state.controls.update();
}

function zoom(factor) {
  if (!state.ready) return;
  const offset = state.camera.position.clone().sub(state.controls.target);
  const length = THREE.MathUtils.clamp(offset.length() * factor, 0.4, 20);
  offset.setLength(length);
  state.camera.position.copy(state.controls.target).add(offset);
  state.controls.update();
}

function toggleFullscreen() {
  const wrap = state.container?.closest('.scene3d-wrap');
  if (!wrap) return;
  if (document.fullscreenElement) document.exitFullscreen();
  else wrap.requestFullscreen?.();
}

function demo() {
  if (!state.ready) return;
  state.layers = {
    points: true, walls: true, priors: true, objects: true, labels: true, grid: true,
  };
  state.autoRotate = true;
  setCamera('iso');
  applyLayers();
  if (typeof window.setSidebarOpen === 'function') window.setSidebarOpen(false);
  if (typeof window.showToast === 'function') {
    window.showToast('Demo 3D: kamera iso, semua layer aktif.', 'success', 3000);
  }
}

function init() {
  const container = document.getElementById('cloud3d');
  if (!container) return;
  state.container = container;
  try {
    state.renderer = new THREE.WebGLRenderer({
      antialias: true,
      alpha: false,
      powerPreference: 'high-performance',
    });
  } catch (error) {
    container.textContent = `WebGL tidak tersedia: ${error.message}`;
    return;
  }
  state.renderer.setPixelRatio(Math.min(2, window.devicePixelRatio || 1));
  state.renderer.outputColorSpace = THREE.SRGBColorSpace;
  state.renderer.setClearColor(0x0a1019, 1);
  container.appendChild(state.renderer.domElement);

  state.scene = new THREE.Scene();
  state.scene.background = new THREE.Color(0x0a1019);
  state.camera = new THREE.PerspectiveCamera(50, 1, 0.03, 100);
  state.camera.up.set(0, 0, 1);
  state.controls = new OrbitControls(state.camera, state.renderer.domElement);
  state.controls.enableDamping = true;
  state.controls.dampingFactor = 0.08;
  state.controls.minDistance = 0.4;
  state.controls.maxDistance = 20;
  state.controls.target.set(1.0, 0.2, 0.8);
  state.controls.addEventListener('start', () => { state.autoRotate = false; });

  state.scene.add(new THREE.HemisphereLight(0xddeeff, 0x18283a, 1.4));
  const sun = new THREE.DirectionalLight(0xffffff, 1.3);
  sun.position.set(4, -5, 8);
  state.scene.add(sun);

  for (const name of ['points', 'walls', 'priors', 'objects', 'labels',
    'presence', 'grid', 'outline', 'axes', 'distances']) {
    makeGroup(name);
  }

  const grid = new THREE.GridHelper(8, 32, 0x2d425c, 0x18283a);
  grid.rotation.x = Math.PI / 2;
  grid.position.set(1.05, 0.35, -0.01);
  state.groups.grid.add(grid);
  const floor = new THREE.Mesh(
    new THREE.PlaneGeometry(8, 8),
    new THREE.MeshBasicMaterial({
      color: 0x0e1825, transparent: true, opacity: 0.40, depthWrite: false,
    }),
  );
  floor.position.set(1.05, 0.35, -0.02);
  state.groups.grid.add(floor);

  const axes = new THREE.AxesHelper(1.4);
  axes.position.set(-0.1, -0.9, 0.01);
  state.groups.axes.add(axes);

  state.renderer.domElement.addEventListener('pointerdown', (event) => {
    state.pointerStart = { x: event.clientX, y: event.clientY };
  });
  state.renderer.domElement.addEventListener('pointerup', (event) => {
    if (!state.pointerStart) return;
    const moved = Math.hypot(event.clientX - state.pointerStart.x,
      event.clientY - state.pointerStart.y);
    if (moved > 5) return;
    const rect = state.renderer.domElement.getBoundingClientRect();
    const pointer = new THREE.Vector2(
      ((event.clientX - rect.left) / rect.width) * 2 - 1,
      -((event.clientY - rect.top) / rect.height) * 2 + 1,
    );
    const raycaster = new THREE.Raycaster();
    raycaster.setFromCamera(pointer, state.camera);
    const hits = raycaster.intersectObjects(state.groups.walls.children
      .concat(state.groups.priors.children, state.groups.objects.children), true);
    if (hits.length && typeof window.selectBoxById === 'function') {
      const candidates = new Map();
      for (const hit of hits) {
        const owner = hit.object.userData.boxId ? hit.object : hit.object.parent;
        const box = owner?.userData?.box;
        if (!box) continue;
        const previous = candidates.get(box.id);
        if (!previous || hit.distance < previous.distance) {
          candidates.set(box.id, { box, distance: hit.distance });
        }
      }
      const rank = (box) => {
        if (box.source === 'prior') return 1;
        if (box.label === 'wall' || box.label === 'wall_edge') return 2;
        return 0;
      };
      const list = [...candidates.values()].sort((a, b) => {
        const byRank = rank(a.box) - rank(b.box);
        if (byRank) return byRank;
        if (Math.abs(a.distance - b.distance) > 1e-4) {
          return a.distance - b.distance;
        }
        return (Number(a.box.length_m) * Number(a.box.width_m))
          - (Number(b.box.length_m) * Number(b.box.width_m));
      });
      if (list.length) window.selectBoxById(list[0].box.id);
    }
  });
  state.renderer.domElement.addEventListener('pointermove', (event) => {
    const rect = state.renderer.domElement.getBoundingClientRect();
    const pointer = new THREE.Vector2(
      ((event.clientX - rect.left) / rect.width) * 2 - 1,
      -((event.clientY - rect.top) / rect.height) * 2 + 1,
    );
    const raycaster = new THREE.Raycaster();
    raycaster.setFromCamera(pointer, state.camera);
    const hits = raycaster.intersectObjects(state.groups.walls.children
      .concat(state.groups.priors.children, state.groups.objects.children), true);
    state.renderer.domElement.style.cursor = hits.length ? 'pointer' : 'grab';
  });

  state.ready = true;
  state.container.closest('.scene3d-wrap')?.classList.add('webgl');
  const status = document.getElementById('scene3d-status');
  if (status) status.textContent = 'WebGL siap · memuat scene…';
  resize();
  new ResizeObserver(resize).observe(container);
  state.renderer.setAnimationLoop(() => {
    if (state.autoRotate) {
      const offset = state.camera.position.clone().sub(state.controls.target);
      offset.applyAxisAngle(new THREE.Vector3(0, 0, 1), 0.0018);
      state.camera.position.copy(state.controls.target).add(offset);
    }
    state.controls.update();
    state.renderer.render(state.scene, state.camera);
  });
  window.dispatchEvent(new Event('room3d-ready'));
}

function resize() {
  if (!state.ready) return;
  const width = state.container.clientWidth || 640;
  const height = state.container.clientHeight || 360;
  state.renderer.setSize(width, height, false);
  state.camera.aspect = width / Math.max(1, height);
  state.camera.updateProjectionMatrix();
}

window.Room3D = {
  init,
  update,
  setLayer,
  setCamera,
  orbit,
  pitch,
  zoom,
  toggleFullscreen,
  demo,
  resize,
  isReady: () => state.ready,
};

init();
