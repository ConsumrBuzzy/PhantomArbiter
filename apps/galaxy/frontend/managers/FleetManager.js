
import * as THREE from 'three';

/**
 * FleetManager
 * Handles high-fidelity trade visualization using InstancedMesh.
 * "Ships" fly from Tokens (Planets) to DEXs (Moons) to visualize liquidty flow.
 */
export class FleetManager {
    constructor(sceneManager, starSystem) {
        this.sceneManager = sceneManager;
        this.starSystem = starSystem;

        this.MAX_SHIPS = 10000;
        this.densityLimit = 10000; // Performance slider control
        this.ships = []; // Active ship data { index, start, end, progress, speed }

        this.initMesh();
    }

    /**
     * Sets the fleet density limit (percentage of events that spawn ships)
     * @param {number} limit - Max number of visible ships (0-10000)
     */
    setDensity(limit) {
        this.densityLimit = Math.max(0, Math.min(this.MAX_SHIPS, limit));
        // Immediately cap current visible count
        this.mesh.count = Math.min(this.ships.length, this.densityLimit);
    }

    initMesh() {
        // Ship Geometry: A small tetrahedron (Star Destroyer / Pyramid style)
        const geometry = new THREE.ConeGeometry(0.5, 1.5, 4);
        geometry.rotateX(Math.PI / 2); // Point forward

        // Material: Emissive based on Buy (Green) / Sell (Red)
        const material = new THREE.MeshBasicMaterial({ color: 0xffffff });

        this.mesh = new THREE.InstancedMesh(geometry, material, this.MAX_SHIPS);
        this.mesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
        this.mesh.count = 0; // Start empty

        // Color array for instances
        this.colors = new Float32Array(this.MAX_SHIPS * 3);
        this.mesh.instanceColor = new THREE.InstancedBufferAttribute(this.colors, 3);

        this.sceneManager.add(this.mesh);

        this.dummy = new THREE.Object3D();
    }

    spawnShip(data) {
        // data: { mint, price, size, is_buy }
        if (this.ships.length >= this.MAX_SHIPS) return; // Cap limit
        if (this.ships.length >= this.densityLimit) return; // Performance slider limit

        const planet = this.starSystem.nodes.get(data.mint);
        if (!planet) return;

        // Determine Start/End
        // Buy: Moon -> Planet (Inflow)
        // Sell: Planet -> Moon (Outflow)
        // For now, we assume a "Center" or random Moon if specific pool unknown

        const planetPos = planet.getWorldPosition(new THREE.Vector3());
        // Random point in space for now as "The Market"
        const marketPos = planetPos.clone().add(new THREE.Vector3((Math.random() - 0.5) * 50, (Math.random() - 0.5) * 50, (Math.random() - 0.5) * 50));

        let start, end, color;

        if (data.is_buy) {
            start = marketPos;
            end = planetPos;
            color = new THREE.Color(0x00ff00);
        } else {
            start = planetPos;
            end = marketPos;
            color = new THREE.Color(0xff0000);
        }

        const index = this.ships.length;

        this.ships.push({
            index: index,
            start: start,
            end: end,
            progress: 0,
            speed: 0.02 + (Math.random() * 0.03) // Variable speed
        });

        // Set Color
        this.colors[index * 3] = color.r;
        this.colors[index * 3 + 1] = color.g;
        this.colors[index * 3 + 2] = color.b;
        this.mesh.instanceColor.needsUpdate = true;

        this.mesh.count = this.ships.length;
    }

    update(delta) {
        if (this.ships.length === 0) return;

        let activeShips = [];
        let dirty = false;

        // Update positions
        for (let i = 0; i < this.ships.length; i++) {
            const ship = this.ships[i];
            ship.progress += ship.speed; // * delta;

            if (ship.progress < 1) {
                // Interpolate
                this.dummy.position.lerpVectors(ship.start, ship.end, ship.progress);
                this.dummy.lookAt(ship.end);
                this.dummy.updateMatrix();

                // If ship index changed (due to removal of others), we need to handle that map
                // Simpler approach: Compact array at end frame, but for now simple swap
                this.mesh.setMatrixAt(i, this.dummy.matrix);

                activeShips.push(ship);
            }
        }

        this.mesh.instanceMatrix.needsUpdate = true;

        // Cleanup completed ships (Naive approach - optimize later with ring buffer)
        if (activeShips.length < this.ships.length) {
            this.ships = activeShips;
            this.mesh.count = this.ships.length;
            // Note: In a real particle system, we'd avoid array slicing and use a cursor
            // But JS Array is fast enough for <10k simplistic logic
        }
    }
}
