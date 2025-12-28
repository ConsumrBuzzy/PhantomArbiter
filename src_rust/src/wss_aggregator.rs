// ------------------------------------------------------------------------
// WSS AGGREGATOR (Phase 17.5: The Wire v2)
// High-performance parallel WebSocket aggregation for free-tier RPC racing
// ------------------------------------------------------------------------
//
// Architecture:
// - Multiple tokio-tungstenite connections to different providers
// - First-in-wins message processing via ConsensusEngine
// - Crossbeam channel for lock-free event delivery to Python
// - Background Tokio runtime managed independently of Python GIL

use pyo3::prelude::*;
use tokio::runtime::Runtime;
use tokio::sync::mpsc;
use tokio_tungstenite::{connect_async, tungstenite::Message};
use futures_util::{StreamExt, SinkExt};
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::Arc;
use crossbeam_channel::{bounded, Receiver, Sender};
use serde::{Deserialize, Serialize};
use serde_json::json;

// ============================================================================
// MESSAGE TYPES
// ============================================================================

/// Raw log event from WebSocket (before parsing)
#[derive(Debug, Clone)]
pub struct RawLogEvent {
    pub provider: String,
    pub slot: u64,
    pub signature: String,
    pub logs: Vec<String>,
    pub timestamp_ns: u64,
}

/// Parsed event ready for Python consumption
#[pyclass]
#[derive(Clone, Debug)]
pub struct WssEvent {
    #[pyo3(get)]
    pub provider: String,
    #[pyo3(get)]
    pub slot: u64,
    #[pyo3(get)]
    pub signature: String,
    #[pyo3(get)]
    pub logs: Vec<String>,
    #[pyo3(get)]
    pub latency_ms: f64,
}

#[pymethods]
impl WssEvent {
    fn __repr__(&self) -> String {
        format!(
            "WssEvent(provider={}, slot={}, sig={}...)",
            self.provider,
            self.slot,
            &self.signature[..8.min(self.signature.len())]
        )
    }
}

/// Statistics for monitoring
#[pyclass]
#[derive(Clone, Debug, Default)]
pub struct WssStats {
    #[pyo3(get)]
    pub active_connections: u64,
    #[pyo3(get)]
    pub messages_received: u64,
    #[pyo3(get)]
    pub messages_accepted: u64,
    #[pyo3(get)]
    pub messages_dropped: u64,
    #[pyo3(get)]
    pub avg_latency_ms: f64,
}

// ============================================================================
// WSS AGGREGATOR
// ============================================================================

/// High-performance WebSocket aggregator.
/// Connects to multiple RPC providers simultaneously and races their messages.
#[pyclass]
pub struct WssAggregator {
    /// Event channel (Rust → Python)
    event_rx: Option<Receiver<WssEvent>>,
    event_tx: Option<Sender<WssEvent>>,
    
    /// Control flag for shutdown
    running: Arc<AtomicBool>,
    
    /// Statistics
    msg_received: Arc<AtomicU64>,
    msg_accepted: Arc<AtomicU64>,
    msg_dropped: Arc<AtomicU64>,
    active_conns: Arc<AtomicU64>,
    
    /// Tokio runtime (owned)
    runtime: Option<Runtime>,
}

#[pymethods]
impl WssAggregator {
    #[new]
    #[pyo3(signature = (channel_size=1000))]
    pub fn new(channel_size: usize) -> PyResult<Self> {
        let (tx, rx) = bounded(channel_size);
        
        Ok(Self {
            event_rx: Some(rx),
            event_tx: Some(tx),
            running: Arc::new(AtomicBool::new(false)),
            msg_received: Arc::new(AtomicU64::new(0)),
            msg_accepted: Arc::new(AtomicU64::new(0)),
            msg_dropped: Arc::new(AtomicU64::new(0)),
            active_conns: Arc::new(AtomicU64::new(0)),
            runtime: None,
        })
    }
    
