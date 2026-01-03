
export class SettingsManager {
    constructor(game) {
        this.game = game;
        this.visible = false;

        // Defaults
        this.settings = {
            fleetDensity: 10000,
            lodNear: 100,
            lodFar: 400,
            showLabels: true
        };

        this.initUI();
    }

    initUI() {
        // Container
        this.panel = document.createElement('div');
        this.panel.id = 'settings-panel';
        this.panel.style.cssText = `
            position: absolute;
            top: 20px;
            right: 240px; /* Left of MiniMap */
            width: 250px;
            background: rgba(0, 20, 0, 0.9);
            border: 1px solid #0f0;
            padding: 15px;
            font-family: 'Courier New', monospace;
            color: #0f0;
            display: none;
            z-index: 50;
        `;

        this.panel.innerHTML = `<div class="panel-title">SYSTEM CONFIG</div>`;

        // Sliders
        this.addSlider('Fleet Density', 0, 10000, this.settings.fleetDensity, (val) => {
            this.settings.fleetDensity = val;
            if (this.game.fleet) this.game.fleet.mesh.count = Math.min(this.game.fleet.ships.length, val);
        });

        this.addSlider('LOD Near', 50, 500, this.settings.lodNear, (val) => {
            this.settings.lodNear = val;
            this.updateLOD();
        });

        this.addSlider('LOD Far', 200, 1000, this.settings.lodFar, (val) => {
            this.settings.lodFar = val;
            this.updateLOD();
        });

        // Toggle Button
        const toggleBtn = document.createElement('button');
        toggleBtn.innerText = "⚙️";
        toggleBtn.style.cssText = `
            position: absolute;
            top: 20px;
            right: 230px;
            background: #000;
            color: #0f0;
            border: 1px solid #0f0;
            cursor: pointer;
            z-index: 51;
            padding: 5px;
        `;
        toggleBtn.onclick = () => {
            this.visible = !this.visible;
            this.panel.style.display = this.visible ? 'block' : 'none';
        };

        document.body.appendChild(this.panel);
        document.body.appendChild(toggleBtn);
    }

    addSlider(label, min, max, val, callback) {
        const row = document.createElement('div');
        row.style.marginBottom = '10px';

        const labelEl = document.createElement('div');
        labelEl.innerText = `${label}: ${val}`;
        labelEl.style.fontSize = '12px';

        const input = document.createElement('input');
        input.type = 'range';
        input.min = min;
        input.max = max;
        input.value = val;
        input.style.width = '100%';
        input.style.accentColor = '#0f0';

        input.oninput = (e) => {
            const v = parseInt(e.target.value);
            labelEl.innerText = `${label}: ${v}`;
            callback(v);
        };

        row.appendChild(labelEl);
        row.appendChild(input);
        this.panel.appendChild(row);
    }

    updateLOD() {
        // Broadcast new thresholds to all nodes
        // This is expensive if we do it every frame, but fine for slider drag end
        // Or we just update the levels of existing LOD objects
        this.game.stars.nodes.forEach(node => {
            if (node instanceof THREE.LOD) {
                // levels[0] is always 0
                node.levels[1].distance = this.settings.lodNear;
                node.levels[2].distance = this.settings.lodFar;
            }
        });
    }
}
