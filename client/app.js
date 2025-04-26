// Connect to Socket.io server
const socket = io("http://localhost:3000");

// DOM Elements
const mapGrid = document.getElementById("map-grid");
const modeButtons = {
  start: document.getElementById("mode-start"),
  goal: document.getElementById("mode-goal"),
  obstacle: document.getElementById("mode-obstacle"),
  erase: document.getElementById("mode-erase"),
};
const startNavigationBtn = document.getElementById("start-navigation");
const stopNavigationBtn = document.getElementById("stop-navigation");
const clearMapBtn = document.getElementById("clear-map");
const logOutput = document.getElementById("log-output");
const positionDisplay = document.getElementById("position-display");
const directionDisplay = document.getElementById("direction-display");
const statusDisplay = document.getElementById("status-display");
const gridSizeSelect = document.getElementById("grid-size");
const applyGridSizeBtn = document.getElementById("apply-grid-size");

// Constants (now variable)
let MAP_SIZE = 10;
const EMPTY = 0;
const ROBOT_START = 1;
const GOAL = 2;
const OBSTACLE = 3;
const PATH = 4;
const CURRENT_ROBOT = 5;

// Application State
const state = {
  currentMode: "start",
  robotStartX: 0,
  robotStartY: 0,
  goalX: null,
  goalY: null,
  currentRobotX: 0,
  currentRobotY: 0,
  robotDirection: "NORTH",
  obstacles: [],
  mapData: Array(MAP_SIZE)
    .fill()
    .map(() => Array(MAP_SIZE).fill(EMPTY)),
  pathCells: [],
  isNavigating: false,
};

// Initialize the map grid
function initializeMap() {
  mapGrid.innerHTML = "";

  // Reset the map data
  state.mapData = Array(MAP_SIZE)
    .fill()
    .map(() => Array(MAP_SIZE).fill(EMPTY));

  for (let y = 0; y < MAP_SIZE; y++) {
    for (let x = 0; x < MAP_SIZE; x++) {
      const cell = document.createElement("div");
      cell.classList.add("grid-cell");
      cell.dataset.x = x;
      cell.dataset.y = y;
      cell.textContent = `${x},${y}`;

      // Add click event for cell selection
      cell.addEventListener("click", () => handleCellClick(x, y));

      mapGrid.appendChild(cell);
    }
  }

  // Set default start position
  state.mapData[state.robotStartY][state.robotStartX] = ROBOT_START;
  state.currentRobotX = state.robotStartX;
  state.currentRobotY = state.robotStartY;

  // Set goal if defined
  if (state.goalX !== null && state.goalY !== null) {
    state.mapData[state.goalY][state.goalX] = GOAL;
  }

  // Adjust grid cell size based on map size
  const cellSize = Math.max(20, Math.min(40, 500 / MAP_SIZE)) + "px";
  document.documentElement.style.setProperty("--cell-size", cellSize);

  updateMapDisplay();
}

// Handle cell click based on current mode
function handleCellClick(x, y) {
  if (state.isNavigating) {
    addLogEntry("System", "Cannot modify map during navigation");
    return;
  }

  const currentCell = state.mapData[y][x];

  // Handle based on current mode
  switch (state.currentMode) {
    case "start":
      // Clear previous start position
      for (let row = 0; row < MAP_SIZE; row++) {
        for (let col = 0; col < MAP_SIZE; col++) {
          if (state.mapData[row][col] === ROBOT_START) {
            state.mapData[row][col] = EMPTY;
          }
        }
      }

      // Set new start position
      if (state.mapData[y][x] !== GOAL) {
        state.mapData[y][x] = ROBOT_START;
        state.robotStartX = x;
        state.robotStartY = y;
        state.currentRobotX = x;
        state.currentRobotY = y;
        addLogEntry("System", `Set start position to (${x},${y})`);
      } else {
        addLogEntry("System", "Cannot set start position on goal");
      }
      break;

    case "goal":
      // Clear previous goal
      for (let row = 0; row < MAP_SIZE; row++) {
        for (let col = 0; col < MAP_SIZE; col++) {
          if (state.mapData[row][col] === GOAL) {
            state.mapData[row][col] = EMPTY;
          }
        }
      }

      // Set new goal
      if (state.mapData[y][x] !== ROBOT_START) {
        state.mapData[y][x] = GOAL;
        state.goalX = x;
        state.goalY = y;
        addLogEntry("System", `Set goal position to (${x},${y})`);
      } else {
        addLogEntry("System", "Cannot set goal on start position");
      }
      break;

    case "obstacle":
      // Toggle obstacle
      if (state.mapData[y][x] === EMPTY) {
        state.mapData[y][x] = OBSTACLE;
        state.obstacles.push({ x, y });
        addLogEntry("System", `Added obstacle at (${x},${y})`);
      } else if (state.mapData[y][x] === OBSTACLE) {
        state.mapData[y][x] = EMPTY;
        state.obstacles = state.obstacles.filter(
          (obs) => !(obs.x === x && obs.y === y)
        );
        addLogEntry("System", `Removed obstacle at (${x},${y})`);
      } else {
        addLogEntry("System", "Cannot place obstacle on start or goal");
      }
      break;

    case "erase":
      // Erase anything except start and goal
      if (state.mapData[y][x] === OBSTACLE) {
        state.mapData[y][x] = EMPTY;
        state.obstacles = state.obstacles.filter(
          (obs) => !(obs.x === x && obs.y === y)
        );
        addLogEntry("System", `Removed obstacle at (${x},${y})`);
      }
      break;
  }

  updateMapDisplay();
}

