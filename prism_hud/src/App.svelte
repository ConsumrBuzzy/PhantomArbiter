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

  // Buffer and Sequence Tracking
  let messageQueue = [];
  let currentSeqId = -1;
  let lastFrameTime = 0;
  
  // Calculate diff rate every second
  setInterval(() => {
    diffRate = diffCount;
    diffCount = 0;
  }, 1000);

  onMount(() => {
    sigmaManager = new SigmaManager('sigma-container');
    sigmaManager.initialize();

    connectWebSocket();
    requestAnimationFrame(processQueue); // Start the loop
  });

  function processQueue(timestamp) {
    // Decay visual effects every frame for smoothness
    if (sigmaManager) sigmaManager.decayEnergy();

    if (messageQueue.length > 0) {
      // Process up to 5 messages per frame to prevent locking
      const batch = messageQueue.splice(0, 5);
      batch.forEach(data => applyUpdate(data));
    }
    requestAnimationFrame(processQueue);
  }

  function applyUpdate(data) {
    if (data.type === 'snapshot') {
        currentSeqId = data.seq_id;
        sigmaManager.processSnapshot(data);
    } else if (data.type === 'diff') {
        if (currentSeqId !== -1 && data.seq_id !== currentSeqId + 1) {
            console.warn(`Sequence Mismatch! Expected ${currentSeqId + 1}, got ${data.seq_id}. Requesting SYNC.`);
            socket.send(JSON.stringify({ action: "REQUEST_SYNC" }));
            messageQueue = []; // Clear buffer on invalid state
            return;
        }
        currentSeqId = data.seq_id;
        diffCount++;
        sigmaManager.processDiff(data);
    } else if (data.type === 'flash') {
        // High-speed visual event (No sequence check needed)
        sigmaManager.processFlash(data);
    }
  }

  function connectWebSocket() {
    socket = new WebSocket('ws://localhost:8765');

    socket.onopen = () => {
      console.log('VisualBridge Connected');
      isConnected = true;
      // Handshake: Explicitly request initial state if needed, though server sends snapshot on connect.
    };

    socket.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === 'PING') {
            socket.send(JSON.stringify({ action: "PONG" }));
            return;
        }
        // Enqueue for RAF loop
        messageQueue.push(data);
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
