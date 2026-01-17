// UI Controller for Electron Renderer
// Handles IPC events from AutoClip Python Engine and Updates UI

// Global App State - Single Source of Truth
window.appState = window.appState || {
  hasRunOnce: false,
  isProcessing: false,
  currentJob: null, // { input, step, percent, elapsed, remaining }
  clips: [],
  logs: []
};

class UIController {
  constructor() {
    this.listenersAttached = false;
    this.updateInterval = null;
    this.init();
  }

  init() {
    console.log("[UI] ===== Initializing UIController =====");

    // Load Projects from Storage
    this.jobs = this.loadProjects();

    // Bind events from Python engine (IPC)
    if (!this.listenersAttached) {
      window.electronAPI.onEvent((event, data) => {
        console.log("[UI] IPC Event received:", data.type, data);

        switch (data.type) {
          case "state":
            if (data.status === 'started') this.handleEngineStarted(data);
            if (data.status === 'completed') this.handleEngineComplete(data);
            break;
          case "progress":
            this.handleEngineProgress(data);
            break;
          case "log":
            this.handleEngineLog(data);
            break;
          case "error":
            this.handleEngineError(data);
            break;
          case "clip":
            this.handleEngineClip(data);
            break;
          case "subtitle":
            this.handleEngineSubtitle(data);
            break;
          case "complete":
            this.handleEngineComplete(data);
            break;
        }
      });
      this.listenersAttached = true;
    }

    // Start polling backup
    this.startPolling();

    // Initial UI Update
    this.updateUI();
  }

  startPolling() {
    if (this.updateInterval) return;

    this.updateInterval = setInterval(() => {
      if (window.appState.isProcessing) {
        console.log("[UI] Polling - isProcessing:", true, "currentPage:", window.router?.currentPage);

        // Update queue if on queue page
        if (window.router?.currentPage === 'queue') {
          this.updateQueue();
        }
      }
    }, 500);

    console.log("[UI] Polling started");
  }

  stopPolling() {
    if (this.updateInterval) {
      clearInterval(this.updateInterval);
      this.updateInterval = null;
      console.log("[UI] Polling stopped");
    }
  }

  // --- STORAGE HELPERS ---
  loadProjects() {
    try {
      const stored = localStorage.getItem('autoclip_projects');
      return stored ? JSON.parse(stored) : [];
    } catch (e) {
      console.error("Failed to load projects", e);
      return [];
    }
  }

  saveProjects() {
    localStorage.setItem('autoclip_projects', JSON.stringify(this.jobs));
    this.updateRecentProjectsList(); // Refresh UI whenever saved
  }

  createProject(data) {
    const newProject = {
      id: Date.now().toString(),
      name: data.name || "Untitled Project",
      type: data.type || "Video Processing",
      totalClips: data.totalClips || 0,
      completedClips: 0,
      status: 'processing',
      createdAt: Date.now(),
      updatedAt: Date.now()
    };
    this.jobs.unshift(newProject); // Add to top
    this.saveProjects();
    this.activeProjectId = newProject.id;
    return newProject;
  }

  updateProjectStatus(id, status, updates = {}) {
    const project = this.jobs.find(j => j.id === id);
    if (project) {
      project.status = status;
      project.updatedAt = Date.now();
      Object.assign(project, updates);
      this.saveProjects();
    }
  }

  // --- IPC HANDLERS ---

  handleEngineStarted(data) {
    console.log("[UI] ===== ENGINE STARTED =====");
    console.log("[UI] Data:", data);
    console.log("[UI] Active Project ID:", this.activeProjectId);

    const activeProject = this.activeProjectId
      ? this.jobs.find(j => j.id === this.activeProjectId)
      : null;

    console.log("[UI] Active Project:", activeProject);

    // Update State - ALWAYS initialize currentJob
    window.appState.isProcessing = true;
    window.appState.hasRunOnce = true;
    window.appState.currentJob = {
      input: activeProject?.name || data.input || 'Processing Video...',
      step: 'Starting...',
      percent: 0,
      elapsed: '0s',
      remaining: 'Calculating...'
    };

    console.log("[UI] State updated:", window.appState);
    console.log("[UI] Navigating to queue...");

    // Create Persistent Project Record if missing
    if (!this.activeProjectId) {
      this.createProject({
        name: "Auto-Started Job",
        type: "Unknown Source",
        totalClips: 5
      });
    }

    // UI Action: navigate -> queue
    if (window.router) window.router.navigate('queue');
    this.updateUI();
  }

