
import * as THREE from 'three';

export class StarSystemManager {
    constructor(sceneManager) {
        this.sceneManager = sceneManager;
        this.nodes = new Map(); // id -> Mesh

        // Label Container (DOM Overlay)
        this.labelContainer = document.createElement('div');
        this.labelContainer.style.position = 'absolute';
        this.labelContainer.style.top = '0';
        this.labelContainer.style.left = '0';
        this.labelContainer.style.width = '100%';
        this.labelContainer.style.height = '100%';
        this.labelContainer.style.pointerEvents = 'none';
        document.body.appendChild(this.labelContainer);
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
        lod.userData.labelEl = this.createLabelElement(
            id,
            label,
            this.formatPrice(params.price),
            params.rsi !== undefined ? params.rsi : 50
        );

        this.sceneManager.add(lod);
        this.nodes.set(id, lod);
        return lod;
    }

    formatPrice(price) {
        if (!price || price === 0) return 'Val: -';
        if (price < 0.000001) return `Val: $${price.toExponential(2)}`;
        if (price < 0.01) return `Val: $${price.toFixed(6)}`;
        return `Val: $${price.toFixed(2)}`;
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

        parentNode.add(moon); // Attach to parent for local coordinate system
        this.nodes.set(id, moon);
        return moon;
    }

    createLabelElement(id, text, details, rsi = 50) {
        const div = document.createElement('div');
        div.id = `label-${id}`;
        div.className = 'node-label';

        // Premium Structure
        const header = document.createElement('div');
        header.className = 'label-header';

        const symbolEl = document.createElement('div');
        symbolEl.className = 'token-symbol';
        symbolEl.innerText = text;

        const priceEl = document.createElement('div');
        priceEl.id = `price-${id}`;
        priceEl.className = 'token-price';
        priceEl.innerText = details;

        header.appendChild(symbolEl);
        header.appendChild(priceEl);

        const rsiContainer = document.createElement('div');
        rsiContainer.className = 'rsi-container';

        const rsiBar = document.createElement('div');
        rsiBar.id = `rsi-bar-${id}`;
        rsiBar.className = 'rsi-bar';
        rsiBar.style.width = `${rsi}%`;
        // Color code RSI
        rsiBar.style.background = rsi > 70 ? '#ff0055' : (rsi < 30 ? '#00ff55' : '#00ccff');

        const rsiVal = document.createElement('div');
        rsiVal.id = `rsi-val-${id}`;
        rsiVal.className = 'rsi-value';
        rsiVal.innerText = `RSI: ${rsi.toFixed(1)}`;

        rsiContainer.appendChild(rsiBar);

        div.appendChild(header);
        div.appendChild(rsiContainer);
        div.appendChild(rsiVal);

        if (this.labelContainer) this.labelContainer.appendChild(div);
        return div;
    }

    updateNodeData(id, update) {
        const node = this.nodes.get(id);
        if (!node || !node.userData.labelEl) return;

        // Update Price
        if (update.p) {
            const priceEl = document.getElementById(`price-${id}`);
            if (priceEl) priceEl.innerText = this.formatPrice(update.p);
        }

        // Update RSI (using fake RSI derived from price change for now if raw RSI not passed)
        // Ideally payload has 'rsi'
        let rsi = update.rsi || 50;

        const rsiBar = document.getElementById(`rsi-bar-${id}`);
        if (rsiBar) {
            rsiBar.style.width = `${rsi}%`;
            rsiBar.style.background = rsi > 70 ? '#ff0055' : (rsi < 30 ? '#00ff55' : '#00ccff');
        }

        const rsiVal = document.getElementById(`rsi-val-${id}`);
        if (rsiVal) rsiVal.innerText = `RSI: ${rsi.toFixed(1)}`;
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
        if (!mesh.userData.labelEl) return;

        const camera = this.sceneManager.camera;
        const tempV = new THREE.Vector3();

        mesh.updateWorldMatrix(true, false);
        mesh.getWorldPosition(tempV);
        tempV.project(camera);

        const x = (tempV.x * .5 + .5) * window.innerWidth;
        const y = (tempV.y * -.5 + .5) * window.innerHeight;

        mesh.userData.labelEl.style.transform = `translate(-50%, -50%) translate(${x}px,${y}px)`;

        // Visibility logic
        const dist = camera.position.distanceTo(mesh.getWorldPosition(new THREE.Vector3()));
        if (tempV.z > 1 || dist > 1500) {
            mesh.userData.labelEl.style.display = 'none';
        } else {
            mesh.userData.labelEl.style.display = 'block';
            mesh.userData.labelEl.style.opacity = Math.max(0, 1 - (dist / 1500));
        }
    }
}
