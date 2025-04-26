// SimuExo Agent Dashboard
// Main application script

// Socket.io connection
let socket;

// Current state
let currentAgents = {};
let selectedAgentId = null;
let simulationStatus = {
    running: false,
    started_at: null,
    agent_count: 0,
    last_update: null
};

// DOM Elements
const agentListEl = document.getElementById('agent-list');
const agentFilterEl = document.getElementById('agent-filter');
const clearFilterEl = document.getElementById('clear-filter');
const agentsGridEl = document.getElementById('agents-grid');
const overviewSectionEl = document.getElementById('overview-section');
const agentDetailSectionEl = document.getElementById('agent-detail-section');
const backToOverviewEl = document.getElementById('back-to-overview');
const agentDetailTitleEl = document.getElementById('agent-detail-title');
const agentDetailIdEl = document.getElementById('agent-detail-id');
const agentDetailStatusEl = document.getElementById('agent-detail-status');
const agentDetailLocationEl = document.getElementById('agent-detail-location');
const agentDetailActionEl = document.getElementById('agent-detail-action');
const agentDetailPositionEl = document.getElementById('agent-detail-position');
const agentDetailUpdateEl = document.getElementById('agent-detail-update');
const chatMessagesEl = document.getElementById('chat-messages');
const chatInputEl = document.getElementById('chat-input');
const sendMessageEl = document.getElementById('send-message');
const historyListEl = document.getElementById('history-list');
const rawStateContentEl = document.getElementById('raw-state-content');
const tabButtons = document.querySelectorAll('.tab-button');
const tabPanes = document.querySelectorAll('.tab-pane');
const statusIndicatorEl = document.getElementById('status-indicator');
const statusDotEl = document.querySelector('.status-dot');
const statusTextEl = document.querySelector('.status-text');
const agentCountEl = document.getElementById('agent-count');
const startedTimeEl = document.getElementById('started-time');
const lastUpdateEl = document.getElementById('last-update');

// Initialize the application
function init() {
    // Connect to Socket.io server
    connectSocket();
    
    // Set up event listeners
    setupEventListeners();
    
    // Fetch initial data
    fetchAgentsData();
    
    // Set up tab navigation
    setupTabs();
}

// Connect to Socket.io server
function connectSocket() {
    socket = io();
    
    // Connection events
    socket.on('connect', () => {
        console.log('Connected to server');
        updateConnectionStatus(true);
        showNotification('Connected to server', 'Connection established successfully', 'success');
    });
    
    socket.on('disconnect', () => {
        console.log('Disconnected from server');
        updateConnectionStatus(false);
        showNotification('Disconnected from server', 'Connection lost. Attempting to reconnect...', 'error');
    });
    
    socket.on('connect_error', (error) => {
        console.error('Connection error:', error);
        updateConnectionStatus(false);
    });
    
    // Data events
    socket.on('simulation_status', (status) => {
        console.log('Received simulation status:', status);
        updateSimulationStatus(status);
    });
    
    socket.on('agent_states', (agents) => {
        console.log('Received agent states:', agents);
        updateAgents(agents);
    });
    
    socket.on('agent_update', (agent) => {
        console.log('Received agent update:', agent);
        updateAgent(agent);
    });
    
    socket.on('agent_message', (message) => {
        console.log('Received agent message:', message);
        handleAgentMessage(message);
    });
    
    socket.on('agent_detail', (data) => {
        console.log('Received agent detail:', data);
        displayAgentDetail(data);
    });
}

// Set up event listeners for UI elements
function setupEventListeners() {
    // Filter agents
    agentFilterEl.addEventListener('input', filterAgents);
    clearFilterEl.addEventListener('click', clearFilter);
    
    // Back to overview
    backToOverviewEl.addEventListener('click', showOverview);
    
    // Send message
    chatInputEl.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            sendMessage();
        }
    });
    sendMessageEl.addEventListener('click', sendMessage);
}

// Fetch initial agents data
function fetchAgentsData() {
    fetch('/api/agents')
        .then(response => response.json())
        .then(data => {
            console.log('Fetched agent data:', data);
            if (data.simulation) {
                updateSimulationStatus(data.simulation);
            }
            if (data.agents) {
                updateAgents(data.agents);
            }
        })
        .catch(error => {
            console.error('Error fetching agents:', error);
            showNotification('Error', 'Failed to fetch agent data', 'error');
        });
}

