// Electron Main Process
// Handles window creation and IPC communication with Python backend

const { app, BrowserWindow, ipcMain, dialog } = require("electron");
const path = require("path");
const { spawn } = require("child_process");
const fs = require("fs");

let mainWindow;
let pythonProcess;
let appState = {
  isProcessing: false,
  hasRunOnce: false,
  currentJob: null,
  clips: [],
  logs: [],
  status: "idle",
  startTime: null,
};

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1400,
    height: 900,
    minWidth: 1200,
    minHeight: 700,
    backgroundColor: "#0a0a0a",
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, "preload.js"),
    },
    frame: true,
    titleBarStyle: "default",
    show: false,
  });

  // Load main HTML file
  mainWindow.loadFile(path.join(__dirname, "renderer", "index.html")).catch((err) => {
    console.error("Failed to load page:", err);
    console.log("Make sure index.html exists in the root folder");
  });

  mainWindow.once("ready-to-show", () => {
    mainWindow.show();
  });

  mainWindow.on("closed", () => {
    mainWindow = null;
    if (pythonProcess) {
      pythonProcess.kill();
    }
  });

  // Open DevTools (Always open for debugging now)
  mainWindow.webContents.openDevTools();
}

app.whenReady().then(() => {
  createWindow();

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    app.quit();
  }
});

// IPC Handlers

// Start Python Engine
ipcMain.handle("start-engine", async (event, payload) => {
  try {
    console.log("Starting engine with payload:", payload);

    // Update app state
    appState.isProcessing = true;
    appState.hasRunOnce = true;
    appState.status = "running";
    appState.startTime = Date.now();
    appState.currentJob = {
      input: payload.input,
      elapsed: "0s",
      remaining: "Calculating...",
      step: "Starting...",
      percent: 0,
    };

    // Send state update to renderer
    sendToRenderer({
      type: "state",
      status: "started",
      job: appState.currentJob,
      input: payload.input,
    });

    // Spawn Python process
    // Determine Python path (prioritize local venv)
    let pythonPath = process.env.PYTHON_PATH || "python";
    const venvPython = process.platform === "win32"
      ? path.join(__dirname, "engine", ".venv", "Scripts", "python.exe")
      : path.join(__dirname, "engine", ".venv", "bin", "python");

    if (fs.existsSync(venvPython)) {
      pythonPath = venvPython;
      console.log("Using venv python:", pythonPath);
    } else {
      console.log("Using system python:", pythonPath);
    }
    const scriptPath = path.join(__dirname, "engine", "engine.py");
    const engineDir = path.join(__dirname, "engine");

    pythonProcess = spawn(
      pythonPath,
      [
        scriptPath,
        "--input",
        payload.input,
        "--output",
        payload.output,
        "--max-clips",
        payload.maxClips.toString(),
        "--clip-duration",
        payload.clipDuration.toString(),
        "--aspect",
        payload.aspect || "16:9",
        "--subtitle",
        payload.subtitle || "tiktok",
        "--subtitle-style",
        payload.subtitleStyle || "tiktok",
        "--subtitle-position",
        payload.subtitlePosition || "center",
        "--subtitle-color",
        payload.subtitleColor || "white",
        "--project-name",
        payload.projectName || "Untitled",
        "--enable-crop",
        payload.enableCrop !== false ? "true" : "false",
        "--quality",
        payload.quality || "balanced",
      ],
      { cwd: engineDir },
    );

    // Handle Python stdout
    pythonProcess.stdout.on("data", (data) => {
      const lines = data.toString().split("\n");
      lines.forEach((line) => {
        const trimmed = line.trim();
        if (!trimmed) return;

        // Structured IPC Event
        if (trimmed.startsWith("IPC_EVENT:")) {
          try {
            const jsonStr = trimmed.substring(10); // Remove "IPC_EVENT:"
            const event = JSON.parse(jsonStr);
            handlePythonEvent(event);
          } catch (e) {
            console.error("Failed to parse IPC event:", trimmed);
          }
        }
        // Regular Log (e.g. tqdm progress bars, print statements)
        else {
          // Also log to console for debugging
          console.log("[PYTHON]:", trimmed);

          sendToRenderer({
            type: "log",
            level: "INFO",
            message: trimmed,
          });
          appState.logs.push({
            timestamp: new Date().toISOString(),
            message: trimmed,
            type: "log",
          });
        }
      });
    });

    // Handle Python stderr
    pythonProcess.stderr.on("data", (data) => {
      const message = data.toString();

      // Comprehensive ffmpeg output filter
      // FFmpeg sends most of its output to stderr, which is NOT an error
      const isFFmpegOutput =
        // Progress indicators
        (message.includes('frame=') && (message.includes('fps=') || message.includes('bitrate=') || message.includes('speed='))) ||
        // Library info
        message.includes('libavutil') ||
        message.includes('libavcodec') ||
        message.includes('libavformat') ||
        message.includes('libavdevice') ||
        message.includes('libavfilter') ||
        message.includes('libswscale') ||
        message.includes('libswresample') ||
        // Build/config info
        message.includes('configuration:') ||
        message.includes('built with') ||
        message.includes('ffmpeg version') ||
        // Input/Output info
        message.includes('Input #') ||
        message.includes('Output #') ||
        message.includes('Stream #') ||
        message.match(/Stream mapping:/i) ||
        // Metadata
        message.includes('Metadata:') ||
        message.includes('Duration:') ||
        message.includes('encoder') ||
        message.includes('major_brand') ||
        message.includes('compatible_brands') ||
        // Codec info
        message.includes('[libx264') ||
        message.includes('[aac') ||
        message.includes('using SAR') ||
        message.includes('using cpu capabilities') ||
        message.includes('profile ') ||
        // Other common ffmpeg messages
        message.includes('Press [q]') ||
        message.match(/^\s*$/);  // Empty lines

      // Only treat as error if it's NOT ffmpeg output
      if (!isFFmpegOutput) {
        console.error("Python error:", message);
        sendToRenderer({
          type: "error",
          message: message,
        });
        appState.logs.push({
          timestamp: new Date().toISOString(),
          message: message,
          type: "error",
        });
      }
    });

    // Handle Python process exit
    pythonProcess.on("close", (code) => {
      console.log(`Python process exited with code ${code}`);
      appState.isProcessing = false;
      appState.currentJob = null;

      if (code === 0) {
        sendToRenderer({
          type: "state",
          status: "completed",
          clips: appState.clips,
        });
      } else {
        sendToRenderer({
          type: "error",
          message: `Process exited with code ${code}`,
        });
      }
    });

    return { success: true };
  } catch (error) {
    console.error("Failed to start engine:", error);
    appState.isProcessing = false;
    appState.status = "error";
    sendToRenderer({
      type: "error",
      message: error.message,
    });
    return { success: false, error: error.message };
  }
});

