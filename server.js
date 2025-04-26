const express = require("express");
const http = require("http");
const mqtt = require("mqtt");
const path = require("path");
const socketIO = require("socket.io");
const cors = require("cors");

const app = express();

app.use(
  cors({
    origin: "*",
    methods: ["GET", "POST"],
  })
);
const server = http.createServer(app);

const io = socketIO(server, {
  cors: {
    origin: "*",
    methods: ["GET", "POST"],
  },
});

// MQTT Configuration
const mqttHost = "localhost"; // Change to your MQTT broker IP
const mqttOptions = {
  username: "hiep",
  password: "1234",
  clientId: "nodejs_server_" + Math.random().toString(16).slice(2, 8),
};

// Connect to MQTT broker
const mqttClient = mqtt.connect(`mqtt://${mqttHost}`, mqttOptions);

// Serve static files
app.use(express.static(path.join(__dirname, "public")));

// Socket.IO connection
io.on("connection", (socket) => {
  console.log("New client connected");

  // Handle navigation requests with coordinates
  socket.on("navigate", (data) => {
    let navCommand = "navigate";
    if (data.start && data.goal) {
      navCommand += `:${data.start.x},${data.start.y}:${data.goal.x},${data.goal.y}`;

      // Add obstacles if available
      if (data.obstacles && data.obstacles.length > 0) {
        navCommand += ":";
        data.obstacles.forEach((obstacle, index) => {
          navCommand += `${obstacle.x},${obstacle.y}`;
          if (index < data.obstacles.length - 1) {
            navCommand += ";";
          }
        });
      }
    }
    console.log("Navigation command:", navCommand);
    mqttClient.publish("mpu6050/alert", navCommand);

    // Send acknowledgment back to client
    socket.emit("command_sent", {
      command: "navigate",
      success: true,
    });
  });

  // Handle stop request
  socket.on("stop", () => {
    console.log("Stop command received");
    mqttClient.publish("mpu6050/alert", "stop");

    socket.emit("command_sent", {
      command: "stop",
      success: true,
    });
  });

  // Handle disconnect
  socket.on("disconnect", () => {
    console.log("Client disconnected");
  });
});

// When MQTT client connects
mqttClient.on("connect", () => {
  console.log("Connected to MQTT broker");

  // Subscribe to all robot topics
  mqttClient.subscribe("robot/#", (err) => {
    if (!err) {
      console.log("Subscribed to robot/# topic");
    } else {
      console.log("Error subscribing:", err);
    }
  });
});

// Forward MQTT messages to web clients via Socket.IO
mqttClient.on("message", (topic, message) => {
  const payload = message.toString();
  console.log(`${topic}: ${payload}`);

  io.emit("mqtt_message", {
    topic: topic,
    payload: payload,
  });
});

// Handle MQTT errors
mqttClient.on("error", (error) => {
  console.error("MQTT Error:", error);
});

// Start the server
const PORT = process.env.PORT || 3000;
server.listen(PORT, () => {
  console.log(`Server running on port ${PORT}`);
});

// try {
//   const data = JSON.parse(message.toString());
//   console.log("Received data:", data); // Log the original data

//   const x = data.x;
//   const y = data.y;
//   console.log(`X: ${x}, Y: ${y}`); // Log the coordinates

//   let command = "";

//   // Check for stop condition first (x and y both in edge ranges)
//   if (
//     ((x >= 340 && x <= 360) || (x >= 0 && x <= 20)) &&
//     ((y >= 340 && y <= 360) || (y >= 0 && y <= 20))
//   ) {
//     command = "stop";
//   }
//   // Check for forward/backward based on x values
//   if (x >= 20 && x <= 120) {
//     command = "forward";
//   }
//   if (x >= 240 && x <= 340) {
//     command = "backward";
//   }
//   // Check for left/right based on y values
//   if (y >= 240 && y <= 340) {
//     command = "left";
//   }
//   if (y >= 20 && y <= 120) {
//     command = "right";
//   }

//   // Only publish if we have a valid command
//   if (command) {
//     client.publish("mpu6050/alert", command);
//     console.log(`Published '${command}' to mpu6050/alert`);
//   }
// } catch (e) {
//   console.error("Invalid message format:", message.toString(), e);
// }
