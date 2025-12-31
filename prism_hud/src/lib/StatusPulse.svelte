<script>
    export let isConnected = false;
    export let diffRate = 0;
</script>

<div class="bg-panel-bg/90 border-t border-gray-800 p-2 flex justify-between items-center text-xs backdrop-blur-md">
    <div class="flex items-center space-x-4">
        <div class="flex items-center space-x-2">
            <div class={`w-2 h-2 rounded-full ${isConnected ? 'bg-neon-green animate-pulse' : 'bg-red-500'}`}></div>
            <span class="font-mono text-gray-400 capitalize">{isConnected ? 'VISUAL BRIDGE ONLINE' : 'SEARCHING FOR BRIDGE...'}</span>
        </div>
        
        <div class="h-4 w-px bg-gray-700"></div>

        <div class="flex items-center space-x-2">
            <span class="text-gray-500">DIFF_RATE:</span>
            <span class="font-mono text-neon-blue">{diffRate} /sec</span>
        </div>
    </div>

    <div class="text-gray-600 font-mono">
        NOMAD CYCLE: SEE
    </div>
</div>
