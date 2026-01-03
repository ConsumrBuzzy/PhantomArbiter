
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
            // Update logic...
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
            mesh.position.set((Math.random() - 0.5) * 500, (Math.random() - 0.5) * 500, (Math.random() - 0.5) * 500);
        }

        mesh.userData = { id, label, type: archetype, nodeType, params };
        mesh.userData.labelEl = this.createLabelElement(id, label, params.price ? `$${params.price.toFixed(6)}` : '');

        this.sceneManager.add(mesh);
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

    createLabelElement(id, text, details) {
        const div = document.createElement('div');
        div.id = `label-${id}`;
        div.className = 'node-label';
        div.style.position = 'absolute';
        div.style.color = '#fff';
        div.style.fontFamily = 'monospace';
        div.style.fontSize = '10px';
        div.style.textShadow = '0 0 2px #000';
        div.style.pointerEvents = 'none';
        div.innerHTML = `<strong>${text}</strong><br><span style="color:#aaa">${details}</span>`;
        if (this.labelContainer) this.labelContainer.appendChild(div);
        return div;
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