  handleEngineProgress(data) {
    console.log("[UI] ===== PROGRESS UPDATE =====");
    console.log("[UI] Progress data:", data);
    console.log("[UI] Current job before:", window.appState.currentJob);
    console.log("[UI] isProcessing:", window.appState.isProcessing);

    // Defensive: Initialize if missing
    if (!window.appState.currentJob) {
      console.warn("[UI] WARNING: currentJob was null! Reinitializing...");
      window.appState.currentJob = {
        input: 'Processing...',
        step: 'Unknown',
        percent: 0,
        elapsed: '0s',
        remaining: 'Calculating...'
      };
    }

    // Update State
    window.appState.currentJob.step = this.getStepDisplayName(data.step);
    window.appState.currentJob.percent = Math.min(100, Math.max(0, data.percent || 0));
    if (data.elapsed) window.appState.currentJob.elapsed = data.elapsed;
    if (data.remaining) window.appState.currentJob.remaining = data.remaining;

    console.log("[UI] Current job after:", window.appState.currentJob);
    console.log("[UI] Current page:", window.router?.currentPage);
    console.log("[UI] Calling updateQueue()...");

    // Update UI - Force update
    this.updateQueue();
  }

  handleEngineLog(data) {
    // Append Log
    window.appState.logs.push({
      timestamp: new Date().toISOString(),
      message: data.message,
      type: data.level === 'WARNING' ? 'warning' : 'info'
    });
    this.updateLogs();
  }

  handleEngineError(data) {
    console.log("[UI] ===== ENGINE ERROR =====");
    console.log("[UI] Error:", data);

    // Update State
    window.appState.isProcessing = false;
    window.appState.logs.push({
      timestamp: new Date().toISOString(),
      message: data.message,
      type: 'error'
    });

    // Update Persistent Project Status
    if (this.activeProjectId) {
      this.updateProjectStatus(this.activeProjectId, 'error');
    }

    // REMOVED: Auto-navigate to logs - Let user decide
    // if (window.router) window.router.navigate('logs');

    // Update UI on current page
    this.updateUI();

    // Show error alert
    alert(`Error: ${data.message}\n\nCheck Logs page for details.`);
  }

  handleEngineClip(data) {
    // Add Clip to Runtime State
    window.appState.clips.push({
      file: data.file,
      duration: data.duration,
      subtitled: false
    });

    // Update Persistent Project Stats
    if (this.activeProjectId) {
      const project = this.jobs.find(j => j.id === this.activeProjectId);
      if (project) {
        this.updateProjectStatus(this.activeProjectId, 'processing', {
          completedClips: (project.completedClips || 0) + 1
        });
      }
    }

    // Also log it
    this.handleEngineLog({ message: `Clip created: ${data.file}`, level: 'INFO' });
  }

  handleEngineSubtitle(data) {
    // Update clip status or log global subtitle
    if (data.clip === 'global') {
      this.handleEngineLog({ message: `Subtitle generated: ${data.subtitle}`, level: 'INFO' });
    } else {
      const clip = window.appState.clips.find(c => c.file === data.clip);
      if (clip) clip.subtitled = true;
    }
  }

  handleEngineComplete(data) {
    // Update State
    window.appState.isProcessing = false;
    window.appState.currentJob = null;

    // Update Persistent Project Status
    if (this.activeProjectId) {
      this.updateProjectStatus(this.activeProjectId, 'completed');
      this.activeProjectId = null; // Clear active reference
    }

    if (data.result && data.result.clips) {
      // Refresh clips from final result if available
      // logic: map result clips to state
    }

    // UI Action: save clips -> navigate -> clips
    if (window.router) window.router.navigate('clips');
    this.updateUI();
  }


  // --- UI UPDATERS ---

