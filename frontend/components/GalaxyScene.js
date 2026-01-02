import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { UnrealBloomPass } from 'three/addons/postprocessing/UnrealBloomPass.js';
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js';
import { OutputPass } from 'three/addons/postprocessing/OutputPass.js';

export class GalaxyScene {
    constructor(containerId) {
        this.container = document.getElementById(containerId);
        this.nodes = new Map();
        this.hopConnections = new Map();
        this.GALAXY_RADIUS = 500;

        this.init();
        this.animate();
    }

    init() {
        // Scene setup
        this.scene = new THREE.Scene();
        this.scene.fog = new THREE.FogExp2(0x000000, 0.001);

        this.camera = new THREE.PerspectiveCamera(75, window.innerWidth / window.innerHeight, 0.1, 5000);
        this.camera.position.set(0, 400, 800);

        this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
        this.renderer.setSize(window.innerWidth, window.innerHeight);
        this.renderer.setPixelRatio(window.devicePixelRatio);
        this.container.appendChild(this.renderer.domElement);

        this.controls = new OrbitControls(this.camera, this.renderer.domElement);
        this.controls.enableDamping = true;
        this.controls.dampingFactor = 0.05;
        this.controls.autoRotate = true;
        this.controls.autoRotateSpeed = 0.5;

        // Lighting
        const ambientLight = new THREE.AmbientLight(0x404040, 2);
        this.scene.add(ambientLight);
        const pointLight = new THREE.PointLight(0xffffff, 2, 2000);
        this.scene.add(pointLight);

        // Post processing
        const renderScene = new RenderPass(this.scene, this.camera);
        const bloomPass = new UnrealBloomPass(new THREE.Vector2(window.innerWidth, window.innerHeight), 1.5, 0.4, 0.85);
        bloomPass.threshold = 0;
        bloomPass.strength = 1.2;
        bloomPass.radius = 0.5;

        this.composer = new EffectComposer(this.renderer);
        this.composer.addPass(renderScene);
        this.composer.addPass(bloomPass);
        this.composer.addPass(new OutputPass());

        // Label system
        this.labelContainer = document.createElement('div');
        this.labelContainer.style.position = 'absolute';
        this.labelContainer.style.top = '0';
        this.labelContainer.style.left = '0';
        this.labelContainer.style.width = '100%';
        this.labelContainer.style.height = '100%';
        this.labelContainer.style.pointerEvents = 'none';
        document.body.appendChild(this.labelContainer);

        window.addEventListener('resize', () => this.onWindowResize());
    }

    onWindowResize() {
        this.camera.aspect = window.innerWidth / window.innerHeight;
        this.camera.updateProjectionMatrix();
        this.renderer.setSize(window.innerWidth, window.innerHeight);
        this.composer.setSize(window.innerWidth, window.innerHeight);
    }

    animate() {
        requestAnimationFrame(() => this.animate());
        this.controls.update();
        this.updateScene();
        this.updateLabels();
        this.composer.render();
    }

    updateScene() {
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

                if (node.userData.orbitalLine) {
                    const lineGeo = node.userData.orbitalLine.geometry;
                    const positions = lineGeo.attributes.position.array;
                    positions[3] = node.position.x;
                    positions[4] = node.position.y;
                    positions[5] = node.position.z;
                    lineGeo.attributes.position.needsUpdate = true;
                }
            } else if (node.userData.velocity) {
                node.position.add(node.userData.velocity);
                node.rotation.x += 0.01;
                node.rotation.y += 0.02;

                if (node.position.length() > this.GALAXY_RADIUS * 1.2) {
                    node.position.setLength(this.GALAXY_RADIUS * 0.1);
                }
            }