// Update the visual display of the map
function updateMapDisplay() {
  // Update the visual grid
  document.querySelectorAll(".grid-cell").forEach((cell) => {
    const x = parseInt(cell.dataset.x);
    const y = parseInt(cell.dataset.y);

    // Remove all classes first
    cell.classList.remove("robot", "goal", "obstacle", "path", "current-robot");

    // Add appropriate class based on map data
    if (state.mapData[y][x] === ROBOT_START) {
      cell.classList.add("robot");
      cell.textContent = "START";
    } else if (state.mapData[y][x] === GOAL) {
      cell.classList.add("goal");
      cell.textContent = "GOAL";
    } else if (state.mapData[y][x] === OBSTACLE) {
      cell.classList.add("obstacle");
      cell.textContent = "X";
    } else {
      // Regular cell, show coordinates
      cell.textContent = `${x},${y}`;
    }

    // Mark path cells
    if (
      state.pathCells.some((p) => p.x === x && p.y === y) &&
      state.mapData[y][x] === EMPTY
    ) {
      cell.classList.add("path");
    }

    // Mark current robot position (if different from start and not navigating)
    if (
      x === state.currentRobotX &&
      y === state.currentRobotY &&
      (state.isNavigating || x !== state.robotStartX || y !== state.robotStartY)
    ) {
      cell.classList.add("current-robot");

      // Add direction indicator
      let directionSymbol = "";
      switch (state.robotDirection) {
        case "NORTH":
          directionSymbol = "↑";
          break;
        case "EAST":
          directionSymbol = "→";
          break;
        case "SOUTH":
          directionSymbol = "↓";
          break;
        case "WEST":
          directionSymbol = "←";
          break;
      }

      cell.innerHTML = `<span class="robot-direction">${directionSymbol}</span>`;
    }
  });
}

// Add a log entry
function addLogEntry(topic, message) {
  const entry = document.createElement("div");
  entry.classList.add("log-entry");

  const timestamp = new Date().toLocaleTimeString();
  entry.innerHTML = `<span class="log-topic">[${timestamp}] ${topic}:</span> ${message}`;

  logOutput.appendChild(entry);
  logOutput.scrollTop = logOutput.scrollHeight;

  // Keep only the last 100 entries
  while (logOutput.children.length > 100) {
    logOutput.removeChild(logOutput.firstChild);
  }
}

// Clear the map
function clearMap() {
  if (state.isNavigating) {
    addLogEntry("System", "Cannot clear map during navigation");
    return;
  }

  // Reset map data
  state.mapData = Array(MAP_SIZE)
    .fill()
    .map(() => Array(MAP_SIZE).fill(EMPTY));

  // Reset start position to current robot position
  state.robotStartX = state.currentRobotX;
  state.robotStartY = state.currentRobotY;
  state.mapData[state.robotStartY][state.robotStartX] = ROBOT_START;

  // Clear goal (don't set on map immediately)
  state.goalX = null;
  state.goalY = null;

  // Clear obstacles and path
  state.obstacles = [];
  state.pathCells = [];

  updateMapDisplay();
  addLogEntry("System", "Map cleared");
}

// Change grid size
function changeGridSize(size) {
  if (state.isNavigating) {
    addLogEntry("System", "Cannot change grid size during navigation");
    return;
  }

  size = parseInt(size);
  if (isNaN(size) || size < 5 || size > 50) {
    addLogEntry("System", "Invalid grid size");
    return;
  }

  // Store current positions
  const prevStartX = state.robotStartX;
  const prevStartY = state.robotStartY;
  const hadGoal = state.goalX !== null && state.goalY !== null;
  const prevGoalX = state.goalX;
  const prevGoalY = state.goalY;

  // Update map size
  MAP_SIZE = size;

  // Adjust positions if they would be outside the new grid
  state.robotStartX = Math.min(prevStartX, MAP_SIZE - 1);
  state.robotStartY = Math.min(prevStartY, MAP_SIZE - 1);
  state.currentRobotX = state.robotStartX;
  state.currentRobotY = state.robotStartY;

  if (hadGoal) {
    state.goalX = Math.min(prevGoalX, MAP_SIZE - 1);
    state.goalY = Math.min(prevGoalY, MAP_SIZE - 1);
  }

  // Filter obstacles to only those within the new grid
  state.obstacles = state.obstacles.filter(
    (obstacle) => obstacle.x < MAP_SIZE && obstacle.y < MAP_SIZE
  );

  // Clear path
  state.pathCells = [];

  // Update CSS variables
  document.documentElement.style.setProperty("--grid-columns", MAP_SIZE);
  document.documentElement.style.setProperty("--grid-rows", MAP_SIZE);

  // Reinitialize the map
  initializeMap();

  addLogEntry("System", `Grid size changed to ${MAP_SIZE}x${MAP_SIZE}`);
}