  updateUI() {
    // Dispatch updates to different sections based on current page/presence
    this.updateDashboard();
    this.updateQueue();
    this.updateLogs();
    this.updateClips();
    this.updateStats(); // Global stats usually in sidebar or dashboard
  }

  updateDashboard() {
    this.updateRecentProjectsList(); // Render Dynamic List

    const dashboardContainer = document.querySelector('.dashboard-content');
    if (!dashboardContainer) return;

    const hasRunOnce = window.appState.hasRunOnce;

    // If we are on dashboard html
    if (!hasRunOnce) {
      // Show empty State
      const emptyState = document.getElementById('dashboard-empty');
      const statsState = document.getElementById('dashboard-stats');
      if (emptyState) emptyState.classList.remove('hidden');
      if (statsState) statsState.classList.add('hidden');
    } else {
      // Show Stats
      const emptyState = document.getElementById('dashboard-empty');
      const statsState = document.getElementById('dashboard-stats');
      if (emptyState) emptyState.classList.add('hidden');
      if (statsState) statsState.classList.remove('hidden');

      // Render Stats
      this.setText('#stat-active-jobs', window.appState.isProcessing ? '1' : '0');
      this.setText('#stat-total-clips', window.appState.clips.length);
      this.setText('#stat-errors', window.appState.logs.filter(l => l.type === 'error').length);
    }
  }

  updateRecentProjectsList() {
    const listContainer = document.getElementById('recent-projects-list');
    if (!listContainer) return;

    const recentJobs = this.jobs.slice(0, 5); // Get top 5

    if (recentJobs.length === 0) {
      listContainer.innerHTML = `
            <div class="flex flex-col items-center justify-center h-full text-gray-500 py-8">
                <p>No recent projects</p>
            </div>
        `;
      return;
    }

    listContainer.innerHTML = recentJobs.map(job => {
      // Determine badge color
      let statusColor = 'text-gray-400 bg-gray-500/10 border-gray-500/20';
      if (job.status === 'processing') statusColor = 'text-blue-400 bg-blue-500/10 border-blue-500/20';
      if (job.status === 'completed') statusColor = 'text-green-400 bg-green-500/10 border-green-500/20';
      if (job.status === 'error') statusColor = 'text-red-400 bg-red-500/10 border-red-500/20';

      const progress = job.totalClips > 0 ? Math.round((job.completedClips / job.totalClips) * 100) : 0;

      return `
        <div class="border-t border-gray-800 pt-3 pb-1 first:border-0 first:pt-0">
            <div class="flex justify-between items-start mb-1">
                <div>
                    <div class="text-white font-medium text-sm truncate max-w-[150px]" title="${job.name}">${job.name}</div>
                    <div class="text-[10px] text-gray-400">${job.type}</div>
                </div>
                <div class="text-right">
                     <span class="inline-block px-1.5 py-0.5 rounded text-[9px] border ${statusColor} uppercase font-bold tracking-wider mb-1">
                        ${job.status}
                    </span>
                     <div class="text-[10px] text-gray-500">${new Date(job.updatedAt).toLocaleDateString()}</div>
                </div>
            </div>
            
            <div class="flex items-center gap-2 mt-1">
                <div class="flex-1 h-1.5 bg-gray-800 rounded-full overflow-hidden">
                    <div class="h-full bg-blue-500 rounded-full transition-all duration-500" style="width: ${progress}%"></div>
                </div>
                <div class="text-[10px] text-gray-400 whitespace-nowrap">${job.completedClips}/${job.totalClips} Clips</div>
            </div>
        </div>
        `;
    }).join('');
  }

  // ... (rest of simple updaters) ...


