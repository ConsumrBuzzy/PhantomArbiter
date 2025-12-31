<script>
  import { onMount, onDestroy } from 'svelte';
  import { SigmaManager } from './sigma_manager.js';
  import StatusPulse from './lib/StatusPulse.svelte'; // We'll create this next

  let sigmaManager;
  let socket;
  let isConnected = false;
  let diffRate = 0;
  let lastDiffTime = Date.now();
  let diffCount = 0;

  // Calculate diff rate every second
  setInterval(() => {
    diffRate = diffCount;
    diffCount = 0;
  }, 1000);

  onMount(() => {
    sigmaManager = new SigmaManager('sigma-container');
    sigmaManager.initialize();

    connectWebSocket();
  });

  function connectWebSocket() {
    socket = new WebSocket('ws://localhost:8765');

    socket.onopen = () => {
      console.log('VisualBridge Connected');
      isConnected = true;
    };

    socket.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        handleData(data);
      } catch (e) {
        console.error('Failed to parse WebSocket message:', e);
      }
    };

    socket.onclose = () => {
      console.log('VisualBridge Disconnected');
      isConnected = false;
      // Reconnect strategy could go here
      setTimeout(connectWebSocket, 5000);
    };
  }

  function handleData(data) {
    if (data.type === 'snapshot') {
      sigmaManager.processSnapshot(data.payload);
    } else if (data.type === 'diff') {
      diffCount++;
      sigmaManager.processDiff(data.payload);
    }
  }

  onDestroy(() => {
    if (socket) socket.close();
    if (sigmaManager) sigmaManager.cleanup();
  });
</script>

<main class="w-screen h-screen bg-dark-bg text-white overflow-hidden relative">
  <!-- The Canvas -->
  <div id="sigma-container" class="absolute inset-0 z-0"></div>

  <!-- HUD Overlay -->
  <div class="absolute top-4 left-4 z-10 pointer-events-none">
    <h1 class="text-2xl font-bold bg-black/50 p-2 rounded text-neon-blue border border-neon-blue/30 backdrop-blur-sm">
      PRISM <span class="text-white text-sm font-normal opacity-70">HUD v1.0</span>
    </h1>
  </div>

  <!-- System Pulse (Footer) -->
  <div class="absolute bottom-0 w-full z-20 pointer-events-none">
     <div class="pointer-events-auto">
        <StatusPulse {isConnected} {diffRate} />
     </div>
  </div>
</main>