// Set up tab navigation
function setupTabs() {
    tabButtons.forEach(button => {
        button.addEventListener('click', () => {
            const tabName = button.getAttribute('data-tab');
            
            // Update active tab button
            tabButtons.forEach(btn => btn.classList.remove('active'));
            button.classList.add('active');
            
            // Show corresponding tab content
            tabPanes.forEach(pane => pane.classList.remove('active'));
            document.getElementById(`${tabName}-tab`).classList.add('active');
            
            // If switching to chat tab, send a request for chat mode
            if (tabName === 'chat' && selectedAgentId) {
                console.log(`Activating chat mode for ${selectedAgentId}`);
                // Send special flag to indicate this is for the chat tab
                socket.emit('request_agent_detail', { 
                    agent_id: selectedAgentId,
                    is_chat_tab: true
                });
            }
        });
    });
}

// Update connection status in the UI
function updateConnectionStatus(connected) {
    if (connected) {
        statusDotEl.classList.add('active');
        statusTextEl.textContent = 'Online';
    } else {
        statusDotEl.classList.remove('active');
        statusTextEl.textContent = 'Offline';
    }
}

// Update simulation status
function updateSimulationStatus(status) {
    simulationStatus = status;
    
    // Update UI
    agentCountEl.textContent = status.agent_count || 0;
    
    if (status.started_at) {
        startedTimeEl.textContent = formatDateTime(new Date(status.started_at));
    } else {
        startedTimeEl.textContent = '-';
    }
    
    if (status.last_update) {
        lastUpdateEl.textContent = formatDateTime(new Date(status.last_update));
    } else {
        lastUpdateEl.textContent = '-';
    }
    
    updateConnectionStatus(status.running);
}

// Update agents list and grid
function updateAgents(agents) {
    // Update agents object
    agents.forEach(agent => {
        currentAgents[agent.id] = agent;
    });
    
    renderAgentList();
    renderAgentGrid();
}

// Update a single agent
function updateAgent(agent) {
    currentAgents[agent.id] = agent;
    
    // Update in list
    const listItem = document.getElementById(`agent-list-item-${agent.id}`);
    if (listItem) {
        updateAgentListItem(listItem, agent);
    } else {
        renderAgentList();
    }
    
    // Update in grid
    const cardItem = document.getElementById(`agent-card-${agent.id}`);
    if (cardItem) {
        updateAgentCard(cardItem, agent);
    } else {
        renderAgentGrid();
    }
    
    // Update detail view if this agent is currently selected
    if (selectedAgentId === agent.id) {
        updateAgentDetailView(agent);
    }
}

// Render the agent list in the sidebar
function renderAgentList() {
    // Clear current list
    agentListEl.innerHTML = '';
    
    // Get filtered agents
    const agents = Object.values(currentAgents);
    const filterText = agentFilterEl.value.toLowerCase();
    const filteredAgents = filterText ? 
        agents.filter(agent => agent.id.toLowerCase().includes(filterText)) : 
        agents;
    
    // Show empty state if no agents
    if (filteredAgents.length === 0) {
        agentListEl.innerHTML = '<li class="empty-list">No agents connected</li>';
        return;
    }
    
    // Sort agents by ID
    filteredAgents.sort((a, b) => a.id.localeCompare(b.id));
    
    // Create list items
    filteredAgents.forEach(agent => {
        const listItem = document.createElement('li');
        listItem.className = 'agent-list-item';
        listItem.id = `agent-list-item-${agent.id}`;
        if (selectedAgentId === agent.id) {
            listItem.classList.add('active');
        }
        
        updateAgentListItem(listItem, agent);
        
        // Add click event
        listItem.addEventListener('click', () => {
            selectAgent(agent.id);
        });
        
        agentListEl.appendChild(listItem);
    });
}

// Update an agent list item with latest data
function updateAgentListItem(listItem, agent) {
    // Get status and location with fallbacks
    const state = agent.state || {};
    let status = state.status || 'Unknown';
    let location = state.location || 'Unknown';
    
    // Use action information to improve display
    if (state.action_type === 'move' && state.action_param) {
        status = `Moving to ${state.action_param}`;
        // If we're moving, show both current and target locations
        if (location && location !== 'Unknown' && location !== state.action_param) {
            location = `${location} → ${state.action_param}`;
        } else {
            location = state.action_param;
        }
    }
    
    listItem.innerHTML = `
        <div class="agent-list-item-header">
            <div class="agent-id">${agent.id}</div>
            <div class="agent-status-indicator">
                <span class="status-dot active"></span>
                <span>${status}</span>
            </div>
        </div>
        <div class="agent-details">
            <div class="agent-location">
                <span class="material-icons">place</span>
                <span>${location}</span>
            </div>
        </div>
    `;
}

