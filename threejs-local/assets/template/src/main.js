import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import './style.css';

const errorBox = document.querySelector('#error');
let errorCount = 0;
function reportError(message) {
  errorCount++;
  errorBox.hidden = false;
  errorBox.textContent = String(message);
}
window.addEventListener('error', event => reportError(event.message));
window.addEventListener('unhandledrejection', event => reportError(event.reason));

function start() {
  const canvas = document.querySelector('canvas');
  const stage = document.querySelector('#stage');
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
  renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
  renderer.shadowMap.enabled = true;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  const scene = new THREE.Scene();
  scene.background = new THREE.Color('#101d2b');
  scene.fog = new THREE.Fog('#101d2b', 13, 30);
  const camera = new THREE.PerspectiveCamera(43, 1, 0.1, 60);
  camera.position.set(6, 4.5, 8);
  const controls = new OrbitControls(camera, canvas);
  controls.target.set(0, 0.6, 0);
  controls.enableDamping = true;
  controls.minDistance = 4;
  controls.maxDistance = 17;
  controls.maxPolarAngle = Math.PI * 0.48;
  controls.autoRotate = true;
  controls.autoRotateSpeed = 0.65;
  controls.update();
  controls.saveState();
  scene.add(new THREE.HemisphereLight('#bde7ff', '#304455', 2));
  const key = new THREE.DirectionalLight('#fff1d8', 4);
  key.position.set(3, 7, 5);
  key.castShadow = true;
  key.shadow.mapSize.set(1024, 1024);
  key.shadow.camera.left = key.shadow.camera.bottom = -6;
  key.shadow.camera.right = key.shadow.camera.top = 6;
  key.shadow.normalBias = 0.025;
  scene.add(key);
  const rim = new THREE.PointLight('#7cafff', 28);
  rim.position.set(-4, 3, -3);
  scene.add(rim);
  const floor = new THREE.Mesh(new THREE.PlaneGeometry(200, 200), new THREE.MeshStandardMaterial({ color: '#172736', roughness: 0.85 }));
  floor.rotation.x = -Math.PI / 2;
  floor.receiveShadow = true;
  scene.add(floor);
  const grid = new THREE.GridHelper(18, 36, '#355063', '#243c4b');
  grid.position.y = 0.003;
  scene.add(grid);
  const geometries = [new THREE.BoxGeometry(1.35, 1.35, 1.35), new THREE.TorusKnotGeometry(0.58, 0.19, 96, 16), new THREE.IcosahedronGeometry(0.85, 0)];
  const colors = ['#72d9bd', '#e7a169', '#92aaf2'];
  const names = ['立方体', '环面结', '二十面体'];
  const objects = geometries.map((geometry, index) => {
    const mesh = new THREE.Mesh(geometry, new THREE.MeshStandardMaterial({ color: colors[index], metalness: 0.25, roughness: 0.3 }));
    mesh.position.set((index - 1) * 2.4, 1.1, 0);
    mesh.castShadow = true;
    mesh.receiveShadow = true;
    mesh.name = names[index];
    scene.add(mesh);
    return mesh;
  });
  let moving = true;
  let elapsed = 0;
  let frames = 0;
  let sampleFrames = 0;
  let sampleTime = performance.now();
  let fps = 0;
  let selected = '无';
  let selections = 0;
  const motion = document.querySelector('#motion');
  const orbit = document.querySelector('#orbit');
  function updateOrbit() {
    orbit.textContent = controls.autoRotate ? '停止环绕' : '开始环绕';
    orbit.setAttribute('aria-pressed', String(controls.autoRotate));
  }
  motion.addEventListener('click', () => {
    moving = !moving;
    motion.textContent = moving ? '暂停动画' : '继续动画';
    motion.setAttribute('aria-pressed', String(moving));
  });
  orbit.addEventListener('click', () => { controls.autoRotate = !controls.autoRotate; updateOrbit(); });
  document.querySelector('#reset').addEventListener('click', () => { controls.reset(); });
  controls.addEventListener('start', () => { controls.autoRotate = false; updateOrbit(); });
  const raycaster = new THREE.Raycaster();
  const pointer = new THREE.Vector2();
  let down;
  canvas.addEventListener('pointerdown', event => { down = [event.clientX, event.clientY]; });
  canvas.addEventListener('pointerup', event => {
    if (!down || Math.hypot(event.clientX - down[0], event.clientY - down[1]) > 5) return;
    const rect = canvas.getBoundingClientRect();
    pointer.set((event.clientX - rect.left) / rect.width * 2 - 1, -(event.clientY - rect.top) / rect.height * 2 + 1);
    raycaster.setFromCamera(pointer, camera);
    const hit = raycaster.intersectObjects(objects)[0];
    if (hit) {
      hit.object.material.color.offsetHSL(0.17, 0, 0);
      selected = hit.object.name;
      selections++;
      document.querySelector('#selection').textContent = `已选择：${selected} · 已变色 ${selections} 次`;
    }
  });
  const resizeObserver = new ResizeObserver(() => {
    const { width, height } = stage.getBoundingClientRect();
    renderer.setSize(width, height, false);
    camera.aspect = width / height;
    camera.updateProjectionMatrix();
  });
  resizeObserver.observe(stage);
  let previous;
  const diagnostic = document.querySelector('#diagnostics');
  renderer.setAnimationLoop(now => {
    const delta = previous === undefined ? 0 : Math.min((now - previous) / 1000, 0.05);
    previous = now;
    if (moving) {
      elapsed += delta;
      objects.forEach((mesh, index) => {
        mesh.rotation.set(elapsed * 0.24, elapsed * (0.3 + index * 0.1), elapsed * 0.1);
        mesh.position.y = 1.1 + Math.sin(elapsed * 1.4 + index) * 0.13;
      });
    }
    controls.update(delta);
    renderer.render(scene, camera);
    frames++;
    sampleFrames++;
    if (now - sampleTime >= 500) {
      fps = Math.round(sampleFrames * 1000 / (now - sampleTime));
      sampleFrames = 0;
      sampleTime = now;
      diagnostic.textContent = JSON.stringify({ webgl: renderer.getContext().getParameter(renderer.getContext().VERSION), frames, fps, animationTime: Number(elapsed.toFixed(2)), camera: camera.position.toArray().map(n => Number(n.toFixed(3))), animation: moving, orbit: controls.autoRotate, selected, selections, errors: errorCount, drawCalls: renderer.info.render.calls, triangles: renderer.info.render.triangles, canvas: [canvas.width, canvas.height] }, null, 2);
    }
  });
}
try { start(); } catch (error) { reportError(error.message); console.error(error); }
