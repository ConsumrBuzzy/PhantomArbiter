
import * as THREE from 'three';

export class StarSystemManager {
    constructor(sceneManager) {
        this.sceneManager = sceneManager;
        this.nodes = new Map(); // id -> Mesh
        this.maxEntities = 1000; // Performance slider limit
        this.nodesByVolume = []; // Sorted for culling

        // Event Callbacks (UI Bridge)
        this.onNodeCreated = null;
        this.onNodeUpdated = null;
        this.onNodeSelected = null;

        // Point Cloud for distant/culled tokens
        this.initPointCloud();

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
                e.stopPropagation();
                console.log(`🏷️ Label Clicked: ${id}`);
                this.selectNode(id);
            };

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

    /**
     * Initialize point cloud for abstracted/distant tokens
     */
    initPointCloud() {
        const geometry = new THREE.BufferGeometry();
        const MAX_POINTS = 5000;
        const positions = new Float32Array(MAX_POINTS * 3);
        const colors = new Float32Array(MAX_POINTS * 3);

        geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
        geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));

        const material = new THREE.PointsMaterial({
            size: 2,
            vertexColors: true,
            transparent: true,
            opacity: 0.6
        });

        this.pointCloud = new THREE.Points(geometry, material);
        this.pointCloud.frustumCulled = false;
        this.sceneManager.add(this.pointCloud);
        this.pointCloudCount = 0;
    }

    /**
     * Sets the maximum visible entities (tokens rendered as meshes)
     * @param {number} limit - Max entities (50-2000)
     */
    setMaxEntities(limit) {
        this.maxEntities = Math.max(50, Math.min(2000, limit));
        this.applyCulling();
    }

    /**
     * Applies culling based on maxEntities - hides low-volume tokens as point cloud
     */
    applyCulling() {
        const sorted = Array.from(this.nodes.entries())
            .filter(([id, node]) => node.userData.params?.volume !== undefined)
            .sort((a, b) => (b[1].userData.params.volume || 0) - (a[1].userData.params.volume || 0));

        let pointIdx = 0;
        const positions = this.pointCloud.geometry.attributes.position.array;
        const colors = this.pointCloud.geometry.attributes.color.array;

        sorted.forEach(([id, node], idx) => {
            if (idx < this.maxEntities) {
                node.visible = true;
                if (node.userData.labelEl) node.userData.labelEl.style.display = '';
            } else {
                node.visible = false;
                if (node.userData.labelEl) node.userData.labelEl.style.display = 'none';

                const pos = node.getWorldPosition(new THREE.Vector3());
                positions[pointIdx * 3] = pos.x;
                positions[pointIdx * 3 + 1] = pos.y;
                positions[pointIdx * 3 + 2] = pos.z;

                const color = new THREE.Color(node.userData.params?.hex_color || '#ffffff');
                colors[pointIdx * 3] = color.r;
                colors[pointIdx * 3 + 1] = color.g;
                colors[pointIdx * 3 + 2] = color.b;

                pointIdx++;
            }
        });

        this.pointCloudCount = pointIdx;
        this.pointCloud.geometry.setDrawRange(0, pointIdx);
        this.pointCloud.geometry.attributes.position.needsUpdate = true;
        this.pointCloud.geometry.attributes.color.needsUpdate = true;
    }

    /**
     * Update node data (price, RSI) from real-time stream
     */
    updateNodeData(id, data) {
        const node = this.nodes.get(id);
        if (!node) return;

        if (data.p !== undefined) node.userData.params.price = data.p;
        if (data.rsi !== undefined) node.userData.params.rsi = data.rsi;

        if (node.userData.labelEl) {
            const detailsEl = node.userData.labelEl.querySelector('.label-details');
            if (detailsEl && data.p) detailsEl.innerText = this.formatPrice(data.p);

            const rsiEl = node.userData.labelEl.querySelector('.label-rsi');
            if (rsiEl && data.rsi !== undefined) {
                const rsi = data.rsi;
                const rsiColor = rsi > 70 ? '#f00' : (rsi < 30 ? '#0f0' : '#fff');
                rsiEl.innerText = `RSI: ${rsi.toFixed(0)}`;
                rsiEl.style.color = rsiColor;
            }
        }

        if (this.onNodeUpdated) this.onNodeUpdated(id, data);
    }

    update(delta) {
        this.nodes.forEach(node => {
            if (node.userData.nodeType === 'MOON') {
                node.userData.orbitAngle += node.userData.orbitSpeed;
                const r = node.userData.orbitRadius;
                const tilt = node.userData.orbitTilt || 0;
                node.position.set(
                    r * Math.cos(node.userData.orbitAngle),
                    r * Math.sin(node.userData.orbitAngle) * tilt,
                    r * Math.sin(node.userData.orbitAngle)
                );
                node.rotation.y += 0.03;
            } else {
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
            if (params.price || params.rsi) {
                this.updateNodeData(id, { p: params.price, rsi: params.rsi });
            }
            return existing;
        }

        const lod = new THREE.LOD();

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

        const geometryLow = new THREE.IcosahedronGeometry(params.radius || 2, 0);
        const materialLow = new THREE.MeshBasicMaterial({
            color: params.hex_color || '#ffffff',
            wireframe: true
        });
        const meshLow = new THREE.Mesh(geometryLow, materialLow);
        lod.addLevel(meshLow, 100);

        const geometryFar = new THREE.TetrahedronGeometry((params.radius || 2) * 0.8, 0);
        const materialFar = new THREE.MeshBasicMaterial({ color: params.hex_color, wireframe: false });
        const meshFar = new THREE.Mesh(geometryFar, materialFar);
        lod.addLevel(meshFar, 400);

        if (params.x !== undefined && params.y !== undefined && params.z !== undefined) {
            lod.position.set(params.x, params.y, params.z);
        } else {
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

        if (this.onNodeCreated) this.onNodeCreated(id, { label, archetype, params });

        return lod;
    }

    formatPrice(price) {
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

        this.detailsPanel.style.display = 'block';

        document.getElementById('dp-title').innerText = node.userData.label;
        document.getElementById('dp-subtitle').innerText = p.category || 'UNKNOWN SECTOR';
        document.getElementById('dp-price').innerText = this.formatPrice(p.price);

        const change = p.change_24h || (Math.random() * 20 - 5);
        const changeEl = document.getElementById('dp-change');
        changeEl.innerText = `${change > 0 ? '+' : ''}${change.toFixed(2)}%`;
        changeEl.style.color = change >= 0 ? '#0f0' : '#f00';

        const mcap = p.market_cap || (Math.random() * 10000000);
        document.getElementById('dp-mcap').innerText = `$${(mcap / 1000000).toFixed(1)}M`;

        const vol = p.volume || (Math.random() * 500000);
        document.getElementById('dp-vol').innerText = `$${(vol / 1000).toFixed(1)}K`;

        if (this.onNodeSelected) this.onNodeSelected(id, node.userData);
    }

    deselectNode() {
        this.detailsPanel.style.display = 'none';
    }

    getCategoryPosition(category) {
        const spread = 400;
        const variation = 150;

        let cx = 0, cz = 0;

        switch (category?.toUpperCase()) {
            case 'MEME': cx = spread; cz = -spread; break;
            case 'GAMING': cx = -spread; cz = spread; break;
            case 'INFRA': cx = -spread; cz = -spread; break;
            case 'DEFI': cx = spread; cz = spread; break;
            case 'STABLE': cx = 0; cz = 0; break;
            default:
                cx = (Math.random() - 0.5) * spread * 3;
                cz = (Math.random() - 0.5) * spread * 3;
        }

        return {
            x: cx + (Math.random() - 0.5) * variation,
            y: (Math.random() - 0.5) * 100,
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

        const dist = camera.position.distanceTo(mesh.getWorldPosition(new THREE.Vector3()));
        if (tempV.z > 1 || dist > 1500) {
            mesh.userData.labelEl.style.display = 'none';
        } else {
            mesh.userData.labelEl.style.display = 'block';
            mesh.userData.labelEl.style.opacity = Math.max(0, 1 - (dist / 1500));
        }
    }
}
