```javascript

import * as THREE from 'three';

export class StarSystemManager {
    constructor(sceneManager, uiManager) {
        this.sceneManager = sceneManager;
        this.uiManager = uiManager;
        this.nodes = new Map(); // id -> Mesh
    }

    update(delta) {
        this.nodes.forEach(node => {
            if (node.userData.nodeType === 'MOON') {
                // Orbital mechanics
                node.userData.orbitAngle += node.userData.orbitSpeed; // * delta technically
                const r = node.userData.orbitRadius;
                const tilt = node.userData.orbitTilt || 0;
                node.position.set(
                    r * Math.cos(node.userData.orbitAngle),
                    r * Math.sin(node.userData.orbitAngle) * tilt,
                    r * Math.sin(node.userData.orbitAngle)
                );
                node.rotation.y += 0.03;
            } else {
                // Planet rotation
                node.rotation.y += 0.005;
            }

            this.updateLabel(node);
        });
    }

    updatePlanets(dataList) {
        dataList.forEach(data => this.updateArchetype(data));
    }

    updateArchetype(data) {
        if (data.archetype === 'MOON' || data.node_type === 'MOON') {
            this.createMoon(data.id, data.label, data.params);
        } else {
            this.createNode(data.id, data.label, data.archetype, data.params, data.node_type || 'TOKEN');
        }
    }

    createNode(id, label, archetype, params, nodeType = 'TOKEN') {
        const existing = this.nodes.get(id);
        if (existing) {
            // Update logic: Refresh Price/RSI if params changed
            if (params.price || params.rsi) {
                this.updateNodeData(id, { p: params.price, rsi: params.rsi });
            }
            return existing;
        }

        // --- LOD Container ---
        const lod = new THREE.LOD();

        // Level 0: High Fidelity (< 100 distance)
        let geometryHigh;
        switch (archetype) {
            case 'GLOBE': geometryHigh = new THREE.SphereGeometry(params.radius || 2, 16, 16); break;
            case 'PLANET': geometryHigh = new THREE.SphereGeometry(params.radius || 3, 32, 32); break;
            case 'SUPERNOVA': geometryHigh = new THREE.IcosahedronGeometry(params.radius || 5, 1); break;
            case 'PULSAR': geometryHigh = new THREE.OctahedronGeometry(params.radius || 2, 0); break;
            case 'NOVA': geometryHigh = new THREE.DodecahedronGeometry(params.radius || 2, 0); break;
            case 'COMET': geometryHigh = new THREE.ConeGeometry(params.radius || 1, params.radius * 2, 8); break;
            case 'WHALE': geometryHigh = new THREE.TorusKnotGeometry(params.radius || 3, 0.5, 64, 8); break;
            default: geometryHigh = new THREE.TetrahedronGeometry(params.radius || 1, 0);
        }

        const materialHigh = new THREE.MeshStandardMaterial({
            color: new THREE.Color(params.hex_color || '#ffffff'),
            emissive: new THREE.Color(params.hex_color || '#000000'),
            emissiveIntensity: params.emissive_intensity || 0.5,
            roughness: params.roughness !== undefined ? params.roughness : 0.5,
            metalness: params.metalness !== undefined ? params.metalness : 0.8,
            wireframe: params.roughness < 0.2
        });

        const meshHigh = new THREE.Mesh(geometryHigh, materialHigh);
        lod.addLevel(meshHigh, 0);

        // Level 1: Low Poly (100 - 400 distance)
        // Use simple shapes for all
        const geometryLow = new THREE.IcosahedronGeometry(params.radius || 2, 0);
        const materialLow = new THREE.MeshBasicMaterial({
            color: params.hex_color || '#ffffff',
            wireframe: true
        });
        const meshLow = new THREE.Mesh(geometryLow, materialLow);
        lod.addLevel(meshLow, 100);

        // Level 2: Point / Very Low ( > 400 distance)
        // If too far, maybe just invisible or a tiny sprite. 
        // For performance, we can just stop rendering or use a Point.
        // Let's use a very low poly tetrahdron
        const geometryFar = new THREE.TetrahedronGeometry((params.radius || 2) * 0.8, 0);
        const materialFar = new THREE.MeshBasicMaterial({ color: params.hex_color, wireframe: false });
        const meshFar = new THREE.Mesh(geometryFar, materialFar);
        lod.addLevel(meshFar, 400);

        // Positioning
        if (params.x !== undefined && params.y !== undefined && params.z !== undefined) {
            lod.position.set(params.x, params.y, params.z);
        } else {
            // Category-based Layout
            const pos = this.getCategoryPosition(params.category || 'UNKNOWN');
            lod.position.set(pos.x, pos.y, pos.z);
        }

        lod.userData = { id, label, type: archetype, nodeType, params };
        
        // DELEGATE UI: Create Label via UIManager
        this.uiManager.createLabel(id, label, params, (selectedId) => {
             this.selectNode(selectedId);
        });

        this.sceneManager.add(lod);
        this.nodes.set(id, lod);
        return lod;
    }

    createMoon(id, label, params) {
        const parentNode = this.nodes.get(params.parent_mint);
        if (!parentNode) return null;

        const geometry = new THREE.SphereGeometry(params.radius || 0.5, 12, 12);
        const material = new THREE.MeshStandardMaterial({
            color: new THREE.Color(params.hex_color || '#888888'),
            emissive: new THREE.Color(params.hex_color || '#444444'),
            emissiveIntensity: params.emissive_intensity || 1.0
        });

        const moon = new THREE.Mesh(geometry, material);
        const orbitRadius = params.orbit_radius || 5;
        const angle = Math.random() * Math.PI * 2;

        moon.position.set(orbitRadius * Math.cos(angle), 0, orbitRadius * Math.sin(angle));

        moon.userData = {
            id, label, type: 'MOON', nodeType: 'MOON', params,
            parentMint: params.parent_mint, orbitAngle: angle, orbitRadius,
            orbitSpeed: params.orbit_speed || 0.02, orbitTilt: (Math.random() - 0.5) * 0.5
        };

        parentNode.add(moon);
        this.nodes.set(id, moon);
        return moon;
    }

    updateNodeData(id, update) {
        const node = this.nodes.get(id);
        if (!node) return;

        // Update Physics/Visuals (if any)
        
        // DELEGATE UI: Update Label
        this.uiManager.updateLabelData(id, { price: update.p, rsi: update.rsi });
    }

    selectNode(id) {
        const node = this.nodes.get(id);
        if (!node) return;

        // DELEGATE UI: Show Details
        this.uiManager.showDetails(node.userData);

        // Highlight Effect 
        // node.children[0].material.emissiveIntensity = 2.0; 
    }

    deselectNode() {
        this.uiManager.hideDetails();
    }

    getCategoryPosition(category) {
        // Spread logic: different quadrants for different sectors
        // MEME, STABLE, GAMING, INFRA, DEFI
        const spread = 400;
        const variation = 150;

        let cx = 0, cz = 0;

        // Simple hashing for category string if unknown
        switch (category?.toUpperCase()) {
            case 'MEME': cx = spread; cz = -spread; break; // Q1
            case 'GAMING': cx = -spread; cz = spread; break; // Q3
            case 'INFRA': cx = -spread; cz = -spread; break; // Q2
            case 'DEFI': cx = spread; cz = spread; break; // Q4
            case 'STABLE': cx = 0; cz = 0; break; // Center
            default: // Random periphery
                cx = (Math.random() - 0.5) * spread * 3;
                cz = (Math.random() - 0.5) * spread * 3;
        }

        return {
            x: cx + (Math.random() - 0.5) * variation,
            y: (Math.random() - 0.5) * 100, // Flatten verticality
            z: cz + (Math.random() - 0.5) * variation
        };
    }

    updateLabel(mesh) {
        // Project 3D position to 2D
        const camera = this.sceneManager.camera;
        const tempV = new THREE.Vector3();

        mesh.updateWorldMatrix(true, false);
        mesh.getWorldPosition(tempV);
        
        const dist = camera.position.distanceTo(tempV);
        tempV.project(camera);

        const x = (tempV.x * .5 + .5) * window.innerWidth;
        const y = (tempV.y * -.5 + .5) * window.innerHeight;

        // DELEGATE UI: Update Position
        this.uiManager.updateLabelPosition(mesh.userData.id, x, y, tempV.z, dist);
    }
}
```