            if (node.userData.trail) {
                node.userData.trail.update(node.position);
            }
        });

        // Cleanup
        if (this.nodes.size > 800) {
            for (const [key, node] of this.nodes) {
                if (node.userData.nodeType === 'EVENT') {
                    this.scene.remove(node);
                    if (node.userData.trail) node.userData.trail.dispose();
                    if (node.userData.labelEl) node.userData.labelEl.remove();
                    node.geometry.dispose();
                    node.material.dispose();
                    this.nodes.delete(key);
                    break;
                }
            }
        }

        this.hopConnections.forEach(conn => conn.update());
    }

    updateLabels() {
        this.nodes.forEach((mesh, id) => {
            if (!mesh.userData.labelEl) return;
            const tempV = new THREE.Vector3();
            mesh.updateWorldMatrix(true, false);
            mesh.getWorldPosition(tempV);
            tempV.project(this.camera);

            const x = (tempV.x * .5 + .5) * window.innerWidth;
            const y = (tempV.y * -.5 + .5) * window.innerHeight;

            mesh.userData.labelEl.style.transform = `translate(-50%, -50%) translate(${x}px,${y}px)`;

            // V35: LOD (Level of Detail) to prevent clumping
            const dist = this.camera.position.distanceTo(mesh.getWorldPosition(new THREE.Vector3()));

            // Prioritize: Whales always visible further
            const isWhale = mesh.userData.params && mesh.userData.params.is_whale;
            const visibleThreshold = isWhale ? 1800 : 800; // Whales visible from 2x distance
            const fullDetailThreshold = 400; // Only show full stats when close

            if (tempV.z > 1 || dist > visibleThreshold) {
                mesh.userData.labelEl.style.display = 'none';
            } else {
                mesh.userData.labelEl.style.display = 'block';
                // Fade out effect
                const opacity = Math.max(0, 1 - (dist / visibleThreshold));
                mesh.userData.labelEl.style.opacity = opacity;

                // Compact Mode (CSS class toggle)
                if (dist > fullDetailThreshold && !isWhale) {
                    mesh.userData.labelEl.classList.add('compact');
                } else {
                    mesh.userData.labelEl.classList.remove('compact');
                }
            }
        });
    }

    // Node Creation / Updates
    updateArchetype(data) {
        if (data.archetype === 'MOON' || data.node_type === 'MOON') {
            this.createMoon(data.id, data.label, data.params);
        } else {
            this.createNode(data.id, data.label, data.archetype, data.params, data.node_type || 'TOKEN', data.event_label);
        }
    }

    createNode(id, label, archetype, params, nodeType = 'TOKEN', eventLabel = '') {
        const existing = this.nodes.get(id);
        if (existing) {
            if (params.price) {
                const details = `$${params.price.toFixed(6)} ${params.is_whale ? '🐋' : ''}`;
                if (existing.userData.labelEl) {
                    existing.userData.labelEl.innerHTML = `<strong>${label}</strong><br><span style="font-size:10px; color:#aaa">${details}</span>`;
                }
            }
            if (nodeType === 'EVENT' && params.flash) {
                existing.material.emissiveIntensity = 10;
                setTimeout(() => { existing.material.emissiveIntensity = params.emissive_intensity || 2; }, 200);
            }
            return existing;
        }

        let geometry;
        switch (archetype) {
            case 'GLOBE': geometry = new THREE.SphereGeometry(params.radius || 2, 16, 16); break;
            case 'PLANET': geometry = new THREE.SphereGeometry(params.radius || 3, 32, 32); break;
            case 'SUPERNOVA': geometry = new THREE.IcosahedronGeometry(params.radius || 5, 1); break;
            case 'PULSAR': geometry = new THREE.OctahedronGeometry(params.radius || 2, 0); break;
            case 'NOVA': geometry = new THREE.DodecahedronGeometry(params.radius || 2, 0); break;
            case 'COMET': geometry = new THREE.ConeGeometry(params.radius || 1, params.radius * 2, 8); break;
            case 'WHALE': geometry = new THREE.TorusKnotGeometry(params.radius || 3, 0.5, 64, 8); break;
            default: geometry = new THREE.TetrahedronGeometry(params.radius || 1, 0);
        }

        const material = new THREE.MeshStandardMaterial({
            color: new THREE.Color(params.hex_color || '#ffffff'),
            emissive: new THREE.Color(params.hex_color || '#000000'),
            emissiveIntensity: params.emissive_intensity || 0.5,
            roughness: params.roughness !== undefined ? params.roughness : 0.5,
            metalness: params.metalness !== undefined ? params.metalness : 0.8,
            wireframe: params.roughness < 0.2
        });

        const mesh = new THREE.Mesh(geometry, material);

        if (params.x !== undefined && params.y !== undefined && params.z !== undefined) {
            mesh.position.set(params.x, params.y, params.z);
        } else {
            // Fallback positioning... (simplified for brevity)
            mesh.position.set((Math.random() - 0.5) * 500, (Math.random() - 0.5) * 500, (Math.random() - 0.5) * 500);
        }

        const velMag = nodeType === 'EVENT' ? (params.velocity_factor || 0.5) * 0.5 : 0.02;
        const vel = new THREE.Vector3().randomDirection().multiplyScalar(velMag);
        mesh.userData = { id, label, velocity: vel, type: archetype, nodeType, params };

        if (archetype === 'COMET' || params.velocity_factor > 1.0) {
            mesh.userData.trail = new TrailRenderer(this.scene, params.hex_color, 20);
        }

        let details = nodeType === 'EVENT' ? eventLabel : `${params.price ? `$${params.price.toFixed(6)}` : ''} ${params.rsi ? `RSI:${params.rsi.toFixed(0)}` : ''}`;
        mesh.userData.labelEl = this.createLabel(id, label, details, params);

        this.scene.add(mesh);
        this.nodes.set(id, mesh);
        return mesh;
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
        moon.position.set(orbitRadius * Math.cos(angle), (Math.random() - 0.5) * 2, orbitRadius * Math.sin(angle));

        moon.userData = {
            id, label, type: 'MOON', nodeType: 'MOON', params,
            parentMint: params.parent_mint, orbitAngle: angle, orbitRadius,
            orbitSpeed: params.orbit_speed || 0.02, orbitTilt: (Math.random() - 0.5) * 0.5
        };

        moon.userData.labelEl = this.createLabel(id, params.dex || 'POOL', params.liquidity ? `$${(params.liquidity / 1000).toFixed(0)}k` : '');

        const lineMaterial = new THREE.LineBasicMaterial({ color: new THREE.Color(params.hex_color || '#444444'), transparent: true, opacity: 0.3 });
        const lineGeometry = new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(0, 0, 0), moon.position.clone()]);
        moon.userData.orbitalLine = new THREE.Line(lineGeometry, lineMaterial);

        parentNode.add(moon.userData.orbitalLine);
        parentNode.add(moon);
        this.nodes.set(id, moon);
        return moon;
    }

    createLabel(id, text, details, params = {}) {
        const div = document.createElement('div');
        div.id = `label-${id}`;
        div.className = 'stat-card';

        // Extract data for display
        const price = params.price ? `$${params.price < 0.01 ? params.price.toFixed(8) : params.price.toFixed(4)}` : '';
        const rsi = params.rsi || 50;
        const volume = params.volume ? this.formatVolume(params.volume) : '';
        const change = params.change_24h || 0;
        const changeClass = change >= 0 ? 'positive' : 'negative';
        const changeStr = change ? `${change >= 0 ? '+' : ''}${change.toFixed(2)}%` : '';
        const isWhale = params.is_whale ? '🐋' : '';
        const liquidity = params.liquidity ? `Liq: ${this.formatVolume(params.liquidity)}` : '';

        // RSI color class
        let rsiClass = 'neutral';
        if (rsi < 30) rsiClass = 'oversold';
        else if (rsi < 45) rsiClass = 'weak';
        else if (rsi > 70) rsiClass = 'overbought';
        else if (rsi > 55) rsiClass = 'strong';

        div.innerHTML = `
            <div class="card-header">
                <span class="symbol">${text}</span>
                <span class="whale-badge">${isWhale}</span>
            </div>
            <div class="card-body">
                <div class="price-row">
                    <span class="price">${price}</span>
                    <span class="change ${changeClass}">${changeStr}</span>
                </div>
                <div class="rsi-container">
                    <span class="rsi-label">RSI</span>
                    <div class="rsi-bar-bg">
                        <div class="rsi-bar ${rsiClass}" style="width: ${rsi}%"></div>
                    </div>
                    <span class="rsi-value">${rsi.toFixed(0)}</span>
                </div>
                <div class="stats-row">
                    <span class="volume">Vol: ${volume}</span>
                    <span class="liquidity">${liquidity}</span>
                </div>
            </div>
        `;

        // Apply styles inline (or rely on CSS file)
        div.style.cssText = `
            position: absolute;
            background: rgba(0, 5, 15, 0.92);
            border: 1px solid rgba(0, 243, 255, 0.6);
            border-radius: 6px;
            padding: 8px 12px;
            color: #fff;
            font-family: 'JetBrains Mono', 'Fira Code', monospace;
            font-size: 11px;
            pointer-events: none;
            min-width: 140px;
            box-shadow: 0 0 20px rgba(0, 243, 255, 0.2), inset 0 0 10px rgba(0, 0, 0, 0.5);
            backdrop-filter: blur(4px);
            transform-origin: center center;
        `;

        this.labelContainer.appendChild(div);
        return div;
    }

    formatVolume(value) {
        if (!value || value === 0) return '-';
        if (value >= 1000000000) return `$${(value / 1000000000).toFixed(1)}B`;
        if (value >= 1000000) return `$${(value / 1000000).toFixed(1)}M`;
        if (value >= 1000) return `$${(value / 1000).toFixed(0)}k`;
        return `$${value.toFixed(0)}`;
    }

    createWhalePulse(x, y, z, color = '#ffd700', intensity = 1.0) {
        const geometry = new THREE.RingGeometry(1, 1.2, 32);
        const material = new THREE.MeshBasicMaterial({ color: new THREE.Color(color), transparent: true, opacity: 0.8, side: THREE.DoubleSide, blending: THREE.AdditiveBlending });
        const pulse = new THREE.Mesh(geometry, material);
        pulse.position.set(x, y, z);
        this.scene.add(pulse);

        const startTime = performance.now();
        const duration = 2000;
        const self = this;

        function animatePulse(time) {
            const progress = (time - startTime) / duration;
            if (progress < 1) {
                const scale = 1 + progress * 100 * intensity;
                pulse.scale.set(scale, scale, scale);
                pulse.material.opacity = 0.8 * (1 - progress);
                requestAnimationFrame(animatePulse);
            } else {
                self.scene.remove(pulse);
                geometry.dispose();
                material.dispose();
            }
        }
        requestAnimationFrame(animatePulse);
    }

    createHopConnection(fromMint, toMint, profit = 0.01) {
        const key = `${fromMint}:${toMint}`;
        if (this.hopConnections.has(key)) return;

        const fromNode = this.nodes.get(fromMint);
        const toNode = this.nodes.get(toMint);
        if (!fromNode || !toNode) return;

        const color = profit > 0.02 ? '#00ff00' : profit > 0.01 ? '#ffff00' : '#ff8800';
        const connection = new HopConnection(this.scene, fromNode, toNode, color, profit);
        this.hopConnections.set(key, connection);
    }
}