    /// Start the aggregator with multiple WSS endpoints.
    /// 
    /// # Arguments
    /// * `endpoints` - List of WSS URLs (e.g., ["wss://mainnet.helius-rpc.com/?api-key=xxx"])
    /// * `program_ids` - List of program IDs to subscribe to (e.g., Raydium, Orca)
    /// * `commitment` - Commitment level ("processed", "confirmed", "finalized")
    #[pyo3(signature = (endpoints, program_ids, commitment="processed"))]
    pub fn start(
        &mut self,
        endpoints: Vec<String>,
        program_ids: Vec<String>,
        commitment: &str,
    ) -> PyResult<()> {
        if self.running.load(Ordering::SeqCst) {
            return Err(PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(
                "Aggregator already running"
            ));
        }
        
        // Create Tokio runtime
        let runtime = Runtime::new()
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e.to_string()))?;
        
        self.running.store(true, Ordering::SeqCst);
        
        let tx = self.event_tx.clone().unwrap();
        let running = self.running.clone();
        let msg_received = self.msg_received.clone();
        let msg_accepted = self.msg_accepted.clone();
        let msg_dropped = self.msg_dropped.clone();
        let active_conns = self.active_conns.clone();
        let commitment = commitment.to_string();
        
        // Spawn connection tasks
        for (idx, endpoint) in endpoints.into_iter().enumerate() {
            let tx = tx.clone();
            let running = running.clone();
            let msg_received = msg_received.clone();
            let msg_accepted = msg_accepted.clone();
            let msg_dropped = msg_dropped.clone();
            let active_conns = active_conns.clone();
            let program_ids = program_ids.clone();
            let commitment = commitment.clone();
            let provider_name = format!("provider_{}", idx);
            
            runtime.spawn(async move {
                run_connection(
                    endpoint,
                    provider_name,
                    program_ids,
                    commitment,
                    tx,
                    running,
                    msg_received,
                    msg_accepted,
                    msg_dropped,
                    active_conns,
                ).await;
            });
        }
        
        self.runtime = Some(runtime);
        
        Ok(())
    }
    
    /// Stop all connections.
    pub fn stop(&mut self) -> PyResult<()> {
        self.running.store(false, Ordering::SeqCst);
        
        // Drop the runtime to stop all tasks
        if let Some(rt) = self.runtime.take() {
            rt.shutdown_background();
        }
        
        Ok(())
    }
    
    /// Poll for the next event (non-blocking).
    /// Returns None if no event is available.
    pub fn poll_event(&self) -> Option<WssEvent> {
        self.event_rx.as_ref()?.try_recv().ok()
    }
    
    /// Poll for multiple events (non-blocking).
    /// Returns up to `max_count` events.
    #[pyo3(signature = (max_count=100))]
    pub fn poll_events(&self, max_count: usize) -> Vec<WssEvent> {
        let mut events = Vec::with_capacity(max_count);
        if let Some(rx) = &self.event_rx {
            while events.len() < max_count {
                match rx.try_recv() {
                    Ok(event) => events.push(event),
                    Err(_) => break,
                }
            }
        }
        events
    }
    
    /// Check if the aggregator is running.
    pub fn is_running(&self) -> bool {
        self.running.load(Ordering::SeqCst)
    }
    
    /// Get current statistics.
    pub fn get_stats(&self) -> WssStats {
        WssStats {
            active_connections: self.active_conns.load(Ordering::Relaxed),
            messages_received: self.msg_received.load(Ordering::Relaxed),
            messages_accepted: self.msg_accepted.load(Ordering::Relaxed),
            messages_dropped: self.msg_dropped.load(Ordering::Relaxed),
            avg_latency_ms: 0.0, // TODO: track latency
        }
    }
    
    /// Get pending event count.
    pub fn pending_count(&self) -> usize {
        self.event_rx.as_ref().map(|rx| rx.len()).unwrap_or(0)
    }
}

// ============================================================================
// CONNECTION LOGIC
// ============================================================================

async fn run_connection(
    endpoint: String,
    provider_name: String,
    program_ids: Vec<String>,
    commitment: String,
    tx: Sender<WssEvent>,
    running: Arc<AtomicBool>,
    msg_received: Arc<AtomicU64>,
    msg_accepted: Arc<AtomicU64>,
    msg_dropped: Arc<AtomicU64>,
    active_conns: Arc<AtomicU64>,
) {
    let mut backoff_ms = 100u64;
    const MAX_BACKOFF_MS: u64 = 30_000;
    
    while running.load(Ordering::SeqCst) {
        match connect_and_subscribe(
            &endpoint,
            &provider_name,
            &program_ids,
            &commitment,
            &tx,
            &running,
            &msg_received,
            &msg_accepted,
            &msg_dropped,
            &active_conns,
        ).await {
            Ok(_) => {
                // Normal disconnect, reset backoff
                backoff_ms = 100;
            }
            Err(e) => {
                eprintln!("[{}] Connection error: {}", provider_name, e);
                // Exponential backoff
                tokio::time::sleep(tokio::time::Duration::from_millis(backoff_ms)).await;
                backoff_ms = (backoff_ms * 2).min(MAX_BACKOFF_MS);
            }
        }
    }
}

