
import * as THREE from 'three';

export class MiniMapManager {
    constructor(sceneManager, containerId) {
        this.sceneManager = sceneManager;
        this.container = document.getElementById(containerId);

        if (!this.container) {
            console.error("MiniMap container not found");
            return;
        }

        // Grid Overlay
        this.container.style.position = 'relative';
        this.addQuadrantLabel('Q1: MEME', 'top: 5px; right: 5px;');
        this.addQuadrantLabel('Q2: DEFI', 'top: 5px; left: 5px;');
        this.addQuadrantLabel('Q3: UTIL', 'bottom: 5px; left: 5px;');
        this.addQuadrantLabel('Q4: DEGEN', 'bottom: 5px; right: 5px;');

        // Crosshair
        const crosshair = document.createElement('div');
        crosshair.style.cssText = `position: absolute; top: 50%; left: 50%; width: 10px; height: 10px; border: 1px solid #0f0; transform: translate(-50%, -50%); pointer-events: none; opacity: 0.5;`;
        this.container.appendChild(crosshair);

        this.width = this.container.clientWidth;
        this.height = this.container.clientHeight;

        // 1. Camera (Orthographic Top-Down)
        // View size: 1000 units?
        const frustumSize = 1000;
        const aspect = this.width / this.height;
        this.camera = new THREE.OrthographicCamera(
            frustumSize * aspect / -2,
            frustumSize * aspect / 2,
            frustumSize / 2,
            frustumSize / -2,
            1,
            2000
        );
        this.camera.position.set(0, 500, 0); // High up
        this.camera.lookAt(0, 0, 0);
        this.camera.layers.enable(0); // See default stuff

        // 2. Renderer
        this.renderer = new THREE.WebGLRenderer({
            alpha: true,
            antialias: false
        });
        this.renderer.setSize(this.width, this.height);
        this.renderer.setClearColor(0x000000, 1);
        this.container.appendChild(this.renderer.domElement);

        // 3. Interaction (Click to Jump)
        this.renderer.domElement.addEventListener('pointerdown', (e) => this.onMiniMapClick(e));

        // 4. Player Marker (Where is the main camera?)
        // We add this to the SCENE but only visible to MiniMap layer if possible?
        // Easier: Just draw a 2D Overlay logic or a sprite.
        // Let's make a Sprite that follows the main camera x/z
        this.marker = new THREE.Mesh(
            new THREE.RingGeometry(10, 15, 32),
            new THREE.MeshBasicMaterial({ color: 0x00ff00, side: THREE.DoubleSide })
        );
        this.marker.rotation.x = -Math.PI / 2;
        this.marker.position.y = 100; // Above plane
        this.sceneManager.scene.add(this.marker);
    }

    onMiniMapClick(event) {
        // Calculate normalized device coordinates (-1 to +1)
        const rect = this.renderer.domElement.getBoundingClientRect();
        const x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
        const y = -((event.clientY - rect.top) / rect.height) * 2 + 1;

        // Unproject to world coordinates
        // For orthographic, it's linear mapping
        const vector = new THREE.Vector3(x, y, 0).unproject(this.camera);

        console.log("Tactical Jump to:", vector);

        // Teleport Main Camera
        // We keep Y (height) but move X/Z
        const mainCam = this.sceneManager.camera;
        const targetPos = new THREE.Vector3(vector.x, mainCam.position.y, vector.z);

        // Animated Transition?
        // For now, snap
        // mainCam.position.copy(targetPos);
        // this.sceneManager.controls.target.set(vector.x, 0, vector.z);

        // Smooth Pan
        this.teleport(vector.x, vector.z);
    }

    teleport(x, z) {
        const controls = this.sceneManager.controls;
        // Tweening could go here
        controls.target.set(x, 0, z);
        this.sceneManager.camera.position.set(x, 400, z + 400); // Maintain offset
        controls.update();
    }

    addQuadrantLabel(text, style) {
        const div = document.createElement('div');
        div.innerText = text;
        div.style.cssText = `position: absolute; color: rgba(0,255,0,0.5); font-size: 10px; pointer-events: none; ${style}`;
        this.container.appendChild(div);
    }

    update() {
        // Sync Marker
        const mainCam = this.sceneManager.camera;
        this.marker.position.x = mainCam.position.x;
        this.marker.position.z = mainCam.position.z;
        // Marker looks at camera target?

        // Render
        this.renderer.render(this.sceneManager.scene, this.camera);
    }
}