// Start navigation
function startNavigation() {
  if (state.isNavigating) {
    addLogEntry("System", "Navigation already in progress");
    return;
  }

  // Check if start position is set
  if (state.robotStartX === null || state.robotStartY === null) {
    addLogEntry("System", "Start position must be set");
    return;
  }

  // Check if goal position is set
  if (state.goalX === null || state.goalY === null) {
    addLogEntry("System", "Goal position must be set");
    return;
  }

  // Send navigation command to server
  socket.emit("navigate", {
    start: { x: state.robotStartX, y: state.robotStartY },
    goal: { x: state.goalX, y: state.goalY },
    obstacles: state.obstacles,
  });

  state.isNavigating = true;
  state.currentRobotX = state.robotStartX;
  state.currentRobotY = state.robotStartY;

  // Clear path visualization
  state.pathCells = [];

  updateMapDisplay();
  addLogEntry("System", "Navigation started");
  statusDisplay.textContent = "Navigation Started";
}

// Stop navigation
function stopNavigation() {
  if (!state.isNavigating) {
    addLogEntry("System", "No navigation in progress");
    return;
  }

  socket.emit("stop");

  state.isNavigating = false;
  updateMapDisplay();
  addLogEntry("System", "Navigation stopped");
  statusDisplay.textContent = "Stopped";
}

// Set active mode
function setActiveMode(mode) {
  if (state.isNavigating) {
    addLogEntry("System", "Cannot change mode during navigation");
    return;
  }

  state.currentMode = mode;

  // Update UI to reflect the active mode
  Object.keys(modeButtons).forEach((key) => {
    if (key === mode) {
      modeButtons[key].classList.add("active");
    } else {
      modeButtons[key].classList.remove("active");
    }
  });

  addLogEntry("System", `Selection mode changed to: ${mode}`);
}

// Process MQTT messages
function processMqttMessage(topic, payload) {
  switch (topic) {
    case "robot/position":
      const positionMatch = payload.match(/\((\d+),(\d+)\)/);
      if (positionMatch) {
        const x = parseInt(positionMatch[1]);
        const y = parseInt(positionMatch[2]);

        // Update current position
        state.currentRobotX = x;
        state.currentRobotY = y;
        positionDisplay.textContent = `(${x},${y})`;
        updateMapDisplay();
      }
      break;

    case "robot/direction":
      const directionMatch = payload.match(/Current direction: (\w+)/);
      if (directionMatch) {
        state.robotDirection = directionMatch[1];
        directionDisplay.textContent = state.robotDirection;
        updateMapDisplay();
      }
      break;

    case "robot/status":
      statusDisplay.textContent = payload;

      // Check if navigation has completed
      if (
        payload.includes("Destination reached") ||
        payload.includes("completed") ||
        payload.includes("Path not found")
      ) {
        state.isNavigating = false;
      }
      break;

    case "robot/path":
      // Extract path from payload like "Path found with 5 steps: (0,0) -> (1,0) -> (2,0) -> (3,0) -> (4,0)"
      const pathMatch = payload.match(
        /Path found with \d+ steps: \(\d+,\d+\) -> (.*)/
      );
      if (pathMatch) {
        const pathStr = pathMatch[1];
        const pathCoords = pathStr.match(/\(\d+,\d+\)/g);

        if (pathCoords) {
          state.pathCells = pathCoords.map((coord) => {
            const [x, y] = coord.replace(/[()]/g, "").split(",").map(Number);
            return { x, y };
          });
          updateMapDisplay();
        }
      }
      break;
  }
}

// Event Listeners
// Mode selection buttons
Object.entries(modeButtons).forEach(([mode, button]) => {
  button.addEventListener("click", () => setActiveMode(mode));
});

// Control buttons
startNavigationBtn.addEventListener("click", startNavigation);
stopNavigationBtn.addEventListener("click", stopNavigation);
clearMapBtn.addEventListener("click", clearMap);

// Grid size change
applyGridSizeBtn.addEventListener("click", () => {
  changeGridSize(gridSizeSelect.value);
});

// Socket events
socket.on("connect", () => {
  addLogEntry("System", "Connected to server");
});

socket.on("disconnect", () => {
  addLogEntry("System", "Disconnected from server");
  state.isNavigating = false;
});

socket.on("mqtt_message", (data) => {
  addLogEntry(data.topic, data.payload);
  processMqttMessage(data.topic, data.payload);
});

socket.on("command_sent", (data) => {
  if (data.success) {
    addLogEntry("System", `Command '${data.command}' sent successfully`);
  } else {
    addLogEntry(
      "Error",
      `Failed to send command: ${data.error || "Unknown error"}`
    );
  }
});

// Initialize the application
initializeMap();
addLogEntry("System", "Robot navigation interface initialized");