  updateQueue() {
    console.log("[UI] ===== UPDATE QUEUE =====");
    console.log("[UI] isProcessing:", window.appState.isProcessing);
    console.log("[UI] currentJob:", window.appState.currentJob);

    const queueContainer = document.getElementById('queue-container');

    if (!queueContainer) {
      console.error("[UI] ERROR: queue-container element NOT FOUND!");
      console.log("[UI] Current page:", window.router?.currentPage);
      console.log("[UI] Body preview:", document.body.innerHTML.substring(0, 200));
      return;
    }

    console.log("[UI] queue-container found:", queueContainer);

    // Prevent event bubbling to nav-item or global listeners
    queueContainer.onclick = (e) => {
      e.stopPropagation();
    };

    if (!window.appState.isProcessing || !window.appState.currentJob) {
      console.log("[UI] Rendering EMPTY state");
      queueContainer.innerHTML = `
            <div class="text-center text-gray-500 py-4 flex flex-col items-center justify-center">
                <div class="text-sm italic">No active jobs running</div>
            </div>
          `;
      return;
    }

    console.log("[UI] Rendering ACTIVE job state");

    // Active Job State
    const job = window.appState.currentJob;
    const progressPercent = Math.min(100, Math.max(0, job.percent || 0));

    queueContainer.innerHTML = `
          <div class="glass-card p-4 border border-blue-500/30 bg-blue-500/5">
              <div class="flex justify-between items-center mb-3">
                  <div class="flex items-center gap-3">
                      <div class="w-8 h-8 rounded bg-blue-500/20 flex items-center justify-center">
                          <svg class="w-4 h-4 text-blue-500 animate-spin" fill="none" viewBox="0 0 24 24">
                              <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                              <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                          </svg>
                      </div>
                      <div>
                          <div class="text-sm font-medium text-white truncate max-w-[300px]" title="${job.input}">
                              ${job.input}
                          </div>
                          <div class="text-xs text-gray-500">Processing...</div>
                      </div>
                  </div>
                   <div class="text-xs font-bold text-blue-400 bg-blue-500/10 px-2 py-1 rounded border border-blue-500/20">RUNNING</div>
              </div>
              
              <div class="flex justify-between text-xs text-gray-400 mb-1">
                  <span>${job.step}</span>
                  <span>${progressPercent.toFixed(0)}%</span>
              </div>

              <div class="progress-container mb-3">
                  <div class="gradient-progress" style="width: ${progressPercent}%; transition: width 0.3s ease;"></div>
              </div>
              
              <div class="flex justify-between items-center">
                   <div class="flex gap-4 text-xs text-gray-500 font-mono">
                      <span>Time Elapsed: ${job.elapsed}</span>
                      <span>Estimated: ${job.remaining}</span>
                  </div>
                  <div class="flex gap-2">
                      <button onclick="window.uiController.stopEngine()" class="p-1.5 rounded-full hover:bg-white/10 text-gray-400 transition-colors">
                          <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 9v6m4-6v6m7-3a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>
                      </button>
                  </div>
              </div>
          </div>
        `;

    console.log("[UI] Queue HTML rendered successfully");
  }

  updateLogs() {
    const logsContainer = document.getElementById('logs-container');
    if (!logsContainer) return;

    if (window.appState.logs.length === 0) {
      logsContainer.innerHTML = `<div class="text-gray-500 text-center italic mt-10">No logs available</div>`;
      return;
    }

    const logsHtml = window.appState.logs.map(log => {
      let colorClass = 'text-gray-300';
      let icon = '<svg class="w-3 h-3 text-blue-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>';

      if (log.type === 'warning') {
        colorClass = 'text-yellow-400';
        icon = '<svg class="w-3 h-3 text-yellow-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"></path></svg>';
      }
      if (log.type === 'error') {
        colorClass = 'text-red-400';
        icon = '<svg class="w-3 h-3 text-red-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>';
      }

      return `<div class="font-mono text-sm py-1 flex items-start gap-2 ${colorClass}">
            <span class="opacity-50 text-xs whitespace-nowrap pt-0.5">[${new Date(log.timestamp).toLocaleTimeString()}]</span>
            <span class="mt-0.5">${icon}</span>
            <span>${log.message}</span>
          </div>`;
    }).join('');

    logsContainer.innerHTML = logsHtml;
    logsContainer.scrollTop = logsContainer.scrollHeight;
  }