// Render the agent grid in the overview
function renderAgentGrid() {
    // Clear current grid
    agentsGridEl.innerHTML = '';
    
    // Get agents
    const agents = Object.values(currentAgents);
    
    // Show empty state if no agents
    if (agents.length === 0) {
        agentsGridEl.innerHTML = `
            <div class="empty-state">
                <div class="empty-icon">
                    <span class="material-icons">group_off</span>
                </div>
                <h3>No Agents Connected</h3>
                <p>Waiting for agents to connect to the simulation...</p>
            </div>
        `;
        return;
    }
    
    // Sort agents by ID
    agents.sort((a, b) => a.id.localeCompare(b.id));
    
    // Create cards
    agents.forEach(agent => {
        const card = document.createElement('div');
        card.className = 'agent-card';
        card.id = `agent-card-${agent.id}`;
        
        updateAgentCard(card, agent);
        
        // Add click event
        card.addEventListener('click', () => {
            selectAgent(agent.id);
        });
        
        agentsGridEl.appendChild(card);
    });
}

// Update an agent card with latest data
function updateAgentCard(card, agent) {
    const state = agent.state || {};
    let status = state.status || 'Unknown';
    let location = state.location || 'Unknown';
    const action = getAgentAction(state);
    const position = getPositionString(state);
    const lastUpdate = agent.last_update ? formatTime(new Date(agent.last_update)) : 'Unknown';
    
    // Use action information to improve display
    if (state.action_type === 'move' && state.action_param) {
        status = `Moving to ${state.action_param}`;
        // If we're moving, show both current and target locations
        if (location && location !== 'Unknown' && location !== state.action_param) {
            location = `${location} → ${state.action_param}`;
        } else {
            location = state.action_param;
        }
    }
    
    card.innerHTML = `
        <div class="agent-card-header">
            <h3>${agent.id}</h3>
            <span class="material-icons">android</span>
        </div>
        <div class="agent-card-content">
            <div class="agent-card-status">
                <span class="status-dot active"></span>
                <span>${status}</span>
            </div>
            <div class="agent-card-info">
                <div class="info-item">
                    <div class="info-label">Location</div>
                    <div class="info-value">${location}</div>
                </div>
                <div class="info-item">
                    <div class="info-label">Action</div>
                    <div class="info-value">${action}</div>
                </div>
                <div class="info-item">
                    <div class="info-label">Position</div>
                    <div class="info-value">${position}</div>
                </div>
                <div class="info-item">
                    <div class="info-label">Last Update</div>
                    <div class="info-value">${lastUpdate}</div>
                </div>
            </div>
        </div>
    `;
}

// Select an agent and show its details
function selectAgent(agentId) {
    selectedAgentId = agentId;
    
    // Update active state in list
    document.querySelectorAll('.agent-list-item').forEach(item => {
        item.classList.remove('active');
    });
    const listItem = document.getElementById(`agent-list-item-${agentId}`);
    if (listItem) {
        listItem.classList.add('active');
    }
    
    // Request agent details from server
    socket.emit('request_agent_detail', { 
        agent_id: agentId,
        is_chat_tab: false  // Default to false when initially selecting
    });
    
    // Show loading state
    agentDetailTitleEl.textContent = `Agent: ${agentId}`;
    agentDetailIdEl.textContent = agentId;
    agentDetailStatusEl.textContent = 'Loading...';
    agentDetailLocationEl.textContent = 'Loading...';
    agentDetailActionEl.textContent = 'Loading...';
    agentDetailPositionEl.textContent = 'Loading...';
    agentDetailUpdateEl.textContent = 'Loading...';
    chatMessagesEl.innerHTML = '<div class="chat-empty-state"><p>Loading messages...</p></div>';
    historyListEl.innerHTML = '<div class="history-empty-state"><p>Loading history...</p></div>';
    rawStateContentEl.textContent = 'Loading...';
    
    // Show detail view
    showAgentDetail();
}

// Display agent detail data
function displayAgentDetail(data) {
    const agent = data.agent;
    const messages = data.messages || [];
    const history = data.history || [];
    
    // Update detail view with agent data
    if (agent) {
        updateAgentDetailView(agent);
    }
    
    // Update chat messages
    renderChatMessages(messages);
    
    // Update history
    renderAgentHistory(history);
    
    // Update raw state
    if (agent && agent.state) {
        rawStateContentEl.textContent = JSON.stringify(agent.state, null, 2);
    } else {
        rawStateContentEl.textContent = 'No state data available.';
    }
}