// Stop Python Engine
ipcMain.handle("stop-engine", async () => {
  try {
    if (pythonProcess) {
      pythonProcess.kill("SIGTERM");
      pythonProcess = null;
    }
    appState.isProcessing = false;
    appState.currentJob = null;
    appState.status = "idle";
    return { success: true };
  } catch (error) {
    console.error("Failed to stop engine:", error);
    return { success: false, error: error.message };
  }
});

// File Selection
ipcMain.handle("select-file", async () => {
  const result = await dialog.showOpenDialog(mainWindow, {
    properties: ["openFile"],
    filters: [
      { name: "Videos", extensions: ["mp4", "avi", "mov", "mkv", "webm"] },
      { name: "All Files", extensions: ["*"] },
    ],
  });

  if (!result.canceled && result.filePaths.length > 0) {
    return { filePath: result.filePaths[0] };
  }
  return null;
});

// Folder Selection
ipcMain.handle("select-folder", async () => {
  const result = await dialog.showOpenDialog(mainWindow, {
    properties: ["openDirectory", "createDirectory"],
  });

  if (!result.canceled && result.filePaths.length > 0) {
    return { folderPath: result.filePaths[0] };
  }
  return null;
});

// Get App State
ipcMain.handle("get-app-state", async () => {
  return appState;
});

// Update App State
ipcMain.handle("update-app-state", async (event, state) => {
  appState = { ...appState, ...state };
  return appState;
});

// Helper Functions

function handlePythonEvent(event) {
  console.log("Python event:", event);

  switch (event.type) {
    case "progress":
      // Update progress from AutoClip engine
      appState.currentJob = {
        ...appState.currentJob,
        step: event.step || "processing",
        percent: event.percent || 0,
        elapsed: calculateElapsed(appState.startTime),
        remaining: estimateRemaining(event.percent),
      };
      break;

    case "clip":
      // Clip created event
      appState.clips.push({
        file: event.file,
        duration: event.duration,
        subtitled: false,
      });
      break;

    case "subtitle":
      // Subtitle added to clip
      if (event.clip && event.clip !== "global") {
        const clip = appState.clips.find((c) => c.file === event.clip);
        if (clip) {
          clip.subtitled = true;
        }
      }
      break;

    case "log":
      // Log message from engine
      const logLevel = event.level || "INFO";
      appState.logs.push({
        timestamp: new Date().toISOString(),
        message: event.message,
        type:
          logLevel === "ERROR"
            ? "error"
            : logLevel === "WARNING"
              ? "warning"
              : "log",
      });
      break;

    case "error":
      // Error from engine
      appState.logs.push({
        timestamp: new Date().toISOString(),
        message: event.message,
        type: "error",
      });
      appState.status = "error";
      break;

    case "state":
      // State change from engine
      if (event.status === "started") {
        appState.startTime = Date.now();
      } else if (event.status === "completed") {
        appState.isProcessing = false;
        appState.currentJob = null;
      }
      break;

    case "complete":
      // Processing complete
      appState.isProcessing = false;
      appState.currentJob = null;
      appState.status = "completed";

      if (event.result && event.result.clips) {
        // Update clips from final result
        appState.clips = event.result.clips.map((clipPath) => ({
          file: clipPath,
          duration: 0,
          subtitled: true,
        }));
      }
      break;
  }

  // Forward event to renderer
  sendToRenderer(event);
}

function calculateElapsed(startTime) {
  if (!startTime) return "0s";
  const elapsed = Math.floor((Date.now() - startTime) / 1000);
  const minutes = Math.floor(elapsed / 60);
  const seconds = elapsed % 60;
  return minutes > 0 ? `${minutes}m ${seconds}s` : `${seconds}s`;
}

function estimateRemaining(percent) {
  if (!percent || percent === 0) return "Calculating...";
  if (!appState.startTime) return "Calculating...";

  const elapsed = (Date.now() - appState.startTime) / 1000;
  const totalEstimate = (elapsed / percent) * 100;
  const remaining = Math.floor(totalEstimate - elapsed);

  if (remaining < 0) return "Almost done...";

  const minutes = Math.floor(remaining / 60);
  const seconds = remaining % 60;
  return minutes > 0 ? `~${minutes}m ${seconds}s` : `~${seconds}s`;
}

function sendToRenderer(data) {
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send("engine-event", data);
  }
}
