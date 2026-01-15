import os

path = 'frontend/js/app.module.js'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

replacement = """    initializeDynamicComponents(viewName) {
        console.log(`Initializing components for ${viewName}`);
        
        if (viewName === 'dashboard') {
            try {
                // Initialize Dashboard Components
                this.unifiedVault = new UnifiedVaultController('unified-vault-container');
                this.tokenWatchlist = new TokenWatchlist('watchlist-panel');
                this.inventory = new Inventory();
                this.systemMetrics = new SystemMetrics('chart-metrics');
                this.memeSniper = new MemeSniperStrip('meme-sniper-mount');
                
                // Re-bind Callbacks
                if (this.unifiedVault) {
                    this.unifiedVault.setBridgeCallback((amount) => {
                        this.ws.send('BRIDGE_TRIGGER', { amount });
                        this.terminal.addLog('BRIDGE', 'INFO', `Bridge initiated: $${amount.toFixed(2)} USDC -> Phantom`);
                    });
                }
                
                // Request Initial Data
                if (this.ws && this.ws.connected) {
                    this.ws.send('GET_SYSTEM_STATS', {});
                    this.ws.send('GET_WATCHLIST', {});
                }
            } catch (e) {
                console.error("Error initializing dashboard components:", e);
            }
        }

        if (viewName.startsWith('engine-')) {
            const engineId = viewName.replace('engine-', '');
            // Engine specific init logic can go here
        }
    }"""

idx = content.find('initializeDynamicComponents(viewName) {')
if idx != -1:
    # Find closing brace needed to replace the whole function
    open_braces = 0
    end_idx = idx
    found_start = False
    for i in range(idx, len(content)):
        if content[i] == '{':
            open_braces += 1
            found_start = True
        elif content[i] == '}':
            open_braces -= 1
        
        if found_start and open_braces == 0:
            end_idx = i + 1
            break
    
    # Check if we actually found the end
    if end_idx > idx:
        new_content = content[:idx] + replacement + content[end_idx:]
        with open(path, 'w', encoding='utf-8') as f:
            f.write(new_content)
        print("Successfully replaced initializeDynamicComponents")
    else:
        print("Could not find end of function")
else:
    print("Function signature not found")