async fn connect_and_subscribe(
    endpoint: &str,
    provider_name: &str,
    program_ids: &[String],
    commitment: &str,
    tx: &Sender<WssEvent>,
    running: &Arc<AtomicBool>,
    msg_received: &Arc<AtomicU64>,
    msg_accepted: &Arc<AtomicU64>,
    msg_dropped: &Arc<AtomicU64>,
    active_conns: &Arc<AtomicU64>,
) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
    // Connect
    let url = url::Url::parse(endpoint)?;
    let (ws_stream, _) = connect_async(url).await?;
    let (mut write, mut read) = ws_stream.split();
    
    active_conns.fetch_add(1, Ordering::Relaxed);
    
    // Subscribe to logsSubscribe for each program
    for (idx, program_id) in program_ids.iter().enumerate() {
        let sub_msg = json!({
            "jsonrpc": "2.0",
            "id": idx + 1,
            "method": "logsSubscribe",
            "params": [
                {
                    "mentions": [program_id]
                },
                {
                    "commitment": commitment
                }
            ]
        });
        
        write.send(Message::Text(sub_msg.to_string())).await?;
    }
    
    // Process messages
    while running.load(Ordering::SeqCst) {
        match tokio::time::timeout(
            tokio::time::Duration::from_secs(30),
            read.next()
        ).await {
            Ok(Some(Ok(Message::Text(text)))) => {
                msg_received.fetch_add(1, Ordering::Relaxed);
                
                // Parse the message
                if let Some(event) = parse_log_notification(&text, provider_name) {
                    match tx.try_send(event) {
                        Ok(_) => {
                            msg_accepted.fetch_add(1, Ordering::Relaxed);
                        }
                        Err(_) => {
                            msg_dropped.fetch_add(1, Ordering::Relaxed);
                        }
                    }
                }
            }
            Ok(Some(Ok(Message::Ping(data)))) => {
                // Respond to ping
                let _ = write.send(Message::Pong(data)).await;
            }
            Ok(Some(Ok(Message::Close(_)))) => {
                break;
            }
            Ok(Some(Err(e))) => {
                eprintln!("[{}] Read error: {}", provider_name, e);
                break;
            }
            Ok(None) => {
                // Stream ended
                break;
            }
            Err(_) => {
                // Timeout - send ping to check connection
                if write.send(Message::Ping(vec![])).await.is_err() {
                    break;
                }
            }
            _ => {}
        }
    }
    
    active_conns.fetch_sub(1, Ordering::Relaxed);
    Ok(())
}

/// Parse a logsSubscribe notification into a WssEvent.
fn parse_log_notification(text: &str, provider_name: &str) -> Option<WssEvent> {
    let v: serde_json::Value = serde_json::from_str(text).ok()?;
    
    // Check if it's a notification (not a subscription confirmation)
    let method = v.get("method")?.as_str()?;
    if method != "logsNotification" {
        return None;
    }
    
    let params = v.get("params")?;
    let result = params.get("result")?;
    let value = result.get("value")?;
    let context = result.get("context")?;
    
    let slot = context.get("slot")?.as_u64()?;
    let signature = value.get("signature")?.as_str()?.to_string();
    let logs: Vec<String> = value.get("logs")?
        .as_array()?
        .iter()
        .filter_map(|l| l.as_str().map(|s| s.to_string()))
        .collect();
    
    let _timestamp_ns = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap()
        .as_nanos() as u64;
    
    Some(WssEvent {
        provider: provider_name.to_string(),
        slot,
        signature,
        logs,
        latency_ms: 0.0, // Would need server timestamp to calculate
    })
}

// ============================================================================
// MODULE REGISTRATION
// ============================================================================

pub fn register_wss_aggregator_classes(m: &PyModule) -> PyResult<()> {
    m.add_class::<WssAggregator>()?;
    m.add_class::<WssEvent>()?;
    m.add_class::<WssStats>()?;
    Ok(())
}
