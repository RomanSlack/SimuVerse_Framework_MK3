# SimuVerse Dashboard Troubleshooting Guide

If you're experiencing issues with the dashboard, here are some common problems and their solutions:

## Recent Fixes (2025-04-25)

We've fixed several dashboard issues:

1. **Location Information**: The dashboard now correctly shows agent locations instead of "Unknown"
2. **Chat Functionality**: Chat now properly connects to agent LLMs and avoids duplicate messages
3. **History Logs**: The dashboard shows all agent history entries, not just the most recent ones
4. **Unity Connection Issues**: Dashboard now shows agent actions and target locations even without Unity connection
5. **Status Display**: Agent status now shows action and destination more clearly, including transition states

These fixes are now part of the main codebase. If you're still experiencing issues, continue with the troubleshooting steps below.

## 1. EventletSocketIO and OpenAI Monkey Patching Issues

The error message about monkey patching and the PortAudio library is a common conflict between EventletSocketIO (used for WebSockets) and the OpenAI library.

### Solutions:

1. **Use the Fallback Dashboard:**
   ```bash
   # Start the fallback version (no WebSockets, but works reliably)
   ./run_dashboard.sh fallback
   ```

2. **Fix PortAudio Library:**
   ```bash
   # On Ubuntu/Debian:
   sudo apt-get install portaudio19-dev
   # On Red Hat/Fedora:
   sudo dnf install portaudio-devel
   # On macOS:
   brew install portaudio
   ```

3. **Set Environment Variable:**
   ```bash
   # Set this before running main.py
   export USE_FALLBACK_DASHBOARD=true
   python main.py
   ```

## 2. Separate Backend and Dashboard

If you want to run the backend and dashboard separately (recommended for development):

1. **Start Main Backend:**
   ```bash
   # Start without dashboard
   cd /home/roman-slack/SimuExoV1/SimuVerse_Backend
   python main.py
   ```

2. **Start Dashboard Separately:**
   ```bash
   # In another terminal
   cd /home/roman-slack/SimuExoV1/SimuVerse_Backend
   ./run_dashboard.sh
   ```

## 3. Installation Issues

If you're missing dependencies:

```bash
# Install the dependencies
./run_dashboard.sh install
```

Or manually:

```bash
pip install flask flask-socketio eventlet
```

## 4. Network Issues

If you can't access the dashboard from other devices:

1. **Check Firewall:**
   Make sure port 5001 is open on your machine.

2. **Use Correct IP:**
   Instead of 'localhost', use your machine's actual IP address.

3. **Verify Host Setting:**
   Make sure the dashboard is bound to '0.0.0.0' not '127.0.0.1'.

## 5. Data Not Updating

If you're not seeing real-time updates:

1. **Browser Console:**
   Check your browser's developer console for WebSocket errors.

2. **Agent Logs:**
   Verify that agent logs are being written correctly in the agent_logs directory.

3. **Restart Browser:**
   Sometimes the WebSocket connection gets stuck - refreshing should fix it.

## 6. Other Errors

For any other errors:

1. **Check Logs:**
   Look at Python console output for error messages.

2. **Restart Everything:**
   Sometimes a full restart of both the backend and the dashboard resolves issues.

3. **Try Fallback Mode:**
   The fallback dashboard should work in almost all environments.

## Need More Help?

If you continue to have issues, you can:

1. Start the dashboard in fallback mode
2. Make sure your agent logs are being correctly written to disk
3. Look for specific error messages in the terminal output