// Update the agent detail view
function updateAgentDetailView(agent) {
    const state = agent.state || {};
    let status = state.status || 'Unknown';
    let location = state.location || 'Unknown';
    
    // Use action information to improve display
    if (state.action_type === 'move' && state.action_param) {
        status = `Moving to ${state.action_param}`;
        // If we're moving, show both current and target locations
        if (location && location !== 'Unknown' && location !== state.action_param) {
            location = `${location} → ${state.action_param}`;
        } else {
            location = state.action_param;
        }
    }
    
    agentDetailTitleEl.textContent = `Agent: ${agent.id}`;
    agentDetailIdEl.textContent = agent.id;
    agentDetailStatusEl.textContent = status;
    agentDetailLocationEl.textContent = location;
    agentDetailActionEl.textContent = getAgentAction(state);
    agentDetailPositionEl.textContent = getPositionString(state);
    agentDetailUpdateEl.textContent = agent.last_update ? 
        formatDateTime(new Date(agent.last_update)) : 'Unknown';
    
    // Update raw state
    rawStateContentEl.textContent = JSON.stringify(state, null, 2);
}

// Render chat messages
function renderChatMessages(messages) {
    if (!messages || messages.length === 0) {
        chatMessagesEl.innerHTML = `
            <div class="chat-empty-state">
                <p>No messages yet. Send a message to start chatting with this agent.</p>
            </div>
        `;
        return;
    }
    
    chatMessagesEl.innerHTML = '';
    
    messages.forEach(message => {
        const messageEl = document.createElement('div');
        messageEl.className = `chat-message from-${message.from}`;
        
        const time = message.timestamp ? formatTime(new Date(message.timestamp)) : '';
        
        messageEl.innerHTML = `
            <div class="message-bubble">${message.content}</div>
            <div class="message-meta">${time}</div>
        `;
        
        chatMessagesEl.appendChild(messageEl);
    });
    
    // Scroll to bottom
    chatMessagesEl.scrollTop = chatMessagesEl.scrollHeight;
}

// Render agent history
function renderAgentHistory(history) {
    if (!history || history.length === 0) {
        historyListEl.innerHTML = `
            <div class="history-empty-state">
                <p>No history available for this agent.</p>
            </div>
        `;
        return;
    }
    
    historyListEl.innerHTML = '';
    
    // Sort history by timestamp (most recent first)
    const sortedHistory = [...history].reverse();
    
    sortedHistory.forEach(item => {
        const historyEl = document.createElement('div');
        historyEl.className = 'history-item';
        
        const time = item.timestamp ? formatDateTime(new Date(item.timestamp)) : '';
        const actionType = item.action_type || 'unknown';
        const actionParam = item.action_param || '';
        
        historyEl.innerHTML = `
            <div class="history-item-header">
                <div class="history-type">${actionType}</div>
                <div class="history-timestamp">${time}</div>
            </div>
            <div class="history-content">${item.text || 'No content'}</div>
            ${actionParam ? `
                <div class="history-meta">
                    <div class="history-tag">${actionParam}</div>
                </div>
            ` : ''}
        `;
        
        historyListEl.appendChild(historyEl);
    });
    
    // Add a "back to top" button if there are many entries
    if (sortedHistory.length > 20) {
        const backToTopButton = document.createElement('button');
        backToTopButton.className = 'back-to-top';
        backToTopButton.innerHTML = '<span class="material-icons">arrow_upward</span> Back to Top';
        backToTopButton.addEventListener('click', () => {
            historyListEl.scrollTop = 0;
        });
        historyListEl.appendChild(backToTopButton);
    }
}

// Handle a new agent message
function handleAgentMessage(message) {
    const { agent_id, message: content, from, timestamp } = message;
    
    // Add to chat if this agent is currently selected
    if (selectedAgentId === agent_id) {
        const messageEl = document.createElement('div');
        messageEl.className = `chat-message from-${from}`;
        
        const time = timestamp ? formatTime(new Date(timestamp)) : '';
        
        messageEl.innerHTML = `
            <div class="message-bubble">${content}</div>
            <div class="message-meta">${time}</div>
        `;
        
        // Remove empty state if it exists
        const emptyState = chatMessagesEl.querySelector('.chat-empty-state');
        if (emptyState) {
            chatMessagesEl.innerHTML = '';
        }
        
        chatMessagesEl.appendChild(messageEl);
        
        // Scroll to bottom
        chatMessagesEl.scrollTop = chatMessagesEl.scrollHeight;
    }
    
    // Show notification for new messages from agents
    if (from === 'agent' && selectedAgentId !== agent_id) {
        showNotification(
            `New message from ${agent_id}`,
            content.length > 50 ? content.substring(0, 50) + '...' : content,
            'info'
        );
    }
}