  updateClips() {
    const clipsContainer = document.getElementById('clips-container');
    if (!clipsContainer) return;

    if (window.appState.clips.length === 0) {
      clipsContainer.innerHTML = `
            <div class="col-span-full glass-card text-center text-gray-400 p-10 flex flex-col items-center justify-center">
                <svg class="w-16 h-16 mb-4 opacity-20" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 4v16M17 4v16M3 8h4m10 0h4M3 12h18M3 16h4m10 0h4M4 20h16a1 1 0 001-1V5a1 1 0 00-1-1H4a1 1 0 00-1 1v14a1 1 0 001 1z"></path></svg>
                <div class="text-lg">No Clips Generated Yet</div>
            </div>
          `;
    } else {
      // Render Grid
      clipsContainer.innerHTML = window.appState.clips.map(clip => `
            <div class="glass-card p-3 group hover:border-blue-500/30 transition-all duration-300">
                <div class="aspect-video bg-black rounded mb-3 overflow-hidden relative group/video">
                    <video src="file://${clip.file}" class="w-full h-full object-cover" controls preload="metadata"></video>
                    
                    <!-- Overlay SVG Play Icon (Optional, if video controls are hidden by default) -->
                    <!-- For standard HTML5 video with controls, specific overlay might block controls, but we can add badges -->
                </div>
                
                <div class="text-xs font-mono text-gray-400 truncate mb-2" title="${clip.file}">
                    ${clip.file.split(/[\\/]/).pop()}
                </div>
                
                <div class="flex justify-between items-center">
                    <div class="flex items-center gap-2">
                        <span class="flex items-center gap-1 text-xs bg-gray-800 px-2 py-1 rounded text-gray-300">
                            <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>
                            ${clip.duration}s
                        </span>
                        
                        ${clip.subtitled ? `
                        <span class="flex items-center gap-1 text-[10px] text-green-400 border border-green-500/20 px-1.5 py-0.5 rounded" title="Subtitled">
                            <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 8h10M7 12h4m1 8l-4-4H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-3l-4 4z"></path></svg>
                            CC
                        </span>` : ''}
                    </div>
                    
                    <button class="p-1.5 hover:bg-white/10 rounded-lg text-gray-400 hover:text-white transition-colors" title="Export/Download">
                        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"></path></svg>
                    </button>
                </div>
            </div>
          `).join('');
    }
  }

  updateStats() {
    // Update global badges or sidebar stats if they exist
    const statusBadge = document.querySelector('.status-badge');
    if (statusBadge) {
      if (window.appState.isProcessing) {
        statusBadge.textContent = "RUNNING";
        statusBadge.className = "status-badge status-running";
      } else {
        statusBadge.textContent = "IDLE";
        statusBadge.className = "status-badge status-idle";
      }
    }
  }


  // --- USER ACTIONS ---

  initNewProjectPage() {
    // Dynamic Input Toggle Logic
    const radioContainer = document.querySelector('.input-type-toggle'); // wrapper
    if (!radioContainer) return; // Might handle in html natively with onclicks, but let's see.

    // Using event delegation or direct bindings if elements exist
    const youtubeInputDiv = document.getElementById('input-youtube');
    const localInputDiv = document.getElementById('input-local');

    document.querySelectorAll('input[name="input-type"]').forEach(radio => {
      radio.onchange = (e) => {
        if (e.target.value === 'youtube') {
          if (youtubeInputDiv) youtubeInputDiv.classList.remove('hidden');
          if (localInputDiv) localInputDiv.classList.add('hidden');
        } else {
          if (youtubeInputDiv) youtubeInputDiv.classList.add('hidden');
          if (localInputDiv) localInputDiv.classList.remove('hidden');
        }
      };
    });

    // File Browse
    const browseFileBtn = document.getElementById('btn-browse-file');
    if (browseFileBtn) {
      browseFileBtn.onclick = async () => {
        const result = await window.electronAPI.selectFile();
        if (result && result.filePath) {
          document.getElementById('local-file-path').value = result.filePath;
        }
      };
    }

    const browseFolderBtn = document.getElementById('btn-browse-folder');
    if (browseFolderBtn) {
      browseFolderBtn.onclick = async () => {
        const result = await window.electronAPI.selectFolder();
        if (result && result.folderPath) {
          document.getElementById('output-folder-path').value = result.folderPath;
        }
      };
    }

    // Sliders
    this.bindSlider('max-clips', 'max-clips-val', '');
    // Discrete: 0=10s, 1=30s, 2=60s
    this.bindDiscreteSlider('clip-duration', 'clip-duration-val', [10, 30, 60], 's');

    // Start Button
    const startBtn = document.getElementById('startProcessingBtn');
    if (startBtn) {
      startBtn.onclick = () => this.startProcessing();
    }
  }

