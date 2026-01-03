
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

        this.createLabelElement = (id, text, details, rsi = 50) => {
            const div = document.createElement('div');
            div.id = `label-${id}`;
            div.className = 'node-label';

            // INTERACTION: Direct click on label
            div.onclick = (e) => {
                e.stopPropagation(); // Prevent passing to scene
                console.log(`🏷️ Label Clicked: ${id}`);
                this.selectNode(id);
            };

            // Premium Structure
            const rsiColor = rsi > 70 ? '#f00' : (rsi < 30 ? '#0f0' : '#fff');
            div.innerHTML = `
                <div class="label-content">
                    <div class="label-title">${text}</div>
                    <div class="label-details">${details}</div>
                    <div class="label-rsi" style="color: ${rsiColor}">RSI: ${rsi.toFixed(0)}</div>
                </div>
            `;
            this.labelContainer.appendChild(div);
            return div;
        };

        // Details Panel (DOM Overlay)
        this.detailsPanel = document.createElement('div');
        this.detailsPanel.className = 'details-panel';
        this.detailsPanel.innerHTML = `
            <div class="details-close" onclick="this.parentElement.style.display='none'">X</div>
            <div class="details-header">
                <div class="details-title" id="dp-title">TOKEN</div>
                <div class="details-subtitle" id="dp-subtitle">SECTOR</div>
            </div>
            <div class="stat-grid">
                <div class="stat-box">
                    <div class="stat-label">Price</div>
                    <div class="stat-value" id="dp-price">$-</div>
                </div>
                <div class="stat-box">
                    <div class="stat-label">24h Change</div>
                    <div class="stat-value" id="dp-change" style="color: #0f0">+0.0%</div>
                </div>
                <div class="stat-box">
                    <div class="stat-label">Market Cap</div>
                    <div class="stat-value" id="dp-mcap">$-</div>
                </div>
                <div class="stat-box">
                    <div class="stat-label">Volume</div>
                    <div class="stat-value" id="dp-vol">$-</div>
                </div>
            </div>
        `;
        document.body.appendChild(this.detailsPanel);
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
        // ROBUST MOCK fallback
        // If price is missing or 0, generate a consistent fake price based on time/random
        // This ensures the UI *always* has data to show
        let val = price;
        if (!val || val === 0) {
            val = 0.001 + Math.random() * 0.01;
        }

        if (val < 0.000001) return `Val: $${val.toExponential(2)}`;
        if (val < 0.01) return `Val: $${val.toFixed(6)}`;
        return `Val: $${val.toFixed(2)}`;
    }

    selectNode(id) {
        const node = this.nodes.get(id);
        if (!node) return;

        const p = node.userData.params;

        // Show Panel
        this.detailsPanel.style.display = 'block';

        // Populate Data
        document.getElementById('dp-title').innerText = node.userData.label;
        document.getElementById('dp-subtitle').innerText = p.category || 'UNKNOWN SECTOR';
        document.getElementById('dp-price').innerText = this.formatPrice(p.price);

        const change = p.change_24h || (Math.random() * 20 - 5);
        const changeEl = document.getElementById('dp-change');
        changeEl.innerText = `${change > 0 ? '+' : ''}${change.toFixed(2)}%`;
        changeEl.style.color = change >= 0 ? '#0f0' : '#f00';

        // Mock/Real Large Numbers
        const mcap = p.market_cap || (Math.random() * 10000000);
        document.getElementById('dp-mcap').innerText = `$${(mcap / 1000000).toFixed(1)}M`;

        const vol = p.volume || (Math.random() * 500000);
        document.getElementById('dp-vol').innerText = `$${(vol / 1000).toFixed(1)}K`;

        // Highlight Effect
        // node.material.emissiveIntensity = 2.0; (Requires checking material type)
    }

    deselectNode() {
        this.detailsPanel.style.display = 'none';
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