// Send a message to the selected agent
function sendMessage() {
    const message = chatInputEl.value.trim();
    
    if (!message || !selectedAgentId) return;
    
    // Clear input
    chatInputEl.value = '';
    
    // Create a unique message ID to avoid duplicates
    const messageId = `msg_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    
    // Send message to server
    fetch(`/api/agent/${selectedAgentId}/message`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ message, messageId })
    })
    .then(response => response.json())
    .then(data => {
        if (data.error) {
            console.error('Error sending message:', data.error);
            showNotification('Error', 'Failed to send message', 'error');
        }
    })
    .catch(error => {
        console.error('Error sending message:', error);
        showNotification('Error', 'Failed to send message', 'error');
    });
    
    // The server will emit the message via socket.io, so we don't need to add it to the UI here
    // The handleAgentMessage function will take care of adding it to the chat when it comes back
    // This prevents duplicate messages
}

// Filter agents in the sidebar
function filterAgents() {
    renderAgentList();
}

// Clear the agent filter
function clearFilter() {
    agentFilterEl.value = '';
    renderAgentList();
}

// Show the overview section
function showOverview() {
    overviewSectionEl.classList.remove('hidden');
    agentDetailSectionEl.classList.add('hidden');
    selectedAgentId = null;
    
    // Update active state in list
    document.querySelectorAll('.agent-list-item').forEach(item => {
        item.classList.remove('active');
    });
}

// Show the agent detail section
function showAgentDetail() {
    overviewSectionEl.classList.add('hidden');
    agentDetailSectionEl.classList.remove('hidden');
}

// Show a notification
function showNotification(title, message, type = 'info') {
    const notificationContainer = document.getElementById('notification-container');
    const notification = document.createElement('div');
    notification.className = `notification ${type}`;
    
    let iconClass = 'notification-info';
    let iconName = 'info';
    
    if (type === 'success') {
        iconClass = 'notification-success';
        iconName = 'check_circle';
    } else if (type === 'error') {
        iconClass = 'notification-error';
        iconName = 'error';
    }
    
    notification.innerHTML = `
        <div class="notification-icon ${iconClass}">
            <span class="material-icons">${iconName}</span>
        </div>
        <div class="notification-content">
            <div class="notification-title">${title}</div>
            <div class="notification-message">${message}</div>
        </div>
        <button class="notification-close">
            <span class="material-icons">close</span>
        </button>
    `;
    
    // Add close button event
    notification.querySelector('.notification-close').addEventListener('click', () => {
        notification.remove();
    });
    
    // Auto remove after 5 seconds
    setTimeout(() => {
        notification.style.opacity = '0';
        setTimeout(() => {
            notification.remove();
        }, 300);
    }, 5000);
    
    notificationContainer.appendChild(notification);
}

// Utility function to format date and time
function formatDateTime(date) {
    return date.toLocaleString();
}

// Utility function to format time only
function formatTime(date) {
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

// Utility function to get agent action from state
function getAgentAction(state) {
    if (!state) return 'Unknown';
    
    // If we have an explicit action_type and action_param, use those first
    if (state.action_type && state.action_param) {
        if (state.action_type === 'move') {
            return `Moving to ${state.action_param}`;
        } else if (state.action_type === 'speak') {
            return `Speaking: ${state.action_param.substring(0, 20)}${state.action_param.length > 20 ? '...' : ''}`;
        } else if (state.action_type === 'converse') {
            return `Talking to ${state.action_param}`;
        } else if (state.action_type === 'nothing') {
            return 'Waiting';
        }
    }
    
    // Fall back to standard behavior
    if (state.is_moving) {
        return `Moving to ${state.desired_location || 'destination'}`;
    }
    
    if (state.is_in_conversation) {
        return `Talking to ${state.conversation_partner || 'someone'}`;
    }
    
    if (state.status) {
        return state.status;
    }
    
    return 'Idle';
}

// Utility function to get formatted position string
function getPositionString(state) {
    if (!state || !state.position) return 'Unknown';
    
    const pos = state.position;
    
    if (typeof pos.x === 'number' && typeof pos.y === 'number' && typeof pos.z === 'number') {
        return `(${pos.x.toFixed(1)}, ${pos.y.toFixed(1)}, ${pos.z.toFixed(1)})`;
    }
    
    return 'Unknown';
}

// Initialize the application when DOM is loaded
document.addEventListener('DOMContentLoaded', init);