  bindSlider(inputId, valId, suffix) {
    const input = document.getElementById(inputId);
    const val = document.getElementById(valId);
    if (input && val) {
      input.oninput = (e) => val.textContent = e.target.value + suffix;
    }
  }

  bindDiscreteSlider(inputId, valId, values, suffix) {
    const input = document.getElementById(inputId);
    const val = document.getElementById(valId);
    if (input && val) {
      input.oninput = (e) => {
        val.textContent = values[e.target.value] + suffix;
      };
    }
  }

  async startProcessing() {
    // Validate
    const inputType = document.querySelector('input[name="input-type"]:checked').value;
    let input = "";

    if (inputType === 'youtube') {
      input = document.getElementById('youtube-url').value.trim();
      if (!input.startsWith('http')) return alert("Invalid YouTube URL");
    } else {
      input = document.getElementById('local-file-path').value.trim();
      if (!input) return alert("Select a video file");
    }

    const output = document.getElementById('output-folder-path').value.trim();
    if (!output) return alert("Select output folder");

    const maxClips = document.getElementById('max-clips').value;

    // Decode Duration
    const durationIndex = document.getElementById('clip-duration').value;
    const durationValues = [10, 30, 60];
    const duration = durationValues[durationIndex];

    // Project Name Handling
    const projectNameInput = document.getElementById('project-name');
    const projectName = projectNameInput ? projectNameInput.value.trim() : "Untitled Project";

    // Crop Toggle
    const enableCropCheckbox = document.getElementById('enable-crop');
    const enableCrop = enableCropCheckbox ? enableCropCheckbox.checked : true;
    console.log('[DEBUG] Enable Crop Checkbox:', enableCrop); // Debug

    // Quality Preset
    const qualitySelect = document.getElementById('quality-preset');
    const qualityPreset = qualitySelect ? qualitySelect.value : 'balanced';
    console.log('[DEBUG] Quality Preset:', qualityPreset); // Debug

    // 1. Create Project Record immediately
    const newProject = this.createProject({
      name: projectName || (inputType === 'local' ? input.split(/[\\\/]/).pop() : "YouTube Video"),
      type: inputType === 'local' ? "Local Video" : "YouTube",
      totalClips: parseInt(maxClips)
    });

    // Build logic payload
    const payload = {
      input,
      inputType,
      output,
      maxClips: parseInt(maxClips),
      clipDuration: parseInt(duration),
      projectName: projectName || "Untitled", // Send project name to engine
      enableCrop: enableCrop, // Send crop toggle to engine
      quality: qualityPreset, // Send quality preset to engine
      // Defaults for now
      aspect: "16:9",
      subtitle: "tiktok",
      projectId: newProject.id
    };

    console.log('[DEBUG] Payload to engine:', payload); // Debug

    // Call Engine
    await window.electronAPI.startEngine(payload);
    // State update happens via IPC event 'started' (engine-state), 
    // BUT for immediate UI feedback we can set it here too or wait for event.
    // Requirement says: "Update state: appState.hasRunOnce = true..."
    // Best to wait for IPC acknowledgement? 
    // User prompt: "Update state: ... Auto navigate -> queue.html"
    // I'll do it here to ensure snappiness.

    /* 
       NOTE: Real implementation usually waits for success return of startEngine 
       before navigating, OR waits for the 'started' event.
       I will rely on the 'started' IPC event handler implemented above to do the nav.
    */
  }

  async stopEngine() {
    await window.electronAPI.stopEngine();
    // State updates via IPC
  }


  // --- HELPERS ---
  setText(selector, text) {
    const el = document.querySelector(selector);
    if (el) el.textContent = text;
  }

  getStepDisplayName(step) {
    if (!step) return '';
    return step.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase());
  }

}

// Initialize
window.uiController = new UIController();
