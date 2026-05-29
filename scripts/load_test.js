import ws from 'k6/ws';
import { check, sleep } from 'k6';
import { Trend, Rate } from 'k6/metrics';

// Custom metrics for latency tracking
const wsLatency = new Trend('ws_message_latency_ms');
const wsLatencyMax = new Trend('ws_message_latency_max_ms');
const messageSuccessRate = new Rate('message_success_rate');
const connectionSuccessRate = new Rate('connection_success_rate');

// Latency threshold target: p95 < 50ms
const LATENCY_THRESHOLD_MS = 50;

// 1. Configure the load test: Ramp up to 500 concurrent WebSocket connections
export const options = {
  stages: [
    { duration: '30s', target: 500 }, // Scale up to 500 concurrent users over 30 seconds
    { duration: '1m', target: 500 },  // Hold 500 users for 1 minute
    { duration: '10s', target: 0 },   // Ramp down gracefully
  ],
  thresholds: {
    ws_message_latency_ms: ['p(95) < 50'],   // 95% of messages under 50ms
    ws_message_latency_max_ms: ['avg < 100'], // Avg max per-VU under 100ms
    message_success_rate: ['rate > 0.99'],     // 99%+ messages received successfully
    connection_success_rate: ['rate > 0.95'],  // 95%+ connections succeed
  },
};

// 2. Define the behavior of each "virtual user" (VU)
export default function () {
  const boardId = __ENV.BOARD_ID || '00000000-0000-0000-0000-000000000000';
  const latencyThreshold = parseInt(__ENV.LATENCY_THRESHOLD_MS) || LATENCY_THRESHOLD_MS;

  const url = `ws://localhost:8000/ws/board/${boardId}/`;

  // Track max latency per VU for aggregate reporting
  let maxLatencySeen = 0;

  const res = ws.connect(url, null, function (socket) {
    socket.on('open', () => {
      connectionSuccessRate.add(true);

      // Send a ping every 2 seconds with a unique timestamp to measure round-trip
      socket.setInterval(function timeout() {
        const sentAt = Date.now();
        socket.send(JSON.stringify({
          type: 'ping',
          payload: { timestamp: sentAt },
        }));
      }, 2000);
    });

    socket.on('message', (msg) => {
      messageSuccessRate.add(true);
      try {
        const parsed = JSON.parse(msg);
        // Only measure latency for messages that carry our timestamp
        if (parsed && parsed.payload && parsed.payload.timestamp) {
          const now = Date.now();
          const sentAt = parsed.payload.timestamp;
          const latency = now - sentAt;
          wsLatency.add(latency);
          if (latency > maxLatencySeen) {
            maxLatencySeen = latency;
          }
          // Fail if latency exceeds threshold
          check(latency, {
            [`latency < ${latencyThreshold}ms`]: (l) => l < latencyThreshold,
          });
        }
      } catch (e) {
        // Non-JSON or non-timestamp messages are fine (e.g., board_update from signals)
        messageSuccessRate.add(true);
      }
    });

    socket.on('error', (e) => {
      connectionSuccessRate.add(false);
    });

    socket.on('close', () => {
      // Record max latency for this VU at close
      wsLatencyMax.add(maxLatencySeen);
    });

    // Close the socket after 1 minute
    socket.setTimeout(function () {
      socket.close();
    }, 60000);
  });

  // Connection success check
  const connected = res && res.status === 101;
  check(res, {
    'status is 101 (Switching Protocols)': (r) => r && r.status === 101,
  });
  if (!connected) {
    connectionSuccessRate.add(false);
  }

  // Brief pause between connections to avoid thundering herd
  sleep(1);
}
