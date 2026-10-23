package main

// python.go — finding a Python that can run train.py.
//
// The server is often started by a Windows scheduled task running as SYSTEM,
// whose PATH has none of the interpreters a person installed — which is how
// face scans failed with `exec: "python": executable file not found in %PATH%`.
// So rather than trusting PATH, look in the usual places and keep the first
// interpreter that can actually import face_recognition.

import (
	"context"
	"log"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"sort"
	"strings"
	"sync"
	"time"
)

type pythonCmd struct {
	exe  string
	args []string // e.g. ["-3"] for the Windows py launcher
}

func (p pythonCmd) command(ctx context.Context, script ...string) *exec.Cmd {
	return exec.CommandContext(ctx, p.exe, append(append([]string{}, p.args...), script...)...)
}

var (
	pythonMu      sync.Mutex
	pythonFound   *pythonCmd
	pythonChecked time.Time
)

func pythonCandidates() []pythonCmd {
	var out []pythonCmd
	add := func(exe string, args ...string) {
		if exe != "" {
			out = append(out, pythonCmd{exe: exe, args: args})
		}
	}
	if env := strings.TrimSpace(os.Getenv("PYTHON_CMD")); env != "" {
		add(env)
	}
	for _, venv := range []string{".venv", "venv"} {
		add(filepath.Join(venv, "Scripts", "python.exe"))
		add(filepath.Join(venv, "bin", "python"))
	}
	if runtime.GOOS == "windows" {
		if p, err := exec.LookPath("py"); err == nil {
			add(p, "-3")
		}
	}
	for _, name := range []string{"python3", "python"} {
		if p, err := exec.LookPath(name); err == nil {
			// The Microsoft Store alias in WindowsApps exists but is not Python.
			if !strings.Contains(strings.ToLower(p), `\windowsapps\`) {
				add(p)
			}
		}
	}
	if runtime.GOOS == "windows" {
		var globs []string
		for _, root := range []string{os.Getenv("ProgramFiles"), os.Getenv("LOCALAPPDATA")} {
			if root != "" {
				globs = append(globs, filepath.Join(root, "Python3*", "python.exe"),
					filepath.Join(root, "Programs", "Python", "Python3*", "python.exe"))
			}
		}
		// Interpreters installed for any user — visible to a task running as SYSTEM.
		globs = append(globs, `C:\Users\*\AppData\Local\Programs\Python\Python3*\python.exe`, `C:\Python3*\python.exe`)
		for _, g := range globs {
			matches, _ := filepath.Glob(g)
			sort.Sort(sort.Reverse(sort.StringSlice(matches))) // newest version first
			for _, m := range matches {
				add(m)
			}
		}
	}
	return out
}

// facePython returns an interpreter with face_recognition installed, or nil.
// A miss is re-checked at most once a minute, so installing Python fixes face
// scanning without restarting the server.
func facePython() *pythonCmd {
	pythonMu.Lock()
	defer pythonMu.Unlock()
	if pythonFound != nil {
		return pythonFound
	}
	if time.Since(pythonChecked) < time.Minute {
		return nil
	}
	pythonChecked = time.Now()
	seen := map[string]bool{}
	for _, cand := range pythonCandidates() {
		key := cand.exe + strings.Join(cand.args, " ")
		if seen[key] {
			continue
		}
		seen[key] = true
		ctx, cancel := context.WithTimeout(context.Background(), 60*time.Second)
		out, err := cand.command(ctx, "-c", "import face_recognition, numpy").CombinedOutput()
		cancel()
		if err != nil {
			log.Printf("[FACE] %s %s can't import face_recognition: %v %s", cand.exe, strings.Join(cand.args, " "),
				err, lastLine(string(out)))
		}
		if err == nil {
			found := cand
			pythonFound = &found
			log.Printf("[FACE] Using Python: %s %s", cand.exe, strings.Join(cand.args, " "))
			return pythonFound
		}
	}
	log.Println("[FACE] No Python with face_recognition found — face scans are unavailable. Run setup-face-python.ps1 (Windows) or install requirements.txt.")
	installFacePython()
	return nil
}

func lastLine(s string) string {
	lines := strings.Split(strings.TrimSpace(s), "\n")
	l := strings.TrimSpace(lines[len(lines)-1])
	if len(l) > 300 {
		l = l[:300]
	}
	return l
}

var (
	setupMu      sync.Mutex
	setupRunning bool
	setupLastRun time.Time
)

// installFacePython runs setup-face-python.ps1 in the background (Windows) when
// no usable Python was found, writing its output to this server's log (Admin
// > Logs > Server). The auto-updater runs the same script after each update;
// this covers a server where that didn't work, with no one at the machine.
// At most once every 30 minutes.
func installFacePython() {
	if runtime.GOOS != "windows" {
		return
	}
	if _, err := os.Stat("setup-face-python.ps1"); err != nil {
		return
	}
	setupMu.Lock()
	if setupRunning || time.Since(setupLastRun) < 30*time.Minute {
		setupMu.Unlock()
		return
	}
	setupRunning, setupLastRun = true, time.Now()
	setupMu.Unlock()

	go func() {
		defer func() {
			setupMu.Lock()
			setupRunning = false
			setupMu.Unlock()
		}()
		log.Println("[FACE] Setting up face-scanning Python (setup-face-python.ps1); this can take several minutes...")
		ctx, cancel := context.WithTimeout(context.Background(), 30*time.Minute)
		defer cancel()
		out, err := exec.CommandContext(ctx, "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
			"-File", "setup-face-python.ps1").CombinedOutput()
		for _, line := range strings.Split(strings.TrimSpace(string(out)), "\n") {
			if l := strings.TrimSpace(line); l != "" {
				log.Printf("[FACE] setup: %s", l)
			}
		}
		if err != nil {
			log.Printf("[FACE] Face-scanning Python setup failed: %v", err)
			return
		}
		pythonMu.Lock()
		pythonChecked = time.Time{} // look again straight away
		pythonMu.Unlock()
		facePython()
	}()
}