// Helper Classes
class TrailRenderer {
    constructor(scene, color, maxPoints = 30) {
        this.scene = scene;
        this.maxPoints = maxPoints;
        this.points = [];
        this.geometry = new THREE.BufferGeometry();
        this.geometry.setAttribute('position', new THREE.BufferAttribute(new Float32Array(maxPoints * 3), 3));
        this.material = new THREE.LineBasicMaterial({ color: new THREE.Color(color), transparent: true, opacity: 0.6, blending: THREE.AdditiveBlending });
        this.line = new THREE.Line(this.geometry, this.material);
        scene.add(this.line);
    }
    update(position) {
        this.points.push(position.clone());
        if (this.points.length > this.maxPoints) this.points.shift();
        const positions = this.line.geometry.attributes.position.array;
        for (let i = 0; i < this.points.length; i++) {
            positions[i * 3] = this.points[i].x; positions[i * 3 + 1] = this.points[i].y; positions[i * 3 + 2] = this.points[i].z;
        }
        this.line.geometry.attributes.position.needsUpdate = true;
        this.line.geometry.setDrawRange(0, this.points.length);
    }
    dispose() { this.scene.remove(this.line); this.geometry.dispose(); this.material.dispose(); }
}

class HopConnection {
    constructor(scene, fromNode, toNode, color, profit) {
        this.scene = scene;
        this.fromNode = fromNode;
        this.toNode = toNode;
        this.geometry = new THREE.BufferGeometry();
        this.material = new THREE.LineBasicMaterial({ color: new THREE.Color(color), transparent: true, opacity: 0.5, linewidth: 1 });
        this.line = new THREE.Line(this.geometry, this.material);
        scene.add(this.line);
        this.update();
    }
    update() {
        const start = this.fromNode.getWorldPosition(new THREE.Vector3());
        const end = this.toNode.getWorldPosition(new THREE.Vector3());
        const mid = new THREE.Vector3().addVectors(start, end).multiplyScalar(0.5);
        mid.y += 10;
        const curve = new THREE.QuadraticBezierCurve3(start, mid, end);
        this.geometry.setFromPoints(curve.getPoints(20));
    }
    dispose() { this.scene.remove(this.line); this.geometry.dispose(); this.material.dispose(); }
}
