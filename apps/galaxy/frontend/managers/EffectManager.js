
import * as THREE from 'three';

export class EffectManager {
    constructor(sceneManager) {
        this.sceneManager = sceneManager;
        this.scene = sceneManager.scene;

        this.initStarfield();
        this.initGrid();
    }

    initStarfield() {
        // Procedural Starfield
        const starGeo = new THREE.BufferGeometry();
        const starCount = 10000;
        const positions = new Float32Array(starCount * 3);

        for (let i = 0; i < starCount; i++) {
            positions[i * 3] = (Math.random() - 0.5) * 4000;
            positions[i * 3 + 1] = (Math.random() - 0.5) * 4000;
            positions[i * 3 + 2] = (Math.random() - 0.5) * 4000;
        }

        starGeo.setAttribute('position', new THREE.BufferAttribute(positions, 3));
        const starMat = new THREE.PointsMaterial({ color: 0xffffff, size: 1.5, transparent: true, opacity: 0.8 });
        this.stars = new THREE.Points(starGeo, starMat);
        this.scene.add(this.stars);
    }

    initGrid() {
        // Subtle data grid plane for orientation
        const grid = new THREE.GridHelper(2000, 50, 0x112233, 0x050505);
        grid.position.y = -200;
        this.scene.add(grid);
    }

    update(delta) {
        // Subtle rotation of background stars
        if (this.stars) {
            this.stars.rotation.y += 0.0001 * delta;
        }
    }

    updateWeather(data) {
        // To be implemented: Congestion shaders
        console.log("Weather update:", data);
    }
}
