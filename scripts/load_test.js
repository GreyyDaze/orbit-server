import ws from 'k6/ws';
import { check } from 'k6';

// 1. Configure the load test: Ramp up to 500 concurrent WebSocket connections
export const options = {
  stages: [
    { duration: '30s', target: 500 }, // Scale up to 500 concurrent users over 30 seconds
    { duration: '1m', target: 500 },  // Hold 500 users for 1 minute
    { duration: '10s', target: 0 },   // Ramp down gracefully
  ],
};

// 2. Define the behavior of each "virtual user" (VU)
export default function () {
  // We need an actual board ID from your local database.
  // We will pass this via an environment variable when running k6.
  const boardId = __ENV.BOARD_ID || '00000000-0000-0000-0000-000000000000'; 
  
  // Note: Django Channels usually runs on :8000 locally via Daphne or runserver
  const url = `ws://localhost:8000/ws/board/${boardId}/`;

  const res = ws.connect(url, null, function (socket) {
    socket.on('open', () => {
      // Simulate real user interaction: A user "moving" something or sending an event
      socket.setInterval(function timeout() {
        // We send a dummy payload that Channels will receive
        socket.send(JSON.stringify({ 
          type: 'ping', 
          payload: { timestamp: Date.now() } 
        }));
      }, 2000); // 1 ping every 2 seconds per user = 250 requests/sec at 500 users
    });

    // When the server broadcasts a message back to the clients
    socket.on('message', (msg) => {
      // In a real scenario, you can check parsing time or latency here
      check(msg, { 'received broadcast message': (msg) => msg.length > 0 });
    });

    // Close the socket connection after 1 minute of testing
    socket.setTimeout(function () {
      socket.close();
    }, 60000); 
  });

  // Check if the connection successfully switched to the WebSocket protocol (101 status code)
  check(res, { 'status is 101 (Switching Protocols)': (r) => r && r.status === 101 });
}
